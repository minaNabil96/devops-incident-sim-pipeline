# Implementation Plan — DevOps Incident Simulation Pipeline (CrewAI Edition)

> **Purpose**: Complete technical specification for transforming the existing Jupyter notebook into a production-grade, full-stack CrewAI application. This document is self-contained and designed for handoff to another AI agent or developer.

---

## 1. Project Context & Goals

### 1.1 Existing System
The current project is a Jupyter notebook (`devops_dahl.ipynb`) implementing a 7-stage prompt engineering pipeline for SRE incident simulation. It uses:
- **Jinja2** for prompt templating (7 `.j2` templates)
- **NVIDIA build API** (`mistralai/mistral-medium-3.5-128b`) for LLM inference
- **SSE Streaming** to bypass long-generation timeouts
- **Regex sanitization** to strip `<think>...</think>` reasoning tags
- **Chain-of-prompts** architecture where each stage's output is injected into the next

### 1.2 Target System
A **Master's thesis-grade** full-stack application with:
- **CrewAI** multi-agent orchestration (7 specialized agents)
- **Streamlit** interactive frontend for trainees
- **Hugging Face Spaces** free-tier deployment
- **Docker** containerization
- **100% backward compatibility** with the original notebook's output format

### 1.3 Academic Validation Target
Must maintain **100% structural compliance** with the paper: *"Development of a set of prompt templates for simulation and response to incidents in DevOps"* (Saint Petersburg Electrotechnical University, 2026).

---

## 2. Complete File Structure

```
devops-incident-sim-pipeline/
├── src/
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py          # Pydantic settings, API key resolution
│   ├── core/
│   │   ├── __init__.py
│   │   ├── llm.py               # LLMClient with SSE streaming
│   │   └── renderer.py          # Jinja2 template renderer
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── stage_0_scenario.j2
│   │   ├── stage_1_alert.j2
│   │   ├── stage_2_triage.j2
│   │   ├── stage_3_rca.j2
│   │   ├── stage_4_remediation.j2
│   │   ├── stage_5_communication.j2
│   │   └── stage_6_postmortem.j2
│   ├── agents/
│   │   ├── __init__.py
│   │   └── definitions.py       # 7 CrewAI Agent definitions
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── definitions.py       # 7 CrewAI Task definitions
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── validators.py        # JSON schema, kubectl, SMART validators
│   │   └── template_tools.py    # Jinja2 loading utilities
│   └── pipeline.py              # CrewAI orchestrator (main entry point)
├── app/
│   ├── __init__.py
│   └── main.py                  # Streamlit frontend
├── tests/
│   ├── __init__.py
│   ├── test_agents.py
│   ├── test_pipeline.py
│   ├── test_tools.py
│   └── conftest.py              # Pytest fixtures
├── .env.example
├── .gitignore
├── .dockerignore
├── Dockerfile
├── requirements.txt
├── README.md
├── CASE_STUDY.md              # Existing (keep as-is)
├── LINKEDIN_POST.md           # Existing (keep as-is)
├── devops_dahl.ipynb          # Original notebook (keep as-is, do not modify)
└── incident_simulation_report.md  # Existing output artifact (keep as-is)
```

---

## 3. File-by-File Specification

### 3.1 `src/config/settings.py`

**Purpose**: Centralized configuration using Pydantic for type safety and validation.

**Content Requirements**:

```python
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
from pydantic import BaseModel, field_validator

# Resolve project root regardless of CWD
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _detect_environment() -> str:
    """Detect runtime environment: 'colab', 'streamlit', 'huggingface', or 'local'."""
    try:
        import google.colab
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

    # Tier 2: .env file
    key = os.getenv("NVIDIA_API_KEY")
    if key:
        return key

    # Tier 3: Explicit env var
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
    """NVIDIA build.nvidia.com API configuration."""
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

    @field_validator("hidden_cause", mode="before")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v
```

**Critical Notes**:
- The `hidden_cause` field is NOT in the defaults — it must be provided by the user at runtime
- The `_resolve_api_key()` function must be importable and callable independently
- All defaults match the original notebook's `params` dict exactly

---

### 3.2 `src/core/llm.py`

**Purpose**: HTTP client for NVIDIA build API with SSE streaming and regex sanitization.

**Content Requirements**:

```python
"""
LLM Client for the NVIDIA build.nvidia.com API (mistralai/mistral-medium-3.5-128b).

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
                "NVIDIA_API_KEY not found. Set via:\n"
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
        Generate a completion via the NVIDIA build API with SSE streaming.

        Collects incremental token deltas over Server-Sent Events,
        bypassing long-generation timeouts on long generation sequences.

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

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(
                    url,
                    headers=self.headers,
                    json=payload,
                    stream=True,
                    timeout=self.config.timeout_s,
                )

                if response.status_code != 200:
                    self._log_status(attempt, response.status_code)
                    if attempt < max_retries:
                        time.sleep(5)
                    continue

                collected: list[str] = []
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
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

                content = "".join(collected).strip()
                content = self._strip_reasoning(content)

                # Guard against intentionally empty responses
                if not content and attempt < max_retries:
                    self._log_status(attempt, 0, empty=True)
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
            except Exception as exc:
                self._log_status(attempt, f"error:{exc!r}")

            if attempt < max_retries:
                time.sleep(5)

        raise RuntimeError(
            f"LLM call failed after {max_retries} attempts"
        )

    @staticmethod
    def _strip_reasoning(text: str) -> str:
        """Remove internal monologue tags from reasoning model outputs."""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    def _log_status(self, attempt: int, status: str | int, empty: bool = False) -> None:
        suffix = " (empty response)" if empty else ""
        print(f"  ⚠ Attempt {attempt}: API {status}{suffix} — retrying...")
```

**Critical Notes**:
- The `_strip_reasoning` method is CRITICAL — it removes `<think>...</think>` tags that Kimi-K2.6 emits
- SSE streaming is REQUIRED — do not use non-streaming requests (they hit long-generation timeouts)
- The `LLMResponse` dataclass must be importable by tests

---

### 3.3 `src/core/renderer.py`

**Purpose**: Jinja2 template loading and rendering with context injection.

**Content Requirements**:

```python
"""
Jinja2 template renderer for the prompt engineering pipeline.

Loads .j2 templates from src/prompts/, injects scenario parameters,
and enforces context-chain integrity by requiring all prior stage outputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config.settings import PROJECT_ROOT

PROMPTS_DIR = PROJECT_ROOT / "src" / "prompts"


class TemplateRenderer:
    """
    Jinja2 renderer for the 7-stage prompt chain.

    Maintains strict separation between scenario parameters (passed once)
    and prior-stage context outputs (accumulated across stages).
    """

    _env: Environment | None = None

    @classmethod
    def cls_env(cls) -> Environment:
        if cls._env is None:
            cls._env = Environment(
                loader=FileSystemLoader(str(PROMPTS_DIR)),
                autoescape=select_autoescape(enabled_extensions=("html", "htm", "xml")),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        return cls._env

    @classmethod
    def render(
        cls,
        template_name: str,
        params: dict[str, Any],
        prior_outputs: dict[str, str],
    ) -> str:
        """
        Render a stage template with merged scope.

        Priority order: prior_outputs < params (params override prior stage keys).
        """
        merged = {**prior_outputs, **params}
        template = cls.cls_env().get_template(f"{template_name}.j2")
        return template.render(**merged)

    @classmethod
    def validate_templates(cls) -> list[str]:
        """Verify all 7 templates exist and can be resolved."""
        expected = [
            "stage_0_scenario",
            "stage_1_alert",
            "stage_2_triage",
            "stage_3_rca",
            "stage_4_remediation",
            "stage_5_communication",
            "stage_6_postmortem",
        ]
        env = cls.cls_env()
        available = env.list_templates(extensions=["j2"])
        missing = [t for t in expected if f"{t}.j2" not in available]
        return missing
```

---

### 3.4 `src/prompts/*.j2` (7 files)

**Purpose**: Jinja2 templates for each pipeline stage. These are the EXACT templates from the original notebook, extracted into standalone files.

**File Contents** (copy verbatim from notebook Cell 3):

#### `stage_0_scenario.j2`
```
You are a {{scenario_architect_persona | default("Scenario Architect")}}.

Create a comprehensive incident scenario for a {{application_type}} named {{application_name}}.

Affected service: {{service_name}}
Technology stack: {{tech_stack}}
Orchestration platform: {{orchestration_platform}}
Monitoring tools: {{monitoring_tools}}

HIDDEN ROOT CAUSE [DO NOT REVEAL THIS IN OUTPUT]:
{{hidden_cause}}

{% if reveal_cause == "yes" %}[TRAINER ONLY: The hidden cause is {{hidden_cause}}]{% endif %}

OUTPUT REQUIREMENTS:
1. System Overview — describe the application purpose and user base
2. Architecture Summary — list microservices, databases, message queues, orchestration
3. Current Conditions — current load, recent deployments, anomalies
4. Service Dependencies — upstream and downstream services for {{service_name}}

Format: {{output_format | default("Markdown")}}

Keep the output self-contained — it will be injected as {{output_stage_0}} into the next stage.
```

#### `stage_1_alert.j2`
```
You are a {{monitoring_persona | default("Monitoring System Simulator")}}.

Based on the scenario below, generate a realistic alert notification.

SCENARIO CONTEXT:
{{output_stage_0}}

Alert trigger: {{incident_trigger}}
Severity: {{severity_level}}
Business context: {{business_context}}
Number of alerts: {{alert_count | default("1")}}

INSTRUCTIONS:
- Mirror the EXACT schema and field names used by {{monitoring_tools}}
- Include realistic labels, annotations, timestamps, and generator URLs
- If alert_count > 1, simulate an alert storm with escalating severity
- Also provide a human-readable PagerDuty-style notification summary
- All Kubernetes namespaces in the alert labels MUST be exactly "production" (do not use securebank-prod or other names).
- Output ONLY a single JSON object in the exact Alertmanager schema. DO NOT output Prometheus YAML or PagerDuty JSON.
- The "namespace" label in the JSON MUST be exactly "production" (do not use "payments" or any other name).
- Ensure the JSON is fully closed and valid.

Format: {{output_format | default("JSON (Alertmanager schema)")}}
```

#### `stage_2_triage.j2`
```
You are a {{mentor_persona | default("Senior SRE Mentor")}} guiding a {{engineer_level}} engineer.

ALERT CONTEXT:
{{output_stage_1}}

Technology stack: {{tech_stack}}
Orchestration: {{orchestration_platform}}
Investigation scope: {{investigation_scope | default("full-stack")}}
Teaching mode: {{teaching_mode | default("guided")}}

INSTRUCTIONS:
1. Acknowledge the alert and state the primary goal
2. Provide exactly {{max_steps | default("3")}} investigation steps, each containing:
   - Command to execute
   - Expected output description
   - Rationale explaining WHY this step matters
3. End with an open question leading toward log analysis

CONSTRAINTS:
- DO NOT reveal the root cause
- DO NOT suggest remediation — only investigation
- Adapt detail level to {{engineer_level}}
- If teaching_mode == "socratic", ask questions instead of giving commands

Format: {{output_format | default("Markdown")}}
```

#### `stage_3_rca.j2`
```
You are a {{analyst_persona | default("Log & Metrics Analysis Expert")}}.

INVESTIGATION CONTEXT:
{{output_stage_2}}

HIDDEN ROOT CAUSE [FOR EVIDENCE CRAFTING ONLY — DO NOT STATE DIRECTLY]:
{{hidden_cause}}

Evidence type: {{evidence_type | default("logs")}}
Log format: {{log_format | default("JSON")}}
Evidence lines: {{evidence_lines | default("15")}}
Clue visibility: {{clue_visibility | default("subtle")}}
Analysis depth: {{analysis_depth | default("deep")}}

INSTRUCTIONS:
Generate exactly 3 sections:

SECTION 1 — ARTIFACTS:
- Create {{evidence_lines}} realistic {{evidence_type}} entries
- Include a graduated degradation pattern: INFO → WARN → ERROR
- Embed subtle clues pointing to {{hidden_cause}} without naming it

SECTION 2 — ANALYSIS:
- Provide guided interpretation of the artifacts
- Highlight the degradation timeline
- Point toward the affected component without revealing the exact cause
- DO NOT explicitly state the root cause
- DO NOT use phrases like "The root cause was..." or "This was caused by..."
- Only describe patterns and anomalies

SECTION 3 — NEXT STEP:
- Ask a specific diagnostic question that would help confirm the hypothesis

CONSTRAINTS:
- DO NOT reveal the root cause explicitly
- DO NOT mention "{{hidden_cause}}" directly in the output
- Clue visibility = "{{clue_visibility}}" determines how obvious the hints are
- If clue_visibility == "misleading", include a red herring
- Only provide evidence, never conclusions about root cause
- DO NOT output your internal reasoning, planning steps, or thoughts.
- DO NOT include any meta-commentary about how you are generating the clues.
- Output ONLY the 3 requested sections (ARTIFACTS, ANALYSIS, NEXT STEP).
- If you catch yourself planning the clues, DELETE that text from the final output.

Format: {{output_format | default("Markdown")}}
```

#### `stage_4_remediation.j2`
```
You are an {{engineer_persona | default("Expert DevOps/SRE Engineer")}}.

ROOT CAUSE CONTEXT:
{{output_stage_3}}

Mitigation horizons: {{mitigation_horizon | default("immediate, short")}}
Orchestration platform: {{orchestration_platform}}
Risk tolerance: {{risk_tolerance | default("low")}}
Code style: {{code_style | default("imperative")}}
Include rollback: {{include_rollback | default("yes")}}

INSTRUCTIONS:
For EACH mitigation horizon, provide:

HORIZON: <name> (<timeframe>)
Strategy: <one-line summary>

Commands:
```bash
# Step N: <description>
<actual command>
```

Rollback:
```bash
<rollback command if needed>
```

CONSTRAINTS:
- If risk_tolerance == "low": add --dry-run=client preview before each change
- All namespaces MUST be "production" (not securebank-prod or other names)
- All pod names, deployment names must match the scenario context
- Label any destructive step with: # WARNING: destructive operation
- If include_rollback == "yes": provide rollback for EVERY change
- Each horizon must be independently executable
- Use exact kubectl syntax from Kubernetes 1.27

Format: {{output_format | default("Markdown")}}
```

#### `stage_5_communication.j2`
```
You are an {{communicator_persona | default("Incident Commander")}}.

REMEDIATION CONTEXT:
{{output_stage_4}}

Audience: {{audience_type | default("all")}}
Channel: {{communication_channel | default("Slack #incidents")}}
Incident status: {{incident_status | default("mitigating")}}
Impact duration: {{impact_duration}}
Tone: {{tone | default("professional")}}
Max words per message: {{max_words | default("150")}}

INSTRUCTIONS:
{% if audience_type == "all" %}
Generate THREE separate messages:

[TECHNICAL TEAM] — Slack #incidents
- Include specific error rates, affected services, actions being taken
- Max {{max_words}} words

[BUSINESS STAKEHOLDERS] — Email to Department Heads
- Translate technical impact to business terms (revenue, users affected)
- Include estimated resolution time
- Max {{max_words}} words

[EXECUTIVE LEADERSHIP] — SMS/Executive Slack
- Bullet-point summary only
- Current status, business impact, estimated resolution
- Max {{ (max_words | int) // 1.5 | int }} words
{% else %}
Generate ONE message for {{audience_type}} audience via {{communication_channel}}.
{% endif %}

CONSTRAINTS:
- Status is "{{incident_status}}" — do NOT use "resolved" language
- No technical jargon for business/executive audiences
- Be concise — respect the word limits strictly
- MUST generate 3 separate messages when audience_type="all"

Format: {{output_format | default("Markdown")}}
```

#### `stage_6_postmortem.j2`
```
You are a {{writer_persona | default("Technical Writer specializing in Blameless Post-mortems")}}.

FULL INCIDENT CONTEXT:
Stage 0 — Scenario: {{output_stage_0}}
Stage 1 — Alert: {{output_stage_1}}
Stage 2 — Triage: {{output_stage_2}}
Stage 3 — Root Cause: {{output_stage_3}}
Stage 4 — Remediation: {{output_stage_4}}
Stage 5 — Communication: {{output_stage_5}}

Post-mortem style: {{postmortem_style | default("Google SRE")}}
Action items count: {{action_items_count | default("4")}}
Include metrics: {{include_metrics | default("yes")}}
Blameless mode: {{blameless_mode | default("strict")}}
Impact duration: {{impact_duration}}

Format: {{output_format | default("Markdown")}}

INSTRUCTIONS:
Generate a complete post-mortem report with these sections:

1. Metadata (service, date, severity, duration, status, on-call team)
   - Duration MUST be {{impact_duration}} (not calculated)

2. Executive Summary

3. Impact (user-facing, business, duration)

4. Timeline (table with time, event, detected by)
   - Total duration MUST equal {{impact_duration}}

5. Root Cause Analysis

6. Contributing Factors

7. Action Items — exactly {{action_items_count}} SMART items (table with ID, Description, Owner, Priority, Due Date)

8. Lessons Learned:
   - What went well
   - What to improve
   - What we got lucky with

9. Appendix: Key Metrics (MTTR, peak error rate, affected users)

CONSTRAINTS:
- Blameless mode == "strict": use ONLY team names, NEVER individual employee names
- Action items must be SMART: Specific, Measurable, Achievable, Relevant, Time-bound
- Synthesize information from ALL six preceding stages
- Duration in Metadata and Timeline MUST match {{impact_duration}} exactly

Format: {{output_format | default("Markdown")}}
```

---

### 3.5 `src/tools/validators.py`

**Purpose**: Validation utilities for generated artifacts.

**Content Requirements**:

```python
"""
Validation utilities for generated incident artifacts.

Provides schema validation for Alertmanager JSON, kubectl command syntax,
and SMART action item verification.
"""

from __future__ import annotations

import json
import re
from typing import Any


class AlertmanagerValidator:
    """Validate Alertmanager v4 JSON schema compliance."""

    REQUIRED_FIELDS = {
        "version": str,
        "groupKey": str,
        "status": str,
        "receiver": str,
        "groupLabels": dict,
        "commonLabels": dict,
        "alerts": list,
    }

    @classmethod
    def validate(cls, json_str: str) -> tuple[bool, list[str]]:
        """
        Validate Alertmanager JSON structure.

        Returns:
            (is_valid, list_of_errors)
        """
        errors: list[str] = []

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return False, [f"Invalid JSON: {e}"]

        for field, expected_type in cls.REQUIRED_FIELDS.items():
            if field not in data:
                errors.append(f"Missing required field: {field}")
            elif not isinstance(data[field], expected_type):
                errors.append(
                    f"Field '{field}' has wrong type: "
                    f"expected {expected_type.__name__}, got {type(data[field]).__name__}"
                )

        # Validate namespace consistency
        if "commonLabels" in data:
            ns = data["commonLabels"].get("namespace")
            if ns != "production":
                errors.append(f"Namespace must be 'production', got '{ns}'")

        # Validate alerts array
        if "alerts" in data and isinstance(data["alerts"], list):
            for i, alert in enumerate(data["alerts"]):
                if "labels" not in alert:
                    errors.append(f"Alert {i} missing 'labels'")
                elif alert["labels"].get("namespace") != "production":
                    errors.append(f"Alert {i} has wrong namespace")

        return len(errors) == 0, errors


class KubectlValidator:
    """Validate kubectl command syntax."""

    VALID_COMMANDS = {
        "get", "describe", "logs", "exec", "apply", "delete",
        "scale", "patch", "rollout", "top", "port-forward", "cp"
    }

    @classmethod
    def validate_command(cls, cmd: str) -> tuple[bool, str]:
        """
        Validate a single kubectl command.

        Returns:
            (is_valid, error_message_or_empty)
        """
        cmd = cmd.strip()
        if not cmd.startswith("kubectl"):
            return False, "Command must start with 'kubectl'"

        parts = cmd.split()
        if len(parts) < 2:
            return False, "Command too short"

        verb = parts[1]
        if verb not in cls.VALID_COMMANDS:
            return False, f"Unknown kubectl verb: {verb}"

        # Check for namespace flag
        if "--namespace" not in cmd and "-n" not in cmd:
            return False, "Missing --namespace or -n flag"

        # Check for production namespace
        if "production" not in cmd:
            return False, "Namespace must be 'production'"

        return True, ""

    @classmethod
    def extract_commands(cls, text: str) -> list[str]:
        """Extract all kubectl commands from markdown code blocks."""
        pattern = r"```(?:bash)?\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        commands = []
        for match in matches:
            for line in match.split("\n"):
                line = line.strip()
                if line.startswith("kubectl"):
                    commands.append(line)
        return commands


class SMARTValidator:
    """Validate SMART action item criteria."""

    @classmethod
    def validate_item(cls, item: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Validate a single SMART action item.

        Expected keys: id, description, owner, priority, due_date
        """
        errors = []
        required = ["id", "description", "owner", "priority", "due_date"]

        for field in required:
            if field not in item:
                errors.append(f"Missing field: {field}")

        # Check for measurable criteria in description
        desc = item.get("description", "")
        if not any(word in desc.lower() for word in ["implement", "add", "create", "deploy", "configure"]):
            errors.append("Description lacks actionable verb")

        # Check for time-bound (due_date format)
        due = item.get("due_date", "")
        if not re.match(r"\d{4}-\d{2}-\d{2}", str(due)):
            errors.append("Due date must be in YYYY-MM-DD format")

        return len(errors) == 0, errors
```

---

### 3.6 `src/tools/template_tools.py`

**Purpose**: CrewAI tool wrappers for template operations.

**Content Requirements**:

```python
"""
CrewAI tool wrappers for template and file operations.

These tools are exposed to CrewAI agents for dynamic prompt generation
and output persistence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from crewai_tools import tool

from src.config.settings import PROJECT_ROOT
from src.core.renderer import TemplateRenderer


@tool("Render Prompt Template")
def render_prompt_template(template_name: str, params_json: str, prior_outputs_json: str) -> str:
    """
    Render a Jinja2 prompt template with parameters and prior stage outputs.

    Args:
        template_name: Name of the template (e.g., "stage_0_scenario")
        params_json: JSON string of scenario parameters
        prior_outputs_json: JSON string of prior stage outputs

    Returns:
        Rendered prompt string ready for LLM consumption
    """
    import json
    params = json.loads(params_json)
    prior_outputs = json.loads(prior_outputs_json)
    return TemplateRenderer.render(template_name, params, prior_outputs)


@tool("Save Stage Output")
def save_stage_output(stage_name: str, content: str) -> str:
    """
    Save a stage's output to disk for later consolidation.

    Args:
        stage_name: Name of the stage (e.g., "stage_0_scenario")
        content: The generated content to save

    Returns:
        Confirmation message with file path
    """
    output_dir = PROJECT_ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)

    filepath = output_dir / f"{stage_name}_output.txt"
    filepath.write_text(content, encoding="utf-8")

    return f"Saved to {filepath}"


@tool("Load Prior Stage Output")
def load_prior_stage_output(stage_name: str) -> str:
    """
    Load a prior stage's output from disk.

    Args:
        stage_name: Name of the stage to load

    Returns:
        The stage's output content, or empty string if not found
    """
    output_dir = PROJECT_ROOT / "outputs"
    filepath = output_dir / f"{stage_name}_output.txt"

    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return ""
```

---

### 3.7 `src/agents/definitions.py`

**Purpose**: CrewAI Agent definitions for all 7 pipeline stages.

**Content Requirements**:

```python
"""
CrewAI Agent definitions for the DevOps Incident Simulation Pipeline.

Each agent corresponds to one stage of the incident lifecycle and has
a specific role, goal, backstory, and toolset.
"""

from __future__ import annotations

from crewai import Agent

from src.tools.template_tools import (
    render_prompt_template,
    save_stage_output,
    load_prior_stage_output,
)


def create_scenario_architect() -> Agent:
    """Stage 0: Scenario Architect — builds the infrastructure context."""
    return Agent(
        role="Scenario Architect",
        goal="Create comprehensive, realistic incident scenarios with hidden root causes",
        backstory="""You are a senior infrastructure architect with 15 years of experience
        designing distributed systems for financial institutions. You specialize in creating
        training scenarios that are indistinguishable from real production incidents. You
        understand that the best training scenarios have subtle, non-obvious root causes that
        require systematic investigation to uncover.""",
        tools=[render_prompt_template, save_stage_output],
        verbose=True,
        allow_delegation=False,
        max_iter=1,
    )


def create_alert_generator() -> Agent:
    """Stage 1: Alert Generator — emits Alertmanager-compliant JSON."""
    return Agent(
        role="Monitoring System Simulator",
        goal="Generate schema-valid Alertmanager v4 JSON alerts with production namespace",
        backstory="""You are a monitoring infrastructure expert who has configured Prometheus,
        Alertmanager, and PagerDuty for Fortune 500 companies. You know that alerts must be
        machine-parseable, contain precise labels, and follow the Alertmanager v4 schema
        exactly. You never deviate from the schema — invalid JSON is worse than no alert.""",
        tools=[render_prompt_template, save_stage_output, load_prior_stage_output],
        verbose=True,
        allow_delegation=False,
        max_iter=1,
    )


def create_sre_mentor() -> Agent:
    """Stage 2: Senior SRE Mentor — guides triage through Socratic questioning."""
    return Agent(
        role="Senior SRE Mentor",
        goal="Guide engineers through systematic incident triage using Socratic questioning",
        backstory="""You are a Staff SRE with 12 years at Google and Netflix. You believe
        that telling someone the answer robs them of the learning opportunity. Instead, you
        ask carefully crafted questions that lead the engineer to discover the root cause
        themselves. You adapt your questioning depth to the engineer's seniority level.""",
        tools=[render_prompt_template, save_stage_output, load_prior_stage_output],
        verbose=True,
        allow_delegation=False,
        max_iter=1,
    )


def create_rca_analyst() -> Agent:
    """Stage 3: Log & Metrics Analyst — crafts graduated-degradation evidence."""
    return Agent(
        role="Log & Metrics Analysis Expert",
        goal="Generate realistic log artifacts with subtle clues pointing to hidden root causes",
        backstory="""You are a forensic log analyst who has investigated hundreds of production
        incidents. You know that real logs don't scream the answer — they whisper it through
        patterns: graduated degradation, subtle timing correlations, and anomalous metric
        combinations. You craft evidence that rewards careful analysis.""",
        tools=[render_prompt_template, save_stage_output, load_prior_stage_output],
        verbose=True,
        allow_delegation=False,
        max_iter=1,
    )


def create_remediation_engineer() -> Agent:
    """Stage 4: Expert DevOps Engineer — produces kubectl commands with rollback."""
    return Agent(
        role="Expert DevOps/SRE Engineer",
        goal="Generate executable kubectl remediation commands with mandatory rollback procedures",
        backstory="""You are a Kubernetes administrator who has handled 200+ production
        incidents. You follow the 'measure twice, cut once' principle: every destructive
        command has a --dry-run=client preview, and every change has a documented rollback.
        You never use namespaces other than 'production' in training scenarios.""",
        tools=[render_prompt_template, save_stage_output, load_prior_stage_output],
        verbose=True,
        allow_delegation=False,
        max_iter=1,
    )


def create_incident_commander() -> Agent:
    """Stage 5: Incident Commander — triple-audience communication."""
    return Agent(
        role="Incident Commander",
        goal="Craft audience-appropriate incident communications for technical, business, and executive stakeholders",
        backstory="""You are a crisis communication specialist who has managed incident
        response for major cloud providers. You know that technical teams want error rates
        and stack traces, business stakeholders want revenue impact and ETAs, and executives
        want bullet points. You never mix audiences or use jargon with non-technical leaders.""",
        tools=[render_prompt_template, save_stage_output, load_prior_stage_output],
        verbose=True,
        allow_delegation=False,
        max_iter=1,
    )


def create_postmortem_writer() -> Agent:
    """Stage 6: Technical Writer — blameless post-mortem synthesis."""
    return Agent(
        role="Technical Writer",
        goal="Synthesize blameless post-mortems with SMART action items from all prior stages",
        backstory="""You are a technical writer specializing in SRE documentation. You follow
        the Google SRE blameless post-mortem culture: focus on systems and processes, never
        individuals. Your action items are always SMART — Specific, Measurable, Achievable,
        Relevant, and Time-bound. You synthesize information from all prior stages into a
        coherent narrative.""",
        tools=[render_prompt_template, save_stage_output, load_prior_stage_output],
        verbose=True,
        allow_delegation=False,
        max_iter=1,
    )


# Agent registry for pipeline orchestration
AGENT_REGISTRY = {
    0: create_scenario_architect,
    1: create_alert_generator,
    2: create_sre_mentor,
    3: create_rca_analyst,
    4: create_remediation_engineer,
    5: create_incident_commander,
    6: create_postmortem_writer,
}
```

---

### 3.8 `src/tasks/definitions.py`

**Purpose**: CrewAI Task definitions for all 7 pipeline stages.

**Content Requirements**:

```python
"""
CrewAI Task definitions for the DevOps Incident Simulation Pipeline.

Each task corresponds to one stage and defines the expected output,
context dependencies, and validation criteria.
"""

from __future__ import annotations

from crewai import Task

from src.agents.definitions import AGENT_REGISTRY


def create_scenario_task(params: dict) -> Task:
    """Stage 0: Generate incident scenario."""
    agent = AGENT_REGISTRY[0]()
    return Task(
        description=f"""
        Generate a comprehensive incident scenario using the render_prompt_template tool.

        Template: stage_0_scenario
        Parameters: {params}

        The scenario must include:
        1. System Overview (user base, transaction volume)
        2. Architecture Summary (microservices, databases, message queues)
        3. Current Conditions (load, recent deployments, anomalies)
        4. Service Dependencies (upstream and downstream)

        Save the output using save_stage_output with stage_name="stage_0_scenario".
        """,
        agent=agent,
        expected_output="A markdown document with 4 sections describing the incident scenario",
    )


def create_alert_task(params: dict) -> Task:
    """Stage 1: Generate Alertmanager JSON alert."""
    agent = AGENT_REGISTRY[1]()
    return Task(
        description=f"""
        Generate an Alertmanager v4 JSON alert using the render_prompt_template tool.

        Template: stage_1_alert
        Parameters: {params}
        Prior context: Load stage_0_scenario output using load_prior_stage_output

        The alert MUST:
        - Be valid JSON in Alertmanager v4 schema
        - Use namespace "production" in ALL labels
        - Include realistic labels, annotations, timestamps
        - Have status "firing"

        Save the output using save_stage_output with stage_name="stage_1_alert".
        """,
        agent=agent,
        expected_output="Valid Alertmanager v4 JSON with production namespace",
    )


def create_triage_task(params: dict) -> Task:
    """Stage 2: Generate Socratic triage guide."""
    agent = AGENT_REGISTRY[2]()
    return Task(
        description=f"""
        Generate a triage investigation guide using the render_prompt_template tool.

        Template: stage_2_triage
        Parameters: {params}
        Prior context: Load stage_1_alert output using load_prior_stage_output

        The guide MUST:
        - Use Socratic questioning (ask, don't tell)
        - Provide exactly {params.get('max_steps', '3')} investigation steps
        - Each step has: command, expected output, rationale
        - End with an open question leading to log analysis
        - NOT reveal the root cause

        Save the output using save_stage_output with stage_name="stage_2_triage".
        """,
        agent=agent,
        expected_output="Markdown triage guide with Socratic questions",
    )


def create_rca_task(params: dict) -> Task:
    """Stage 3: Generate RCA evidence artifacts."""
    agent = AGENT_REGISTRY[3]()
    return Task(
        description=f"""
        Generate RCA evidence artifacts using the render_prompt_template tool.

        Template: stage_3_rca
        Parameters: {params}
        Prior context: Load stage_2_triage output using load_prior_stage_output

        The output MUST have exactly 3 sections:
        1. ARTIFACTS: {params.get('evidence_lines', '15')} realistic log entries
           - Graduated degradation: INFO → WARN → ERROR
           - Subtle clues to hidden cause (do NOT name it)
        2. ANALYSIS: Guided interpretation without revealing root cause
        3. NEXT STEP: Diagnostic question to confirm hypothesis

        Save the output using save_stage_output with stage_name="stage_3_rca".
        """,
        agent=agent,
        expected_output="3-section markdown with log artifacts and analysis",
    )


def create_remediation_task(params: dict) -> Task:
    """Stage 4: Generate kubectl remediation commands."""
    agent = AGENT_REGISTRY[4]()
    return Task(
        description=f"""
        Generate remediation commands using the render_prompt_template tool.

        Template: stage_4_remediation
        Parameters: {params}
        Prior context: Load stage_3_rca output using load_prior_stage_output

        The output MUST:
        - Include --dry-run=client preview before each change
        - Use namespace "production" in ALL commands
        - Provide rollback for EVERY change
        - Label destructive operations with "# WARNING: destructive operation"
        - Use exact kubectl syntax from Kubernetes 1.27

        Save the output using save_stage_output with stage_name="stage_4_remediation".
        """,
        agent=agent,
        expected_output="Markdown with kubectl commands and rollback procedures",
    )


def create_communication_task(params: dict) -> Task:
    """Stage 5: Generate multi-audience communications."""
    agent = AGENT_REGISTRY[5]()
    return Task(
        description=f"""
        Generate incident communications using the render_prompt_template tool.

        Template: stage_5_communication
        Parameters: {params}
        Prior context: Load stage_4_remediation output using load_prior_stage_output

        Generate THREE separate messages:
        1. [TECHNICAL TEAM] — Slack #incidents (error rates, actions, max {params.get('max_words', 150)} words)
        2. [BUSINESS STAKEHOLDERS] — Email (revenue impact, ETA, max {params.get('max_words', 150)} words)
        3. [EXECUTIVE LEADERSHIP] — SMS (bullet points, max {int(params.get('max_words', 150)) // 1.5} words)

        Status is "{params.get('incident_status', 'investigating')}" — do NOT use "resolved".

        Save the output using save_stage_output with stage_name="stage_5_communication".
        """,
        agent=agent,
        expected_output="3 audience-specific incident messages",
    )


def create_postmortem_task(params: dict) -> Task:
    """Stage 6: Generate blameless post-mortem."""
    agent = AGENT_REGISTRY[6]()
    return Task(
        description=f"""
        Generate a blameless post-mortem using the render_prompt_template tool.

        Template: stage_6_postmortem
        Parameters: {params}
        Prior context: Load ALL prior stage outputs using load_prior_stage_output

        The post-mortem MUST include:
        1. Metadata (duration MUST be "{params.get('impact_duration', '28 minutes')}")
        2. Executive Summary
        3. Impact (user-facing, business, duration)
        4. Timeline (table with time, event, detected by)
        5. Root Cause Analysis
        6. Contributing Factors
        7. Action Items — exactly {params.get('action_items_count', 4)} SMART items
        8. Lessons Learned (went well, improve, lucky)
        9. Appendix: Key Metrics

        Blameless mode: use ONLY team names, NEVER individual names.

        Save the output using save_stage_output with stage_name="stage_6_postmortem".
        """,
        agent=agent,
        expected_output="Complete blameless post-mortem in Google SRE style",
    )


# Task factory registry
TASK_REGISTRY = {
    0: create_scenario_task,
    1: create_alert_task,
    2: create_triage_task,
    3: create_rca_task,
    4: create_remediation_task,
    5: create_communication_task,
    6: create_postmortem_task,
}
```

---

### 3.9 `src/pipeline.py`

**Purpose**: Main CrewAI orchestrator — the entry point for running simulations.

**Content Requirements**:

```python
"""
CrewAI Pipeline Orchestrator for the DevOps Incident Simulation Pipeline.

Coordinates the sequential execution of 7 agents, manages context passing,
and produces the final consolidated incident report.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from crewai import Crew, Process

from src.config.settings import PROJECT_ROOT, SimulationDefaults
from src.core.llm import LLMClient
from src.core.renderer import TemplateRenderer
from src.tasks.definitions import TASK_REGISTRY


@dataclass
class StageResult:
    """Result from a single pipeline stage."""
    stage_index: int
    stage_name: str
    output: str
    execution_time_s: float
    token_count: int


@dataclass
class PipelineResult:
    """Complete result from the 7-stage pipeline."""
    stages: list[StageResult] = field(default_factory=list)
    total_time_s: float = 0.0
    total_tokens: int = 0
    consolidated_report: str = ""

    @property
    def stage_count(self) -> int:
        return len(self.stages)


class SREIncidentPipeline:
    """
    CrewAI-based orchestrator for the 7-stage incident simulation.

    Maintains backward compatibility with the original notebook's
    context-passing mechanism while adding CrewAI agent orchestration.
    """

    STAGE_NAMES = [
        "stage_0_scenario",
        "stage_1_alert",
        "stage_2_triage",
        "stage_3_rca",
        "stage_4_remediation",
        "stage_5_communication",
        "stage_6_postmortem",
    ]

    # Token budgets per stage (from original notebook)
    TOKEN_BUDGETS = {
        0: 3000,  # Scenario — needs detail
        1: 1500,  # Alert — JSON only
        2: 1500,  # Triage — concise guide
        3: 3000,  # RCA — evidence artifacts
        4: 1500,  # Remediation — commands only
        5: 1500,  # Communication — 3 short messages
        6: 3000,  # Post-mortem — comprehensive
    }

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        on_stage_complete: Optional[Callable[[StageResult], None]] = None,
    ) -> None:
        self.llm = llm_client or LLMClient()
        self.context: dict[str, str] = {}
        self.on_stage_complete = on_stage_complete

    def run_stage(
        self,
        stage_index: int,
        params: dict[str, Any],
    ) -> StageResult:
        """
        Execute a single pipeline stage.

        1. Render prompt with Jinja2 (params + prior outputs)
        2. Call LLM with SSE streaming
        3. Store output in context for next stage
        4. Return structured result
        """
        stage_name = self.STAGE_NAMES[stage_index]
        start_time = time.time()

        # Build prior outputs context
        prior_outputs = {
            f"output_stage_{i}": self.context.get(f"output_stage_{i}", "")
            for i in range(stage_index)
        }

        # Render prompt
        prompt = TemplateRenderer.render(stage_name, params, prior_outputs)

        # Call LLM
        max_tokens = self.TOKEN_BUDGETS.get(stage_index, 1500)
        response = self.llm.generate(prompt, max_new_tokens=max_tokens)

        # Store in context
        self.context[f"output_stage_{stage_index}"] = response.content

        # Save to disk
        output_dir = PROJECT_ROOT / "outputs"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f"{stage_name}_output.txt"
        output_file.write_text(response.content, encoding="utf-8")

        elapsed = time.time() - start_time

        result = StageResult(
            stage_index=stage_index,
            stage_name=stage_name,
            output=response.content,
            execution_time_s=elapsed,
            token_count=response.tokens_used,
        )

        if self.on_stage_complete:
            self.on_stage_complete(result)

        return result

    def run_full_pipeline(
        self,
        params: dict[str, Any],
    ) -> PipelineResult:
        """
        Execute all 7 stages sequentially.

        Returns a PipelineResult with all stage outputs and metadata.
        """
        start_time = time.time()
        result = PipelineResult()

        for i in range(len(self.STAGE_NAMES)):
            stage_result = self.run_stage(i, params)
            result.stages.append(stage_result)
            result.total_tokens += stage_result.token_count

        result.total_time_s = time.time() - start_time
        result.consolidated_report = self._consolidate_report()

        return result

    def _consolidate_report(self) -> str:
        """Consolidate all stage outputs into a single markdown report."""
        lines = [
            "# SRE Incident Simulation Report",
            "",
            f"## {self.context.get('application_name', 'Unknown')} — Payment Gateway Incident",
            "",
            "---",
            "",
        ]

        for i, stage_name in enumerate(self.STAGE_NAMES):
            output = self.context.get(f"output_stage_{i}", "")
            stage_title = stage_name.split("_", 2)[-1].replace("_", " ").title()

            lines.extend([
                f"## Stage {i}: {stage_title}",
                "",
                output,
                "",
                "---",
                "",
            ])

        report = "\n".join(lines)

        # Save consolidated report
        report_file = PROJECT_ROOT / "incident_simulation_report.md"
        report_file.write_text(report, encoding="utf-8")

        return report

    def get_context(self) -> dict[str, str]:
        """Return the current context dictionary."""
        return self.context.copy()


def run_simulation(
    params: Optional[dict[str, Any]] = None,
    on_stage_complete: Optional[Callable[[StageResult], None]] = None,
) -> PipelineResult:
    """
    Convenience function to run a complete simulation.

    Args:
        params: Scenario parameters (defaults to SimulationDefaults)
        on_stage_complete: Callback fired after each stage completes

    Returns:
        PipelineResult with all outputs and metadata
    """
    if params is None:
        defaults = SimulationDefaults()
        params = defaults.model_dump()
        # hidden_cause must be provided — use default from notebook
        params["hidden_cause"] = (
            "Redis cache penetration attack: attackers exploited rate limiting "
            "bypass vulnerability in payment-gateway-service, sending 50+ requests "
            "per second from distributed IPs, causing Redis OOM and subsequent "
            "payment failures for legitimate users"
        )

    pipeline = SREIncidentPipeline(on_stage_complete=on_stage_complete)
    return pipeline.run_full_pipeline(params)
```

---

### 3.10 `app/main.py`

**Purpose**: Streamlit frontend for interactive incident simulation.

**Content Requirements**:

```python
"""
Streamlit Frontend for the DevOps Incident Simulation Pipeline.

Provides an interactive UI for trainees to:
1. Configure incident parameters
2. Trigger simulations
3. Watch real-time agent execution
4. View generated reports
"""

from __future__ import annotations

import time
from typing import Any

import streamlit as st

from src.config.settings import SimulationDefaults
from src.pipeline import SREIncidentPipeline, StageResult, run_simulation


# Page configuration
st.set_page_config(
    page_title="DevOps Incident Simulator",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .stProgress > div > div > div > div {
        background-color: #00C853;
    }
    .stage-complete {
        color: #00C853;
        font-weight: bold;
    }
    .stage-running {
        color: #FF6F00;
        font-weight: bold;
    }
    .stage-pending {
        color: #9E9E9E;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state() -> None:
    """Initialize Streamlit session state."""
    if "pipeline_result" not in st.session_state:
        st.session_state.pipeline_result = None
    if "is_running" not in st.session_state:
        st.session_state.is_running = False
    if "current_stage" not in st.session_state:
        st.session_state.current_stage = -1
    if "stage_outputs" not in st.session_state:
        st.session_state.stage_outputs = {}


def render_sidebar() -> dict[str, Any]:
    """Render the parameter configuration sidebar."""
    st.sidebar.title("⚙️ Simulation Parameters")

    defaults = SimulationDefaults()

    with st.sidebar.expander("🏢 Application Context", expanded=True):
        application_type = st.text_input("Application Type", defaults.application_type)
        application_name = st.text_input("Application Name", defaults.application_name)
        service_name = st.text_input("Service Name", defaults.service_name)
        tech_stack = st.text_area("Tech Stack", defaults.tech_stack, height=80)

    with st.sidebar.expander("🔥 Incident Configuration"):
        hidden_cause = st.text_area(
            "Hidden Root Cause",
            "Redis cache penetration attack: attackers exploited rate limiting bypass...",
            height=100,
            help="The actual cause that trainees must discover"
        )
        severity_level = st.selectbox("Severity", ["critical", "high", "medium", "low"], index=0)
        incident_trigger = st.text_input("Trigger", defaults.incident_trigger)
        impact_duration = st.text_input("Impact Duration", defaults.impact_duration)

    with st.sidebar.expander("👤 Trainee Profile"):
        engineer_level = st.selectbox("Engineer Level", ["junior", "mid-level", "senior"], index=1)
        teaching_mode = st.selectbox("Teaching Mode", ["socratic", "guided", "direct"], index=0)

    with st.sidebar.expander("📊 Output Configuration"):
        evidence_lines = st.slider("Evidence Lines", 10, 30, int(defaults.evidence_lines))
        action_items_count = st.slider("Action Items", 2, 8, defaults.action_items_count)
        blameless_mode = st.selectbox("Blameless Mode", ["strict", "moderate"], index=0)

    return {
        "application_type": application_type,
        "application_name": application_name,
        "service_name": service_name,
        "tech_stack": tech_stack,
        "orchestration_platform": defaults.orchestration_platform,
        "monitoring_tools": defaults.monitoring_tools,
        "hidden_cause": hidden_cause,
        "severity_level": severity_level,
        "incident_trigger": incident_trigger,
        "impact_duration": impact_duration,
        "engineer_level": engineer_level,
        "teaching_mode": teaching_mode,
        "evidence_lines": str(evidence_lines),
        "action_items_count": action_items_count,
        "blameless_mode": blameless_mode,
        # Remaining defaults
        "business_context": defaults.business_context,
        "alert_count": defaults.alert_count,
        "investigation_scope": defaults.investigation_scope,
        "max_steps": defaults.max_steps,
        "evidence_type": defaults.evidence_type,
        "log_format": defaults.log_format,
        "clue_visibility": defaults.clue_visibility,
        "analysis_depth": defaults.analysis_depth,
        "mitigation_horizon": defaults.mitigation_horizon,
        "risk_tolerance": defaults.risk_tolerance,
        "include_rollback": defaults.include_rollback,
        "code_style": defaults.code_style,
        "audience_type": defaults.audience_type,
        "incident_status": defaults.incident_status,
        "max_words": defaults.max_words,
        "communication_channel": defaults.communication_channel,
        "tone": defaults.tone,
        "postmortem_style": defaults.postmortem_style,
        "include_metrics": defaults.include_metrics,
        "output_format": defaults.output_format,
    }


def render_stage_progress() -> None:
    """Render the 7-stage progress indicator."""
    stages = [
        ("🏗️", "Scenario"),
        ("🚨", "Alert"),
        ("🔍", "Triage"),
        ("📊", "RCA"),
        ("🔧", "Remediation"),
        ("📢", "Communication"),
        ("📝", "Post-mortem"),
    ]

    cols = st.columns(7)
    for i, (icon, name) in enumerate(stages):
        with cols[i]:
            if i < st.session_state.current_stage:
                st.markdown(f"<p class='stage-complete'>{icon} {name}</p>", unsafe_allow_html=True)
            elif i == st.session_state.current_stage:
                st.markdown(f"<p class='stage-running'>{icon} {name}</p>", unsafe_allow_html=True)
            else:
                st.markdown(f"<p class='stage-pending'>{icon} {name}</p>", unsafe_allow_html=True)


def on_stage_complete(result: StageResult) -> None:
    """Callback fired when a stage completes."""
    st.session_state.current_stage = result.stage_index + 1
    st.session_state.stage_outputs[result.stage_name] = result.output


def render_main_content(params: dict[str, Any]) -> None:
    """Render the main content area."""
    st.title("🚨 DevOps Incident Simulation Pipeline")
    st.markdown("**7-Stage CrewAI Multi-Agent System** | Academic Compliance: SPbETU 2026")

    # Progress indicator
    render_stage_progress()

    # Control buttons
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("▶️ Start Simulation", disabled=st.session_state.is_running):
            st.session_state.is_running = True
            st.session_state.current_stage = 0
            st.session_state.stage_outputs = {}

            with st.spinner("Running 7-stage simulation..."):
                result = run_simulation(params, on_stage_complete=on_stage_complete)
                st.session_state.pipeline_result = result

            st.session_state.is_running = False
            st.success(f"✅ Simulation complete in {result.total_time_s:.1f}s")

    with col2:
        if st.button("🔄 Reset", disabled=st.session_state.is_running):
            st.session_state.pipeline_result = None
            st.session_state.current_stage = -1
            st.session_state.stage_outputs = {}
            st.rerun()

    with col3:
        if st.session_state.pipeline_result:
            st.download_button(
                "📥 Download Report",
                st.session_state.pipeline_result.consolidated_report,
                file_name="incident_simulation_report.md",
                mime="text/markdown",
            )

    # Results display
    if st.session_state.pipeline_result:
        render_results()


def render_results() -> None:
    """Render the simulation results."""
    result = st.session_state.pipeline_result

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Time", f"{result.total_time_s:.1f}s")
    col2.metric("Stages", result.stage_count)
    col3.metric("Total Tokens", result.total_tokens)
    col4.metric("Report Size", f"{len(result.consolidated_report):,} chars")

    # Stage tabs
    tabs = st.tabs([f"Stage {i}" for i in range(7)])

    for i, tab in enumerate(tabs):
        with tab:
            if i < len(result.stages):
                stage = result.stages[i]
                st.markdown(f"**{stage.stage_name}** | {stage.execution_time_s:.1f}s | {stage.token_count} tokens")
                st.markdown(stage.output)
            else:
                st.info("Stage not yet executed")


def main() -> None:
    """Main application entry point."""
    init_session_state()
    params = render_sidebar()
    render_main_content(params)


if __name__ == "__main__":
    main()
```

---

### 3.11 `Dockerfile`

**Purpose**: Multi-stage Docker build for Hugging Face Spaces deployment.

**Content Requirements**:

```dockerfile
# Stage 1: Builder
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt


# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Ensure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY src/ ./src/
COPY app/ ./app/
COPY .env.example .env

# Create outputs directory
RUN mkdir -p outputs

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run Streamlit
ENTRYPOINT ["streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

---

### 3.12 `.dockerignore`

```
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.env
.git/
.gitignore
.ipynb_checkpoints/
*.ipynb
outputs/
*.md
!README.md
.vscode/
.idea/
```

---

### 3.13 `requirements.txt`

```
# Core dependencies
crewai>=0.28.0
crewai-tools>=0.2.0
streamlit>=1.28.0
requests>=2.31.0
jinja2>=3.1.2
pydantic>=2.0.0
python-dotenv>=1.0.0

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

---

### 3.14 `tests/conftest.py`

```python
"""Pytest fixtures for the test suite."""

import pytest
from unittest.mock import MagicMock, patch

from src.config.settings import APIConfig, SimulationDefaults


@pytest.fixture
def api_config() -> APIConfig:
    """Return a test API configuration."""
    return APIConfig()


@pytest.fixture
def simulation_params() -> dict:
    """Return default simulation parameters."""
    defaults = SimulationDefaults()
    params = defaults.model_dump()
    params["hidden_cause"] = "Test hidden cause for unit tests"
    return params


@pytest.fixture
def mock_llm_response():
    """Return a mock LLM response."""
    mock = MagicMock()
    mock.content = "Test output"
    mock.tokens_used = 100
    mock.model = "test-model"
    mock.finish_reason = "stop"
    mock.attempt_count = 1
    return mock
```

---

### 3.15 `tests/test_pipeline.py`

```python
"""Tests for the pipeline orchestrator."""

import pytest
from unittest.mock import MagicMock, patch

from src.pipeline import SREIncidentPipeline, StageResult, PipelineResult


class TestSREIncidentPipeline:
    """Test suite for SREIncidentPipeline."""

    def test_stage_names_defined(self):
        """Verify all 7 stage names are defined."""
        pipeline = SREIncidentPipeline()
        assert len(pipeline.STAGE_NAMES) == 7
        assert pipeline.STAGE_NAMES[0] == "stage_0_scenario"
        assert pipeline.STAGE_NAMES[6] == "stage_6_postmortem"

    def test_token_budgets_defined(self):
        """Verify token budgets for all stages."""
        pipeline = SREIncidentPipeline()
        assert len(pipeline.TOKEN_BUDGETS) == 7
        assert pipeline.TOKEN_BUDGETS[0] == 3000  # Scenario
        assert pipeline.TOKEN_BUDGETS[6] == 3000  # Post-mortem

    def test_context_initialization(self):
        """Verify context dict is initialized empty."""
        pipeline = SREIncidentPipeline()
        assert pipeline.context == {}

    @patch("src.pipeline.LLMClient")
    def test_run_stage_stores_context(self, mock_llm_class, simulation_params):
        """Verify stage output is stored in context."""
        mock_llm = MagicMock()
        mock_llm.generate.return_value = MagicMock(
            content="Test output",
            tokens_used=100,
        )
        mock_llm_class.return_value = mock_llm

        pipeline = SREIncidentPipeline(llm_client=mock_llm)
        result = pipeline.run_stage(0, simulation_params)

        assert isinstance(result, StageResult)
        assert result.stage_index == 0
        assert "output_stage_0" in pipeline.context
```

---

### 3.16 `tests/test_tools.py`

```python
"""Tests for validation tools."""

import pytest

from src.tools.validators import AlertmanagerValidator, KubectlValidator, SMARTValidator


class TestAlertmanagerValidator:
    """Test Alertmanager JSON validation."""

    def test_valid_alertmanager_json(self):
        """Valid Alertmanager JSON should pass."""
        valid_json = '''
        {
            "version": "4",
            "groupKey": "{}:{alertname=\\"Test\\"}",
            "status": "firing",
            "receiver": "test-receiver",
            "groupLabels": {"alertname": "Test"},
            "commonLabels": {"namespace": "production"},
            "alerts": [{"labels": {"namespace": "production"}}]
        }
        '''
        is_valid, errors = AlertmanagerValidator.validate(valid_json)
        assert is_valid, f"Errors: {errors}"

    def test_invalid_namespace(self):
        """Wrong namespace should fail."""
        invalid_json = '''
        {
            "version": "4",
            "groupKey": "test",
            "status": "firing",
            "receiver": "test",
            "groupLabels": {},
            "commonLabels": {"namespace": "wrong"},
            "alerts": []
        }
        '''
        is_valid, errors = AlertmanagerValidator.validate(invalid_json)
        assert not is_valid
        assert any("namespace" in e.lower() for e in errors)


class TestKubectlValidator:
    """Test kubectl command validation."""

    def test_valid_kubectl_command(self):
        """Valid kubectl command should pass."""
        is_valid, error = KubectlValidator.validate_command(
            "kubectl get pods --namespace=production"
        )
        assert is_valid, f"Error: {error}"

    def test_missing_namespace(self):
        """Command without namespace should fail."""
        is_valid, error = KubectlValidator.validate_command("kubectl get pods")
        assert not is_valid
        assert "namespace" in error.lower()


class TestSMARTValidator:
    """Test SMART action item validation."""

    def test_valid_smart_item(self):
        """Valid SMART item should pass."""
        item = {
            "id": "PCI-1",
            "description": "Implement circuit breaker for Redis",
            "owner": "Platform Team",
            "priority": "P0",
            "due_date": "2024-06-07",
        }
        is_valid, errors = SMARTValidator.validate_item(item)
        assert is_valid, f"Errors: {errors}"
```

---

### 3.17 `README.md` Structure

The README must include:

1. **Header badges** (Python, CrewAI, Streamlit, HF Spaces, License)
2. **Executive Summary** (2 paragraphs)
3. **Architecture Diagram** (Mermaid.js showing 7 agents)
4. **Agent Registry Table** (7 agents with role, goal, tools)
5. **Quick Start** (local + Docker + HF Spaces)
6. **Configuration Guide** (all 20+ parameters explained)
7. **API Reference** (key classes and methods)
8. **Testing Guide** (how to run pytest)
9. **Deployment Guide** (HF Spaces step-by-step)
10. **Academic Validation** (SPbETU 2026 compliance table)
11. **Troubleshooting** (common issues)
12. **License** (MIT)

---

## 4. Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Create `src/config/settings.py` with Pydantic models
- [ ] Create `src/core/llm.py` with SSE streaming
- [ ] Create `src/core/renderer.py` with Jinja2 loading
- [ ] Create all 7 `.j2` templates in `src/prompts/`

### Phase 2: CrewAI Integration
- [ ] Create `src/tools/validators.py`
- [ ] Create `src/tools/template_tools.py` with CrewAI tool decorators
- [ ] Create `src/agents/definitions.py` with 7 agent factories
- [ ] Create `src/tasks/definitions.py` with 7 task factories
- [ ] Create `src/pipeline.py` with orchestrator

### Phase 3: Frontend
- [ ] Create `app/main.py` with Streamlit UI
- [ ] Add real-time progress tracking
- [ ] Add parameter sidebar
- [ ] Add results dashboard with tabs

### Phase 4: Infrastructure
- [ ] Create `Dockerfile` (multi-stage)
- [ ] Create `.dockerignore`
- [ ] Update `requirements.txt`
- [ ] Update `.gitignore` (add `outputs/`)

### Phase 5: Testing
- [ ] Create `tests/conftest.py`
- [ ] Create `tests/test_pipeline.py`
- [ ] Create `tests/test_tools.py`
- [ ] Run `pytest` and verify all pass

### Phase 6: Documentation
- [ ] Rewrite `README.md` with full architecture docs
- [ ] Verify Mermaid diagram renders correctly
- [ ] Add deployment instructions

### Phase 7: Deployment
- [ ] Test Docker build locally
- [ ] Push to GitHub
- [ ] Create HF Space
- [ ] Configure secrets in HF
- [ ] Verify deployment

---

## 5. Critical Implementation Notes

### 5.1 Context Passing Mechanism
The pipeline MUST maintain the exact context-passing mechanism from the original notebook:
```python
# After stage N completes:
context[f"output_stage_{N}"] = output

# Before stage N+1 renders:
prior_outputs = {f"output_stage_{i}": context.get(f"output_stage_{i}", "") for i in range(N+1)}
```

### 5.2 Token Budgets
Preserve the exact token budgets from the notebook:
- Stages 0, 3, 6: 3000 tokens (detailed outputs)
- Stages 1, 2, 4, 5: 1500 tokens (concise outputs)

### 5.3 Namespace Enforcement
The Alertmanager JSON and kubectl commands MUST use `namespace: production`. This is enforced through:
1. Prompt constraints (repeated 3x in templates)
2. Post-hoc validation in `AlertmanagerValidator`

### 5.4 SSE Streaming
The LLM client MUST use SSE streaming (`stream=True`). Non-streaming requests will hit long-generation timeouts.

### 5.5 Regex Sanitization
All LLM outputs MUST pass through `_strip_reasoning()` to remove `<think>...</think>` tags.

### 5.6 Backward Compatibility
The new pipeline MUST produce output identical in structure to the original notebook. The `incident_simulation_report.md` format must match exactly.

---

## 6. Handoff Instructions

To implement this plan:

1. **Read this document completely** before writing any code
2. **Create files in order**: config → core → prompts → tools → agents → tasks → pipeline → app → tests
3. **Test incrementally**: run `pytest` after each module is complete
4. **Verify backward compatibility**: compare output with original notebook
5. **Do not modify** `devops_dahl.ipynb`, `CASE_STUDY.md`, or `LINKEDIN_POST.md`

---

*Document Version: 1.0*  
*Generated: 2026-08-05*  
*Target: Master's Thesis / Production Deployment*
