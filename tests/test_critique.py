"""
Tests for the self-critique engine, and specifically for what it can and cannot know.

The engine has two evidence sources that answer different questions. These tests pin the
boundary between them, because conflating the two is how a framework ends up certifying
work it never checked.
"""

import pytest

from orrery.core.critique import GoalVerification, SelfCritiqueEngine
from orrery.core.types import ActionPayload, ExecutionReceipt, StateContext


def _context_with(successes: int, failures: int) -> StateContext:
    context = StateContext(goal="critique boundary")
    for index in range(successes + failures):
        action = ActionPayload(action_name=f"action_{index}")
        context.planned_actions.append(action)
        context.execution_receipts.append(
            ExecutionReceipt(
                action_id=action.action_id,
                action_name=action.action_name,
                success=index < successes,
                error=None if index < successes else "boom",
            )
        )
    return context


def test_success_ratio_alone_passes_a_plan_that_did_not_reach_its_goal():
    """
    The limitation, stated as a test so it is never mistaken for a fix.

    Three of four actions succeed, which clears the threshold. Nothing here knows or can
    know whether the goal was met. This is not a bug in the ratio; it is the ratio
    measuring the only thing it measures.
    """
    engine = SelfCritiqueEngine(threshold=0.70)
    critique = engine.evaluate(_context_with(successes=3, failures=1))

    assert critique.score == 0.75
    assert critique.passed
    assert critique.goal_verified is None, "no check ran, so the goal is unverified, not met"
    assert "not verified" in critique.reasoning


def test_goal_check_overrides_a_passing_success_ratio():
    """
    LAW7-GOAL. A goal check can only veto; a high ratio cannot overrule it.
    """
    engine = SelfCritiqueEngine(
        threshold=0.70,
        goal_check=lambda _: GoalVerification(verified=False, detail="batch/b.txt does not exist"),
    )
    critique = engine.evaluate(_context_with(successes=3, failures=1))

    assert critique.score == 0.75, "the ratio is still reported honestly"
    assert not critique.passed
    assert critique.goal_verified is False
    assert "batch/b.txt does not exist" in critique.reasoning
    assert any("batch/b.txt does not exist" in rec for rec in critique.recommendations), (
        "the reason must reach lessons, or backtracking retries the same plan"
    )


def test_goal_check_cannot_rescue_a_failing_ratio():
    engine = SelfCritiqueEngine(
        threshold=0.70, goal_check=lambda _: GoalVerification(verified=True, detail="fine")
    )
    critique = engine.evaluate(_context_with(successes=1, failures=3))

    assert not critique.passed
    assert critique.goal_verified is True


def test_goal_check_that_raises_counts_as_unverified():
    def exploding(_):
        raise RuntimeError("verifier is broken")

    engine = SelfCritiqueEngine(threshold=0.70, goal_check=exploding)
    critique = engine.evaluate(_context_with(successes=4, failures=0))

    assert not critique.passed
    assert critique.goal_verified is False
    assert "RuntimeError" in critique.verification_detail


def test_strict_mode_refuses_any_failed_action():
    """
    The `meta_skills.critique.strict_mode` setting existed in config and did nothing.
    """
    engine = SelfCritiqueEngine(threshold=0.70, strict_mode=True)
    critique = engine.evaluate(_context_with(successes=3, failures=1))

    assert not critique.passed
    assert "strict mode" in critique.reasoning


def test_strict_mode_still_passes_a_clean_plan():
    engine = SelfCritiqueEngine(threshold=0.70, strict_mode=True)
    critique = engine.evaluate(_context_with(successes=4, failures=0))

    assert critique.passed
    assert critique.score == 1.0


def test_zero_receipts_against_a_plan_is_recorded_as_a_failure():
    """
    Previously this returned early without appending, so the dispatcher fell through to
    its optimistic default and marked the cycle COMPLETED having executed nothing.
    """
    context = StateContext(goal="nothing ran")
    context.planned_actions.append(ActionPayload(action_name="never_dispatched"))

    critique = SelfCritiqueEngine().evaluate(context)

    assert not critique.passed
    assert critique.score == 0.0
    assert context.critiques[-1] is critique
