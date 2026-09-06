"""
Tests for individual cycle phase handlers and direct phase invocation.

The existing test_tiers.py exercises cycles through run_cycle(), which tests
the full dispatcher flow. These tests call each phase handler directly to verify
the tier-specific logic in isolation and to close the coverage gap on cycle
implementation code.
"""

import asyncio

from orrery.core.types import StateContext, CycleTier, CycleStatus, ActionPayload
from orrery.cycles.meta import MetaCycle
from orrery.cycles.macro import MacroCycle
from orrery.cycles.meso import MesoCycle
from orrery.cycles.micro import MicroCycle
from tests.conftest import StubAdapter


# --- MetaCycle phase handler tests ---


def test_meta_perceive_appends_hypothesis():
    async def run():
        ctx = StateContext(goal="Strategic alignment", tier=CycleTier.META)
        cycle = MetaCycle(context=ctx)
        result = await cycle.perceive()
        assert any("[META]" in h for h in result.hypotheses)
        assert "Strategic alignment" in result.hypotheses[0]
        assert cycle.context is result

    asyncio.run(run())


def test_meta_plan_sets_strategy_and_queues_action():
    async def run():
        ctx = StateContext(goal="Strategy test", tier=CycleTier.META)
        cycle = MetaCycle(context=ctx)
        result = await cycle.plan()
        assert result.variables["strategy"] == "Hierarchical meta-level decomposition"
        assert any(a.action_name == "meta_strategy_alignment" for a in result.planned_actions)

    asyncio.run(run())


def test_meta_reflect_runs_critique():
    async def run():
        ctx = StateContext(goal="Reflection test", tier=CycleTier.META)
        cycle = MetaCycle(context=ctx)
        cycle.register_adapter(StubAdapter(), name="default")
        # Run perceive+plan+execute so there are receipts to critique
        await cycle.perceive()
        await cycle.plan()
        await cycle.execute()
        result = await cycle.reflect()
        assert len(result.critiques) > 0

    asyncio.run(run())


def test_meta_perceive_accepts_explicit_context():
    """Phase handlers should use the explicitly passed context, not self.context."""
    async def run():
        cycle = MetaCycle()
        explicit = StateContext(goal="Explicit context", tier=CycleTier.META)
        result = await cycle.perceive(context=explicit)
        assert result is explicit
        assert any("Explicit context" in h for h in result.hypotheses)

    asyncio.run(run())


# --- MacroCycle phase handler tests ---


def test_macro_perceive_appends_hypothesis():
    async def run():
        ctx = StateContext(goal="Workflow parsing", tier=CycleTier.MACRO)
        cycle = MacroCycle(context=ctx)
        result = await cycle.perceive()
        assert any("[MACRO]" in h for h in result.hypotheses)

    asyncio.run(run())


def test_macro_plan_queues_milestone_action():
    async def run():
        ctx = StateContext(goal="Milestone test", tier=CycleTier.MACRO)
        cycle = MacroCycle(context=ctx)
        result = await cycle.plan()
        assert any(a.action_name == "execute_macro_milestone" for a in result.planned_actions)
        assert result.planned_actions[0].params["milestone"] == "phase_1_setup"

    asyncio.run(run())


def test_macro_reflect_runs_critique():
    async def run():
        ctx = StateContext(goal="Macro reflection", tier=CycleTier.MACRO)
        cycle = MacroCycle(context=ctx)
        cycle.register_adapter(StubAdapter(), name="default")
        await cycle.perceive()
        await cycle.plan()
        await cycle.execute()
        result = await cycle.reflect()
        assert len(result.critiques) > 0

    asyncio.run(run())


# --- MesoCycle phase handler tests ---


def test_meso_perceive_appends_hypothesis():
    async def run():
        ctx = StateContext(goal="Tool sensing", tier=CycleTier.MESO)
        cycle = MesoCycle(context=ctx)
        result = await cycle.perceive()
        assert any("[MESO]" in h for h in result.hypotheses)

    asyncio.run(run())


def test_meso_plan_queues_tool_sequence():
    async def run():
        ctx = StateContext(goal="Tool plan", tier=CycleTier.MESO)
        cycle = MesoCycle(context=ctx)
        result = await cycle.plan()
        assert any(a.action_name == "dispatch_tool_sequence" for a in result.planned_actions)

    asyncio.run(run())


def test_meso_reflect_runs_critique():
    async def run():
        ctx = StateContext(goal="Meso reflection", tier=CycleTier.MESO)
        cycle = MesoCycle(context=ctx)
        cycle.register_adapter(StubAdapter(), name="default")
        await cycle.perceive()
        await cycle.plan()
        await cycle.execute()
        result = await cycle.reflect()
        assert len(result.critiques) > 0

    asyncio.run(run())


# --- MicroCycle phase handler tests ---


def test_micro_perceive_appends_hypothesis():
    async def run():
        ctx = StateContext(goal="Atomic observation", tier=CycleTier.MICRO)
        cycle = MicroCycle(context=ctx)
        result = await cycle.perceive()
        assert any("[MICRO]" in h for h in result.hypotheses)

    asyncio.run(run())


def test_micro_plan_queues_atomic_action():
    async def run():
        ctx = StateContext(goal="Atomic plan", tier=CycleTier.MICRO)
        cycle = MicroCycle(context=ctx)
        result = await cycle.plan()
        assert any(a.action_name == "atomic_action" for a in result.planned_actions)

    asyncio.run(run())


def test_micro_reflect_runs_critique():
    async def run():
        ctx = StateContext(goal="Micro reflection", tier=CycleTier.MICRO)
        cycle = MicroCycle(context=ctx)
        cycle.register_adapter(StubAdapter(), name="default")
        await cycle.perceive()
        await cycle.plan()
        await cycle.execute()
        result = await cycle.reflect()
        assert len(result.critiques) > 0

    asyncio.run(run())


# --- Cross-cutting tests ---


def test_each_tier_reports_its_own_tier_in_context():
    """Every cycle must stamp the context with its own tier, not the default."""
    async def run():
        for cycle_cls, expected_tier in [
            (MetaCycle, CycleTier.META),
            (MacroCycle, CycleTier.MACRO),
            (MesoCycle, CycleTier.MESO),
            (MicroCycle, CycleTier.MICRO),
        ]:
            cycle = cycle_cls()
            assert cycle.tier == expected_tier
            assert cycle.context.tier == expected_tier

    asyncio.run(run())


def test_spawn_child_inherits_settings_and_policy():
    """Children spawned via spawn_child must inherit the parent's settings and delegation policy."""
    async def run():
        parent = MesoCycle()
        child = parent.spawn_child(MicroCycle)
        assert child.settings is parent.settings
        assert child.delegation_policy is parent.delegation_policy

    asyncio.run(run())
