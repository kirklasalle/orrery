"""
Effect envelopes: judging an action by what it reaches, not by what it is called.

Every other control in Orrery is enumerative. Prohibitions name actions, protected paths
name locations, classifications name action names — all of them lists somebody wrote in
advance, and all of them silent on an action invented next year. An envelope inverts that.
It declares the **boundary of what may be reached**, so a brand-new action is judged by
where it lands. Nobody has to have heard of it.

Two declarations, and both must permit:

- The **adapter** declares what it will ever touch. That is a claim by the person who wrote
  the code, and it is the one that can be checked against the implementation.
- The **deployment** declares what anything may touch here. That is the operator's boundary,
  and it holds regardless of what an adapter claims about itself.

The effective envelope is their intersection, which can only ever be narrower than either.
An adapter cannot widen the operator's boundary by declaring a generous one, and an
operator cannot grant an adapter reach its author never intended.

A breach is a **known** violation, not an unknown, so it is refused outright rather than
quarantined. Quarantine is for "I cannot characterise this"; an envelope breach is the
opposite — the action is perfectly well characterised and lands somewhere it may not.

**Why an adapter must declare its target parameters, when protection does not.** The two
gates scan differently on purpose. Protection asks "does this action reach a *forbidden*
place?", so over-scanning is safe: examining every value costs a rare false refusal and
closes the hole where a parameter nobody had named slipped past. An envelope asks the
opposite — "is everything this action touches *inside* the permitted region?" — and there
over-scanning is fatal, because the text of a file being written is not a path and would be
refused for failing to live inside a directory. So an adapter declares which of its
parameters name targets. That is a claim about its own signature, which its author
certainly knows, and an adapter that declares none under enforcement is refused rather than
waved through.

**What this does not cover, stated plainly.** Orrery infers reach from the values an action
carries, so it sees filesystem paths and nothing else. An adapter that opens a socket, calls
an API, or writes through a handle it obtained earlier is outside an envelope's view, and no
amount of parameter inspection will bring it inside. Adding a dimension here means adding an
observer for it, not adding a field. Until then, an envelope bounds where an action *points*,
which is worth having and is not the same as bounding what it does.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Sequence

from pydantic import BaseModel

from orrery.core.interdiction import resolve_under, strings_in
from orrery.core.types import ActionPayload

logger = logging.getLogger(__name__)

POLICY_ID = "LAW1-ENVELOPE"


class EffectEnvelope(BaseModel):
    """
    The region an action may reach. An allowlist: anything not inside is outside.
    """

    paths: List[str] = []

    @property
    def declared(self) -> bool:
        return bool(self.paths)

    def resolved(self, root: Optional[Path] = None) -> List[Path]:
        found = [resolve_under(entry, root) for entry in self.paths]
        return [path for path in found if path is not None]


class EnvelopeDecision(BaseModel):
    allowed: bool
    policy_id: str = POLICY_ID
    reason: Optional[str] = None


def _within(candidate: Path, permitted: Sequence[Path]) -> bool:
    """
    Containment runs one way here, unlike protection. The question is whether the candidate
    lies *inside* the permitted region, so an action aimed at a parent of that region is
    outside it — deleting the root is not permitted by an envelope covering root/data.
    """
    return any(candidate == area or candidate.is_relative_to(area) for area in permitted)


def _overlaps(candidate: Path, permitted: Sequence[Path]) -> bool:
    """
    Whether a candidate and the permitted region touch at all, in either direction. Used
    only for an adapter's claimed root: a sandbox that *contains* the permitted region is
    the ordinary case, while one entirely elsewhere is a decoy.
    """
    return any(
        candidate == area or candidate.is_relative_to(area) or area.is_relative_to(candidate)
        for area in permitted
    )


class EnvelopeGate:
    """
    Refuses actions that reach outside the intersection of the adapter's declared envelope
    and the deployment's.
    """

    def __init__(
        self,
        enforce: bool = False,
        deployment: Optional[EffectEnvelope] = None,
    ):
        self.enforce = enforce
        self.deployment = deployment or EffectEnvelope()

    @staticmethod
    def declared_by(adapter: object) -> Optional[EffectEnvelope]:
        envelope = getattr(adapter, "effect_envelope", None)
        return envelope if isinstance(envelope, EffectEnvelope) and envelope.declared else None

    def evaluate(self, action: ActionPayload, adapter: object) -> EnvelopeDecision:
        if not self.enforce:
            return EnvelopeDecision(allowed=True)

        root = getattr(adapter, "root", None)
        adapter_envelope = self.declared_by(adapter)

        if adapter_envelope is None and not self.deployment.declared:
            return EnvelopeDecision(
                allowed=False,
                reason=(
                    f"envelope enforcement is on and nothing declares a boundary: adapter "
                    f"{action.target_adapter!r} declares no effect_envelope and the deployment "
                    f"declares no envelope.paths, so no reach is permitted"
                ),
            )

        target_params = getattr(adapter, "target_params", None)
        if target_params is None:
            return EnvelopeDecision(
                allowed=False,
                reason=(
                    f"adapter {action.target_adapter!r} declares no target_params, so which of "
                    f"its parameters name a location cannot be known; declare them, or declare "
                    f"an empty tuple to state that none do"
                ),
            )

        # An adapter's root is its own assertion about where it lives, and relative paths are
        # resolved under it. A root entirely elsewhere would make every relative path resolve
        # somewhere harmless, so it must at least touch the permitted region before it is
        # trusted to resolve anything. A sandbox containing that region is ordinary; one in a
        # different tree is a decoy.
        if root is not None and self.deployment.declared:
            claimed = Path(root).resolve()
            if not _overlaps(claimed, self.deployment.resolved(None)):
                return EnvelopeDecision(
                    allowed=False,
                    reason=(
                        f"adapter {action.target_adapter!r} claims a root at {claimed}, which "
                        f"lies entirely outside the envelope this deployment permits"
                    ),
                )

        candidates = []
        for key in target_params:
            for value in strings_in(action.params.get(key)):
                resolved = resolve_under(value, root)
                if resolved is not None:
                    candidates.append((value, resolved))

        if not candidates:
            # Nothing in this action points anywhere the framework can see. That is not the
            # same as the action reaching nowhere, and the module docstring says so.
            return EnvelopeDecision(allowed=True)

        for raw, candidate in candidates:
            if adapter_envelope is not None and not _within(candidate, adapter_envelope.resolved(root)):
                return EnvelopeDecision(
                    allowed=False,
                    reason=(
                        f"{raw!r} reaches outside the envelope adapter "
                        f"{action.target_adapter!r} declares for itself"
                    ),
                )
            if self.deployment.declared and not _within(candidate, self.deployment.resolved(None)):
                return EnvelopeDecision(
                    allowed=False,
                    reason=f"{raw!r} reaches outside the envelope this deployment permits",
                )

        return EnvelopeDecision(allowed=True)
