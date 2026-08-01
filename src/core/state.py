"""
State Checkpointing and Backtracking Management.
"""

from typing import Dict, Optional, List
import copy
from src.core.types import Checkpoint, StateContext, CycleStatus, CyclePhase


class CheckpointManager:
    """
    Manages persistent and in-memory checkpoints for stateful cognitive cycles,
    enabling point-in-time rewind and backtracking upon reflection failure.
    """

    def __init__(self, max_checkpoints: int = 100):
        self.max_checkpoints = max_checkpoints
        self._checkpoints: Dict[str, Checkpoint] = {}
        self._cycle_history: Dict[str, List[str]] = {}

    def create_checkpoint(self, context: StateContext) -> Checkpoint:
        """
        Takes a snapshot of the current StateContext.
        """
        state_snapshot = context.model_dump()
        checkpoint = Checkpoint(
            cycle_id=context.cycle_id,
            tier=context.tier,
            phase=context.current_phase,
            state_data=state_snapshot,
            step_number=context.step_count,
        )

        self._checkpoints[checkpoint.checkpoint_id] = checkpoint
        
        if context.cycle_id not in self._cycle_history:
            self._cycle_history[context.cycle_id] = []
        self._cycle_history[context.cycle_id].append(checkpoint.checkpoint_id)

        # Enforce storage limits
        if len(self._checkpoints) > self.max_checkpoints:
            oldest_id = list(self._checkpoints.keys())[0]
            del self._checkpoints[oldest_id]

        context.active_checkpoint_id = checkpoint.checkpoint_id
        return checkpoint

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """
        Retrieves a checkpoint by ID.
        """
        return self._checkpoints.get(checkpoint_id)

    def restore_checkpoint(self, checkpoint_id: str) -> Optional[StateContext]:
        """
        Restores a StateContext from a checkpoint ID.
        """
        checkpoint = self.get_checkpoint(checkpoint_id)
        if not checkpoint:
            return None

        # Re-instantiate StateContext from state snapshot
        restored_context = StateContext.model_validate(checkpoint.state_data)
        restored_context.status = CycleStatus.CHECKPOINTED
        return restored_context

    def backtrack(self, context: StateContext) -> StateContext:
        """
        Rewinds the context state to the most recent valid checkpoint for the cycle.
        """
        history = self._cycle_history.get(context.cycle_id, [])
        if not history:
            # Fallback if no prior checkpoint exists
            context.status = CycleStatus.FAILED
            return context

        last_checkpoint_id = history[-1]
        restored = self.restore_checkpoint(last_checkpoint_id)
        if not restored:
            context.status = CycleStatus.FAILED
            return context

        restored.backtrack_count = context.backtrack_count + 1
        restored.status = CycleStatus.BACKTRACKING
        restored.current_phase = CyclePhase.PLANNING  # Re-route to planning
        return restored
