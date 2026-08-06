"""
Command-line entry point for the DevOps Incident Simulation Pipeline.

Usage:
    python run.py                     # fresh full run
    python run.py --resume            # reuse completed stages on disk
    python run.py --summary           # print per-stage summary only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the project root is importable regardless of launch directory.
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.pipeline import run_simulation  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DevOps Incident Simulation Pipeline"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse completed stage outputs already saved to outputs/",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print per-stage summary instead of the full report",
    )
    args = parser.parse_args()

    result = run_simulation(resume=args.resume)

    for s in result.stages:
        print(
            f"[{s.stage_index}] {s.stage_name}: "
            f"{len(s.output)} chars, {s.execution_time_s:.1f}s "
            f"({s.token_count} tokens)"
        )
    print()
    print(
        f"TOTAL: {result.total_time_s:.1f}s | "
        f"{result.total_tokens} tokens | {result.stage_count} stages"
    )
    print(f"REPORT: {len(result.consolidated_report)} chars "
          f"-> incident_simulation_report.md")

    if not args.summary:
        print("\n" + result.consolidated_report)


if __name__ == "__main__":
    main()