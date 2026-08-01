"""
Tests for Meta-Skills: Checkpointing, Backtracking, and Self-Critique.
"""

import asyncio
from src.core.types import (
    StateContext,
    CyclePhase,
    CycleStatus,
    CycleTier,
    ExecutionReceipt,
    ActionPayload,
)
from src.core.state import CheckpointManager
from src.core.critique import SelfCritiqueEngine
from src.core.dispatcher import CycleDispatcher


def test_checkpointing_and_restore():
    manager = CheckpointManager()
    context = StateContext(goal="Checkpoint test", tier=CycleTier.MESO)
    context.variables["test_key"] = "test_val"

    checkpoint = manager.create_checkpoint(context)
    assert checkpoint.checkpoint_id is not None
    assert checkpoint.phase == CyclePhase.PERCEPTION

    # Mutate context
    context.variables["test_key"] = "mutated_val"

    # Restore from checkpoint
    restored = manager.restore_checkpoint(checkpoint.checkpoint_id)
    assert restored is not None
    assert restored.variables["test_key"] == "test_val"
    assert restored.status == CycleStatus.CHECKPOINTED


def test_self_critique_evaluation_passed():
    engine = SelfCritiqueEngine(threshold=0.70)
    context = StateContext(goal="Critique pass test")
    
    # Add successful execution receipts
    context.planned_actions.append(ActionPayload(action_name="act_1"))
    context.execution_receipts.append(
        ExecutionReceipt(action_id="act_1", action_name="act_1", success=True)
    )

    result = engine.evaluate(context)
    assert result.passed is True
    assert result.score == 1.0


def test_self_critique_evaluation_failed():
    engine = SelfCritiqueEngine(threshold=0.70)
    context = StateContext(goal="Critique fail test")
    
    # Add failed execution receipts
    context.planned_actions.append(ActionPayload(action_name="act_1"))
    context.execution_receipts.append(
        ExecutionReceipt(action_id="act_1", action_name="act_1", success=False, error="Execution timeout")
    )

    result = engine.evaluate(context)
    assert result.passed is False
    assert result.score == 0.0
    assert len(result.recommendations) > 0


def test_backtracking_trigger_on_failed_reflection():
    async def run():
        context = StateContext(goal="Backtracking simulation", tier=CycleTier.MICRO)
        dispatcher = CycleDispatcher()

        # Custom execution handler that forces failure
        async def failing_execution_handler(ctx: StateContext) -> StateContext:
            ctx.execution_receipts.append(
                ExecutionReceipt(action_id="f1", action_name="fail_action", success=False, error="Simulated failure")
            )
            return ctx

        dispatcher.register_handler(CyclePhase.EXECUTION, failing_execution_handler)

        # Run step 1: PERCEPTION (creates checkpoint) -> PLANNING
        context = await dispatcher.step(context)
        # Run step 2: PLANNING -> EXECUTION
        context = await dispatcher.step(context)
        # Run step 3: EXECUTION -> REFLECTION (runs failing execution)
        context = await dispatcher.step(context)
        # Run step 4: REFLECTION (critique fails score=0.0 -> triggers backtrack to PLANNING)
        context = await dispatcher.step(context)

        assert context.status == CycleStatus.BACKTRACKING
        assert context.backtrack_count == 1
        assert context.current_phase == CyclePhase.PLANNING

    asyncio.run(run())
