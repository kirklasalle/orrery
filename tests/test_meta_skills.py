"""
Tests for Meta-Skills: Checkpointing, Disk Persistence, Backtracking, and Self-Critique.
"""

import asyncio
from pathlib import Path
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
    manager = CheckpointManager(storage_dir=".test_checkpoints")
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


def test_disk_checkpoint_persistence():
    storage_dir = ".test_checkpoints_disk"
    manager = CheckpointManager(storage_dir=storage_dir)
    context = StateContext(goal="Disk persistence test", tier=CycleTier.MACRO)
    context.variables["disk_key"] = "saved_on_disk"

    checkpoint = manager.create_checkpoint(context)
    
    # Verify file exists on disk
    expected_path = Path(storage_dir) / context.cycle_id / f"{checkpoint.checkpoint_id}.json"
    assert expected_path.exists()

    # Clear in-memory cache to force disk load
    manager._checkpoints.clear()
    
    loaded = manager.get_checkpoint(checkpoint.checkpoint_id)
    assert loaded is not None
    assert loaded.checkpoint_id == checkpoint.checkpoint_id

    restored = manager.restore_checkpoint(checkpoint.checkpoint_id)
    assert restored is not None
    assert restored.variables["disk_key"] == "saved_on_disk"


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

        # Step 1: PERCEPTION (creates checkpoint) -> PLANNING
        context = await dispatcher.step(context)
        # Step 2: PLANNING -> EXECUTION
        context = await dispatcher.step(context)
        # Step 3: EXECUTION -> REFLECTION (runs failing execution)
        context = await dispatcher.step(context)
        # Step 4: REFLECTION (critique fails score=0.0 -> triggers backtrack to PLANNING)
        context = await dispatcher.step(context)

        assert context.status == CycleStatus.BACKTRACKING
        assert context.backtrack_count == 1
        assert context.current_phase == CyclePhase.PLANNING

    asyncio.run(run())
