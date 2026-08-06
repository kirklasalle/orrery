"""
Tests for checkpoint tamper-evidence, chain verification, and retention.
"""

import json
import os
import uuid

import pytest

from orrery.core import integrity
from orrery.core.integrity import IntegrityError
from orrery.core.state import CheckpointManager
from orrery.core.types import CyclePhase, CycleTier, StateContext


def _manager(tmp_path, **kwargs) -> CheckpointManager:
    return CheckpointManager(storage_dir=str(tmp_path / "checkpoints"), **kwargs)


def _checkpoint_path(manager: CheckpointManager, checkpoint) -> "os.PathLike":
    return manager.storage_dir / checkpoint.cycle_id / f"{checkpoint.checkpoint_id}.json"


def test_checkpoint_is_sealed_with_a_digest(tmp_path):
    manager = _manager(tmp_path)
    context = StateContext(goal="seal me")

    checkpoint = manager.create_checkpoint(context)

    assert checkpoint.content_hash and len(checkpoint.content_hash) == 64
    assert checkpoint.prev_hash == integrity.GENESIS_HASH
    assert integrity.verify(checkpoint) is None


def test_checkpoints_form_a_chain(tmp_path):
    manager = _manager(tmp_path)
    context = StateContext(goal="chain me")

    first = manager.create_checkpoint(context)
    context.current_phase = CyclePhase.PLANNING
    second = manager.create_checkpoint(context)

    assert second.prev_hash == first.content_hash

    result = manager.verify_chain(context.cycle_id)
    assert result.verified, result.summary
    assert result.checked == 2


def test_edited_checkpoint_file_is_refused_on_load(tmp_path):
    manager = _manager(tmp_path)
    context = StateContext(goal="original goal")
    checkpoint = manager.create_checkpoint(context)

    path = _checkpoint_path(manager, checkpoint)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["state_data"]["goal"] = "attacker's goal"
    path.write_text(json.dumps(payload), encoding="utf-8")

    # Drop the in-memory copy so the read has to come from the edited file.
    manager._checkpoints.clear()

    assert manager.get_checkpoint(checkpoint.checkpoint_id) is None
    assert manager.restore_checkpoint(checkpoint.checkpoint_id) is None


def test_broken_link_is_detected_even_when_each_checkpoint_is_self_consistent(tmp_path):
    manager = _manager(tmp_path)
    context = StateContext(goal="chain me")
    manager.create_checkpoint(context)
    context.current_phase = CyclePhase.PLANNING
    second = manager.create_checkpoint(context)

    # Re-seal the second checkpoint onto a predecessor that never existed. Its own digest
    # is valid, so only the chain walk can catch this.
    integrity.seal(second, prev_hash="f" * 64)

    result = manager.verify_chain(context.cycle_id)
    assert not result.verified
    assert "does not link to its predecessor" in result.summary


def test_signature_is_required_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv(integrity.CHECKPOINT_KEY_ENV, "correct-horse-battery-staple")
    manager = _manager(tmp_path, require_signature=True)
    context = StateContext(goal="sign me")

    checkpoint = manager.create_checkpoint(context)
    assert checkpoint.signature is not None
    assert integrity.verify(checkpoint, require_signature=True) is None

    # A different key must not validate the same digest.
    monkeypatch.setenv(integrity.CHECKPOINT_KEY_ENV, "wrong-key")
    assert integrity.verify(checkpoint, require_signature=True) is not None


def test_unsigned_checkpoint_raises_when_signature_is_required(tmp_path, monkeypatch):
    monkeypatch.delenv(integrity.CHECKPOINT_KEY_ENV, raising=False)
    manager = _manager(tmp_path, require_signature=True)
    context = StateContext(goal="unsigned")
    checkpoint = manager.create_checkpoint(context)

    manager._checkpoints.clear()

    with pytest.raises(IntegrityError):
        manager.get_checkpoint(checkpoint.checkpoint_id)


def test_disk_retention_prunes_oldest_and_keeps_the_head(tmp_path):
    manager = _manager(tmp_path, max_checkpoints_on_disk_per_cycle=3)
    context = StateContext(goal="prune me")

    created = [manager.create_checkpoint(context) for _ in range(6)]

    cycle_dir = manager.storage_dir / context.cycle_id
    assert len(list(cycle_dir.glob("*.json"))) == 3
    assert _checkpoint_path(manager, created[-1]).exists()
    assert not _checkpoint_path(manager, created[0]).exists()

    # The surviving chain still verifies, and reports that it was truncated.
    result = manager.verify_chain(context.cycle_id)
    assert result.verified, result.summary
    assert result.truncated


def test_memory_eviction_never_drops_a_cycles_head(tmp_path):
    manager = _manager(tmp_path, max_checkpoints=2, max_checkpoints_on_disk_per_cycle=0)
    heads = []
    for _ in range(5):
        context = StateContext(goal="evict me")
        manager.create_checkpoint(context)
        heads.append(manager._cycle_history[context.cycle_id][-1])

    for head in heads:
        assert head in manager._checkpoints


def test_purge_cycle_removes_memory_and_disk(tmp_path):
    manager = _manager(tmp_path)
    context = StateContext(goal="purge me")
    for _ in range(3):
        manager.create_checkpoint(context)

    removed = manager.purge_cycle(context.cycle_id)

    assert removed == 3
    assert context.cycle_id not in manager._cycle_history
    assert not (manager.storage_dir / context.cycle_id).exists()


def test_backtracking_still_works_over_a_sealed_chain(tmp_path):
    manager = _manager(tmp_path)
    context = StateContext(goal="rewind me")
    manager.create_checkpoint(context)
    context.step_count = 7
    context.lessons.append("do not repeat that")

    restored = manager.backtrack(context)

    assert restored.step_count == 7
    assert restored.lessons == ["do not repeat that"]
    assert restored.backtrack_count == 1


def test_missing_checkpoint_id_is_rejected_before_disk_access(tmp_path):
    manager = _manager(tmp_path)
    assert manager.get_checkpoint("../../etc/passwd") is None
    assert manager.get_checkpoint(str(uuid.uuid4())) is None
