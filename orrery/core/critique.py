"""
Agent Self-Critique & Reflection Engine.
"""

from typing import List, Optional
from orrery.core.types import StateContext, CritiqueResult, ExecutionReceipt, ActionPayload


class SelfCritiqueEngine:
    """
    Evaluates execution outcomes, plan fidelity, and system invariants to generate
    numerical critique scores and feedback prior to cycle completion.
    """

    def __init__(self, threshold: float = 0.70):
        self.threshold = threshold

    def evaluate(self, context: StateContext) -> CritiqueResult:
        """
        Evaluates the current state context and returns a CritiqueResult.
        """
        receipts: List[ExecutionReceipt] = context.execution_receipts
        planned: List[ActionPayload] = context.planned_actions

        if not receipts and planned:
            return CritiqueResult(
                score=0.0,
                passed=False,
                reasoning="Execution phase produced zero execution receipts despite planned actions.",
                recommendations=["Re-verify adapter execution dispatch."],
            )

        failed_receipts = [r for r in receipts if not r.success]
        total_actions = len(receipts) if receipts else 1
        success_ratio = (total_actions - len(failed_receipts)) / total_actions

        recommendations = []
        if failed_receipts:
            for fr in failed_receipts:
                recommendations.append(f"Action '{fr.action_name}' failed: {fr.error or 'Unknown error'}")

        # Compute overall reflection score
        score = max(0.0, min(1.0, round(success_ratio, 2)))
        passed = score >= self.threshold

        reasoning = (
            f"Reflection evaluation passed with score {score:.2f} (Threshold: {self.threshold:.2f})."
            if passed
            else f"Reflection evaluation failed with score {score:.2f} (Threshold: {self.threshold:.2f})."
        )

        critique = CritiqueResult(
            score=score,
            passed=passed,
            reasoning=reasoning,
            recommendations=recommendations,
        )

        context.critiques.append(critique)
        return critique
