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


def _resolve_api_key() -> str:
    """
    Resolve NVIDIA_API_KEY through three-tier fallback chain:
    1. Google Colab Secrets (if in Colab)
    2. .env file (loaded at import time)
    3. Environment variable
    """
    env = _detect_environment()

    # Tier 1: Colab Secrets
    if env == "colab":
        try:
            from google.colab import userdata
            key = userdata.get("NVIDIA_API_KEY")
            if key:
                return key
        except Exception:
            pass

    # Tier 2: .env file (already loaded by load_dotenv)
    key = os.getenv("NVIDIA_API_KEY")
    if key:
        return key

    # Tier 3: Explicit env var (documented fallback)
    return ""  # Triggers ValueError at LLMClient init


class APIKeyResolution(BaseModel):
    """Secure API key resolution with three-tier fallback chain."""

    source: str = "auto"
    value: Optional[str] = None

    def resolve(self) -> str:
        if self.value:
            return self.value
        return _resolve_api_key()


class APIConfig(BaseModel):
    """NVIDIA build.nvidia.com API configuration (OpenAI-compatible)."""

    base_url: str = "https://integrate.api.nvidia.com/v1/chat/completions"
    model: str = "mistralai/mistral-medium-3.5-128b"
    max_tokens: int = 3000
    temperature: float = 0.1
    top_p: float = 0.9
    max_retries: int = 3
    timeout_s: int = 300

    key_resolution: APIKeyResolution = APIKeyResolution()


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
