"""
Tests for delegation governance: depth, fan-out, population, ancestry, tier ordering.
"""

import asyncio

from orrery.core.config import DelegationSettings, Settings
from orrery.core.delegation import DelegationBudget, DelegationPolicy, DelegationRequest, authorize
from orrery.core.types import CycleStatus, CycleTier, StateContext
from orrery.cycles.base import BaseCycle
from orrery.cycles.macro import MacroCycle
from orrery.cycles.meso import MesoCycle
from orrery.cycles.meta import MetaCycle
from orrery.cycles.micro import MicroCycle
from tests.conftest import StubAdapter


def _wire(cycle: BaseCycle) -> BaseCycle:
    cycle.register_adapter(StubAdapter(), name="default")
    return cycle


def _request(parent: BaseCycle, child: BaseCycle, depth: int = 1) -> DelegationRequest:
    return DelegationRequest(
        parent_cycle_id=parent.context.cycle_id,
        parent_tier=parent.tier,
        child_cycle_id=child.context.cycle_id,
        child_tier=child.tier,
        depth=depth,
        ancestry=parent.ancestry,
    )


def test_depth_cap_refuses_delegation():
    budget = DelegationBudget(max_depth=2)
    parent, child = MetaCycle(), MacroCycle()

    decision = authorize(_request(parent, child, depth=3), budget)

    assert not decision.allowed
    assert decision.policy_id == "DEL-001"


def test_fan_out_cap_refuses_delegation():
    budget = DelegationBudget(max_children_per_cycle=2)
    parent = MetaCycle()

    for _ in range(2):
        assert authorize(_request(parent, MacroCycle()), budget).allowed

    decision = authorize(_request(parent, MacroCycle()), budget)
    assert not decision.allowed
    assert decision.policy_id == "DEL-002"


def test_population_cap_refuses_delegation():
    budget = DelegationBudget(max_total_cycles=2, max_children_per_cycle=99)
    parent = MetaCycle()

    for _ in range(2):
        assert authorize(_request(parent, MacroCycle()), budget).allowed

    decision = authorize(_request(parent, MacroCycle()), budget)
    assert not decision.allowed
    assert decision.policy_id == "DEL-003"


def test_ancestry_loop_is_refused():
    budget = DelegationBudget()
    parent, child = MetaCycle(), MacroCycle()
    parent.ancestry = (child.context.cycle_id,)

    decision = authorize(_request(parent, child), budget)

    assert not decision.allowed
    assert decision.policy_id == "DEL-004"


def test_self_delegation_is_refused():
    budget = DelegationBudget()
    parent = MetaCycle()
    request = DelegationRequest(
        parent_cycle_id=parent.context.cycle_id,
        parent_tier=CycleTier.META,
        child_cycle_id=parent.context.cycle_id,
        child_tier=CycleTier.MACRO,
        depth=1,
    )

    decision = authorize(request, budget)

    assert not decision.allowed
    assert decision.policy_id == "DEL-004"


def test_delegation_must_descend_the_tier_hierarchy():
    budget = DelegationBudget()

    upward = authorize(_request(MicroCycle(), MetaCycle()), budget)
    sideways = authorize(_request(MesoCycle(), MesoCycle()), budget)

    assert not upward.allowed and upward.policy_id == "DEL-005"
    assert not sideways.allowed and sideways.policy_id == "DEL-005"


def test_normal_descent_is_allowed():
    budget = DelegationBudget()
    assert authorize(_request(MetaCycle(), MacroCycle()), budget).allowed


def test_refused_delegation_produces_a_failed_receipt_and_never_runs_the_child():
    async def run():
        parent = _wire(MacroCycle(context=StateContext(goal="parent", tier=CycleTier.MACRO)))
        child = _wire(MetaCycle())  # Upward delegation: refused by DEL-005.

        result = await parent.delegate_to_child(child)

        assert result.status == CycleStatus.FAILED
        assert result.step_count == 0, "a refused child must not execute"

        receipts = [r for r in parent.context.execution_receipts if not r.success]
        assert len(receipts) == 1
        assert "DEL-005" in (receipts[0].error or "")
        assert any("DEL-005" in lesson for lesson in parent.context.lessons)

    asyncio.run(run())


def test_recursion_bomb_is_bounded_by_the_shared_budget():
    """
    A full META run delegates META -> MACRO -> MESO -> MICRO. With max_depth=1 only the
    first hop may happen; the rest must be refused rather than spawned.
    """

    async def run():
        settings = Settings(delegation=DelegationSettings(max_depth=1, max_total_cycles=99))
        root = _wire(MetaCycle(context=StateContext(goal="spawn", tier=CycleTier.META), settings=settings))

        await root.run_cycle()

        # Each backtrack re-spawns a child, so `spawned` counts attempts; what matters is
        # that only the root ever successfully spawned, so the tree never got deeper than 1.
        assert set(root.delegation_budget.children_by_parent) == {root.context.cycle_id}
        assert root.delegation_budget.spawned <= root.delegation_budget.max_children_per_cycle
        assert root.delegation_budget.refusals
        assert all("DEL-001" in refusal for refusal in root.delegation_budget.refusals)

    asyncio.run(run())


def test_full_tier_descent_is_permitted_by_default_limits():
    async def run():
        root = _wire(MetaCycle(context=StateContext(goal="descend", tier=CycleTier.META)))

        result = await root.run_cycle()

        assert result.status == CycleStatus.COMPLETED
        assert root.delegation_budget.spawned == 3, "META -> MACRO -> MESO -> MICRO"
        assert not root.delegation_budget.refusals

    asyncio.run(run())


def test_children_inherit_depth_ancestry_and_budget():
    async def run():
        parent = _wire(MetaCycle(context=StateContext(goal="parent", tier=CycleTier.META)))
        child = _wire(MacroCycle())

        await parent.delegate_to_child(child)

        assert child.depth == 1
        assert child.ancestry == (parent.context.cycle_id,)
        assert child.delegation_budget is parent.delegation_budget

    asyncio.run(run())


def test_custom_policy_can_tighten_authorization():
    class NoDelegation(DelegationPolicy):
        def authorize(self, request, budget):
            decision = super().authorize(request, budget)
            if decision.allowed:
                return decision.model_copy(
                    update={"allowed": False, "policy_id": "SITE-001", "reason": "delegation disabled"}
                )
            return decision

    async def run():
        parent = _wire(
            MetaCycle(context=StateContext(goal="parent", tier=CycleTier.META), delegation_policy=NoDelegation())
        )
        result = await parent.delegate_to_child(_wire(MacroCycle()))

        assert result.status == CycleStatus.FAILED
        assert any("SITE-001" in (r.error or "") for r in parent.context.execution_receipts)

    asyncio.run(run())
