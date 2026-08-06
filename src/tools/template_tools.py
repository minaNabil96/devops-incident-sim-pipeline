"""
CrewAI tool wrappers for template and file operations.

These tools are exposed to CrewAI agents for dynamic prompt generation
and output persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crewai.tools import tool

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


# Convenience re-export of the project root for external tooling
__all__ = [
    "render_prompt_template",
    "save_stage_output",
    "load_prior_stage_output",
]
