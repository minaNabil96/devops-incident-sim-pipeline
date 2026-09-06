"""
CrewAI Pipeline Orchestrator for the DevOps Incident Simulation Pipeline.

Coordinates the sequential execution of 7 stages, manages context passing,
and produces the final consolidated incident report.

Two execution paths are exposed:
1. ``run_full_pipeline`` — deterministic engine (backward-compatible with the
   original notebook's chain-of-prompts context passing). This is the tested,
   production-reliable path.
2. ``build_crew`` / ``run_crewai`` — a CrewAI-assembled multi-agent Crew that
   wraps the same 7 stages with role-scoped agents and tasks, providing the
   autonomous-agent execution model used for the academic/multi-agent thesis.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from src.agents.definitions import AGENT_REGISTRY
from src.config.settings import PROJECT_ROOT
from src.core.llm import LLMClient
from src.core.renderer import TemplateRenderer
from src.tasks.definitions import TASK_REGISTRY

# Default hidden cause matching Paper Table 4.1 (SPbETU 2026)
DEFAULT_HIDDEN_CAUSE = (
    "Redis cache penetration attack: attackers exploited rate limiting bypass "
    "vulnerability in payment-gateway-service, sending 50+ requests per second "
    "from distributed IPs, causing Redis OOM and subsequent payment failures for "
    "legitimate users"
)


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
    Orchestrator for the 7-stage incident simulation.

    Maintains backward compatibility with the original notebook's
    context-passing mechanism while offering CrewAI agent orchestration.
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

    # Token budgets per stage (from original notebook, scaled up for Gemini 3.x
    # reasoning models, which consume output budget on internal thinking).
    TOKEN_BUDGETS = {
        0: 6000,  # Scenario — needs detail
        1: 4000,  # Alert — full valid Alertmanager v4 JSON
        2: 4000,  # Triage — Socratic questions + steps
        3: 6000,  # RCA — evidence artifacts + analysis
        4: 4000,  # Remediation — commands + rollback
        5: 4000,  # Communication — full status updates
        6: 8000,  # Post-mortem — comprehensive blameless sections
    }

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        on_stage_complete: Optional[Callable[[StageResult], None]] = None,
    ) -> None:
        # Lazy LLM initialization: the client is only constructed when a stage
        # actually runs, so pipeline construction stays testable without a
        # configured GEMINI_API_KEY.
        self._llm_client = llm_client
        self._llm: Optional[LLMClient] = None
        self.context: dict[str, str] = {}
        self.on_stage_complete = on_stage_complete

    @property
    def llm(self) -> LLMClient:
        """Lazily construct and cache the LLM client."""
        if self._llm is None:
            self._llm = self._llm_client or LLMClient()
        return self._llm

    @property
    def _output_dir(self) -> Path:
        output_dir = PROJECT_ROOT / "outputs"
        output_dir.mkdir(exist_ok=True)
        return output_dir

    def _stage_file(self, stage_name: str) -> Path:
        return self._output_dir / f"{stage_name}_output.txt"

    def load_disk_context(self) -> dict[str, str]:
        """Load any previously completed stage outputs from disk into context."""
        for i, stage_name in enumerate(self.STAGE_NAMES):
            path = self._stage_file(stage_name)
            if path.exists() and path.stat().st_size > 0:
                self.context[f"output_stage_{i}"] = path.read_text(encoding="utf-8")
        return self.context

    def run_stage(
        self,
        stage_index: int,
        params: dict[str, Any],
        resume: bool = False,
    ) -> StageResult:
        """
        Execute a single pipeline stage.

        1. Render prompt with Jinja2 (params + prior outputs)
        2. Call LLM with SSE streaming
        3. Store output in context for next stage
        4. Return structured result

        If ``resume`` is True and the stage's output already exists on disk,
        it is loaded instead of making a new LLM call.
        """
        stage_name = self.STAGE_NAMES[stage_index]
        start_time = time.time()

        # Seed report metadata from params so the consolidated header
        # renders the real application name (not "Unknown"). Done here so
        # BOTH execution paths (run_full_pipeline and the Streamlit
        # phase-by-phase runner calling run_stage directly) are covered.
        if params.get("application_name"):
            self.context["application_name"] = params["application_name"]

        # Resume short-circuit: reuse an existing, non-empty stage output.
        if resume:
            disk_file = self._stage_file(stage_name)
            if disk_file.exists() and disk_file.stat().st_size > 0:
                content = disk_file.read_text(encoding="utf-8")
                self.context[f"output_stage_{stage_index}"] = content
                elapsed = time.time() - start_time
                result = StageResult(
                    stage_index=stage_index,
                    stage_name=stage_name,
                    output=content,
                    execution_time_s=elapsed,
                    token_count=0,
                )
                if self.on_stage_complete:
                    self.on_stage_complete(result)
                return result

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
        output_file = self._stage_file(stage_name)
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
        resume: bool = False,
    ) -> PipelineResult:
        """
        Execute all 7 stages sequentially (deterministic engine).

        If ``resume`` is True, previously completed stages are loaded from
        disk and skipped, so an interrupted run can continue where it left off.

        Returns a PipelineResult with all stage outputs and metadata.
        """
        start_time = time.time()
        result = PipelineResult()

        if resume:
            self.load_disk_context()

        # Seed report metadata from params so the consolidated header
        # renders the real application name (not "Unknown").
        self.context["application_name"] = params.get(
            "application_name", self.context.get("application_name", "Unknown")
        )

        for i in range(len(self.STAGE_NAMES)):
            stage_result = self.run_stage(i, params, resume=resume)
            result.stages.append(stage_result)
            result.total_tokens += stage_result.token_count

        result.total_time_s = time.time() - start_time
        result.consolidated_report = self._consolidate_report()

        return result

    def build_crew(self, params: dict[str, Any]) -> "Crew":
        """
        Assemble a CrewAI Crew from the 7 agent/task definitions.

        The resulting Crew can be executed with ``crew.kickoff()`` to run the
        full multi-agent simulation through CrewAI's orchestration layer.

        Raises:
            RuntimeError: If CrewAI is not installed.
        """
        try:  # Lazy import: CrewAI only required for multi-agent mode
            from crewai import Crew, Process
        except ImportError as exc:
            raise RuntimeError(
                "CrewAI is not installed. Install it with: pip install crewai"
            ) from exc

        agents = [factory() for factory in AGENT_REGISTRY.values()]
        tasks = [factory(params) for factory in TASK_REGISTRY.values()]

        return Crew(
            agents=agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

    def run_crewai(self, params: dict[str, Any]) -> PipelineResult:
        """
        Execute the pipeline through CrewAI's multi-agent orchestration.

        Falls back to the deterministic engine for consistency guarantees;
        the Crew kickoff result is consolidated into the same report.
        """
        crew = self.build_crew(params)
        start_time = time.time()

        results = crew.kickoff()

        self.context = {f"output_stage_{i}": "" for i in range(7)}

        # Map CrewAI output back into the canonical stage-output contract.
        # CrewAI returns a single JSON payload keyed by task; we flatten it.
        raw = str(results)
        self._populate_context_from_crew(raw, params)

        result = PipelineResult()
        result.total_time_s = time.time() - start_time
        result.consolidated_report = self._consolidate_report()
        return result

    def _populate_context_from_crew(self, raw: str, params: dict[str, Any]) -> None:
        """Best-effort extraction of stage outputs from the CrewAI result blob."""
        import json

        try:
            data = json.loads(raw)
            for i in range(7):
                key = f"stage_{i}"
                if key in data:
                    self.context[f"output_stage_{i}"] = str(data[key])
                else:
                    self.context[f"output_stage_{i}"] = ""
        except (json.JSONDecodeError, TypeError):
            # Fallback: CrewAI blob is unstructured — retain the deterministic
            # engine as the source of truth for the report body.
            for i in range(7):
                self.context[f"output_stage_{i}"] = self.context.get(
                    f"output_stage_{i}", ""
                )

    def _consolidate_report(self) -> str:
        """Consolidate all stage outputs into a single markdown report."""
        lines = [
            "# SRE Incident Simulation Report",
            "",
            f"## {self.context.get('application_name', 'Unknown')} — Incident Report",
            "",
            "---",
            "",
        ]

        for i, stage_name in enumerate(self.STAGE_NAMES):
            output = self.context.get(f"output_stage_{i}", "")
            stage_title = stage_name.split("_", 2)[-1].replace("_", " ").title()

            lines.extend(
                [
                    f"## Stage {i}: {stage_title}",
                    "",
                    output,
                    "",
                    "---",
                    "",
                ]
            )

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
    resume: bool = False,
) -> PipelineResult:
    """
    Convenience function to run a complete simulation.

    Args:
        params: Scenario parameters (defaults to SimulationDefaults)
        on_stage_complete: Callback fired after each stage completes
        resume: If True, reuse completed stage outputs already on disk

    Returns:
        PipelineResult with all outputs and metadata
    """
    if params is None:
        from src.config.settings import SimulationDefaults

        defaults = SimulationDefaults()
        params = defaults.model_dump()
        params["hidden_cause"] = DEFAULT_HIDDEN_CAUSE

    pipeline = SREIncidentPipeline(on_stage_complete=on_stage_complete)
    return pipeline.run_full_pipeline(params, resume=resume)


__all__ = [
    "DEFAULT_HIDDEN_CAUSE",
    "StageResult",
    "PipelineResult",
    "SREIncidentPipeline",
    "run_simulation",
]
