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
        # Budgets are scaled up for Gemini 3.x reasoning models to avoid
        # premature truncation of thesis-format stage outputs.
        assert pipeline.TOKEN_BUDGETS[0] >= 3000  # Scenario
        assert pipeline.TOKEN_BUDGETS[6] >= 6000  # Post-mortem

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


class TestRevealGuard:
    """Tests for the hidden-cause reveal-guard (stages 0-2)."""

    def test_detect_reveal_classification_terms(self):
        """Classification vocabulary in stage 0-2 output is flagged."""
        pipeline = SREIncidentPipeline()
        assert pipeline._detect_reveal(
            "This strongly suggests a coordinated, automated attack", ""
        ) is not None
        assert pipeline._detect_reveal("malicious traffic pattern detected", "") is not None
        assert pipeline._detect_reveal("The rate limiter was bypassed by an exploit", "") is not None

    def test_detect_reveal_clean_observations_pass(self):
        """Raw observational content is not flagged."""
        pipeline = SREIncidentPipeline()
        clean = (
            "Error rate increased from 0.2% to 34%. P95 latency rose to 7.1s. "
            "Redis memory usage spiked from 430MB to 950MB with active key "
            "evictions. Request volume rose from 1,200 to 4,300 req/min."
        )
        assert pipeline._detect_reveal(clean, "Redis cache penetration attack") is None

    def test_detect_reveal_hidden_cause_fragment(self):
        """Distinctive hidden-cause phrases are flagged even without buzzwords."""
        pipeline = SREIncidentPipeline()
        hidden = (
            "Redis cache penetration attack: attackers exploited rate limiting "
            "bypass vulnerability in payment-gateway-service"
        )
        leak = "Telemetry shows a rate limiting bypass vulnerability in the path"
        assert pipeline._detect_reveal(leak, hidden) is not None

    def test_run_stage_regenerates_on_reveal(self, simulation_params):
        """A leaking stage 0 output triggers one regeneration with the clean result kept."""
        mock_llm = MagicMock()
        responses = [
            MagicMock(content="Anomalies suggest a coordinated attack on the gateway", tokens_used=10),
            MagicMock(content="Error rate rose to 34%. Redis memory at 950MB.", tokens_used=10),
        ]
        mock_llm.generate.side_effect = responses

        pipeline = SREIncidentPipeline(llm_client=mock_llm)
        result = pipeline.run_stage(0, simulation_params)

        assert mock_llm.generate.call_count == 2
        assert "attack" not in result.output.lower()
        assert pipeline.context["output_stage_0"] == result.output

    def test_run_stage_no_regeneration_when_clean(self, simulation_params):
        """Clean stage output does not trigger the guard (single LLM call)."""
        mock_llm = MagicMock()
        mock_llm.generate.return_value = MagicMock(
            content="Error rate 34%, P95 7.1s, Redis evictions active.", tokens_used=10
        )

        pipeline = SREIncidentPipeline(llm_client=mock_llm)
        pipeline.run_stage(2, simulation_params)

        assert mock_llm.generate.call_count == 1

    def test_guard_skipped_for_late_stages(self, simulation_params):
        """Stages 3-6 may reference the cause (RCA/post-mortem) — no guard."""
        mock_llm = MagicMock()
        mock_llm.generate.return_value = MagicMock(
            content="Root cause: attackers exploited a rate limiting bypass", tokens_used=10
        )

        pipeline = SREIncidentPipeline(llm_client=mock_llm)
        result = pipeline.run_stage(3, simulation_params)

        assert mock_llm.generate.call_count == 1
        assert "attackers" in result.output.lower()