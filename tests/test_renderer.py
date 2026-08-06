"""Tests for the LLM client and template renderer."""

from __future__ import annotations

from unittest.mock import patch

from src.core.renderer import TemplateRenderer


class TestTemplateRenderer:
    """Test the Jinja2 template renderer."""

    def test_all_templates_present(self):
        """All 7 templates must exist on disk."""
        missing = TemplateRenderer.validate_templates()
        assert missing == [], f"Missing templates: {missing}"

    def test_render_stage_0(self, simulation_params):
        """Stage 0 renders with scenario parameters."""
        output = TemplateRenderer.render("stage_0_scenario", simulation_params, {})
        assert "Scenario Architect" in output
        assert simulation_params["application_name"] in output
        assert simulation_params["hidden_cause"] in output

    def test_render_stage_1_includes_context(self, simulation_params):
        """Stage 1 renders with prior stage output injected."""
        prior = {"output_stage_0": "# SecureBank Pro Scenario"}
        output = TemplateRenderer.render("stage_1_alert", simulation_params, prior)
        assert "# SecureBank Pro Scenario" in output
        assert "Alertmanager" in output

    def test_render_missing_template(self):
        """Missing template raises TemplateNotFound."""
        import pytest
        from jinja2 import TemplateNotFound

        with pytest.raises(TemplateNotFound):
            TemplateRenderer.render("does_not_exist", {}, {})

    @patch("src.core.llm.re.sub")
    def test_strip_reasoning(self, mock_sub):
        """The reasoning sanitizer is applied to LLM output."""
        from src.core.llm import LLMClient

        LLMClient._strip_reasoning("<think>internal</think>visible")
        mock_sub.assert_called_once()
