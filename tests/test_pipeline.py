"""Tests for the pipeline orchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.pipeline import SREIncidentPipeline, StageResult


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

    def test_run_stage_stores_context(self, simulation_params):
        """Verify stage output is stored in context and returns a StageResult."""
        mock_llm = MagicMock()
        mock_llm.generate.return_value = MagicMock(
            content="Test output",
            tokens_used=100,
        )

        pipeline = SREIncidentPipeline(llm_client=mock_llm)
        result = pipeline.run_stage(0, simulation_params)

        assert isinstance(result, StageResult)
        assert result.stage_index == 0
        assert result.stage_name == "stage_0_scenario"
        assert "output_stage_0" in pipeline.context
        assert pipeline.context["output_stage_0"] == "Test output"

    def test_run_full_pipeline_produces_consolidated_report(self, simulation_params):
        """Verify a full pipeline run produces a consolidated report."""
        mock_llm = MagicMock()
        mock_llm.generate.return_value = MagicMock(
            content="Stage output content",
            tokens_used=42,
        )

        pipeline = SREIncidentPipeline(llm_client=mock_llm)
        result = pipeline.run_full_pipeline(simulation_params)

        assert result.stage_count == 7
        assert result.total_tokens == 7 * 42
        assert result.total_time_s > 0
        assert "# SRE Incident Simulation Report" in result.consolidated_report
        assert "Stage 0" in result.consolidated_report
        assert "Stage 6" in result.consolidated_report

    def test_on_stage_complete_callback(self, simulation_params):
        """Verify the completion callback fires per stage."""
        mock_llm = MagicMock()
        mock_llm.generate.return_value = MagicMock(
            content="x", tokens_used=1
        )

        fired: list[StageResult] = []
        pipeline = SREIncidentPipeline(
            llm_client=mock_llm,
            on_stage_complete=lambda r: fired.append(r),
        )
        pipeline.run_full_pipeline(simulation_params)

        assert len(fired) == 7
        assert [r.stage_index for r in fired] == list(range(7))

    def test_build_crew(self, simulation_params):
        """Verify a CrewAI Crew can be assembled from agent/task registries."""
        pipeline = SREIncidentPipeline()
        crew = pipeline.build_crew(simulation_params)
        assert crew is not None
        assert len(crew.agents) == 7
        assert len(crew.tasks) == 7