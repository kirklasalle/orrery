"""
Quarantine: what to do with an action the framework cannot characterise.

Approval and quarantine answer different questions, and conflating them weakens the
stronger one. `RISK-001` approval answers a *known* question — "this is IRREVERSIBLE, may
I?" — where the system understands the action perfectly well and only needs consent.
Quarantine answers an *unknown*: "I cannot characterise this at all." If unclassifiable
actions were routed through the approval gate, an `ApprovalToken` would quietly stop
meaning "a human authorised this specific irreversible action" and start meaning "somebody
clicked yes on something nobody understood."

So an action whose name its adapter never declared is **held**, not guessed at. It does not
run, it does not silently fail, and it does not vanish: it is recorded, countable, and
resolvable. Releasing it requires a `Classification` — a statement of *what the action is*,
signed by an operator — rather than a permission. That difference matters for three reasons:

- A clicked approval leaves the system exactly as ignorant next time. A classification can
  be written back into the adapter's `declared_risks`, so the gap closes instead of being
  stepped over. A healthy deployment's quarantine population shrinks; one that grows is
  telling you the adapters are under-declared.
- With operator signing, a classification carries a person's key. "I said this was
  reversible" is auditable in a way "I clicked yes" is not.
- The ledger gets to distinguish *characterised* from *authorised*, which are different acts.

**A classification is not an authorisation, and the code must never let it become one.**
An `ApprovalToken` is deliberately narrow: one `action_id`, single use, expiring. A
classification is necessarily broad — it describes a *kind* of action, or it is useless. If
those collapse into one object, the broad thing inherits the narrow thing's authority and
this becomes a permission cache with a governance label on it. So a classification only
ever *describes*: once released from quarantine, the action faces the ordinary risk gate
unchanged, and an action classified IRREVERSIBLE still needs its own approval token to run.

Off by default. With quarantine disabled, an undeclared action falls back to the existing
fail-safe in `BaseAdapter.risk_for()` — treated as IRREVERSIBLE, which is a safe guess but
still a guess presented as a classification.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from orrery.core import signing
from orrery.core.integrity import canonical_json
from orrery.core.types import ActionPayload, ActionRisk

logger = logging.getLogger(__name__)

POLICY_ID = "LAW1-QUARANTINE"


class Classification(BaseModel):
    """
    An operator's statement of what a kind of action *is*. Never a permission to run it.
    """

    adapter: str
    action_name: str
    risk: ActionRisk
    note: str = ""
    classified_by: str
    classified_at: str = ""
    signature: Optional[str] = None

    @property
    def key(self) -> str:
        return f"{self.adapter}:{self.action_name}"

    def digest(self) -> str:
        payload = self.model_dump(mode="json", exclude={"signature"})
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class QuarantineRecord(BaseModel):
    """
    One held action. Enough to review it later, without the parameter *values*, which may
    carry data the reviewer has no business reading.
    """

    adapter: str
    action_name: str
    action_id: str
    reason: str
    cycle_id: Optional[str] = None
    tier: Optional[str] = None
    parameter_keys: List[str] = []
    first_seen: str = ""

    @property
    def key(self) -> str:
        return f"{self.adapter}:{self.action_name}"


class QuarantineDecision(BaseModel):
    allowed: bool
    policy_id: str = POLICY_ID
    reason: Optional[str] = None
    classification: Optional[Classification] = None
    record: Optional[QuarantineRecord] = None


def sign_classification(classification: Classification) -> Classification:
    signer = signing.signer_from_env()
    if signer is None:
        return classification
    if not classification.classified_by:
        classification.classified_by = signer.key_id
    classification.signature = signer.sign(classification.digest())
    return classification


def classification_is_valid(classification: Classification) -> bool:
    envelope = signing.decode_signature(classification.signature)
    if envelope is None or envelope.algorithm != signing.ED25519:
        return False
    # As with approvals: the key that signed must be the operator the statement names.
    if envelope.key_id != classification.classified_by:
        logger.warning(
            "Classification of %s names %r but was signed by key %r.",
            classification.key,
            classification.classified_by,
            envelope.key_id,
        )
        return False
    return signing.keyring_from_env().verify(classification.digest(), classification.signature)


class ClassificationStore:
    """
    The operator's answers to "what is this action?", keyed by adapter and action name.
    """

    def __init__(self, classifications: Optional[List[Classification]] = None):
        self._by_key: Dict[str, Classification] = {
            item.key: item for item in (classifications or [])
        }

    @property
    def keys(self) -> List[str]:
        return sorted(self._by_key)

    def add(self, classification: Classification) -> None:
        self._by_key[classification.key] = classification

    def lookup(self, adapter: str, action_name: str) -> Optional[Classification]:
        return self._by_key.get(f"{adapter}:{action_name}")

    def as_payload(self) -> Dict[str, Any]:
        return {
            "classifications": [
                item.model_dump(mode="json") for _, item in sorted(self._by_key.items())
            ]
        }

    @classmethod
    def from_file(cls, path: Path) -> "ClassificationStore":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Classification store at %s is unreadable: %s", path, exc)
            return cls()

        entries = raw.get("classifications", raw if isinstance(raw, list) else [])
        return cls([Classification.model_validate(entry) for entry in entries])

    def save(self, path: Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.as_payload(), indent=2) + "\n", encoding="utf-8")
        return target


class QuarantineGate:
    """
    Holds actions the framework cannot characterise, and releases them only against an
    operator's classification.
    """

    def __init__(
        self,
        enabled: bool = False,
        store: Optional[ClassificationStore] = None,
        record_path: Optional[str] = None,
        require_signed: bool = False,
    ):
        self.enabled = enabled
        self.store = store or ClassificationStore()
        self.require_signed = require_signed
        self.record_path = Path(record_path) if record_path else None

    @staticmethod
    def is_declared(action: ActionPayload, adapter: Any) -> bool:
        return action.action_name in (getattr(adapter, "declared_risks", {}) or {})

    def evaluate(self, action: ActionPayload, adapter: Any) -> QuarantineDecision:
        if not self.enabled or self.is_declared(action, adapter):
            return QuarantineDecision(allowed=True)

        classification = self.store.lookup(action.target_adapter, action.action_name)
        if classification is None:
            return QuarantineDecision(
                allowed=False,
                reason=(
                    f"adapter {action.target_adapter!r} does not declare action "
                    f"{action.action_name!r}, so its risk is unknown rather than assumed; "
                    f"held for operator classification"
                ),
                record=self._build_record(action),
            )

        if self.require_signed and not classification_is_valid(classification):
            return QuarantineDecision(
                allowed=False,
                reason=(
                    f"classification of {classification.key} by "
                    f"{classification.classified_by!r} is unsigned or its signature is invalid"
                ),
                record=self._build_record(action),
            )

        # Released, and nothing more. The action still faces the risk and approval gates.
        return QuarantineDecision(allowed=True, classification=classification)

    def _build_record(self, action: ActionPayload) -> QuarantineRecord:
        return QuarantineRecord(
            adapter=action.target_adapter,
            action_name=action.action_name,
            action_id=action.action_id,
            reason="undeclared action",
            parameter_keys=sorted(action.params),
            first_seen=datetime.now(timezone.utc).isoformat(),
        )

    def record(self, record: QuarantineRecord) -> None:
        """
        Appends the held action to the review queue. Records outlive the cycle so an
        operator can classify at leisure; the queue is append-only, so a growing one is
        visible rather than silently discarded.
        """
        if self.record_path is None:
            return
        try:
            self.record_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.record_path, "a", encoding="utf-8") as handle:
                handle.write(record.model_dump_json() + "\n")
        except OSError as exc:
            logger.error("Could not record quarantined action: %s", exc)

    def pending(self) -> List[QuarantineRecord]:
        """
        Held actions still lacking a classification, deduplicated by adapter and action.
        """
        if self.record_path is None or not self.record_path.is_file():
            return []

        seen: Dict[str, QuarantineRecord] = {}
        for line in self.record_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = QuarantineRecord.model_validate_json(line)
            except ValueError:
                continue
            if self.store.lookup(record.adapter, record.action_name) is None:
                seen.setdefault(record.key, record)
        return list(seen.values())
