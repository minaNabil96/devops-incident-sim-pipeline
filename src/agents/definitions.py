"""
CrewAI Agent definitions for the DevOps Incident Simulation Pipeline.

Each agent corresponds to one stage of the incident lifecycle and has
a specific role, goal, backstory, and toolset.
"""

from __future__ import annotations

from typing import Callable

from crewai import Agent

from src.tools.template_tools import (
    load_prior_stage_output,
    render_prompt_template,
    save_stage_output,
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


# Agent factory registry for pipeline orchestration
AGENT_REGISTRY: dict[int, Callable[[], Agent]] = {
    0: create_scenario_architect,
    1: create_alert_generator,
    2: create_sre_mentor,
    3: create_rca_analyst,
    4: create_remediation_engineer,
    5: create_incident_commander,
    6: create_postmortem_writer,
}

__all__ = [
    "create_scenario_architect",
    "create_alert_generator",
    "create_sre_mentor",
    "create_rca_analyst",
    "create_remediation_engineer",
    "create_incident_commander",
    "create_postmortem_writer",
    "AGENT_REGISTRY",
]
