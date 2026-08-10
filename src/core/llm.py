"""
LLM Client for the Google Gemini API (OpenAI-compatible endpoint,
default model: gemini-3.6-flash).

Implements:
  - SSE streaming with live finish_reason capture
  - Truncation recovery (finish_reason == "length" or dropped stream)
  - Typed error classification (QuotaExhaustedError, LLMConfigError,
    TransientAPIError) so callers can react appropriately
  - Exponential backoff with Retry-After header support for transients
  - Auto-continuation of truncated responses so stages are never partial
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

from src.config.settings import APIConfig, _resolve_api_key


class QuotaExhaustedError(RuntimeError):
    """Daily / spend-based quota exhausted. Not recoverable within a session."""


class LLMConfigError(RuntimeError):
    """Bad request (400/403/404). Not retryable; check model name and key."""


class TransientAPIError(RuntimeError):
    """Transient API error (429 rate limit, 5xx). Retry with backoff."""

    def __init__(self, message: str, retry_after: Optional[float] = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class LLMResponse:
    """Structured response from the LLM API."""
    content: str
    tokens_used: int
    model: str
    finish_reason: str
    attempt_count: int


_QUOTA_MARKERS = (
    "you exceeded your current quota",
    "resource_exhausted",
    "quota exceeded",
    "billing details",
)


class LLMClient:
    """
    HTTP client for the Google Gemini OpenAI-compatible API using SSE streaming.

    Implements a five-tier resilience chain:
    1. Primary request with configurable timeout
    2. Live finish_reason detection (does not assume "stop")
    3. Auto-continuation of truncated responses so stages are never saved partial
    4. Exponential backoff with Retry-After honor for transient 429/5xx
    5. Fail-fast on quota exhaustion and configuration errors (no waste)
    """

    MAX_CONTINUATIONS = 4
    MAX_CONTINUATION_TOKENS = 28000
    MAX_BACKOFF_S = 60.0

    def __init__(self, config: Optional[APIConfig] = None) -> None:
        self.config = config or APIConfig()

        api_key = _resolve_api_key()
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY not found. Set via:\n"
                "  Colab Secrets | .env file | Environment variable"
            )

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _base_payload(self, max_new_tokens: int) -> dict:
        payload = {
            "model": self.config.model,
            "max_tokens": max_new_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "stream": True,
        }
        effort = self._reasoning_effort()
        if effort:
            payload["reasoning_effort"] = effort
        return payload

    def _reasoning_effort(self) -> Optional[str]:
        """Best-effort thinking reduction for Gemini 3.x reasoning models.

        Lowering reasoning effort frees output budget for actual content,
        which reduces how often truncation recovery is triggered. The
        ``reasoning_effort`` field is documented as supported on the
        Gemini OpenAI-compat endpoint; if the deployed model rejects it
        with HTTP 400, ``_post_stream`` retries the request without it.
        """
        if self.config.reasoning_effort is not None:
            return self.config.reasoning_effort or None
        if self.config.model.startswith("gemini-3"):
            return "low"
        return None

    def _post_stream(self, payload: dict):
        """POST + classify. Returns (content, finish_reason, saw_done, tokens)."""
        response = requests.post(
            self.config.base_url,
            headers=self.headers,
            json=payload,
            stream=True,
            timeout=(30, self.config.timeout_s),
        )

        if response.status_code == 200:
            return self._consume_stream(response)

        body = response.text[:300].replace("\n", " ")
        retry_after = self._parse_retry_after(response.headers.get("Retry-After"))

        if response.status_code == 400 and payload.get("reasoning_effort"):
            clean = {k: v for k, v in payload.items() if k != "reasoning_effort"}
            self._log_status(-1, "400 retrying without reasoning_effort")
            response = requests.post(
                self.config.base_url,
                headers=self.headers,
                json=clean,
                stream=True,
                timeout=(30, self.config.timeout_s),
            )
            if response.status_code == 200:
                return self._consume_stream(response)
            body = response.text[:300].replace("\n", " ")

        if response.status_code == 429:
            if any(marker in body.lower() for marker in _QUOTA_MARKERS):
                raise QuotaExhaustedError(
                    f"Daily / spend quota exhausted for {self.config.model}. "
                    f"The free-tier allowance is used up; wait for the daily "
                    f"quota to reset or upgrade the plan. Server said: {body}"
                )
            raise TransientAPIError(
                f"HTTP 429: {body}", retry_after=retry_after
            )

        if response.status_code in (400, 403, 404):
            raise LLMConfigError(
                f"HTTP {response.status_code}: {body}. Check GEMINI_MODEL "
                f"and API key permissions."
            )

        raise TransientAPIError(
            f"HTTP {response.status_code}: {body}", retry_after=retry_after
        )

    @staticmethod
    def _parse_retry_after(value: Optional[str]) -> Optional[float]:
        """Parse a Retry-After header (seconds or HTTP-date) to a float."""
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                target = parsedate_to_datetime(value)
                if target is None:
                    return None
                return max(0.0, target.timestamp() - time.time())
            except (TypeError, ValueError, OverflowError):
                return None

    @staticmethod
    def _consume_stream(
        response: requests.Response,
    ) -> tuple[str, Optional[str], bool, int]:
        """
        Drain an SSE stream, returning:
          (content, finish_reason, saw_done, tokens_received)

        ``saw_done`` is False when the connection ends before the ``[DONE]``
        marker, which is the signature of a silently dropped stream.
        """
        collected: list[str] = []
        finish_reason: Optional[str] = None
        saw_done = False
        tokens_received = 0

        for line in response.iter_lines():
            if not line:
                continue

            decoded = line.decode("utf-8", errors="replace")
            if not decoded.startswith("data: "):
                continue

            raw = decoded[6:]

            if raw.strip() == "[DONE]":
                saw_done = True
                break

            try:
                chunk = json.loads(raw)
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                delta = (choice.get("delta") or {}).get("content", "")
                if delta:
                    collected.append(delta)
                    tokens_received += 1
                fr = choice.get("finish_reason")
                if fr:
                    finish_reason = fr
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue

        return "".join(collected), finish_reason, saw_done, tokens_received

    def _is_truncated(self, finish_reason: Optional[str], saw_done: bool) -> bool:
        """True when the model hit its token cap or the stream was cut off."""
        if finish_reason == "length":
            return True
        if finish_reason is None and not saw_done:
            return True
        return False

    @staticmethod
    def _looks_incomplete(content: str) -> bool:
        """
        Conservative structural check for output that was cut off even though
        the stream reported ``stop`` (Gemini sometimes truncates mid-JSON or
        mid-code-fence while still ending the stream cleanly).
        """
        if not content:
            return False
        stripped = content.rstrip()
        if not stripped:
            return False

        # Unclosed triple-backtick code fence (e.g. remediation bash block).
        if stripped.count("```") % 2 != 0:
            return True
        # Unbalanced JSON-ish braces / brackets (Alert payload, RCA artifacts).
        if stripped.count("{") > stripped.count("}"):
            return True
        if stripped.count("[") > stripped.count("]"):
            return True
        # Unbalanced double quotes on the LAST line, JSON-style: a truncated value
        # like `"description": "HTTP 5xx error rate for payment-gateway-``.
        # Only applies when the line looks like JSON (has a `": ` key/value
        # separator), ignoring escaped quotes to avoid false positives.
        last_line = stripped.rsplit("\n", 1)[-1]
        unescaped = last_line.replace('\\"', "")
        if unescaped.count('"') % 2 != 0 and ('": "' in last_line or '": ' in last_line):
            return True
        # Response ends on a dangling continuation token.
        if stripped.endswith((",", ":", "-", "--", "\\", "|", "| ", ">")):
            return True
        return False

    @staticmethod
    def _strip_preamble(text: str) -> str:
        """
        Remove a leading planning-outline block that reasoning models
        occasionally emit as real content before the actual answer
        (e.g. ``), Stage 1 (Alert), ... 6. Refine Markdown Formatting: ...``
        followed by the first real ``#`` heading). Only triggers on
        outline-looking text so legitimate intros are never damaged.
        """
        if not text:
            return text
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.match(r"^#{1,6}\s", line):
                prefix = "\n".join(lines[:i]).strip()
                if not prefix or len(prefix) > 700:
                    return text
                outline = re.search(r"^\d+\.\s*\*\*", prefix, flags=re.M)
                stage_recap = ") Stage " in prefix
                if outline or stage_recap:
                    return "\n".join(lines[i:])
                return text
        return text

    def _backoff_delay(
        self, attempt: int, retry_after: Optional[float]
    ) -> float:
        """Compute the next retry delay (seconds), honoring Retry-After."""
        if retry_after is not None and retry_after > 0:
            return min(retry_after, self.MAX_BACKOFF_S)
        base = min(2 ** max(0, attempt - 1), self.MAX_BACKOFF_S)
        return base + random.uniform(0, 1)

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 3000,
        max_retries: Optional[int] = None,
    ) -> LLMResponse:
        """
        Generate a completion via the Google Gemini OpenAI-compatible API
        with SSE streaming.

        Collects incremental token deltas over Server-Sent Events,
        bypassing long-generation timeouts.

        If the stream reports truncation (``finish_reason == "length"`` or a
        dropped stream), issue continuation calls that resume exactly where
        the previous response stopped, up to ``MAX_CONTINUATIONS`` times,
        so the returned content is always a complete stage output.

        Quota-exhaustion and configuration errors are surfaced immediately
        without burning retries; transient 429/5xx responses use
        exponential backoff and honor ``Retry-After`` headers.

        Post-processes reasoning model leakage (<think>...</think> tags)
        via regex sanitization.
        """
        max_retries = max_retries or self.config.max_retries
        url = self.config.base_url
        failures: list[str] = []

        for attempt in range(1, max_retries + 1):
            try:
                payload = self._base_payload(max_new_tokens)
                payload["messages"] = [{"role": "user", "content": prompt}]

                content, finish_reason, saw_done, tokens_received = self._post_stream(payload)
                content = self._strip_reasoning(content).strip()

                # Continuation loop: recover from token-cap / dropped-stream
                # truncation until the response ends cleanly or we hit limits.
                continuations = 0
                while (
                    (self._is_truncated(finish_reason, saw_done)
                     or self._looks_incomplete(content))
                    and continuations < self.MAX_CONTINUATIONS
                    and content
                    and tokens_received < self.MAX_CONTINUATION_TOKENS
                ):
                    tail = content[-1500:]
                    messages = [
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": tail},
                        {
                            "role": "user",
                            "content": (
                                "The previous assistant message was cut off. "
                                "Continue writing exactly where it stopped. "
                                "Do not repeat text, do not summarize, do not "
                                "add a preamble. Continue the content directly."
                            ),
                        },
                    ]
                    cont_payload = self._base_payload(max_new_tokens)
                    cont_payload["messages"] = messages

                    cont_content, finish_reason, saw_done, cont_tokens = self._post_stream(cont_payload)
                    cont_content = self._strip_reasoning(cont_content).strip()
                    if not cont_content:
                        break

                    content = f"{content}\n{cont_content}".strip()
                    tokens_received += cont_tokens
                    continuations += 1

                # Guard against intentionally empty responses
                if not content and attempt < max_retries:
                    self._log_status(attempt, 0, empty=True)
                    failures.append("empty response")
                    time.sleep(self._backoff_delay(attempt, None))
                    continue

                return LLMResponse(
                    content=self._strip_preamble(content),
                    tokens_used=tokens_received,
                    model=self.config.model,
                    finish_reason=finish_reason or "stop",
                    attempt_count=attempt,
                )

            except (QuotaExhaustedError, LLMConfigError):
                raise
            except TransientAPIError as exc:
                delay = self._backoff_delay(attempt, exc.retry_after)
                self._log_status(attempt, f"transient ({exc}); waiting {delay:.1f}s")
                failures.append(str(exc))
                if attempt < max_retries:
                    time.sleep(delay)
            except requests.exceptions.Timeout:
                self._log_status(attempt, "timeout")
                failures.append("timeout")
                if attempt < max_retries:
                    time.sleep(self._backoff_delay(attempt, None))
            except Exception as exc:
                self._log_status(attempt, f"error:{exc!r}")
                failures.append(f"error:{exc!r}")
                if attempt < max_retries:
                    time.sleep(self._backoff_delay(attempt, None))

        raise RuntimeError(
            f"LLM call failed after {max_retries} attempts "
            f"(url={url}, model={self.config.model}, "
            f"key={'set' if _resolve_api_key() else 'MISSING'}): "
            f"{failures}"
        )

    @staticmethod
    def _strip_reasoning(text: str) -> str:
        """Remove internal monologue tags from reasoning model outputs."""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    def _log_status(self, attempt: int, status: str | int, empty: bool = False) -> None:
        suffix = " (empty response)" if empty else ""
        print(f"  [retry] Attempt {attempt}: API {status}{suffix} - retrying...")
