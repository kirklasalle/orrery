"""
Tests for CycleDispatcher state machine transitions across 4 phases.
"""

import asyncio
from src.core.dispatcher import CycleDispatcher
from src.core.types import StateContext, CyclePhase, CycleStatus, CycleTier


def test_dispatcher_single_step_transitions():
    async def run():
        context = StateContext(goal="Test transition pipeline", tier=CycleTier.META)
        dispatcher = CycleDispatcher()

        # Step 1: PERCEPTION -> PLANNING
        assert context.current_phase == CyclePhase.PERCEPTION
        context = await dispatcher.step(context)
        assert context.current_phase == CyclePhase.PLANNING
        assert len(context.hypotheses) > 0

        # Step 2: PLANNING -> EXECUTION
        context = await dispatcher.step(context)
        assert context.current_phase == CyclePhase.EXECUTION
        assert len(context.planned_actions) > 0

        # Step 3: EXECUTION -> REFLECTION
        context = await dispatcher.step(context)
        assert context.current_phase == CyclePhase.REFLECTION
        assert len(context.execution_receipts) > 0

        # Step 4: REFLECTION -> COMPLETED
        context = await dispatcher.step(context)
        assert context.status == CycleStatus.COMPLETED
        assert len(context.critiques) > 0
        assert context.critiques[-1].passed is True

    asyncio.run(run())


def test_dispatcher_run_full_cycle():
    async def run():
        context = StateContext(goal="Test full cycle run", tier=CycleTier.MACRO)
        dispatcher = CycleDispatcher()

        final_context = await dispatcher.run_full_cycle(context)
        assert final_context.status == CycleStatus.COMPLETED
        assert final_context.step_count == 4

    asyncio.run(run())
