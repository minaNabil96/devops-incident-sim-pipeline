"""
Streamlit Frontend for the DevOps Incident Simulation Pipeline.

Provides an interactive UI for trainees to:
1. Configure incident parameters
2. Trigger simulations
3. Watch real-time agent execution
4. View generated reports
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is importable regardless of launch directory
# (Streamlit / standalone script runs insert their own dir into sys.path).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from datetime import datetime
from typing import Any

import streamlit as st

from src.config.settings import SimulationDefaults
from src.pipeline import (
    DEFAULT_HIDDEN_CAUSE,
    PipelineResult,
    StageResult,
    SREIncidentPipeline,
)

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="DevOps Incident Simulator",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom styling
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
        .stage-complete { color: #00C853; font-weight: bold; }
        .stage-running  { color: #FF6F00; font-weight: bold; }
        .stage-pending  { color: #9E9E9E; }
        .metric-card    { border: 1px solid #31333F; border-radius: 8px;
                          padding: 12px; background: #0E1117; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def init_session_state() -> None:
    """Initialize Streamlit session state."""
    st.session_state.setdefault("pipeline", None)
    st.session_state.setdefault("pipeline_result", None)  # finalized PipelineResult
    st.session_state.setdefault("is_running", False)
    st.session_state.setdefault("current_stage", -1)
    st.session_state.setdefault("stage_outputs", {})
    st.session_state.setdefault("stage_results", [])  # ordered StageResult list
    st.session_state.setdefault("start_ts", None)
    st.session_state.setdefault("run_params", None)
    st.session_state.setdefault("run_params_ready", False)


# ---------------------------------------------------------------------------
# Sidebar: parameter configuration
# ---------------------------------------------------------------------------
def render_sidebar() -> dict[str, Any]:
    """Render the parameter configuration sidebar."""
    st.sidebar.title("⚙️ Simulation Parameters")
    d = SimulationDefaults()

    with st.sidebar.expander("🏢 Application Context", expanded=True):
        application_type = st.text_input("Application Type", d.application_type)
        application_name = st.text_input("Application Name", d.application_name)
        service_name = st.text_input("Service Name", d.service_name)
        tech_stack = st.text_area("Tech Stack", d.tech_stack, height=80)

    with st.sidebar.expander("🔥 Incident Configuration"):
        hidden_cause = st.text_area(
            "Hidden Root Cause",
            DEFAULT_HIDDEN_CAUSE,
            height=110,
            help="The actual cause that trainees must discover",
        )
        severity_level = st.selectbox(
            "Severity", ["critical", "high", "medium", "low"], index=0
        )
        incident_trigger = st.text_input("Trigger", d.incident_trigger)
        impact_duration = st.text_input("Impact Duration", d.impact_duration)

    with st.sidebar.expander("👤 Trainee Profile"):
        engineer_level = st.selectbox(
            "Engineer Level", ["junior", "mid-level", "senior"], index=1
        )
        teaching_mode = st.selectbox(
            "Teaching Mode", ["socratic", "guided", "direct"], index=0
        )

    with st.sidebar.expander("📊 Output Configuration"):
        evidence_lines = st.slider("Evidence Lines", 10, 30, int(d.evidence_lines))
        action_items_count = st.slider("Action Items", 2, 8, d.action_items_count)
        blameless_mode = st.selectbox(
            "Blameless Mode", ["strict", "moderate"], index=0
        )

    return {
        **d.model_dump(),
        **{
            "application_type": application_type,
            "application_name": application_name,
            "service_name": service_name,
            "tech_stack": tech_stack,
            "hidden_cause": hidden_cause,
            "severity_level": severity_level,
            "incident_trigger": incident_trigger,
            "impact_duration": impact_duration,
            "engineer_level": engineer_level,
            "teaching_mode": teaching_mode,
            "evidence_lines": str(evidence_lines),
            "action_items_count": action_items_count,
            "blameless_mode": blameless_mode,
        },
    }


# ---------------------------------------------------------------------------
# Progress + execution callback
# ---------------------------------------------------------------------------
STAGE_ICONS = [
    ("Stage 0", "🏗️", "Scenario"),
    ("Stage 1", "🚨", "Alert"),
    ("Stage 2", "🔍", "Triage"),
    ("Stage 3", "📊", "RCA"),
    ("Stage 4", "🔧", "Remediation"),
    ("Stage 5", "📢", "Communication"),
    ("Stage 6", "📝", "Post-mortem"),
]

STAGE_COUNT = len(STAGE_ICONS)


def render_stage_progress() -> None:
    """Render the 7-stage progress indicator (incl. live timing)."""
    cols = st.columns(STAGE_COUNT)
    for i, (_, icon, name) in enumerate(STAGE_ICONS):
        with cols[i]:
            status = ""
            done = i < st.session_state.current_stage
            running = i == st.session_state.current_stage
            if done:
                # show per-stage duration if available
                sr = _stage_result(i)
                label = f"{_duration_seconds(sr)}"
                st.markdown(
                    f"<p class='stage-complete'>{icon}{name}<br>"
                    f"<small>&#9200; {label}</small></p>",
                    unsafe_allow_html=True,
                )
            elif running:
                st.markdown(
                    f"<p class='stage-running'>{icon} {name}<br>"
                    f"<small>&#9203; running…</small></p>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<p class='stage-pending'>{icon} {name}</p>",
                    unsafe_allow_html=True,
                )


def _duration_seconds(sr: StageResult | None) -> str:
    if sr is None:
        return "--"
    return f"{sr.execution_time_s:.0f}s"


def _stage_result(i: int) -> StageResult | None:
    results = st.session_state.stage_results
    for sr in results:
        if sr.stage_index == i:
            return sr
    return None


def _elapsed() -> str:
    if not st.session_state.start_ts:
        return "0s"
    return f"{(datetime.now() - st.session_state.start_ts).total_seconds():.0f}s"


@st.cache_data(show_spinner=False)
def _render_pdf(markdown: str) -> bytes:
    """Render the consolidated report to PDF bytes (cached by content)."""
    from src.core.pdf import markdown_to_pdf

    return markdown_to_pdf(markdown)


def start_run(params: dict[str, Any]) -> None:
    """Kick off a phase-by-phase simulation run."""
    st.session_state.pipeline = SREIncidentPipeline()
    st.session_state.stage_results = []
    st.session_state.current_stage = 0
    st.session_state.is_running = True
    st.session_state.start_ts = datetime.now()
    st.session_state.run_params = params
    st.session_state.run_params_ready = True


def advance_pipeline() -> None:
    """
    Execute exactly one stage per script rerun, then rerun so the browser
    receives the accumulated output before the next stage begins.
    """
    if not st.session_state.get("run_params_ready"):
        return
    pipe = st.session_state.pipeline
    idx = st.session_state.current_stage

    # Nothing left to run -> finalize
    if idx >= STAGE_COUNT:
        _finalize_and_rerun(pipe)
        return

    params = st.session_state.run_params
    with st.spinner(f"Running {STAGE_ICONS[idx][2]} stage…"):
        stage_result = pipe.run_stage(idx, params)

    st.session_state.stage_results.append(stage_result)
    st.session_state.current_stage = idx + 1
    st.session_state.is_running = idx + 1 < STAGE_COUNT
    st.rerun()


def _finalize_and_rerun(pipe: SREIncidentPipeline) -> None:
    """Consolidate the report, store PipelineResult, and stop the runner."""
    report = pipe._consolidate_report()  # noqa: SLF001 - internal helper
    results = st.session_state.stage_results
    total_tokens = sum(sr.token_count for sr in results)
    total_time = 0.0
    if st.session_state.start_ts:
        total_time = (datetime.now() - st.session_state.start_ts).total_seconds()

    pr = PipelineResult(
        stages=results,
        total_time_s=total_time,
        total_tokens=total_tokens,
        consolidated_report=report,
    )
    st.session_state.pipeline_result = pr
    st.session_state.run_params_ready = False
    st.session_state.is_running = False
    st.session_state.current_stage = STAGE_COUNT
    st.rerun()


# ---------------------------------------------------------------------------
# Results rendering
# ---------------------------------------------------------------------------
def render_results() -> None:
    """Render the simulation results dashboard (incremental, phase by phase)."""
    result = st.session_state.pipeline_result
    results = st.session_state.stage_results

    # Live metrics while running
    total_tokens = sum(sr.token_count for sr in results)
    done = len(results)
    mcol1, mcol2, mcol3 = st.columns(3)
    mcol1.metric("Elapsed", _elapsed())
    mcol2.metric("Stages Completed", f"{done}/{STAGE_COUNT}")
    mcol3.metric("Tokens Used", total_tokens)

    st.markdown("---")

    # Phase-by-phase stage outputs (appear as each stage completes)
    if results:
        for sr in results:
            icon = STAGE_ICONS[sr.stage_index][1]
            short = sr.stage_name.replace("stage_", "").replace("_", " ").title()
            with st.expander(
                f"{icon} {short} — {_duration_seconds(sr)} · {sr.token_count} tokens",
                expanded=sr.stage_index == len(results) - 1,
            ):
                st.markdown(sr.output)

    # Final consolidated report + export once finished
    if result is not None and not st.session_state.is_running:
        st.markdown("---")
        st.subheader("📄 Consolidated Report")
        md_text = result.consolidated_report
        pdf_bytes = _render_pdf(md_text)

        with st.expander("Report Export", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    "⬇️ Download Report (.md)",
                    md_text,
                    file_name="incident_simulation_report.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            with c2:
                st.download_button(
                    "⬇️ Download Report (.pdf)",
                    pdf_bytes,
                    file_name="incident_simulation_report.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    help="Export the consolidated report as a printable PDF.",
                )
        with st.expander("Full Markdown Report", expanded=False):
            st.text(md_text)


def render_main_content(params: dict[str, Any]) -> None:
    """Render the main content area (phase-by-stage streaming runner)."""
    st.title("🚨 DevOps Incident Simulation Pipeline")
    st.caption("**7-Stage Multi-Agent System** | Academic Compliance: SPbETU 2026")

    render_stage_progress()

    if st.session_state.is_running:
        st.info(
            f"⏳ Simulation in progress — stages appear below as they complete. "
            f"Elapsed: {_elapsed()}"
        )
    else:
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("▶️ Start Simulation", use_container_width=True):
                start_run(params)
                st.rerun()
        with col2:
            if st.button("🔄 Reset", use_container_width=True):
                st.session_state.pipeline_result = None
                st.session_state.stage_results = []
                st.session_state.current_stage = -1
                st.session_state.is_running = False
                st.session_state.run_params_ready = False
                st.rerun()
        with col3:
            if st.session_state.pipeline_result:
                st.caption("✅ Completed — report available below.")

    st.markdown("---")
    render_results()


def main() -> None:
    """Main application entry point."""
    init_session_state()

    params = render_sidebar()

    # Auto-advance one stage per rerun while a run is active (or pending
    # finalization).  AdvanceP handles finalization and clears run_params_ready.
    st.session_state.setdefault("run_params_ready", False)
    if st.session_state.run_params_ready:
        render_main_content(params)
        advance_pipeline()
        return

    render_main_content(params)


if __name__ == "__main__":
    main()