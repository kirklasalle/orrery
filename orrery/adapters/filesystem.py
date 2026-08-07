"""
Filesystem adapter. This one is real.

Every other bundled adapter fabricates its results. This adapter reads, writes, moves, and
deletes actual files, which makes it the first place Orrery's claims can be checked against
the world rather than against itself.

It is also the first adapter with a genuinely irreversible action. `delete_file` is
classified IRREVERSIBLE, so the approval gate refuses it without explicit human consent.
That is the point of choosing this adapter first: risk classification is theatre until
something can actually be destroyed.

All paths are confined to a sandbox root (Law 6). A path that resolves outside the root is
refused before any I/O happens.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any, ClassVar, Dict, Mapping, Optional

from orrery.adapters.base import BaseAdapter
from orrery.core.envelope import EffectEnvelope
from orrery.core.types import ActionPayload, ActionRisk, ExecutionReceipt, StateContext

logger = logging.getLogger(__name__)


class FileSystemAdapter(BaseAdapter):
    """
    Sandboxed filesystem access. Real I/O, confined to `root`.
    """

    is_simulation: ClassVar[bool] = False

    target_params: ClassVar[tuple] = ("path", "source", "destination")

    declared_risks: ClassVar[Mapping[str, ActionRisk]] = {
        "read_file": ActionRisk.READ_ONLY,
        "list_dir": ActionRisk.READ_ONLY,
        "stat_path": ActionRisk.READ_ONLY,
        "make_dir": ActionRisk.REVERSIBLE,
        "move_path": ActionRisk.REVERSIBLE,
        "write_file": ActionRisk.COMPENSABLE,
        "append_file": ActionRisk.COMPENSABLE,
        "delete_file": ActionRisk.IRREVERSIBLE,
        "delete_tree": ActionRisk.IRREVERSIBLE,
    }

    def __init__(self, root: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(name="filesystem", config=config)
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_read_bytes = int(self.config.get("max_read_bytes", 1_048_576))
        # The sandbox is this adapter's own boundary. Declaring it lets a deployment narrow
        # it further without the adapter knowing anything about that deployment.
        self.effect_envelope = EffectEnvelope(paths=[str(self.root)])

    def _resolve(self, relative: str) -> Path:
        """
        Resolves a caller-supplied path inside the sandbox, refusing anything that escapes it.
        """
        if relative is None:
            raise ValueError("path is required")

        candidate = Path(relative)
        if candidate.is_absolute() or candidate.drive or candidate.anchor:
            raise ValueError(f"absolute paths are not permitted: {relative!r}")

        resolved = (self.root / candidate).resolve()
        if resolved != self.root and not resolved.is_relative_to(self.root):
            raise ValueError(f"path escapes the adapter sandbox: {relative!r}")
        return resolved

    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        def _observe() -> Dict[str, Any]:
            usage = shutil.disk_usage(self.root)
            entries = sorted(p.name for p in self.root.iterdir())
            return {
                "platform": "filesystem",
                "root": str(self.root),
                "entry_count": len(entries),
                "entries": entries[:50],
                "free_bytes": usage.free,
            }

        return await asyncio.to_thread(_observe)

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        handler = getattr(self, f"_do_{action.action_name}", None)
        if handler is None:
            return self._receipt(
                action,
                success=False,
                error=f"{self.name} adapter does not implement action {action.action_name!r}",
            )

        try:
            output = await asyncio.to_thread(handler, action.params)
        except Exception as exc:
            logger.warning("Filesystem action %r failed: %s", action.action_name, exc)
            return self._receipt(action, success=False, error=f"{type(exc).__name__}: {exc}")

        return self._receipt(action, success=True, output=output)

    def _receipt(
        self,
        action: ActionPayload,
        success: bool,
        output: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> ExecutionReceipt:
        return ExecutionReceipt(
            action_id=action.action_id,
            action_name=action.action_name,
            success=success,
            output=output,
            error=error,
        )

    # Action handlers. Each runs on a worker thread and returns JSON-serializable output.

    def _do_read_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = self._resolve(params.get("path"))
        size = path.stat().st_size
        if size > self.max_read_bytes:
            raise ValueError(
                f"{path.name} is {size} bytes, over the {self.max_read_bytes}-byte read limit."
            )
        return {
            "path": str(path.relative_to(self.root)),
            "bytes": size,
            "content": path.read_text(encoding="utf-8"),
        }

    def _do_list_dir(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = self._resolve(params.get("path", "."))
        entries = [
            {"name": child.name, "is_dir": child.is_dir(), "bytes": child.stat().st_size}
            for child in sorted(path.iterdir())
        ]
        return {"path": str(path.relative_to(self.root)) if path != self.root else ".", "entries": entries}

    def _do_stat_path(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = self._resolve(params.get("path"))
        exists = path.exists()
        return {
            "path": str(path.relative_to(self.root)),
            "exists": exists,
            "is_dir": path.is_dir() if exists else False,
            "bytes": path.stat().st_size if exists else 0,
        }

    def _do_make_dir(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = self._resolve(params.get("path"))
        path.mkdir(parents=True, exist_ok=True)
        return {"path": str(path.relative_to(self.root)), "created": True}

    def _do_write_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = self._resolve(params.get("path"))
        content = params.get("content", "")
        existed = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"path": str(path.relative_to(self.root)), "bytes": len(content), "overwrote": existed}

    def _do_append_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = self._resolve(params.get("path"))
        content = params.get("content", "")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(content)
        return {"path": str(path.relative_to(self.root)), "appended_bytes": len(content)}

    def _do_move_path(self, params: Dict[str, Any]) -> Dict[str, Any]:
        source = self._resolve(params.get("source"))
        destination = self._resolve(params.get("destination"))
        if destination.exists():
            raise FileExistsError(f"destination already exists: {params.get('destination')!r}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)
        return {
            "source": str(source.relative_to(self.root)),
            "destination": str(destination.relative_to(self.root)),
        }

    def _do_delete_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = self._resolve(params.get("path"))
        if path.is_dir():
            raise IsADirectoryError(f"{params.get('path')!r} is a directory; use delete_tree")
        path.unlink()
        return {"path": str(path.relative_to(self.root)), "deleted": True}

    def _do_delete_tree(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = self._resolve(params.get("path"))
        if path == self.root:
            raise ValueError("refusing to delete the sandbox root")
        shutil.rmtree(path)
        return {"path": str(path.relative_to(self.root)), "deleted": True}
