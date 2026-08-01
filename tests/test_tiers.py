"""
Tests for Hierarchical Abstraction Tiers (Meta, Macro, Meso, Micro).
"""

import asyncio
from src.core.types import StateContext, CycleTier, CycleStatus
from src.cycles.meta import MetaCycle
from src.cycles.macro import MacroCycle
from src.cycles.meso import MesoCycle
from src.cycles.micro import MicroCycle


def test_meta_cycle_execution():
    async def run():
        context = StateContext(goal="High-level strategy goal", tier=CycleTier.META)
        meta = MetaCycle(context=context)
        result = await meta.run_cycle()
        assert result.status == CycleStatus.COMPLETED
        assert result.tier == CycleTier.META
        assert any("[META]" in h for h in result.hypotheses)

    asyncio.run(run())


def test_macro_cycle_execution():
    async def run():
        context = StateContext(goal="Workflow sequence goal", tier=CycleTier.MACRO)
        macro = MacroCycle(context=context)
        result = await macro.run_cycle()
        assert result.status == CycleStatus.COMPLETED
        assert result.tier == CycleTier.MACRO

    asyncio.run(run())


def test_meso_cycle_execution():
    async def run():
        context = StateContext(goal="Tool chain goal", tier=CycleTier.MESO)
        meso = MesoCycle(context=context)
        result = await meso.run_cycle()
        assert result.status == CycleStatus.COMPLETED
        assert result.tier == CycleTier.MESO

    asyncio.run(run())


def test_micro_cycle_execution():
    async def run():
        context = StateContext(goal="Atomic visual action goal", tier=CycleTier.MICRO)
        micro = MicroCycle(context=context)
        result = await micro.run_cycle()
        assert result.status == CycleStatus.COMPLETED
        assert result.tier == CycleTier.MICRO

    asyncio.run(run())
