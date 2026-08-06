"""
CrewAI Task definitions for the DevOps Incident Simulation Pipeline.

Each task corresponds to one stage and defines the expected output,
context dependencies, and validation criteria.
"""

from __future__ import annotations

from typing import Any, Callable

from crewai import Task

from src.agents.definitions import AGENT_REGISTRY


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
    max_words = _params_i(params, "max_words", 150)
    return Task(
        description=f"""
            Generate incident communications using the render_prompt_template tool.

            Template: stage_5_communication
            Parameters: {params}
            Prior context: Load stage_4_remediation output using load_prior_stage_output

            Generate THREE separate messages:
            1. [TECHNICAL TEAM] — Slack #incidents (error rates, actions, max {max_words} words)
            2. [BUSINESS STAKEHOLDERS] — Email (revenue impact, ETA, max {max_words} words)
            3. [EXECUTIVE LEADERSHIP] — SMS (bullet points, max {max_words // 1.5} words)

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


def _params_i(params: dict, key: str, default: int) -> int:
    """Fetch an integer parameter with a safe fallback."""
    raw = params.get(key, default)
    if isinstance(raw, int):
        return raw
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


# Task factory registry
TASK_REGISTRY: dict[int, Callable[[dict], Task]] = {
    0: create_scenario_task,
    1: create_alert_task,
    2: create_triage_task,
    3: create_rca_task,
    4: create_remediation_task,
    5: create_communication_task,
    6: create_postmortem_task,
}

__all__ = [
    "create_scenario_task",
    "create_alert_task",
    "create_triage_task",
    "create_rca_task",
    "create_remediation_task",
    "create_communication_task",
    "create_postmortem_task",
    "TASK_REGISTRY",
]