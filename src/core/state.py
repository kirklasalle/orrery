"""
State Checkpointing and Disk Persistence Management.
"""

from typing import Dict, Optional, List
import os
import json
import logging
from pathlib import Path
from src.core.types import Checkpoint, StateContext, CycleStatus, CyclePhase

logger = logging.getLogger(__name__)


class CheckpointManager:
    """
    Manages persistent disk and in-memory checkpoints for stateful cognitive cycles,
    enabling point-in-time rewind, backtracking, and cross-session resume.
    """

    def __init__(self, max_checkpoints: int = 100, storage_dir: str = ".checkpoints"):
        self.max_checkpoints = max_checkpoints
        self.storage_dir = Path(storage_dir)
        self._checkpoints: Dict[str, Checkpoint] = {}
        self._cycle_history: Dict[str, List[str]] = {}
        
        # Ensure storage directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_checkpoint(self, context: StateContext) -> Checkpoint:
        """
        Takes a snapshot of the current StateContext, stores in memory and persists to disk.
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

        # Enforce in-memory storage limits
        if len(self._checkpoints) > self.max_checkpoints:
            oldest_id = list(self._checkpoints.keys())[0]
            del self._checkpoints[oldest_id]

        context.active_checkpoint_id = checkpoint.checkpoint_id
        
        # Persist to disk
        self._save_to_disk(checkpoint)
        
        return checkpoint

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """
        Retrieves a checkpoint by ID from memory or disk.
        """
        if checkpoint_id in self._checkpoints:
            return self._checkpoints[checkpoint_id]
        
        # Fallback to disk read
        return self._load_from_disk(checkpoint_id)

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
            context.status = CycleStatus.FAILED
            return context

        last_checkpoint_id = history[-1]
        restored = self.restore_checkpoint(last_checkpoint_id)
        if not restored:
            context.status = CycleStatus.FAILED
            return context

        restored.backtrack_count = context.backtrack_count + 1
        restored.status = CycleStatus.BACKTRACKING
        restored.current_phase = CyclePhase.PLANNING  # Re-route to planning phase
        return restored

    def _save_to_disk(self, checkpoint: Checkpoint) -> Path:
        """
        Serializes a checkpoint object to disk in JSON format.
        """
        cycle_dir = self.storage_dir / checkpoint.cycle_id
        cycle_dir.mkdir(parents=True, exist_ok=True)
        filepath = cycle_dir / f"{checkpoint.checkpoint_id}.json"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(checkpoint.model_dump_json(indent=2))

        return filepath

    def _load_from_disk(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """
        Searches disk for a checkpoint JSON file and loads it.
        """
        for cycle_dir in self.storage_dir.glob("*"):
            if cycle_dir.is_dir():
                target_file = cycle_dir / f"{checkpoint_id}.json"
                if target_file.exists():
                    try:
                        with open(target_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        checkpoint = Checkpoint.model_validate(data)
                        self._checkpoints[checkpoint.checkpoint_id] = checkpoint
                        return checkpoint
                    except Exception as e:
                        logger.error(f"Failed to load checkpoint from disk ({target_file}): {e}")
        return None
