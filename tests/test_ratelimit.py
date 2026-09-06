"""
Tests for RateLimitGate and rate-limiting policy (LAW10-RATELIMIT).

Checks that burst operations exceeding sliding-window ceilings are refused BEFORE execution,
preventing resource exhaustion, API quota overruns, and runaway loops.
"""

from pathlib import Path
import pytest

from orrery.core.config import Settings, RateLimitSettings, RateLimitRuleConfig
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.ratelimit import RateLimitDecision, RateLimitGate, RateLimitRule, RATELIMIT_POLICY
from orrery.core.types import ActionPayload, ActionRisk, StateContext
from orrery.adapters.base import BaseAdapter, ExecutionReceipt


class DummyAdapter(BaseAdapter):
    is_simulation = True
    declared_risks = {"ping": ActionRisk.READ_ONLY}

    def __init__(self, name: str = "dummy_adapter"):
        super().__init__(name=name)

    async def perceive_environment(self, context: StateContext) -> dict:
        return {}

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        return self._receipt(action=action, success=True, output="pong")


def test_burst_actions_exceeding_rate_limit_are_refused():
    """
    LAW10-RATELIMIT: Bursts exceeding the configured ceiling are refused.
    Named test target for the governance policy.
    """
    rule = RateLimitRule(
        name="burst_protection",
        action="ping",
        max_calls=3,
        window_seconds=10.0,
    )
    gate = RateLimitGate(rules=[rule], enabled=True)

    action = ActionPayload(
        action_name="ping",
        target_adapter="dummy",
        risk=ActionRisk.READ_ONLY,
    )

    t0 = 1000.0
    # First 3 calls succeed
    for i in range(3):
        decision = gate.evaluate(action, now=t0 + i)
        assert decision.allowed is True

    # 4th call within the 10-second window is refused
    decision_4 = gate.evaluate(action, now=t0 + 4)
    assert decision_4.allowed is False
    assert decision_4.policy_id == RATELIMIT_POLICY
    assert "Rate limit 'burst_protection' exceeded" in decision_4.reason
    assert decision_4.observed_count == 3
    assert decision_4.limit == 3


def test_rate_limit_window_expiration():
    """Calls outside the sliding window expire and free up capacity."""
    rule = RateLimitRule(
        name="window_test",
        max_calls=2,
        window_seconds=5.0,
    )
    gate = RateLimitGate(rules=[rule], enabled=True)
    action = ActionPayload(action_name="compute", target_adapter="dummy")

    t0 = 2000.0
    assert gate.evaluate(action, now=t0).allowed is True
    assert gate.evaluate(action, now=t0 + 1).allowed is True

    # Limit reached
    assert gate.evaluate(action, now=t0 + 2).allowed is False

    # After 5.1s, the first call at t0 has rolled out of the window
    assert gate.evaluate(action, now=t0 + 5.1).allowed is True


def test_rate_limit_rule_matching_by_adapter_and_action():
    """Rules only match matching adapter and action."""
    rule = RateLimitRule(
        name="specific_rule",
        adapter="target_a",
        action="action_x",
        max_calls=1,
        window_seconds=10.0,
    )
    gate = RateLimitGate(rules=[rule], enabled=True)

    matching = ActionPayload(action_name="action_x", target_adapter="target_a")
    diff_adapter = ActionPayload(action_name="action_x", target_adapter="target_b")
    diff_action = ActionPayload(action_name="action_y", target_adapter="target_a")

    # Matching call consumes the 1-call quota
    assert gate.evaluate(matching, now=100.0).allowed is True
    assert gate.evaluate(matching, now=101.0).allowed is False

    # Non-matching calls are not affected by this rule
    assert gate.evaluate(diff_adapter, now=101.0).allowed is True
    assert gate.evaluate(diff_action, now=101.0).allowed is True


def test_rate_limit_reset_clears_history():
    """Reset clears history so calls can resume immediately."""
    rule = RateLimitRule(name="reset_rule", max_calls=1, window_seconds=60.0)
    gate = RateLimitGate(rules=[rule], enabled=True)
    action = ActionPayload(action_name="test", target_adapter="dummy")

    assert gate.evaluate(action, now=10.0).allowed is True
    assert gate.evaluate(action, now=11.0).allowed is False

    gate.reset()
    assert gate.evaluate(action, now=12.0).allowed is True


def test_rate_limit_disabled_allows_all():
    """When disabled, gate permits all actions regardless of rules."""
    rule = RateLimitRule(name="disabled_rule", max_calls=1, window_seconds=60.0)
    gate = RateLimitGate(rules=[rule], enabled=False)
    action = ActionPayload(action_name="test", target_adapter="dummy")

    assert gate.evaluate(action).allowed is True
    assert gate.evaluate(action).allowed is True
    assert gate.evaluate(action).allowed is True


@pytest.mark.asyncio
async def test_dispatcher_refuses_rate_limited_action(tmp_path):
    """Full CycleDispatcher integration: rate-limited actions are refused and ledgered."""
    rule = RateLimitRule(
        name="dispatcher_limit",
        action="ping",
        max_calls=1,
        window_seconds=60.0,
    )
    gate = RateLimitGate(rules=[rule], enabled=True)

    dispatcher = CycleDispatcher(
        rate_limit_gate=gate,
        settings=Settings(allow_simulated_adapters=True),
    )
    adapter = DummyAdapter(name="dummy")
    dispatcher.register_adapter(adapter)

    action = ActionPayload(
        action_name="ping",
        target_adapter="dummy",
        risk=ActionRisk.READ_ONLY,
    )

    # 1st call executes successfully
    receipt1 = await dispatcher.execute_action(action)
    assert receipt1.success is True
    assert receipt1.output["result"] == "pong"

    # 2nd call is intercepted by RateLimitGate
    receipt2 = await dispatcher.execute_action(action)
    assert receipt2.success is False
    assert "LAW10-RATELIMIT" in receipt2.error
    assert "exceeded" in receipt2.error
