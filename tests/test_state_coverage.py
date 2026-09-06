"""
Additional state module tests to close coverage gaps.

Targets: memory eviction, disk pruning edge cases, purge_cycle, verify_chain
failures, backtrack_to_checkpoint edge cases, and _load_from_disk error paths.
"""

import json
from pathlib import Path

import pytest

from orrery.core.state import CheckpointManager
from orrery.core.types import StateContext, CycleTier, CycleStatus, CyclePhase


# --- Memory eviction ---


def test_evict_from_memory_removes_oldest_unprotected(tmp_path):
    """When more checkpoints exist than max_checkpoints, the oldest unprotected are evicted."""
    manager = CheckpointManager(storage_dir=str(tmp_path / "cp"), max_checkpoints=3)
    ctx = StateContext(goal="Eviction test")

    checkpoints = []
    for i in range(5):
        cp = manager.create_checkpoint(ctx)
        checkpoints.append(cp.checkpoint_id)

    # Only 3 should survive in memory; the most recent + protected ones
    assert len(manager._checkpoints) <= 3


def test_evict_protects_chain_heads(tmp_path):
    """The head of each cycle's chain should never be evicted."""
    manager = CheckpointManager(storage_dir=str(tmp_path / "cp"), max_checkpoints=2)

    ctx1 = StateContext(goal="Cycle 1")
    cp1 = manager.create_checkpoint(ctx1)

    ctx2 = StateContext(goal="Cycle 2")
    cp2 = manager.create_checkpoint(ctx2)
    cp3 = manager.create_checkpoint(ctx2)

    # Both chain heads should be accessible
    assert manager.get_checkpoint(cp1.checkpoint_id) is not None
    assert manager.get_checkpoint(cp3.checkpoint_id) is not None


# --- Disk pruning ---


def test_prune_disk_truncates_oldest(tmp_path):
    """When a cycle exceeds the disk limit, the oldest checkpoints are pruned."""
    manager = CheckpointManager(
        storage_dir=str(tmp_path / "cp"),
        max_checkpoints=100,  # Don't evict from memory
        max_checkpoints_on_disk_per_cycle=3,
    )
    ctx = StateContext(goal="Pruning test")

    for _ in range(6):
        manager.create_checkpoint(ctx)

    history = manager._cycle_history.get(ctx.cycle_id, [])
    assert len(history) <= 3


# --- purge_cycle ---


def test_purge_cycle_removes_all_checkpoints(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path / "cp"))
    ctx = StateContext(goal="Purge test")

    cp1 = manager.create_checkpoint(ctx)
    cp2 = manager.create_checkpoint(ctx)
    cycle_id = ctx.cycle_id

    removed = manager.purge_cycle(cycle_id)
    assert removed >= 1
    assert manager.get_checkpoint(cp1.checkpoint_id) is None
    assert manager.get_checkpoint(cp2.checkpoint_id) is None
    assert cycle_id not in manager._cycle_history


def test_purge_nonexistent_cycle_returns_zero(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path / "cp"))
    assert manager.purge_cycle("nonexistent-cycle-id") == 0


# --- verify_chain ---


def test_verify_chain_empty_history(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path / "cp"))
    result = manager.verify_chain("no-such-cycle")
    assert result.verified
    assert result.checked == 0


def test_verify_chain_detects_missing_checkpoint(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path / "cp"))
    ctx = StateContext(goal="Chain test")
    cp = manager.create_checkpoint(ctx)
    cycle_id = ctx.cycle_id

    # Remove the checkpoint from memory and disk to simulate corruption
    del manager._checkpoints[cp.checkpoint_id]
    checkpoint_files = list((tmp_path / "cp").rglob(f"{cp.checkpoint_id}.json"))
    for f in checkpoint_files:
        f.unlink()

    result = manager.verify_chain(cycle_id)
    assert not result.verified
    assert any("missing" in f for f in result.failures)


def test_verify_chain_detects_tampered_checkpoint(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path / "cp"))
    ctx = StateContext(goal="Tamper test")
    cp = manager.create_checkpoint(ctx)
    cycle_id = ctx.cycle_id

    # Tamper with the checkpoint's content hash
    stored = manager._checkpoints[cp.checkpoint_id]
    stored.content_hash = "0" * 64

    result = manager.verify_chain(cycle_id)
    assert not result.verified


# --- backtrack ---


def test_backtrack_with_no_checkpoints_fails(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path / "cp"))
    ctx = StateContext(goal="No checkpoints")
    result = manager.backtrack(ctx)
    assert result.status == CycleStatus.FAILED


def test_backtrack_restores_to_last_checkpoint(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path / "cp"))
    ctx = StateContext(goal="Backtrack test")
    ctx.hypotheses.append("original hypothesis")

    cp = manager.create_checkpoint(ctx)

    # Modify context after checkpointing
    ctx.hypotheses.append("new hypothesis after checkpoint")
    ctx.step_count = 5

    restored = manager.backtrack(ctx)
    assert restored.status == CycleStatus.BACKTRACKING
    assert restored.current_phase == CyclePhase.PLANNING
    assert restored.backtrack_count == 1
    assert restored.step_count >= 5  # Preserves step count


# --- _load_from_disk error paths ---


def test_load_from_disk_with_corrupt_json(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path / "cp"))
    ctx = StateContext(goal="Corrupt load test")
    cp = manager.create_checkpoint(ctx)
    cycle_id = ctx.cycle_id
    cp_id = cp.checkpoint_id

    # Remove from memory so it tries to load from disk
    del manager._checkpoints[cp_id]

    # Corrupt the file
    for f in (tmp_path / "cp").rglob(f"{cp_id}.json"):
        f.write_text("{{{invalid json", encoding="utf-8")

    result = manager.get_checkpoint(cp_id)
    assert result is None


def test_load_from_disk_rejects_malformed_identifier(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path / "cp"))
    # A path-traversal-style identifier should be rejected
    result = manager._load_from_disk("../../etc/passwd")
    assert result is None
