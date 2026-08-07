"""
State Checkpointing and Disk Persistence Management.
"""

from typing import Dict, Optional, List
import os
import json
import logging
from pathlib import Path
from orrery.core import integrity
from orrery.core.integrity import ChainVerification, IntegrityError
from orrery.core.types import Checkpoint, StateContext, CycleStatus, CyclePhase, validate_identifier

logger = logging.getLogger(__name__)


class CheckpointManager:
    """
    Manages persistent disk and in-memory checkpoints for stateful cognitive cycles,
    enabling point-in-time rewind, backtracking, and cross-session resume.

    Checkpoints form a per-cycle hash chain, so an altered or truncated history is
    detectable rather than merely unlikely.
    """

    def __init__(
        self,
        max_checkpoints: int = 100,
        storage_dir: str = ".checkpoints",
        max_checkpoints_on_disk_per_cycle: int = 50,
        verify_on_load: bool = True,
        require_signature: bool = False,
        require_asymmetric: bool = False,
    ):
        self.max_checkpoints = max_checkpoints
        self.max_checkpoints_on_disk_per_cycle = max_checkpoints_on_disk_per_cycle
        self.verify_on_load = verify_on_load
        self.require_signature = require_signature or require_asymmetric
        self.require_asymmetric = require_asymmetric
        self.storage_dir = Path(storage_dir)
        self._checkpoints: Dict[str, Checkpoint] = {}
        self._cycle_history: Dict[str, List[str]] = {}
        self._chain_head: Dict[str, str] = {}

        # Ensure storage directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_within_storage(self, *parts: str) -> Path:
        """
        Resolves a path beneath the storage root, rejecting any result that escapes it.
        """
        root = self.storage_dir.resolve()
        candidate = root.joinpath(*parts).resolve()

        if candidate != root and not candidate.is_relative_to(root):
            raise ValueError(f"Refusing checkpoint path outside storage root: {candidate}")

        return candidate

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
        integrity.seal(checkpoint, self._chain_head.get(context.cycle_id))
        self._chain_head[context.cycle_id] = checkpoint.content_hash or integrity.GENESIS_HASH

        self._checkpoints[checkpoint.checkpoint_id] = checkpoint
        
        if context.cycle_id not in self._cycle_history:
            self._cycle_history[context.cycle_id] = []
        self._cycle_history[context.cycle_id].append(checkpoint.checkpoint_id)

        self._evict_from_memory()

        context.active_checkpoint_id = checkpoint.checkpoint_id
        
        # Persist to disk
        self._save_to_disk(checkpoint)
        self._prune_disk(context.cycle_id)
        
        return checkpoint

    def _evict_from_memory(self) -> None:
        """
        Evicts oldest in-memory checkpoints, never the head of a cycle's chain, which
        backtracking still needs. Evicted entries remain readable from disk.
        """
        if len(self._checkpoints) <= self.max_checkpoints:
            return

        protected = {history[-1] for history in self._cycle_history.values() if history}
        for checkpoint_id in list(self._checkpoints.keys()):
            if len(self._checkpoints) <= self.max_checkpoints:
                break
            if checkpoint_id not in protected:
                del self._checkpoints[checkpoint_id]

    def _prune_disk(self, cycle_id: str) -> None:
        """
        Bounds unattended disk growth by deleting the oldest checkpoints of a cycle.
        Pruning truncates the head of the hash chain; it never rewrites a link, so the
        surviving chain still verifies and reports itself as truncated.
        """
        limit = self.max_checkpoints_on_disk_per_cycle
        if limit <= 0:
            return

        history = self._cycle_history.get(cycle_id, [])
        overflow = len(history) - limit
        if overflow <= 0:
            return

        for checkpoint_id in history[:overflow]:
            try:
                self._resolve_within_storage(cycle_id, f"{checkpoint_id}.json").unlink(missing_ok=True)
            except (OSError, ValueError) as exc:
                logger.warning("Could not prune checkpoint %s: %s", checkpoint_id, exc)
            self._checkpoints.pop(checkpoint_id, None)

        self._cycle_history[cycle_id] = history[overflow:]

    def purge_cycle(self, cycle_id: str) -> int:
        """
        Removes every checkpoint for a cycle from memory and disk. Returns the count removed.
        """
        removed = 0
        for checkpoint_id in self._cycle_history.pop(cycle_id, []):
            self._checkpoints.pop(checkpoint_id, None)
            try:
                path = self._resolve_within_storage(cycle_id, f"{checkpoint_id}.json")
            except ValueError:
                continue
            if path.exists():
                path.unlink()
                removed += 1

        self._chain_head.pop(cycle_id, None)
        try:
            cycle_dir = self._resolve_within_storage(cycle_id)
        except ValueError:
            return removed
        if cycle_dir.is_dir() and not any(cycle_dir.iterdir()):
            cycle_dir.rmdir()
        return removed

    def verify_chain(self, cycle_id: str) -> ChainVerification:
        """
        Walks a cycle's checkpoints, confirming each digest and each link to its predecessor.
        """
        history = self._cycle_history.get(cycle_id, [])
        result = ChainVerification(cycle_id=cycle_id, verified=True, checked=0)
        if not history:
            return result

        expected_prev: Optional[str] = None
        for position, checkpoint_id in enumerate(history):
            checkpoint = self.get_checkpoint(checkpoint_id)
            if checkpoint is None:
                result.verified = False
                result.failures.append(f"checkpoint {checkpoint_id} is missing from the chain")
                continue

            reason = integrity.verify(
                checkpoint,
                require_signature=self.require_signature,
                require_asymmetric=self.require_asymmetric,
            )
            if reason:
                result.verified = False
                result.failures.append(reason)

            if position == 0:
                result.truncated = checkpoint.prev_hash not in (None, integrity.GENESIS_HASH)
            elif checkpoint.prev_hash != expected_prev:
                result.verified = False
                result.failures.append(
                    f"checkpoint {checkpoint_id} does not link to its predecessor"
                )

            expected_prev = checkpoint.content_hash
            result.checked += 1

        return result

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

        Rollback rewinds work, never the record of it: the step counter, lessons, and
        attempt log survive so the next attempt is informed rather than identical.
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

        restored.step_count = max(restored.step_count, context.step_count)
        restored.backtrack_count = context.backtrack_count + 1
        restored.lessons = list(context.lessons)
        restored.attempt_log = list(context.attempt_log)
        restored.status = CycleStatus.BACKTRACKING
        restored.current_phase = CyclePhase.PLANNING  # Re-route to planning phase
        return restored

    def _save_to_disk(self, checkpoint: Checkpoint) -> Path:
        """
        Serializes a checkpoint object to disk in JSON format.
        """
        cycle_dir = self._resolve_within_storage(checkpoint.cycle_id)
        cycle_dir.mkdir(parents=True, exist_ok=True)
        filepath = self._resolve_within_storage(checkpoint.cycle_id, f"{checkpoint.checkpoint_id}.json")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(checkpoint.model_dump_json(indent=2))

        # Checkpoints carry full goal and state data; restrict to the owning user.
        os.chmod(filepath, 0o600)

        return filepath

    def _load_from_disk(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """
        Searches disk for a checkpoint JSON file and loads it.
        """
        try:
            validate_identifier(checkpoint_id)
        except ValueError:
            logger.error(f"Rejected malformed checkpoint identifier: {checkpoint_id!r}")
            return None

        for cycle_dir in self.storage_dir.glob("*"):
            if cycle_dir.is_dir():
                target_file = cycle_dir / f"{checkpoint_id}.json"
                if target_file.exists():
                    try:
                        with open(target_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        checkpoint = Checkpoint.model_validate(data)
                    except Exception as e:
                        logger.error(f"Failed to load checkpoint from disk ({target_file}): {e}")
                        return None

                    if self.verify_on_load:
                        reason = integrity.verify(
                            checkpoint,
                            require_signature=self.require_signature,
                            require_asymmetric=self.require_asymmetric,
                        )
                        if reason:
                            # A checkpoint that cannot be trusted must not be restored from.
                            logger.error("Refusing tampered checkpoint from %s: %s", target_file, reason)
                            if self.require_signature:
                                raise IntegrityError(reason)
                            return None

                    self._checkpoints[checkpoint.checkpoint_id] = checkpoint
                    return checkpoint
        return None
