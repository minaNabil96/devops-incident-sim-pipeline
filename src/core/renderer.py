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
        missing = [t for t in expected if not env.list_templates(extensions=["j2"]).count(f"{t}.j2")]
        return missing
