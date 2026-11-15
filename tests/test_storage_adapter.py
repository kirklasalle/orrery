"""
Tests for Governed Cloud/Object Storage Adapter.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from orrery.adapters.storage import StorageAdapter
from orrery.core.types import ActionPayload, ActionRisk, CycleTier, StateContext


def test_storage_adapter_risk_classification():
    adapter = StorageAdapter()
    assert adapter.classify_risk(ActionPayload(action_name="get_object", params={"bucket": "b", "key": "k"}, tier=CycleTier.MICRO, target_adapter="storage")) == ActionRisk.READ_ONLY
    assert adapter.classify_risk(ActionPayload(action_name="list_objects", params={"bucket": "b"}, tier=CycleTier.MICRO, target_adapter="storage")) == ActionRisk.READ_ONLY
    assert adapter.classify_risk(ActionPayload(action_name="stat_object", params={"bucket": "b", "key": "k"}, tier=CycleTier.MICRO, target_adapter="storage")) == ActionRisk.READ_ONLY
    assert adapter.classify_risk(ActionPayload(action_name="put_object", params={"bucket": "b", "key": "k"}, tier=CycleTier.MICRO, target_adapter="storage")) == ActionRisk.COMPENSABLE
    assert adapter.classify_risk(ActionPayload(action_name="copy_object", params={"bucket": "b", "key": "k"}, tier=CycleTier.MICRO, target_adapter="storage")) == ActionRisk.COMPENSABLE
    assert adapter.classify_risk(ActionPayload(action_name="delete_object", params={"bucket": "b", "key": "k"}, tier=CycleTier.MICRO, target_adapter="storage")) == ActionRisk.IRREVERSIBLE
    assert adapter.classify_risk(ActionPayload(action_name="delete_bucket", params={"bucket": "b"}, tier=CycleTier.MICRO, target_adapter="storage")) == ActionRisk.IRREVERSIBLE


def test_storage_adapter_allowed_buckets_and_prefixes():
    adapter = StorageAdapter(
        allowed_buckets=["prod-data", "staging"],
        allowed_prefixes=["tenant-a/", "shared/"],
    )

    # Disallowed bucket
    r1 = adapter.execute(ActionPayload(
        action_name="get_object",
        params={"bucket": "confidential-finance", "key": "tenant-a/report.pdf"},
        tier=CycleTier.MICRO,
        target_adapter="storage",
    ))
    assert not r1.success
    assert "not permitted by allowed_buckets" in r1.error

    # Disallowed prefix
    r2 = adapter.execute(ActionPayload(
        action_name="get_object",
        params={"bucket": "prod-data", "key": "tenant-b/secrets.txt"},
        tier=CycleTier.MICRO,
        target_adapter="storage",
    ))
    assert not r2.success
    assert "does not match any allowed prefix" in r2.error

    # Path traversal attempt
    r3 = adapter.execute(ActionPayload(
        action_name="get_object",
        params={"bucket": "prod-data", "key": "tenant-a/../../etc/passwd"},
        tier=CycleTier.MICRO,
        target_adapter="storage",
    ))
    assert not r3.success
    assert "illegal path traversal tokens" in r3.error


def test_storage_adapter_crud_operations(tmp_path: Path):
    store_root = tmp_path / "storage_root"
    adapter = StorageAdapter(storage_root=store_root)

    # 1. Put object
    put_act = ActionPayload(
        action_name="put_object",
        params={"bucket": "my-bucket", "key": "docs/readme.txt", "data": "hello object storage"},
        tier=CycleTier.MICRO,
        target_adapter="storage",
    )
    r1 = adapter.execute(put_act)
    assert r1.success
    assert r1.output["size_bytes"] == len("hello object storage")
    assert "etag" in r1.output

    # 2. Get object
    get_act = ActionPayload(
        action_name="get_object",
        params={"bucket": "my-bucket", "key": "docs/readme.txt"},
        tier=CycleTier.MICRO,
        target_adapter="storage",
    )
    r2 = adapter.execute(get_act)
    assert r2.success
    assert r2.output["text"] == "hello object storage"

    # 3. Stat object
    stat_act = ActionPayload(
        action_name="stat_object",
        params={"bucket": "my-bucket", "key": "docs/readme.txt"},
        tier=CycleTier.MICRO,
        target_adapter="storage",
    )
    r3 = adapter.execute(stat_act)
    assert r3.success
    assert r3.output["size_bytes"] == len("hello object storage")

    # 4. List objects
    list_act = ActionPayload(
        action_name="list_objects",
        params={"bucket": "my-bucket", "prefix": "docs/"},
        tier=CycleTier.MICRO,
        target_adapter="storage",
    )
    r4 = adapter.execute(list_act)
    assert r4.success
    assert len(r4.output["objects"]) == 1
    assert r4.output["objects"][0]["key"] == "docs/readme.txt"

    # 5. Copy object
    copy_act = ActionPayload(
        action_name="copy_object",
        params={"bucket": "my-bucket", "key": "docs/readme.txt", "dest_key": "docs/readme.bak"},
        tier=CycleTier.MICRO,
        target_adapter="storage",
    )
    r5 = adapter.execute(copy_act)
    assert r5.success

    # 6. Delete object
    del_act = ActionPayload(
        action_name="delete_object",
        params={"bucket": "my-bucket", "key": "docs/readme.txt"},
        tier=CycleTier.MICRO,
        target_adapter="storage",
    )
    r6 = adapter.execute(del_act)
    assert r6.success

    # 7. Delete bucket
    del_b_act = ActionPayload(
        action_name="delete_bucket",
        params={"bucket": "my-bucket"},
        tier=CycleTier.MICRO,
        target_adapter="storage",
    )
    r7 = adapter.execute(del_b_act)
    assert r7.success
    assert not (store_root / "my-bucket").exists()


def test_storage_adapter_simulation_mode():
    adapter = StorageAdapter(is_simulation=True)
    r = adapter.execute(ActionPayload(
        action_name="put_object",
        params={"bucket": "sim-bucket", "key": "file.txt", "data": "data"},
        tier=CycleTier.MICRO,
        target_adapter="storage",
    ))
    assert r.success
    assert r.output["simulated"] is True


@pytest.mark.asyncio
async def test_storage_adapter_async_interface(tmp_path: Path):
    adapter = StorageAdapter(storage_root=tmp_path / "storage", is_simulation=True)
    context = StateContext()
    env = await adapter.perceive_environment(context)
    assert env["adapter"] == "storage"
    assert env["is_simulation"] is True

    act = ActionPayload(action_name="get_object", params={"bucket": "b", "key": "k"}, tier=CycleTier.MICRO, target_adapter="storage")
    r = await adapter.execute_action(act)
    assert r.success


def test_storage_adapter_edge_cases(tmp_path: Path):
    store_root = tmp_path / "store"
    adapter = StorageAdapter(storage_root=store_root, max_object_bytes=50)

    # 1. Unknown action
    r1 = adapter.execute(ActionPayload(action_name="unsupported_op", params={"bucket": "b", "key": "k"}, tier=CycleTier.MICRO, target_adapter="storage"))
    assert not r1.success
    assert "unknown storage action" in r1.error

    # 2. Put object missing data
    r2 = adapter.execute(ActionPayload(action_name="put_object", params={"bucket": "b", "key": "k"}, tier=CycleTier.MICRO, target_adapter="storage"))
    assert not r2.success
    assert "missing 'data'" in r2.error

    # 3. Object size exceeds max_object_bytes
    r3 = adapter.execute(ActionPayload(action_name="put_object", params={"bucket": "b", "key": "k", "data": "a" * 100}, tier=CycleTier.MICRO, target_adapter="storage"))
    assert not r3.success
    assert "exceeds max allowed bytes" in r3.error

    # 4. Get/stat nonexistent object
    r4 = adapter.execute(ActionPayload(action_name="get_object", params={"bucket": "b", "key": "missing.txt"}, tier=CycleTier.MICRO, target_adapter="storage"))
    assert not r4.success
    assert "not found" in r4.error

    r5 = adapter.execute(ActionPayload(action_name="stat_object", params={"bucket": "b", "key": "missing.txt"}, tier=CycleTier.MICRO, target_adapter="storage"))
    assert not r5.success
    assert "not found" in r5.error

    # 5. Delete nonexistent object/bucket
    r6 = adapter.execute(ActionPayload(action_name="delete_object", params={"bucket": "b", "key": "missing.txt"}, tier=CycleTier.MICRO, target_adapter="storage"))
    assert not r6.success
    assert "not found" in r6.error

    r7 = adapter.execute(ActionPayload(action_name="delete_bucket", params={"bucket": "missing-bucket"}, tier=CycleTier.MICRO, target_adapter="storage"))
    assert not r7.success
    assert "does not exist" in r7.error

    # 6. Perceive environment with active buckets
    (store_root / "mybucket").mkdir(parents=True)
    import asyncio
    env = asyncio.run(adapter.perceive_environment(StateContext()))
    assert "mybucket" in env["active_buckets"]


def test_storage_rejects_dot_bucket_and_delete_bucket_traversal(tmp_path: Path):
    parent_dir = tmp_path / "parent"
    store_root = parent_dir / "store"
    store_root.mkdir(parents=True)
    sentinel = parent_dir / "keep_me.txt"
    sentinel.write_text("do not delete", encoding="utf-8")

    adapter = StorageAdapter(storage_root=store_root)
    for bad_bucket in ("..", ".", "a/../b"):
        res = adapter.execute(ActionPayload(
            action_name="delete_bucket",
            params={"bucket": bad_bucket},
            tier=CycleTier.MICRO,
            target_adapter="storage",
        ))
        assert not res.success, f"delete_bucket must reject {bad_bucket!r}"
        assert sentinel.exists(), "parent sentinel must not be deleted"

    for bad_bucket in ("..", "."):
        res_put = adapter.execute(ActionPayload(
            action_name="put_object",
            params={"bucket": bad_bucket, "key": "escape.txt", "data": "x"},
            tier=CycleTier.MICRO,
            target_adapter="storage",
        ))
        assert not res_put.success


def test_storage_copy_object_validates_dest_bucket_and_key(tmp_path: Path):
    store_root = tmp_path / "store"
    outside = tmp_path / "outside.txt"
    adapter = StorageAdapter(
        storage_root=store_root,
        allowed_buckets=["allowed"],
        allowed_prefixes=["safe/"],
    )
    put_res = adapter.execute(ActionPayload(
        action_name="put_object",
        params={"bucket": "allowed", "key": "safe/src.txt", "data": "secret"},
        tier=CycleTier.MICRO,
        target_adapter="storage",
    ))
    assert put_res.success

    for dest_bucket, dest_key in (
        ("..", "safe/out.txt"),
        ("forbidden-bucket", "safe/out.txt"),
        ("allowed", str(outside)),
        ("allowed", "/abs/out.txt"),
        ("allowed", "\\abs\\out.txt"),
        ("allowed", "unsafe/out.txt"),
    ):
        res = adapter.execute(ActionPayload(
            action_name="copy_object",
            params={
                "bucket": "allowed",
                "key": "safe/src.txt",
                "dest_bucket": dest_bucket,
                "dest_key": dest_key,
            },
            tier=CycleTier.MICRO,
            target_adapter="storage",
        ))
        assert not res.success, f"copy_object must reject dest=({dest_bucket!r}, {dest_key!r})"
    assert not outside.exists()
