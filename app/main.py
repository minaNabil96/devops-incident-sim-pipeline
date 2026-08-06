"""
Streamlit Frontend for the DevOps Incident Simulation Pipeline.

Provides an interactive UI for trainees to:
1. Configure incident parameters
2. Trigger simulations
3. Watch real-time agent execution
4. View generated reports
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from src.config.settings import SimulationDefaults
from src.pipeline import DEFAULT_HIDDEN_CAUSE, StageResult
from src.pipeline import run_simulation

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
    st.session_state.setdefault("pipeline_result", None)
    st.session_state.setdefault("is_running", False)
    st.session_state.setdefault("current_stage", -1)
    st.session_state.setdefault("stage_outputs", {})


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


def render_stage_progress() -> None:
    """Render the 7-stage progress indicator."""
    cols = st.columns(7)
    for i, (_, icon, name) in enumerate(STAGE_ICONS):
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


# ---------------------------------------------------------------------------
# Results rendering
# ---------------------------------------------------------------------------
def render_results() -> None:
    """Render the simulation results dashboard."""
    result = st.session_state.pipeline_result
    if result is None:
        return

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Time", f"{result.total_time_s:.1f}s")
    col2.metric("Stages", result.stage_count)
    col3.metric("Total Tokens", result.total_tokens)
    col4.metric("Report Size", f"{len(result.consolidated_report):,} chars")

    st.markdown("---")

    # Report preview in expandable
    with st.expander("📄 Consolidated Report — Full Markdown", expanded=False):
        st.download_button(
            "⬇️ Download Report (.md)",
            result.consolidated_report,
            file_name="incident_simulation_report.md",
            mime="text/markdown",
        )
        st.text(result.consolidated_report)

    # Stage tabs
    if result.stages:
        tabs = st.tabs([f"{icon} {name}" for _, icon, name in STAGE_ICONS])
        for i, tab in enumerate(tabs):
            with tab:
                if i < len(result.stages):
                    stage = result.stages[i]
                    st.caption(
                        f"{stage.stage_name} · {stage.execution_time_s:.1f}s · "
                        f"{stage.token_count} tokens"
                    )
                    st.markdown(stage.output)
                else:
                    st.info("Stage not yet executed.")


# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
def render_main_content(params: dict[str, Any]) -> None:
    """Render the main content area."""
    st.title("🚨 DevOps Incident Simulation Pipeline")
    st.caption("**7-Stage CrewAI Multi-Agent System** | Academic Compliance: SPbETU 2026")

    render_stage_progress()

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("▶️ Start Simulation", disabled=st.session_state.is_running, use_container_width=True):
            st.session_state.is_running = True
            st.session_state.current_stage = 0
            st.session_state.stage_outputs = {}

            try:
                with st.spinner("Running 7-stage simulation..."):
                    result = run_simulation(
                        params, on_stage_complete=on_stage_complete
                    )
                    st.session_state.pipeline_result = result
                st.success(f"✅ Simulation complete in {result.total_time_s:.1f}s")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Simulation failed: {exc}")
            finally:
                st.session_state.is_running = False

    with col2:
        if st.button("🔄 Reset", use_container_width=True):
            st.session_state.pipeline_result = None
            st.session_state.current_stage = -1
            st.session_state.stage_outputs = {}
            st.rerun()

    with col3:
        if st.session_state.pipeline_result:
            st.caption("Ready to download report below.")

    st.markdown("---")
    render_results()


def main() -> None:
    """Main application entry point."""
    init_session_state()
    params = render_sidebar()
    render_main_content(params)


if __name__ == "__main__":
    main()