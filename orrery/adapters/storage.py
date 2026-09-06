"""
Governed Object/Cloud Storage Adapter (Law 2, Law 4, Law 6).

Provides governed object storage operations (S3/GCS bucket-object semantics) with:
- Strict action risk categorization:
    get_object, list_objects, stat_object -> ActionRisk.READ_ONLY
    put_object, copy_object               -> ActionRisk.COMPENSABLE
    delete_object, delete_bucket          -> ActionRisk.IRREVERSIBLE (enforcing Approval Gate scrutiny)
- Multi-tenant bucket allowlisting (Law 2 Envelope)
- Prefix confinement (restricting agents to designated tenant subdirectories)
- Path traversal rejection in object keys (preventing directory escape)
- Deterministic local filesystem backing store for tests, edge, and air-gapped runtimes
- Signed execution receipts with ETag and byte counts
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Mapping, Optional, Sequence, Union

from orrery.adapters.base import BaseAdapter
from orrery.core.types import ActionPayload, ActionRisk, ExecutionReceipt, StateContext

logger = logging.getLogger(__name__)


class StorageAdapter(BaseAdapter):
    """
    Governed Object Storage Adapter.
    """

    adapter_name = "storage"
    target_params: ClassVar[tuple] = ("bucket", "key")

    declared_risks: ClassVar[Mapping[str, ActionRisk]] = {
        "get_object": ActionRisk.READ_ONLY,
        "list_objects": ActionRisk.READ_ONLY,
        "stat_object": ActionRisk.READ_ONLY,
        "put_object": ActionRisk.COMPENSABLE,
        "copy_object": ActionRisk.COMPENSABLE,
        "delete_object": ActionRisk.IRREVERSIBLE,
        "delete_bucket": ActionRisk.IRREVERSIBLE,
    }

    def __init__(
        self,
        storage_root: Optional[Union[str, Path]] = None,
        allowed_buckets: Optional[Sequence[str]] = None,
        allowed_prefixes: Optional[Sequence[str]] = None,
        max_object_bytes: int = 20 * 1024 * 1024,  # 20MB
        is_simulation: bool = False,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(name=self.adapter_name, config=config)
        self.allowed_buckets = set(allowed_buckets) if allowed_buckets else None
        self.allowed_prefixes = list(allowed_prefixes) if allowed_prefixes else None
        self.max_object_bytes = max_object_bytes
        self.is_simulation = is_simulation

        # Local backing store
        if storage_root:
            self.root = Path(storage_root).resolve()
            self.root.mkdir(parents=True, exist_ok=True)
        else:
            self.root = None

    def classify_risk(self, action: ActionPayload) -> ActionRisk:
        return self.risk_for(action.action_name)

    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        buckets = []
        if self.root and self.root.exists():
            buckets = [p.name for p in self.root.iterdir() if p.is_dir()]

        return {
            "adapter": self.adapter_name,
            "allowed_buckets": list(self.allowed_buckets) if self.allowed_buckets else "ALL",
            "allowed_prefixes": self.allowed_prefixes or "ALL",
            "max_object_bytes": self.max_object_bytes,
            "is_simulation": self.is_simulation,
            "active_buckets": buckets,
        }

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        return self.execute(action)

    def execute(self, action: ActionPayload) -> ExecutionReceipt:
        action_name = action.action_name
        params = action.params

        if action_name not in self.declared_risks:
            return self._receipt(
                action=action,
                success=False,
                error=f"unknown storage action '{action_name}' on adapter '{self.adapter_name}'",
            )

        bucket = str(params.get("bucket") or "").strip()
        if not bucket or not re.match(r"^[a-zA-Z0-9.\-_]{1,63}$", bucket):
            return self._receipt(action=action, success=False, error=f"invalid bucket name '{bucket}'")

        # Envelope check 1: Allowed buckets
        if self.allowed_buckets and bucket not in self.allowed_buckets:
            return self._receipt(
                action=action,
                success=False,
                error=f"Envelope violation: bucket '{bucket}' is not permitted by allowed_buckets",
            )

        key = str(params.get("key") or "").strip()
        if action_name not in ("delete_bucket", "list_objects"):
            if not key:
                return self._receipt(action=action, success=False, error="missing required parameter 'key'")

            # Path traversal rejection
            if ".." in key or key.startswith("/") or "\\" in key:
                return self._receipt(
                    action=action,
                    success=False,
                    error=f"Envelope violation: key '{key}' contains illegal path traversal tokens",
                )

            # Envelope check 2: Allowed prefixes
            if self.allowed_prefixes:
                if not any(key.startswith(pfx) for pfx in self.allowed_prefixes):
                    return self._receipt(
                        action=action,
                        success=False,
                        error=f"Envelope violation: key '{key}' does not match any allowed prefix: {self.allowed_prefixes}",
                    )

        if self.is_simulation or not self.root:
            return self._receipt(
                action=action,
                success=True,
                output={
                    "simulated": True,
                    "bucket": bucket,
                    "key": key,
                    "action": action_name,
                    "etag": hashlib.md5(f"{bucket}:{key}".encode()).hexdigest(),
                },
            )

        bucket_dir = self.root / bucket
        target_path = bucket_dir / key

        try:
            if action_name == "put_object":
                data = params.get("data")
                if data is None:
                    return self._receipt(action=action, success=False, error="missing 'data' payload for put_object")

                data_bytes = data.encode("utf-8") if isinstance(data, str) else bytes(data)
                if len(data_bytes) > self.max_object_bytes:
                    return self._receipt(
                        action=action,
                        success=False,
                        error=f"object size {len(data_bytes)} exceeds max allowed bytes {self.max_object_bytes}",
                    )

                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(data_bytes)
                etag = hashlib.md5(data_bytes).hexdigest()

                return self._receipt(
                    action=action,
                    success=True,
                    output={
                        "bucket": bucket,
                        "key": key,
                        "size_bytes": len(data_bytes),
                        "etag": etag,
                    },
                )

            elif action_name == "get_object":
                if not target_path.is_file():
                    return self._receipt(action=action, success=False, error=f"object '{key}' not found in '{bucket}'")

                content_bytes = target_path.read_bytes()
                try:
                    text_content = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    text_content = None

                etag = hashlib.md5(content_bytes).hexdigest()
                return self._receipt(
                    action=action,
                    success=True,
                    output={
                        "bucket": bucket,
                        "key": key,
                        "size_bytes": len(content_bytes),
                        "etag": etag,
                        "text": text_content,
                    },
                )

            elif action_name == "stat_object":
                if not target_path.is_file():
                    return self._receipt(action=action, success=False, error=f"object '{key}' not found in '{bucket}'")

                st = target_path.stat()
                return self._receipt(
                    action=action,
                    success=True,
                    output={
                        "bucket": bucket,
                        "key": key,
                        "size_bytes": st.st_size,
                        "modified_at": st.st_mtime,
                    },
                )

            elif action_name == "list_objects":
                prefix = str(params.get("prefix") or "")
                if not bucket_dir.exists():
                    return self._receipt(action=action, success=True, output={"bucket": bucket, "objects": []})

                objects = []
                for p in bucket_dir.rglob("*"):
                    if p.is_file():
                        rel_key = p.relative_to(bucket_dir).as_posix()
                        if not prefix or rel_key.startswith(prefix):
                            objects.append({"key": rel_key, "size_bytes": p.stat().st_size})

                return self._receipt(
                    action=action,
                    success=True,
                    output={"bucket": bucket, "objects": objects},
                )

            elif action_name == "copy_object":
                dest_bucket = str(params.get("dest_bucket") or bucket)
                dest_key = str(params.get("dest_key") or "")
                if not dest_key or ".." in dest_key:
                    return self._receipt(action=action, success=False, error="invalid dest_key")

                if not target_path.is_file():
                    return self._receipt(action=action, success=False, error=f"source object '{key}' not found")

                dest_path = self.root / dest_bucket / dest_key
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target_path, dest_path)

                return self._receipt(
                    action=action,
                    success=True,
                    output={
                        "source": f"{bucket}/{key}",
                        "destination": f"{dest_bucket}/{dest_key}",
                    },
                )

            elif action_name == "delete_object":
                if not target_path.is_file():
                    return self._receipt(action=action, success=False, error=f"object '{key}' not found")
                target_path.unlink()
                return self._receipt(
                    action=action,
                    success=True,
                    output={"bucket": bucket, "key": key, "deleted": True},
                )

            elif action_name == "delete_bucket":
                if not bucket_dir.exists():
                    return self._receipt(action=action, success=False, error=f"bucket '{bucket}' does not exist")
                shutil.rmtree(bucket_dir)
                return self._receipt(
                    action=action,
                    success=True,
                    output={"bucket": bucket, "deleted": True},
                )

        except Exception as exc:
            return self._receipt(
                action=action,
                success=False,
                error=f"Storage operation failed ({type(exc).__name__}): {exc}",
            )

        return self._receipt(action=action, success=False, error="unhandled storage action")
