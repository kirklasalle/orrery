"""
Tests for Industry Benchmark Harness (GAIA, SWE-bench, Tau-bench).
"""

import pytest
from orrery.bench.industry import (
    IndustryBenchmarkRunner,
    IndustryBenchmarkSuite,
    BenchmarkSimulatedAdapter,
    get_gaia_tasks,
    get_swe_bench_tasks,
    get_tau_bench_tasks,
)
from orrery.core.types import ActionPayload, ActionRisk, StateContext


@pytest.fixture
def runner() -> IndustryBenchmarkRunner:
    return IndustryBenchmarkRunner(sandbox_root="d:/sandbox")


@pytest.mark.asyncio
async def test_gaia_suite_benchmark(runner: IndustryBenchmarkRunner) -> None:
    report = await runner.run_benchmark(suite=IndustryBenchmarkSuite.GAIA)
    assert report.total_tasks == 2
    summary = report.suites[0]
    assert summary.suite == "gaia"
    assert summary.governed_success_rate == 1.0
    assert summary.governed_violation_rate == 0.0
    assert summary.ungoverned_violation_rate > 0.0
    assert summary.backtracking_recovery_rate == 1.0


@pytest.mark.asyncio
async def test_swe_bench_suite_benchmark(runner: IndustryBenchmarkRunner) -> None:
    report = await runner.run_benchmark(suite=IndustryBenchmarkSuite.SWE_BENCH)
    assert report.total_tasks == 2
    summary = report.suites[0]
    assert summary.suite == "swe_bench"
    assert summary.governed_success_rate == 1.0
    assert summary.governed_violation_rate == 0.0
    assert summary.backtracking_recovery_rate == 1.0


@pytest.mark.asyncio
async def test_tau_bench_suite_benchmark(runner: IndustryBenchmarkRunner) -> None:
    report = await runner.run_benchmark(suite=IndustryBenchmarkSuite.TAU_BENCH)
    assert report.total_tasks == 2
    summary = report.suites[0]
    assert summary.suite == "tau_bench"
    assert summary.governed_success_rate == 1.0
    assert summary.governed_violation_rate == 0.0
    assert summary.backtracking_recovery_rate == 1.0


@pytest.mark.asyncio
async def test_all_industry_suites(runner: IndustryBenchmarkRunner) -> None:
    report = await runner.run_benchmark(suite=IndustryBenchmarkSuite.ALL)
    assert report.total_tasks == 6
    assert len(report.suites) == 3
    for s in report.suites:
        assert s.governed_success_rate == 1.0
        assert s.governed_violation_rate == 0.0
    md = report.summary_markdown()
    assert "GAIA" in md
    assert "SWE_BENCH" in md
    assert "TAU_BENCH" in md


def test_simulated_adapter_execution() -> None:
    adapter = BenchmarkSimulatedAdapter()
    assert adapter.perceive_environment(StateContext(goal="test"))["sandbox_root"] == "d:/sandbox"

    # Synchronous execute
    rec = adapter.execute(ActionPayload(action_name="read_sandbox_file"))
    assert rec.success is True

    # Charge account
    rec_charge = adapter.execute(
        ActionPayload(
            action_name="charge_account",
            params={"user_id": "u1", "amount": 25},
        )
    )
    assert rec_charge.success is True
    assert rec_charge.output["remaining_balance"] == 75


def test_cli_industry_benchmarks(tmp_path) -> None:
    import sys
    from unittest.mock import patch
    from orrery.tools.benchmark_industry import main

    out_file = tmp_path / "industry_report.json"
    test_args = ["benchmark_industry", "--suite", "gaia", "--output", str(out_file)]
    with patch.object(sys, "argv", test_args):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 0
    assert out_file.exists()
