"""
CLI Tool: Empirical θ_critique Threshold Calibration.

Usage:
    python -m orrery.tools.calibrate_critique [--objective fail_closed|balanced|high_throughput]
                                              [--format markdown|json]
                                              [--output <path>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from orrery.core.calibration import (
    CalibrationObjective,
    CritiqueCalibrator,
    get_standard_benchmark_calibration_samples,
)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m orrery.tools.calibrate_critique",
        description="Empirically calibrate the critique threshold (theta_critique) against ground-truth benchmarks.",
    )
    parser.add_argument(
        "--objective",
        choices=["fail_closed", "balanced", "high_throughput"],
        default="fail_closed",
        help="Optimization objective (default: fail_closed).",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional file path to write the calibration report.",
    )

    args = parser.parse_args(argv)

    samples = get_standard_benchmark_calibration_samples()
    calibrator = CritiqueCalibrator(samples)
    obj = CalibrationObjective(args.objective)

    if args.format == "json":
        metrics = calibrator.sweep()
        optimal = calibrator.find_optimal_threshold(obj)
        payload = {
            "objective": obj.value,
            "optimal_threshold": optimal.model_dump(mode="json") if optimal else None,
            "sweep_metrics": [m.model_dump(mode="json") for m in metrics],
        }
        content = json.dumps(payload, indent=2)
    else:
        content = calibrator.generate_report(objective=obj)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(f"Calibration report written to {args.output}")
    else:
        print(content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
