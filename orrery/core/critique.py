"""
Agent Self-Critique & Reflection Engine.

The engine has two independent sources of evidence, and they answer different questions.

The **success ratio** over receipts answers "did the adapters do what they were told?"
The **goal check** answers "is the goal actually met?" Only the second one is about the
world. A plan can execute almost perfectly and achieve nothing: three of four actions
succeeding scores 0.75, clears a 0.70 threshold, and says nothing at all about whether
the file the fourth action was supposed to read now exists.

So a goal check, when supplied, is authoritative and can only veto. A high ratio cannot
overrule it. And when no goal check is supplied the result says so — `goal_verified` is
`None`, never `True`, because "nobody checked" is not the same as "it worked".
"""

from typing import Callable, List, Optional

from pydantic import BaseModel

from orrery.core.types import StateContext, CritiqueResult, ExecutionReceipt, ActionPayload


class GoalVerification(BaseModel):
    """The verdict of an out-of-band check against the world."""

    verified: bool
    detail: str = ""


GoalCheck = Callable[[StateContext], GoalVerification]


class SelfCritiqueEngine:
    """
    Evaluates execution outcomes, plan fidelity, and system invariants to generate
    numerical critique scores and feedback prior to cycle completion.
    """

    def __init__(
        self,
        threshold: float = 0.70,
        strict_mode: bool = False,
        goal_check: Optional[GoalCheck] = None,
    ):
        self.threshold = threshold
        self.strict_mode = strict_mode
        self.goal_check = goal_check

    def _verify_goal(self, context: StateContext) -> Optional[GoalVerification]:
        if self.goal_check is None:
            return None
        try:
            return self.goal_check(context)
        except Exception as exc:
            # A goal check that crashes has verified nothing. Reading that as success would
            # be the precise failure this engine exists to prevent.
            return GoalVerification(
                verified=False, detail=f"goal check raised {type(exc).__name__}: {exc}"
            )

    def evaluate(self, context: StateContext) -> CritiqueResult:
        """
        Evaluates the current state context and returns a CritiqueResult.
        """
        receipts: List[ExecutionReceipt] = context.execution_receipts
        planned: List[ActionPayload] = context.planned_actions

        if not receipts and planned:
            barren = CritiqueResult(
                score=0.0,
                passed=False,
                reasoning="Execution phase produced zero execution receipts despite planned actions.",
                recommendations=["Re-verify adapter execution dispatch."],
            )
            context.critiques.append(barren)
            return barren

        failed_receipts = [r for r in receipts if not r.success]
        total_actions = len(receipts) if receipts else 1
        success_ratio = (total_actions - len(failed_receipts)) / total_actions

        recommendations = [
            f"Action '{fr.action_name}' failed: {fr.error or 'Unknown error'}"
            for fr in failed_receipts
        ]

        # Compute overall reflection score
        score = max(0.0, min(1.0, round(success_ratio, 2)))
        passed = score >= self.threshold

        reasoning = (
            f"Reflection evaluation passed with score {score:.2f} (Threshold: {self.threshold:.2f})."
            if passed
            else f"Reflection evaluation failed with score {score:.2f} (Threshold: {self.threshold:.2f})."
        )

        if self.strict_mode and failed_receipts:
            passed = False
            reasoning = (
                f"Reflection refused in strict mode: {len(failed_receipts)} of {total_actions} "
                f"action(s) failed (score {score:.2f})."
            )

        verification = self._verify_goal(context)
        if verification is not None and not verification.verified:
            passed = False
            reasoning = (
                f"Reflection refused: {total_actions - len(failed_receipts)} of {total_actions} "
                f"action(s) succeeded (score {score:.2f}), but the goal is not met: "
                f"{verification.detail}"
            )
            recommendations.append(f"Goal not met: {verification.detail}")
        elif verification is None and passed:
            reasoning += " Score reflects adapter outcomes only; goal attainment was not verified."

        critique = CritiqueResult(
            score=score,
            passed=passed,
            reasoning=reasoning,
            recommendations=recommendations,
            goal_verified=verification.verified if verification else None,
            verification_detail=verification.detail if verification else "",
        )

        context.critiques.append(critique)
        return critique
