"""
Tests for Empirical Critique Calibration (Law 7).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from orrery.core.calibration import (
    CalibrationObjective,
    CalibrationSample,
    CritiqueCalibrator,
    ThresholdMetrics,
    get_standard_benchmark_calibration_samples,
)
from orrery.tools.calibrate_critique import main as calibrate_cli_main


def test_calibration_sample_creation():
    sample = CalibrationSample(
        task_id="test_task",
        arm_id="test_arm",
        score=0.85,
        actual_success=True,
        goal_verified=True,
    )
    assert sample.task_id == "test_task"
    assert sample.score == 0.85
    assert sample.actual_success is True


def test_critique_calibrator_sweep():
    samples = [
        CalibrationSample(task_id="t1", score=0.9, actual_success=True),
        CalibrationSample(task_id="t2", score=0.7, actual_success=False),
        CalibrationSample(task_id="t3", score=0.5, actual_success=False),
    ]
    calibrator = CritiqueCalibrator(samples)
    metrics = calibrator.sweep(thresholds=[0.6, 0.8])

    assert len(metrics) == 2
    # At threshold 0.6: t1 (0.9, True) -> TP, t2 (0.7, False) -> FP, t3 (0.5, False) -> TN
    m06 = metrics[0]
    assert m06.threshold == 0.6
    assert m06.tp == 1
    assert m06.fp == 1
    assert m06.tn == 1
    assert m06.fn == 0

    # At threshold 0.8: t1 (0.9, True) -> TP, t2 (0.7, False) -> TN, t3 (0.5, False) -> TN
    m08 = metrics[1]
    assert m08.threshold == 0.8
    assert m08.tp == 1
    assert m08.fp == 0
    assert m08.tn == 2
    assert m08.fn == 0


def test_critique_calibrator_optimal_threshold_selection():
    samples = get_standard_benchmark_calibration_samples()
    calibrator = CritiqueCalibrator(samples)

    # Under FAIL_CLOSED: must minimize FP (false positives)
    opt_fail_closed = calibrator.find_optimal_threshold(CalibrationObjective.FAIL_CLOSED)
    assert opt_fail_closed is not None
    assert opt_fail_closed.fp == 0
    assert opt_fail_closed.threshold >= 0.80

    # Under BALANCED: maximizes F1
    opt_balanced = calibrator.find_optimal_threshold(CalibrationObjective.BALANCED)
    assert opt_balanced is not None
    assert opt_balanced.f1_score >= 0.90

    # Under HIGH_THROUGHPUT: maximizes Accuracy
    opt_throughput = calibrator.find_optimal_threshold(CalibrationObjective.HIGH_THROUGHPUT)
    assert opt_throughput is not None
    assert opt_throughput.accuracy >= 0.90


def test_critique_calibrator_empty_dataset():
    calibrator = CritiqueCalibrator()
    assert calibrator.sweep() == []
    assert calibrator.find_optimal_threshold() is None
    assert "No calibration samples" in calibrator.generate_report()


def test_calibrate_critique_cli_markdown(tmp_path: Path):
    out_file = tmp_path / "calibration_report.md"
    ret = calibrate_cli_main(["--objective", "fail_closed", "--format", "markdown", "--output", str(out_file)])
    assert ret == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "# Empirical θ_critique Calibration Report" in content
    assert "Recommended θ_critique" in content


def test_calibrate_critique_cli_json(tmp_path: Path):
    out_file = tmp_path / "calibration_report.json"
    ret = calibrate_cli_main(["--objective", "balanced", "--format", "json", "--output", str(out_file)])
    assert ret == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["objective"] == "balanced"
    assert "optimal_threshold" in data
    assert len(data["sweep_metrics"]) > 0
