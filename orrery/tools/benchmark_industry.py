"""
CLI Runner: Industry Benchmark Suite (GAIA, SWE-bench, Tau-bench).

Usage:
    python -m orrery.tools.benchmark_industry [--suite all|gaia|swe_bench|tau_bench] [--output benchmarks/report.json]
"""

import argparse
import asyncio
import sys
from pathlib import Path

from orrery.bench.industry import IndustryBenchmarkRunner, IndustryBenchmarkSuite


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run industry benchmark evaluation comparing Ungoverned Baseline vs. Orrery Governed."
    )
    parser.add_argument(
        "--suite",
        type=str,
        choices=["all", "gaia", "swe_bench", "tau_bench"],
        default="all",
        help="Benchmark suite to evaluate (default: all)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path to output the benchmark report JSON",
    )
    args = parser.parse_args()

    print(f"[Orrery Industry Benchmark] Initializing benchmark harness (suite={args.suite})...")
    runner = IndustryBenchmarkRunner()
    report = asyncio.run(runner.run_benchmark(suite=IndustryBenchmarkSuite(args.suite)))

    print("\n" + report.summary_markdown())

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(f"\n[Orrery Industry Benchmark] Benchmark report written to {out_path.resolve()}")

    # Assert that governed violation rate is 0.0%
    has_violations = any(s.governed_violation_rate > 0 for s in report.suites)
    if has_violations:
        print("\n[Orrery Industry Benchmark] CRITICAL: Governed agent permitted a security violation!", file=sys.stderr)
        sys.exit(1)
    else:
        print("\n[Orrery Industry Benchmark] All governed runs completed with 0.0% security violations.")
        sys.exit(0)


if __name__ == "__main__":
    main()
