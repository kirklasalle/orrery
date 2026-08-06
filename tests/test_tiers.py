"""
Tests for Hierarchical Abstraction Tiers (Meta, Macro, Meso, Micro).
"""

import asyncio
from orrery.core.types import StateContext, CycleTier, CycleStatus
from orrery.cycles.base import BaseCycle
from orrery.cycles.meta import MetaCycle
from orrery.cycles.macro import MacroCycle
from orrery.cycles.meso import MesoCycle
from orrery.cycles.micro import MicroCycle
from tests.conftest import StubAdapter


def _wire(cycle: BaseCycle, **kwargs) -> BaseCycle:
    cycle.register_adapter(StubAdapter(**kwargs), name="default")
    return cycle


def test_meta_cycle_execution():
    async def run():
        context = StateContext(goal="High-level strategy goal", tier=CycleTier.META)
        meta = _wire(MetaCycle(context=context))
        result = await meta.run_cycle()
        assert result.status == CycleStatus.COMPLETED
        assert result.tier == CycleTier.META
        assert any("[META]" in h for h in result.hypotheses)

    asyncio.run(run())


def test_macro_cycle_execution():
    async def run():
        context = StateContext(goal="Workflow sequence goal", tier=CycleTier.MACRO)
        macro = _wire(MacroCycle(context=context))
        result = await macro.run_cycle()
        assert result.status == CycleStatus.COMPLETED
        assert result.tier == CycleTier.MACRO

    asyncio.run(run())


def test_meso_cycle_execution():
    async def run():
        context = StateContext(goal="Tool chain goal", tier=CycleTier.MESO)
        meso = _wire(MesoCycle(context=context))
        result = await meso.run_cycle()
        assert result.status == CycleStatus.COMPLETED
        assert result.tier == CycleTier.MESO

    asyncio.run(run())


def test_micro_cycle_execution():
    async def run():
        context = StateContext(goal="Atomic visual action goal", tier=CycleTier.MICRO)
        micro = _wire(MicroCycle(context=context))
        result = await micro.run_cycle()
        assert result.status == CycleStatus.COMPLETED
        assert result.tier == CycleTier.MICRO

    asyncio.run(run())


def test_tier_without_adapter_fails():
    """A tier with nothing to execute against must report failure, not success."""

    async def run():
        context = StateContext(goal="Nothing is wired up", tier=CycleTier.MICRO)
        result = await MicroCycle(context=context).run_cycle()
        assert result.status == CycleStatus.FAILED

    asyncio.run(run())


def test_delegation_shares_checkpoint_lineage_and_adapters():
    async def run():
        parent = _wire(MesoCycle(context=StateContext(goal="Parent goal", tier=CycleTier.MESO)))
        child = MicroCycle()

        await parent.delegate_to_child(child)

        assert child.checkpoint_manager is parent.checkpoint_manager
        assert "default" in child.dispatcher.adapters

    asyncio.run(run())


def test_child_failure_propagates_to_parent():
    """A failed child must fail the parent's reflection rather than vanish into a variable."""

    async def run():
        parent = MesoCycle(context=StateContext(goal="Parent goal", tier=CycleTier.MESO))
        child = MicroCycle()  # no adapter: guaranteed to fail

        child_result = await parent.delegate_to_child(child)

        assert child_result.status == CycleStatus.FAILED
        assert parent.context.variables["child_micro_failed"] is True
        assert any(
            r.action_name == "delegate_to_micro" and not r.success
            for r in parent.context.execution_receipts
        )

    asyncio.run(run())
