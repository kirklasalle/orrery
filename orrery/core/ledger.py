"""
Append-only event ledger (Law 9).

State is rewindable; the record of what happened is not. Backtracking rolls the
StateContext back to a checkpoint, which is exactly why the audit trail cannot live
there. The ledger is a separate, forward-only, hash-linked log: every event is appended,
nothing is ever updated or deleted, and rollback is itself recorded as an event.

The class deliberately exposes no delete, update, or truncate operation.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from pydantic import BaseModel, Field, ValidationError

from orrery.core.integrity import GENESIS_HASH, canonical_json, sign_digest, signature_matches
import hashlib
import hmac

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

logger = logging.getLogger(__name__)


class LedgerEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sequence: int
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str
    cycle_id: Optional[str] = None
    tier: Optional[str] = None
    policy_id: Optional[str] = None
    summary: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)
    prev_hash: str = GENESIS_HASH
    content_hash: Optional[str] = None
    signature: Optional[str] = None

    def digest(self) -> str:
        payload = self.model_dump(mode="json", exclude={"content_hash", "signature"})
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class LedgerVerification(BaseModel):
    verified: bool
    checked: int = 0
    failures: List[str] = Field(default_factory=list)

    @property
    def summary(self) -> str:
        return f"{self.checked} event(s) verified." if self.verified else "; ".join(self.failures)


class EventLedger:
    """
    Forward-only, hash-linked audit log. Writes one JSON object per line so a partially
    written tail can never corrupt the events before it.
    """

    def __init__(self, storage_dir: str = ".ledger", filename: str = "events.jsonl", persist: bool = True):
        self.storage_dir = Path(storage_dir)
        self.persist = persist
        self._events: List[LedgerEvent] = []
        self._head: str = GENESIS_HASH
        self._path: Optional[Path] = None
        self._lock_path: Optional[Path] = None
        self._thread_lock = threading.Lock()

        if self.persist:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            self._path = self.storage_dir / filename
            self._lock_path = self.storage_dir / f".{filename}.lock"
            if self._path.exists() and self._path.stat().st_size > 0:
                self._hydrate_existing()

    @contextmanager
    def _acquire_lock(self) -> Iterator[None]:
        """Acquires an in-process thread lock and cross-process advisory file lock."""
        with self._thread_lock:
            if not self._lock_path:
                yield
                return
            with open(self._lock_path, "a+b") as lock_handle:
                lock_handle.seek(0, os.SEEK_END)
                if lock_handle.tell() == 0:
                    lock_handle.write(b"\0")
                    lock_handle.flush()
                lock_handle.seek(0)
                if sys.platform == "win32":
                    msvcrt.locking(lock_handle.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    lock_handle.seek(0)
                    if sys.platform == "win32":
                        msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def _hydrate_existing(self) -> None:
        """Loads and verifies an existing persisted ledger chain, failing closed on corruption."""
        assert self._path is not None
        with self._acquire_lock():
            try:
                loaded = self.read(self._path)
            except (OSError, json.JSONDecodeError, ValidationError) as exc:
                raise ValueError(
                    f"Refusing to append to corrupted event ledger at {self._path}: {exc}"
                ) from exc

            self._events = loaded
            verification = self.verify()
            if not verification.verified:
                raise ValueError(
                    f"Refusing to append to corrupted event ledger at {self._path}: {verification.summary}"
                )
            if self._events:
                self._head = self._events[-1].content_hash or GENESIS_HASH

    @property
    def path(self) -> Optional[Path]:
        return self._path

    @property
    def events(self) -> List[LedgerEvent]:
        return list(self._events)

    def append(
        self,
        event_type: str,
        summary: str = "",
        cycle_id: Optional[str] = None,
        tier: Optional[str] = None,
        policy_id: Optional[str] = None,
        **data: Any,
    ) -> LedgerEvent:
        with self._acquire_lock():
            if self._path is not None and self._path.exists() and self._path.stat().st_size > 0:
                latest = self.read(self._path)
                if len(latest) > len(self._events):
                    self._events = latest
                    self._head = self._events[-1].content_hash or GENESIS_HASH

            event = LedgerEvent(
                sequence=len(self._events),
                event_type=event_type,
                summary=summary,
                cycle_id=cycle_id,
                tier=tier,
                policy_id=policy_id,
                data=data,
                prev_hash=self._head,
            )
            event.content_hash = event.digest()
            event.signature = sign_digest(event.content_hash)

            self._events.append(event)
            self._head = event.content_hash
            self._write_unlocked(event)
            return event

    def events_for(self, cycle_id: str) -> List[LedgerEvent]:
        return [event for event in self._events if event.cycle_id == cycle_id]

    def verify(self) -> LedgerVerification:
        result = LedgerVerification(verified=True)
        expected_prev = GENESIS_HASH

        for idx, event in enumerate(self._events):
            if event.sequence != idx:
                result.verified = False
                result.failures.append(f"event {event.sequence} has unexpected sequence (expected {idx})")

            if event.prev_hash != expected_prev:
                result.verified = False
                result.failures.append(f"event {event.sequence} does not link to its predecessor")

            recomputed = event.digest()
            if not event.content_hash or not hmac.compare_digest(recomputed, event.content_hash):
                result.verified = False
                result.failures.append(f"event {event.sequence} content hash mismatch")

            if event.signature is not None and not signature_matches(
                event.content_hash or "", event.signature
            ):
                result.verified = False
                result.failures.append(f"event {event.sequence} signature does not match")

            expected_prev = event.content_hash or GENESIS_HASH
            result.checked += 1

        return result

    def _write_unlocked(self, event: LedgerEvent) -> None:
        if not self._path:
            return
        try:
            is_new = not self._path.exists()
            with open(self._path, "a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json() + "\n")
                handle.flush()
            if is_new:
                # The ledger records goals and action names; restrict to the owning user.
                os.chmod(self._path, 0o600)
        except OSError as exc:
            # A ledger that cannot be written must be loud, but must not take the cycle down.
            logger.error("Could not append to the event ledger at %s: %s", self._path, exc)

    @classmethod
    def read(cls, path: Path) -> List[LedgerEvent]:
        events: List[LedgerEvent] = []
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    events.append(LedgerEvent.model_validate(json.loads(line)))
        return events
