"""
Model comparison harness.

Runs the exact thesis SecureBank scenario through a given model,
saving each stage output + consolidated report into outputs/<model>/.

Usage:
    python tools/compare_models.py MODEL_ID [MODEL_ID ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config.settings import APIConfig, SimulationDefaults
from src.core.llm import LLMClient
from src.pipeline import DEFAULT_HIDDEN_CAUSE, SREIncidentPipeline


def slug(model_id: str) -> str:
    return model_id.replace("/", "--").replace("@", "_").replace(".", "-")


def run_for(model_id: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    params = SimulationDefaults().model_dump()
    params["hidden_cause"] = DEFAULT_HIDDEN_CAUSE
    params["application_name"] = "SecureBank Pro"
    params["service_name"] = "payment-gateway-service"
    params["engineer_level"] = "mid-level"
    params["teaching_mode"] = "socratic"
    params["evidence_type"] = "logs + metrics"
    params["clue_visibility"] = "subtle"
    params["analysis_depth"] = "deep"
    params["mitigation_horizon"] = "immediate"
    params["risk_tolerance"] = "low"
    params["include_rollback"] = "yes"
    params["audience_type"] = "technical"
    params["incident_status"] = "investigating"
    params["impact_duration"] = "28 minutes"
    params["postmortem_style"] = "Google SRE"
    params["action_items_count"] = 4
    params["blameless_mode"] = "strict"

    config = APIConfig(model=model_id)
    client = LLMClient(config)
    pipeline = SREIncidentPipeline(llm_client=client)

    result = pipeline.run_full_pipeline(params)

    # Save stage outputs + consolidated report for this model
    for stage in result.stages:
        (out_dir / f"stage_{stage.stage_index}.txt").write_text(
            stage.output, encoding="utf-8"
        )
    (out_dir / "report.md").write_text(
        result.consolidated_report, encoding="utf-8"
    )

    print(f"\n=== {model_id} COMPLETE ===")
    for s in result.stages:
        print(f"  [{s.stage_index}] {s.stage_name}: {len(s.output)} chars, "
              f"{s.execution_time_s:.1f}s ({s.token_count} tok)")
    print(f"  TOTAL: {result.total_time_s:.1f}s | {result.total_tokens} tokens | "
          f"report={len(result.consolidated_report)} chars")


def main() -> None:
    models = sys.argv[1:]
    if not models:
        print("usage: python tools/compare_models.py <model_id> [model_id ...]")
        return
    base = _PROJECT_ROOT / "comparison"
    for model_id in models:
        try:
            run_for(model_id, base / slug(model_id))
        except Exception as exc:  # noqa: BLE001
            print(f"\n=== {model_id} FAILED: {exc!r} ===")


if __name__ == "__main__":
    main()