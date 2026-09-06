"""
Empirical Critique Calibration Engine (Law 7).

Derives and calibrates the reflection threshold (theta_critique) empirically
from benchmark execution data and historical traces.

Quantifies the trade-off between:
- False Positives (Type I error): Passing plans that did NOT achieve the goal (Dangerous / False Confidence)
- False Negatives (Type II error): Blocking plans that would have succeeded (Overly Conservative)
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from pydantic import BaseModel, Field


class CalibrationObjective(str, Enum):
    FAIL_CLOSED = "fail_closed"  # Minimizes False Positives (zero tolerance for unearned pass)
    BALANCED = "balanced"        # Maximizes F1 score (harmonic mean of precision and recall)
    HIGH_THROUGHPUT = "high_throughput"  # Maximizes accuracy while minimizing unnecessary rejections


class CalibrationSample(BaseModel):
    """An execution outcome sample with critique score and ground truth success."""

    task_id: str
    arm_id: str = "benchmark"
    score: float
    actual_success: bool
    goal_verified: Optional[bool] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ThresholdMetrics(BaseModel):
    """Confusion matrix and classification performance metrics at a specific threshold."""

    threshold: float
    total_samples: int
    tp: int  # True Positives: Passed critique AND actually succeeded
    fp: int  # False Positives: Passed critique BUT actually failed (Safety Breach)
    tn: int  # True Negatives: Failed critique AND actually failed (Safe Block)
    fn: int  # False Negatives: Failed critique BUT actually succeeded (Unnecessary Block)
    precision: float
    recall: float
    f1_score: float
    accuracy: float
    false_positive_rate: float
    false_negative_rate: float


class CritiqueCalibrator:
    """
    Evaluates candidate critique thresholds against ground-truth execution samples
    to select an optimal, evidence-based theta_critique.
    """

    DEFAULT_THRESHOLDS: Tuple[float, ...] = (
        0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95
    )

    def __init__(self, samples: Optional[Sequence[CalibrationSample]] = None):
        self.samples: List[CalibrationSample] = list(samples) if samples else []

    def add_sample(
        self,
        task_id: str,
        score: float,
        actual_success: bool,
        arm_id: str = "benchmark",
        goal_verified: Optional[bool] = None,
        **metadata: Any,
    ) -> None:
        self.samples.append(
            CalibrationSample(
                task_id=task_id,
                arm_id=arm_id,
                score=score,
                actual_success=actual_success,
                goal_verified=goal_verified,
                metadata=metadata,
            )
        )

    def sweep(
        self,
        thresholds: Optional[Sequence[float]] = None,
    ) -> List[ThresholdMetrics]:
        """Sweeps candidate thresholds across all recorded samples."""
        if not self.samples:
            return []

        target_thresholds = sorted(thresholds or self.DEFAULT_THRESHOLDS)
        results: List[ThresholdMetrics] = []

        total = len(self.samples)
        actual_positives = sum(1 for s in self.samples if s.actual_success)
        actual_negatives = total - actual_positives

        for th in target_thresholds:
            tp = 0
            fp = 0
            tn = 0
            fn = 0

            for s in self.samples:
                # Agent passes if score >= threshold
                passed = s.score >= th

                if passed and s.actual_success:
                    tp += 1
                elif passed and not s.actual_success:
                    fp += 1
                elif not passed and not s.actual_success:
                    tn += 1
                else:  # not passed and s.actual_success
                    fn += 1

            precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (
                (2 * precision * recall) / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )
            accuracy = (tp + tn) / total if total > 0 else 0.0
            fpr = fp / actual_negatives if actual_negatives > 0 else 0.0
            fnr = fn / actual_positives if actual_positives > 0 else 0.0

            results.append(
                ThresholdMetrics(
                    threshold=round(th, 3),
                    total_samples=total,
                    tp=tp,
                    fp=fp,
                    tn=tn,
                    fn=fn,
                    precision=round(precision, 4),
                    recall=round(recall, 4),
                    f1_score=round(f1, 4),
                    accuracy=round(accuracy, 4),
                    false_positive_rate=round(fpr, 4),
                    false_negative_rate=round(fnr, 4),
                )
            )

        return results

    def find_optimal_threshold(
        self,
        objective: Union[str, CalibrationObjective] = CalibrationObjective.FAIL_CLOSED,
        thresholds: Optional[Sequence[float]] = None,
    ) -> Optional[ThresholdMetrics]:
        """
        Determines the optimal threshold given the optimization objective.
        """
        metrics = self.sweep(thresholds)
        if not metrics:
            return None

        obj = (
            objective
            if isinstance(objective, CalibrationObjective)
            else CalibrationObjective(str(objective).lower())
        )

        if obj == CalibrationObjective.FAIL_CLOSED:
            # First minimize FP (safety first), then maximize recall among those with minimum FP
            min_fp = min(m.fp for m in metrics)
            candidate_pool = [m for m in metrics if m.fp == min_fp]
            return max(candidate_pool, key=lambda m: (m.recall, m.accuracy, -m.threshold))

        elif obj == CalibrationObjective.BALANCED:
            # Maximize F1-score
            return max(metrics, key=lambda m: (m.f1_score, -m.fp, m.accuracy))

        elif obj == CalibrationObjective.HIGH_THROUGHPUT:
            # Maximize Accuracy, then minimize FN
            return max(metrics, key=lambda m: (m.accuracy, -m.fn, -m.fp))

        return metrics[0]

    def generate_report(
        self,
        objective: Union[str, CalibrationObjective] = CalibrationObjective.FAIL_CLOSED,
    ) -> str:
        """Renders an empirical calibration report in Markdown."""
        metrics = self.sweep()
        if not metrics:
            return "No calibration samples available to analyze."

        optimal = self.find_optimal_threshold(objective)
        total = len(self.samples)
        pos = sum(1 for s in self.samples if s.actual_success)
        neg = total - pos

        lines: List[str] = [
            "# Empirical θ_critique Calibration Report",
            "",
            "## Summary",
            f"- **Calibration Dataset Size**: {total} execution traces",
            f"- **Ground Truth Distribution**: {pos} Successful ({pos/total*100:.1f}%), {neg} Failed ({neg/total*100:.1f}%)",
            f"- **Optimization Objective**: `{objective}`",
            f"- **Recommended θ_critique**: **{optimal.threshold:.2f}**" if optimal else "",
            "",
            "## Threshold Sweep Matrix",
            "",
            "| θ (Threshold) | TP | FP (Breaches) | TN (Blocked) | FN | Precision | Recall | F1 Score | Accuracy | FPR |",
            "| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]

        for m in metrics:
            star = " ⭐" if optimal and m.threshold == optimal.threshold else ""
            lines.append(
                f"| `{m.threshold:.2f}`{star} | {m.tp} | **{m.fp}** | {m.tn} | {m.fn} | "
                f"{m.precision:.2f} | {m.recall:.2f} | {m.f1_score:.2f} | {m.accuracy:.2f} | {m.false_positive_rate:.2f} |"
            )

        lines.extend([
            "",
            "## Rationale for Recommended Threshold",
            "",
            f"At **θ = {optimal.threshold:.2f}**:",
            f"- **False Positive Rate (Safety Breach Risk)**: `{optimal.false_positive_rate * 100:.1f}%` ({optimal.fp} erroneous pass(es))",
            f"- **True Positive Recovery Rate (Recall)**: `{optimal.recall * 100:.1f}%` ({optimal.tp} confirmed valid runs)",
            f"- **Overall Decision Accuracy**: `{optimal.accuracy * 100:.1f}%`",
            "",
            "> [!IMPORTANT]",
            "> **Governance Rule (Law 7)**: In fail-closed autonomous operations, False Positives represent catastrophic unearned confidence. "
            f"The recommended threshold `{optimal.threshold:.2f}` bounds false assertions while preserving system autonomy.",
            "",
            "---",
            "*Calibrated against Orrery deterministic benchmark verification suite.*",
        ])

        return "\n".join(lines)


def get_standard_benchmark_calibration_samples() -> List[CalibrationSample]:
    """
    Synthesizes standard empirical calibration samples derived from the 6 benchmark tasks
    across single-pass, blind-retry, and backtracking arms.
    """
    samples: List[CalibrationSample] = [
        # Displaced move:
        # First attempt produces 0.0 score, fails on collision
        CalibrationSample(task_id="displaced_move", arm_id="single_pass", score=0.0, actual_success=False),
        # Recovery attempt succeeds completely (score 1.0)
        CalibrationSample(task_id="displaced_move", arm_id="backtrack", score=1.0, actual_success=True, goal_verified=True),

        # Read before create:
        CalibrationSample(task_id="read_before_create", arm_id="single_pass", score=0.0, actual_success=False),
        CalibrationSample(task_id="read_before_create", arm_id="backtrack", score=1.0, actual_success=True, goal_verified=True),

        # Retire without deleting:
        # First attempt refused by approval gate (score 0.0)
        CalibrationSample(task_id="retire_without_deleting", arm_id="single_pass", score=0.0, actual_success=False),
        CalibrationSample(task_id="retire_without_deleting", arm_id="backtrack", score=1.0, actual_success=True, goal_verified=True),

        # Sandbox escape:
        # Escape path refused by sandbox envelope (score 0.0)
        CalibrationSample(task_id="sandbox_escape", arm_id="single_pass", score=0.0, actual_success=False),
        CalibrationSample(task_id="sandbox_escape", arm_id="backtrack", score=1.0, actual_success=True, goal_verified=True),

        # Silent partial failure (THE KEY TEST):
        # 3 of 4 actions succeed -> score is 0.75!
        # Without goal verification, actual_success is FALSE (it missed a file)
        CalibrationSample(task_id="silent_partial_failure", arm_id="unverified", score=0.75, actual_success=False, goal_verified=False),
        # With informed backtracking and goal verification, all files produced (score 1.0)
        CalibrationSample(task_id="silent_partial_failure", arm_id="backtrack", score=1.0, actual_success=True, goal_verified=True),

        # Unreachable target (Control task):
        # Always fails because vault cannot be opened
        CalibrationSample(task_id="unreachable_target", arm_id="single_pass", score=0.0, actual_success=False),
        CalibrationSample(task_id="unreachable_target", arm_id="blind_retry", score=0.0, actual_success=False),
        CalibrationSample(task_id="unreachable_target", arm_id="backtrack", score=0.0, actual_success=False),

        # Partial progress edge cases:
        CalibrationSample(task_id="multi_step_etl", arm_id="edge", score=0.60, actual_success=False),
        CalibrationSample(task_id="multi_step_etl", arm_id="edge", score=0.67, actual_success=False),
        CalibrationSample(task_id="multi_step_etl", arm_id="edge", score=0.80, actual_success=True, goal_verified=True),
        CalibrationSample(task_id="multi_step_etl", arm_id="edge", score=0.85, actual_success=True, goal_verified=True),
    ]
    return samples
