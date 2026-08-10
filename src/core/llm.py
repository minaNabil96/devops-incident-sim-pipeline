"""
LLM Client for the Google Gemini API (OpenAI-compatible endpoint,
default model: gemini-2.5-flash).

Handles SSE streaming, retry logic, and post-processing sanitization
(removal of <think> reasoning tags).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests

from src.config.settings import APIConfig, _resolve_api_key


@dataclass
class LLMResponse:
    """Structured response from the LLM API."""
    content: str
    tokens_used: int
    model: str
    finish_reason: str
    attempt_count: int


class LLMClient:
    """
    HTTP client for the NVIDIA build.nvidia.com API using SSE streaming.

    Implements a three-tier resilience chain:
    1. Primary request with configurable timeout
    2. Exponential backoff retry on transient failures
    3. Graceful DSL parsing on partial responses
    """

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

        Post-processes reasoning model leakage (<think>...</think> tags)
        via regex sanitization.
        """
        max_retries = max_retries or self.config.max_retries
        url = self.config.base_url

        payload = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_new_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "stream": True,
        }

        failures: list[str] = []
        for attempt in range(1, max_retries + 1):
            try:
                # Timeout as (connect, read) tuple: generous read timeout keeps
                # the connection alive across slow token streams / long
                # reasoning phases before the first SSE chunk arrives.
                response = requests.post(
                    url,
                    headers=self.headers,
                    json=payload,
                    stream=True,
                    timeout=(30, self.config.timeout_s),
                )

                if response.status_code != 200:
                    body = response.text[:160].replace("\n", " ")
                    failures.append(f"HTTP {response.status_code}: {body}")
                    self._log_status(attempt, f"{response.status_code} ({body})")
                    if attempt < max_retries:
                        time.sleep(5)
                    continue

                collected: list[str] = []
                last_chunk_at = time.time()
                tokens_received = 0

                for line in response.iter_lines():
                    if not line:
                        continue

                    decoded = line.decode("utf-8", errors="replace")
                    if not decoded.startswith("data: "):
                        continue

                    raw = decoded[6:]

                    if raw.strip() == "[DONE]":
                        break

                    try:
                        chunk = json.loads(raw)
                        delta = chunk["choices"][0].get("delta", {}).get("content", "")
                        if delta:
                            collected.append(delta)
                            tokens_received += 1
                            last_chunk_at = time.time()
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

                content = "".join(collected).strip()
                content = self._strip_reasoning(content)

                # Guard against intentionally empty responses
                if not content and attempt < max_retries:
                    self._log_status(attempt, 0, empty=True)
                    failures.append("empty response")
                    time.sleep(5)
                    continue

                return LLMResponse(
                    content=content,
                    tokens_used=tokens_received,
                    model=self.config.model,
                    finish_reason="stop",
                    attempt_count=attempt,
                )

            except requests.exceptions.Timeout:
                self._log_status(attempt, "timeout")
                failures.append("timeout")
            except Exception as exc:
                self._log_status(attempt, f"error:{exc!r}")
                failures.append(f"error:{exc!r}")

            if attempt < max_retries:
                time.sleep(5)

        raise RuntimeError(
            f"LLM call failed after {max_retries} attempts "
            f"(url={url}, model={self.config.model}, key={'set' if _resolve_api_key() else 'MISSING'}): "
            f"{failures}"
        )

    @staticmethod
    def _strip_reasoning(text: str) -> str:
        """Remove internal monologue tags from reasoning model outputs."""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    def _log_status(self, attempt: int, status: str | int, empty: bool = False) -> None:
        suffix = " (empty response)" if empty else ""
        print(f"  [retry] Attempt {attempt}: API {status}{suffix} - retrying...")
