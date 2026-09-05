"""Behavioural tests for the LLM client using mocked HTTP responses.

These tests exercise the resilience logic (truncation recovery, error
classification, backoff) without hitting the real Gemini endpoint.
"""

import json
from unittest.mock import MagicMock, patch

import requests

from src.config.settings import APIConfig
from src.core.llm import (
    LLMClient,
    LLMConfigError,
    QuotaExhaustedError,
    TransientAPIError,
)


def _make_stream_resp(events):
    resp = MagicMock()
    resp.status_code = 200
    resp.iter_lines.return_value = [e.encode() for e in events]
    resp.headers = {}
    return resp


def _sse(pieces, finish=None, include_done=True, usage_tokens=None):
    lines = []
    for p in pieces:
        lines.append("data: " + json.dumps({"choices": [{"delta": {"content": p}}]}))
    if finish:
        lines.append("data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": finish}]}))
    if usage_tokens is not None:
        # Usage-only chunk (empty choices), OpenAI include_usage style.
        lines.append(
            "data: "
            + json.dumps({"choices": [], "usage": {"completion_tokens": usage_tokens}})
        )
    if include_done:
        lines.append("data: [DONE]")
    return lines


def _err_resp(status_code, body='{"error":{"message":"err"}}', headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = body
    resp.headers = headers or {}
    resp.iter_lines.return_value = []
    return resp


def _build_client(max_retries=2):
    cfg = APIConfig(
        base_url="http://x",
        model="gemini-3.7-flash",
        max_retries=max_retries,
        timeout_s=5,
        enable_fallback=False,
    )
    return LLMClient(cfg)


def _build_fallback_client(max_retries=2):
    """Client with the OrcaRouter fallback provider enabled."""
    cfg = APIConfig(
        base_url="http://primary",
        model="gemini-3.7-flash",
        fallback_base_url="http://fallback",
        fallback_model="deepseek/deepseek-v4-flash-free",
        enable_fallback=True,
        max_retries=max_retries,
        timeout_s=5,
    )
    with patch("src.core.llm._resolve_fallback_api_key", return_value="sk-orca-test"):
        return LLMClient(cfg)


# ---------------------------------------------------------------------------
# Test 1: complete response (single call, finish_reason=stop)
# ---------------------------------------------------------------------------
def test_complete_response():
    calls = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        calls.append(json)
        return _make_stream_resp(_sse(["Hello", " world"], finish="stop"))

    c = _build_client()
    with patch.object(requests, "post", side_effect=mock):
        r = c.generate("test", max_new_tokens=100)

    assert r.content == "Hello world", r.content
    assert r.finish_reason == "stop"
    assert len(calls) == 1, f"expected 1 call, got {len(calls)}"
    print("[OK] test_complete_response")


# ---------------------------------------------------------------------------
# Test 2: finish_reason=length triggers continuation
# ---------------------------------------------------------------------------
def test_truncation_continues():
    calls = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        calls.append(json)
        msgs = json["messages"]
        if len(msgs) == 1:
            return _make_stream_resp(_sse(["## Part one - ", "cut here"], finish="length"))
        return _make_stream_resp(_sse([" continued.", "\nEnd."], finish="stop"))

    c = _build_client()
    with patch.object(requests, "post", side_effect=mock):
        r = c.generate("test", max_new_tokens=100)

    assert "Part one" in r.content
    assert "continued" in r.content
    assert "End" in r.content
    assert len(calls) == 2
    print("[OK] test_truncation_continues")


# ---------------------------------------------------------------------------
# Test 3: quota-exhausted 429 fails fast (NO retries, NO continuation)
# ---------------------------------------------------------------------------
def test_quota_exhausted_fails_fast():
    calls = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        calls.append(json)
        return _err_resp(
            429,
            body='{"error":{"code":429,"message":"You exceeded your current quota, please check your plan and billing details"}}',
        )

    c = _build_client(max_retries=3)
    with patch.object(requests, "post", side_effect=mock):
        try:
            c.generate("test", max_new_tokens=100)
        except QuotaExhaustedError as e:
            assert len(calls) == 1, f"expected 1 call only, got {len(calls)}"
            assert "quota" in str(e).lower()
            print("[OK] test_quota_exhausted_fails_fast")
            return
    raise AssertionError("expected QuotaExhaustedError")


# ---------------------------------------------------------------------------
# Test 4: transient 429 honors Retry-After, then succeeds
# ---------------------------------------------------------------------------
def test_transient_429_with_retry_after():
    calls = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        calls.append(json)
        if len(calls) == 1:
            return _err_resp(
                429,
                body='{"error":{"code":429,"message":"rate exceeded"}}',
                headers={"Retry-After": "1"},
            )
        return _make_stream_resp(_sse(["OK"], finish="stop"))

    c = _build_client()
    with patch.object(requests, "post", side_effect=mock), \
         patch("src.core.llm.time.sleep") as sleep_mock:
        r = c.generate("test", max_new_tokens=100)

    assert r.content == "OK"
    assert len(calls) == 2
    # sleep should be called with a value >= Retry-After (1)
    sleeps = [c.args[0] for c in sleep_mock.call_args_list if c.args]
    assert any(s >= 1.0 for s in sleeps), f"expected sleep >= 1s, got {sleeps}"
    print("[OK] test_transient_429_with_retry_after")


# ---------------------------------------------------------------------------
# Test 5: 400 / 403 / 404 fail fast as LLMConfigError
# ---------------------------------------------------------------------------
def test_config_error_fails_fast():
    calls = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        calls.append(json)
        return _err_resp(404, body='{"error":{"code":404,"message":"model not found"}}')

    c = _build_client(max_retries=3)
    with patch.object(requests, "post", side_effect=mock):
        try:
            c.generate("test", max_new_tokens=100)
        except LLMConfigError as e:
            assert len(calls) == 1
            print("[OK] test_config_error_fails_fast")
            return
    raise AssertionError("expected LLMConfigError")


# ---------------------------------------------------------------------------
# Test 6: dropped stream (no [DONE]) triggers continuation
# ---------------------------------------------------------------------------
def test_dropped_stream_continues():
    calls = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        calls.append(json)
        msgs = json["messages"]
        if len(msgs) == 1:
            # stream ends without [DONE]
            return _make_stream_resp(_sse(["Some content"], finish=None, include_done=False))
        return _make_stream_resp(_sse([" more text"], finish="stop"))

    c = _build_client()
    with patch.object(requests, "post", side_effect=mock):
        r = c.generate("test", max_new_tokens=100)

    assert "Some content" in r.content
    assert "more text" in r.content
    assert len(calls) == 2
    print("[OK] test_dropped_stream_continues")


# ---------------------------------------------------------------------------
# Test 7: reasoning_effort 400 -> retry once without it
# ---------------------------------------------------------------------------
def test_reasoning_effort_400_fallback():
    calls = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        calls.append(json)
        if json.get("reasoning_effort"):
            return _err_resp(400, body='{"error":{"message":"unsupported field"}}')
        return _make_stream_resp(_sse(["Worked"], finish="stop"))

    c = _build_client()
    with patch.object(requests, "post", side_effect=mock):
        r = c.generate("test", max_new_tokens=100)

    assert r.content == "Worked"
    assert len(calls) == 2
    assert "reasoning_effort" in calls[0]
    assert "reasoning_effort" not in calls[1]
    print("[OK] test_reasoning_effort_400_fallback")


# ---------------------------------------------------------------------------
# Test 8: _strip_reasoning still strips reasoning tags
# ---------------------------------------------------------------------------
def test_strip_reasoning_tags():
    out = LLMClient._strip_reasoning("<think>secret</think>visible")
    assert "secret" not in out
    assert "visible" in out
    print("[OK] test_strip_reasoning_tags")


# ---------------------------------------------------------------------------
# Test 9: 5xx retries with exponential backoff
# ---------------------------------------------------------------------------
def test_5xx_retries_then_succeeds():
    calls = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        calls.append(json)
        if len(calls) < 2:
            return _err_resp(503, body='{"error":{"message":"unavailable"}}')
        return _make_stream_resp(_sse(["Recovered"], finish="stop"))

    c = _build_client(max_retries=3)
    with patch.object(requests, "post", side_effect=mock), \
         patch("src.core.llm.time.sleep"):
        r = c.generate("test", max_new_tokens=100)

    assert r.content == "Recovered"
    assert len(calls) == 2
    print("[OK] test_5xx_retries_then_succeeds")


# ---------------------------------------------------------------------------
# Test 10: continuation hits quota mid-stream -> QuotaExhaustedError propagates
# ---------------------------------------------------------------------------
def test_continuation_quota_propagates():
    calls = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        calls.append(json)
        msgs = json["messages"]
        if len(msgs) == 1:
            return _make_stream_resp(_sse(["Start "], finish="length"))
        # Continuation hits daily quota
        return _err_resp(
            429,
            body='{"error":{"code":429,"message":"You exceeded your current quota"}}',
        )

    c = _build_client()
    with patch.object(requests, "post", side_effect=mock):
        try:
            c.generate("test", max_new_tokens=100)
        except QuotaExhaustedError:
            assert len(calls) == 2, f"expected 2 calls, got {len(calls)}"
            print("[OK] test_continuation_quota_propagates")
            return
    raise AssertionError("expected QuotaExhaustedError")


# ---------------------------------------------------------------------------
# Test 11: _looks_incomplete catches mid-JSON truncation
# ---------------------------------------------------------------------------
def test_looks_incomplete_json():
    assert LLMClient._looks_incomplete('{"a": 1, "b": "')
    assert LLMClient._looks_incomplete('{"a": 1,')
    assert not LLMClient._looks_incomplete('{"a": 1}')
    print("[OK] test_looks_incomplete_json")


# ---------------------------------------------------------------------------
# Test 12: _looks_incomplete catches unclosed code fence
# ---------------------------------------------------------------------------
def test_looks_incomplete_code_fence():
    assert LLMClient._looks_incomplete("```bash\necho hi")
    assert not LLMClient._looks_incomplete("```bash\necho hi\n```")
    print("[OK] test_looks_incomplete_code_fence")


# ---------------------------------------------------------------------------
# Test 13: _strip_preamble removes leaked planning outline
# ---------------------------------------------------------------------------
def test_strip_preamble_outline():
    text = (
        "), Stage 1 (Alert), Stage 2 (Triage), Stage 3 (Root Cause), "
        "Stage 4 (Remediation), Stage 5 (Communication).\n\n"
        "6.  **Refine Markdown Formatting**: Clean headers.\n\n"
        "# Post-Mortem Report: payment-gateway-service\n\nBody"
    )
    out = LLMClient._strip_preamble(text)
    assert out.startswith("# Post-Mortem Report"), out
    assert "Body" in out
    print("[OK] test_strip_preamble_outline")


# ---------------------------------------------------------------------------
# Test 14: _strip_preamble leaves legitimate intros untouched
# ---------------------------------------------------------------------------
def test_strip_preamble_keeps_legit_intro():
    text = "Welcome to the incident response. Here is our analysis.\n\n## Findings\n\nBody"
    out = LLMClient._strip_preamble(text)
    assert out == text, out
    print("[OK] test_strip_preamble_keeps_legit_intro")


# ---------------------------------------------------------------------------
# Test 15: mid-JSON truncation with finish_reason=stop still continues
# ---------------------------------------------------------------------------
def test_incomplete_content_continues_even_on_stop():
    calls = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        calls.append(json)
        msgs = json["messages"]
        if len(msgs) == 1:
            # finish_reason="stop" but content is cut mid-JSON
            return _make_stream_resp(_sse(['{"alerts": [{"name": '], finish="stop"))
        return _make_stream_resp(_sse(['"completed"}],"status": "ok"}'], finish="stop"))

    c = _build_client()
    with patch.object(requests, "post", side_effect=mock):
        r = c.generate("test", max_new_tokens=100)

    assert "completed" in r.content
    assert r.content.strip().endswith("}")
    assert len(calls) == 2
    print("[OK] test_incomplete_content_continues_even_on_stop")


# ---------------------------------------------------------------------------
# Test 16: primary quota-exhausted -> OrcaRouter fallback serves the response
# ---------------------------------------------------------------------------
def test_fallback_on_primary_quota():
    urls = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        urls.append(url)
        if url == "http://primary":
            return _err_resp(
                429,
                body='{"error":{"code":429,"message":"You exceeded your current quota"}}',
            )
        return _make_stream_resp(_sse(["Fallback answer"], finish="stop"))

    c = _build_fallback_client()
    with patch.object(requests, "post", side_effect=mock):
        r = c.generate("test", max_new_tokens=100)

    assert r.content == "Fallback answer"
    assert r.model == "deepseek/deepseek-v4-flash-free"
    assert "http://primary" in urls
    assert "http://fallback" in urls
    print("[OK] test_fallback_on_primary_quota")


# ---------------------------------------------------------------------------
# Test 17: primary exhausts retries (5xx) -> fallback serves the response
# ---------------------------------------------------------------------------
def test_fallback_on_primary_persistent_5xx():
    def mock(url, headers=None, json=None, stream=None, timeout=None):
        if url == "http://primary":
            return _err_resp(503, body='{"error":{"message":"unavailable"}}')
        return _make_stream_resp(_sse(["Recovered via fallback"], finish="stop"))

    c = _build_fallback_client(max_retries=2)
    with patch.object(requests, "post", side_effect=mock), \
         patch("src.core.llm.time.sleep"):
        r = c.generate("test", max_new_tokens=100)

    assert r.content == "Recovered via fallback"
    assert r.model == "deepseek/deepseek-v4-flash-free"
    print("[OK] test_fallback_on_primary_persistent_5xx")


# ---------------------------------------------------------------------------
# Test 18: fallback provider never carries the Gemini reasoning_effort field
# ---------------------------------------------------------------------------
def test_fallback_payload_has_no_reasoning_effort():
    payloads = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        payloads.append((url, json))
        if url == "http://primary":
            return _err_resp(
                429,
                body='{"error":{"code":429,"message":"You exceeded your current quota"}}',
            )
        return _make_stream_resp(_sse(["ok"], finish="stop"))

    c = _build_fallback_client()
    with patch.object(requests, "post", side_effect=mock):
        c.generate("test", max_new_tokens=100)

    fallback_payloads = [p for (u, p) in payloads if u == "http://fallback"]
    assert fallback_payloads, "fallback was never called"
    assert all("reasoning_effort" not in p for p in fallback_payloads)
    print("[OK] test_fallback_payload_has_no_reasoning_effort")


# ---------------------------------------------------------------------------
# Test 19: fallback disabled (no key) -> quota error propagates, no 2nd provider
# ---------------------------------------------------------------------------
def test_no_fallback_when_disabled():
    urls = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        urls.append(url)
        return _err_resp(
            429,
            body='{"error":{"code":429,"message":"You exceeded your current quota"}}',
        )

    c = _build_client(max_retries=3)  # fallback disabled
    with patch.object(requests, "post", side_effect=mock):
        try:
            c.generate("test", max_new_tokens=100)
        except QuotaExhaustedError:
            assert all(u == "http://x" for u in urls)
            print("[OK] test_no_fallback_when_disabled")
            return
    raise AssertionError("expected QuotaExhaustedError")


# ---------------------------------------------------------------------------
# Test 20: primary succeeds -> fallback provider is never contacted
# ---------------------------------------------------------------------------
def test_primary_success_skips_fallback():
    urls = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        urls.append(url)
        return _make_stream_resp(_sse(["Primary answer"], finish="stop"))

    c = _build_fallback_client()
    with patch.object(requests, "post", side_effect=mock):
        r = c.generate("test", max_new_tokens=100)

    assert r.content == "Primary answer"
    assert r.model == "gemini-3.7-flash"
    assert "http://fallback" not in urls
    print("[OK] test_primary_success_skips_fallback")


# ---------------------------------------------------------------------------
# Test 21: provider usage.completion_tokens is used for the token count
# ---------------------------------------------------------------------------
def test_usage_tokens_reported():
    def mock(url, headers=None, json=None, stream=None, timeout=None):
        # single content chunk (chunk_count would be 1) but usage says 128
        return _make_stream_resp(
            _sse(["The full answer in one chunk"], finish="stop", usage_tokens=128)
        )

    c = _build_client()
    with patch.object(requests, "post", side_effect=mock):
        r = c.generate("test", max_new_tokens=100)

    assert r.content == "The full answer in one chunk"
    assert r.tokens_used == 128, r.tokens_used
    print("[OK] test_usage_tokens_reported")


# ---------------------------------------------------------------------------
# Test 22: single-chunk response without usage still reports > 0 tokens
# ---------------------------------------------------------------------------
def test_single_chunk_nonzero_tokens():
    def mock(url, headers=None, json=None, stream=None, timeout=None):
        # One content chunk, no usage summary -> must not report 0 tokens
        return _make_stream_resp(_sse(["hello there general kenobi"], finish="stop"))

    c = _build_client()
    with patch.object(requests, "post", side_effect=mock):
        r = c.generate("test", max_new_tokens=100)

    assert r.content == "hello there general kenobi"
    assert r.tokens_used > 0, r.tokens_used
    print("[OK] test_single_chunk_nonzero_tokens")


# ---------------------------------------------------------------------------
# Test 23: stream_options.include_usage is present in the request payload
# ---------------------------------------------------------------------------
def test_payload_requests_usage():
    payloads = []

    def mock(url, headers=None, json=None, stream=None, timeout=None):
        payloads.append(json)
        return _make_stream_resp(_sse(["ok"], finish="stop"))

    c = _build_client()
    with patch.object(requests, "post", side_effect=mock):
        c.generate("test", max_new_tokens=100)

    assert payloads[0].get("stream_options") == {"include_usage": True}
    print("[OK] test_payload_requests_usage")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_complete_response()
    test_truncation_continues()
    test_quota_exhausted_fails_fast()
    test_transient_429_with_retry_after()
    test_config_error_fails_fast()
    test_dropped_stream_continues()
    test_reasoning_effort_400_fallback()
    test_strip_reasoning_tags()
    test_5xx_retries_then_succeeds()
    test_continuation_quota_propagates()
    test_looks_incomplete_json()
    test_looks_incomplete_code_fence()
    test_strip_preamble_outline()
    test_strip_preamble_keeps_legit_intro()
    test_incomplete_content_continues_even_on_stop()
    test_fallback_on_primary_quota()
    test_fallback_on_primary_persistent_5xx()
    test_fallback_payload_has_no_reasoning_effort()
    test_no_fallback_when_disabled()
    test_primary_success_skips_fallback()
    test_usage_tokens_reported()
    test_single_chunk_nonzero_tokens()
    test_payload_requests_usage()
    print("\n=== ALL 23 TESTS PASSED ===")
