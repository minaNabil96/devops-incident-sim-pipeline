"""
Configuration module for the DevOps Incident Simulation Pipeline.

Centralizes all runtime settings: API credentials, model parameters,
simulation defaults, and environment management.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel

# Resolve project root regardless of CWD
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _detect_environment() -> str:
    """Detect runtime environment: 'colab', 'streamlit', 'huggingface', or 'local'."""
    try:
        import google.colab  # noqa: F401
        return "colab"
    except ImportError:
        pass

    if os.environ.get("STREAMLIT_SERVER_PORT") or os.environ.get("STREAMLIT_SHARING_MODE"):
        return "streamlit"

    if os.environ.get("SPACE_ID"):  # Hugging Face Spaces
        return "huggingface"

    return "local"


def _resolve_env_key(name: str) -> str:
    """
    Resolve an API key through a four-tier fallback chain:
    1. Google Colab Secrets (if in Colab)
    2. Streamlit secrets (st.secrets) — covers Streamlit Cloud / HF Spaces
    3. .env file (loaded at import time)
    4. Environment variable
    """
    env = _detect_environment()

    # Tier 1: Colab Secrets
    if env == "colab":
        try:
            from google.colab import userdata
            key = userdata.get(name)
            if key:
                return key
        except Exception:
            pass

    # Tier 2: Streamlit secrets. On Streamlit Cloud, dashboard secrets are
    # exposed via st.secrets; env-var mirroring is not guaranteed, so read
    # st.secrets explicitly. Guarded so it never raises when Streamlit is
    # absent or no secrets file exists (bare CLI / pytest / Colab).
    try:
        import streamlit as st  # noqa: PLC0415

        if name in st.secrets:
            value = st.secrets[name]
            if value:
                # TOML lists (e.g. GEMINI_API_KEYS = ["a", "b"]) arrive as
                # list/tuple; join them so downstream comma-splitting works.
                if isinstance(value, (list, tuple)):
                    return ",".join(str(v) for v in value)
                return str(value)
    except Exception:
        pass

    # Tier 3: .env file (already loaded by load_dotenv) / Tier 4: env var
    return os.getenv(name) or ""


def _split_keys(raw: str) -> list[str]:
    """Split a comma/newline separated key list, preserving order."""
    return [k.strip() for k in str(raw).replace("\n", ",").split(",") if k.strip()]


def _resolve_api_keys() -> list[str]:
    """
    Resolve ALL Gemini API keys, de-duplicated and order-preserving.

    Sources: GEMINI_API_KEY (single) and GEMINI_API_KEYS (comma-separated or
    a TOML list in st.secrets). Multiple keys multiply free-tier capacity —
    but note Gemini quota is per Google Cloud *project*, so keys from the same
    project still share one quota; use keys from different projects.
    """
    keys: list[str] = []
    for name in ("GEMINI_API_KEY", "GEMINI_API_KEYS"):
        for key in _split_keys(_resolve_env_key(name)):
            if key not in keys:
                keys.append(key)
    return keys


def _resolve_api_key() -> str:
    """Resolve the primary provider key (first GEMINI_API_KEY)."""
    keys = _resolve_api_keys()
    return keys[0] if keys else ""


def _resolve_agentrouter_api_key() -> str:
    """Resolve the AgentRouter key (AGENTROUTER_API_KEY). Optional."""
    return _resolve_env_key("AGENTROUTER_API_KEY")


def _resolve_fallback_api_key() -> str:
    """Resolve the fallback provider key (FALLBACK_API_KEY or ORCAROUTER_API_KEY)."""
    return _resolve_env_key("FALLBACK_API_KEY") or _resolve_env_key(
        "ORCAROUTER_API_KEY"
    )


class APIKeyResolution(BaseModel):
    """Secure API key resolution with three-tier fallback chain."""

    source: str = "auto"
    value: Optional[str] = None

    def resolve(self) -> str:
        if self.value:
            return self.value
        return _resolve_api_key()


class APIConfig(BaseModel):
    """Google Gemini API configuration (OpenAI-compatible endpoint)."""

    base_url: str = os.getenv(
        "GEMINI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    )
    model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    # Ordered Gemini models to attempt before the fallback provider. Google
    # retires Flash models quickly (2.5 -> 404) and the free tier grants a
    # separate daily quota per model, so a chain adds both resilience and
    # free capacity. GEMINI_MODEL is always tried first.
    gemini_models: str = os.getenv(
        "GEMINI_MODELS",
        "gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash",
    )
    max_tokens: int = 8192
    temperature: float = 0.1
    top_p: float = 0.9
    max_retries: int = 3
    timeout_s: int = 300
    # Optional override for thinking budget. When None, the LLM client
    # auto-selects "low" for Gemini 3.x reasoning models to keep content
    # within max_tokens. Set GEMINI_REASONING_EFFORT to force a value.
    reasoning_effort: Optional[str] = os.getenv("GEMINI_REASONING_EFFORT") or None

    # --- Secondary provider: AgentRouter (tried after every Gemini attempt) ---
    # OpenAI-compatible gateway exposing DeepSeek. Only used when
    # AGENTROUTER_API_KEY is present.
    agentrouter_base_url: str = os.getenv(
        "AGENTROUTER_BASE_URL",
        "https://agentrouter.org/v1/chat/completions",
    )
    agentrouter_model: str = os.getenv("AGENTROUTER_MODEL", "deepseek-v4-flash")

    # --- Fallback provider (used when Gemini and AgentRouter are exhausted/down) ---
    # Any OpenAI-compatible endpoint works. Defaults to OrcaRouter. The generic
    # FALLBACK_* names take precedence, so the fallback can be repointed at
    # another gateway (e.g. OpenRouter, Groq) without touching the code.
    fallback_base_url: str = (
        os.getenv("FALLBACK_BASE_URL")
        or os.getenv("ORCAROUTER_BASE_URL")
        or "https://api.orcarouter.ai/v1/chat/completions"
    )
    fallback_model: str = (
        os.getenv("FALLBACK_MODEL")
        or os.getenv("ORCAROUTER_MODEL")
        or "deepseek/deepseek-v4-flash-free"
    )
    enable_fallback: bool = os.getenv("ENABLE_LLM_FALLBACK", "true").lower() not in (
        "0",
        "false",
        "no",
    )

    key_resolution: APIKeyResolution = APIKeyResolution()

    @property
    def gemini_model_chain(self) -> list[str]:
        """Ordered, de-duplicated Gemini models to try before the fallback."""
        chain: list[str] = []
        for candidate in [self.model, *self.gemini_models.split(",")]:
            candidate = candidate.strip()
            if candidate and candidate not in chain:
                chain.append(candidate)
        return chain


class SimulationDefaults(BaseModel):
    """Default scenario parameters matching Paper Table 4.1 (SPbETU 2026)."""

    application_type: str = "banking platform"
    application_name: str = "SecureBank Pro"
    service_name: str = "payment-gateway-service"
    tech_stack: str = "Python/FastAPI, PostgreSQL 14, Redis 7, Kubernetes 1.27"
    orchestration_platform: str = "Kubernetes 1.27 on AWS EKS"
    monitoring_tools: str = "Prometheus + Grafana + PagerDuty"
    severity_level: str = "critical"
    business_context: str = "regular hours"
    alert_count: str = "1"
    incident_trigger: str = "high error rate"
    engineer_level: str = "mid-level"
    teaching_mode: str = "socratic"
    investigation_scope: str = "full-stack"
    max_steps: str = "3"
    evidence_type: str = "logs + metrics"
    log_format: str = "JSON"
    evidence_lines: str = "15"
    clue_visibility: str = "subtle"
    analysis_depth: str = "deep"
    mitigation_horizon: str = "immediate"
    risk_tolerance: str = "low"
    include_rollback: str = "yes"
    code_style: str = "imperative"
    audience_type: str = "all"
    incident_status: str = "investigating"
    impact_duration: str = "28 minutes"
    max_words: int = 150
    communication_channel: str = "Slack #incidents"
    tone: str = "professional"
    postmortem_style: str = "Google SRE"
    action_items_count: int = 4
    include_metrics: str = "yes"
    blameless_mode: str = "strict"
    output_format: str = "Markdown"

    # NOTE: hidden_cause is intentionally NOT a default field.
    # It must be supplied by the caller at runtime.
