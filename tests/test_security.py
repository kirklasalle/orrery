"""
Security regression tests: checkpoint identifier validation and path containment.
"""

import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from orrery.core.state import CheckpointManager
from orrery.core.types import (
    Checkpoint,
    CyclePhase,
    CycleTier,
    StateContext,
    validate_identifier,
)

TRAVERSAL_IDS = [
    "../../ESCAPED",
    "..\\..\\ESCAPED",
    "/absolute/path",
    "C:\\Windows\\Temp",
    "nested/child",
    "",
    "not-a-uuid",
    "urn:uuid:3f2b8c1e-0a4d-4c7e-9b1f-2d6a5e8c4b70",
    "{3f2b8c1e-0a4d-4c7e-9b1f-2d6a5e8c4b70}",
    "3F2B8C1E-0A4D-4C7E-9B1F-2D6A5E8C4B70",
]


@pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
def test_validate_identifier_rejects_non_canonical_uuid(bad_id):
    with pytest.raises(ValueError):
        validate_identifier(bad_id)


def test_validate_identifier_accepts_canonical_uuid():
    good = str(uuid.uuid4())
    assert validate_identifier(good) == good


@pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
def test_state_context_rejects_traversal_on_construction(bad_id):
    with pytest.raises(ValidationError):
        StateContext(goal="attack", cycle_id=bad_id)


@pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
def test_state_context_rejects_traversal_on_assignment(bad_id):
    context = StateContext(goal="attack")
    with pytest.raises(ValidationError):
        context.cycle_id = bad_id


def test_checkpoint_rejects_traversal_cycle_id():
    with pytest.raises(ValidationError):
        Checkpoint(
            cycle_id="../../ESCAPED",
            tier=CycleTier.META,
            phase=CyclePhase.PERCEPTION,
            state_data={},
        )


def test_active_checkpoint_id_allows_none_but_rejects_traversal():
    context = StateContext(goal="attack")
    context.active_checkpoint_id = None
    with pytest.raises(ValidationError):
        context.active_checkpoint_id = "../../ESCAPED"


def test_load_from_disk_rejects_malformed_identifier(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path / "cp"))
    assert manager._load_from_disk("../../etc/passwd") is None
    assert manager.get_checkpoint("../../etc/passwd") is None


def test_checkpoint_write_stays_within_storage_root(tmp_path):
    storage_dir = tmp_path / "cp"
    manager = CheckpointManager(storage_dir=str(storage_dir))
    context = StateContext(goal="containment")

    checkpoint = manager.create_checkpoint(context)
    written = (storage_dir / context.cycle_id / f"{checkpoint.checkpoint_id}.json").resolve()

    assert written.exists()
    assert written.is_relative_to(storage_dir.resolve())
    assert not (tmp_path.parent / "ESCAPED").exists()


def test_resolve_within_storage_rejects_escape(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path / "cp"))
    with pytest.raises(ValueError):
        manager._resolve_within_storage("..", "..", "ESCAPED")


def test_checkpoint_roundtrip_still_works(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path / "cp"))
    context = StateContext(goal="roundtrip")
    context.variables["k"] = "v"

    checkpoint = manager.create_checkpoint(context)
    manager._checkpoints.clear()

    restored = manager.restore_checkpoint(checkpoint.checkpoint_id)
    assert restored is not None
    assert restored.variables["k"] == "v"
