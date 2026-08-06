"""
Delegation governance.

A cycle tree that can spawn children without limit is a recursion bomb with a
philosophy. Every delegation is authorized before it runs, against depth, fan-out,
total-population, tier-ordering, and ancestry-cycle constraints.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from orrery.core.types import CycleTier

logger = logging.getLogger(__name__)

# Delegation must move down the abstraction hierarchy, never sideways or up.
_TIER_RANK: Dict[CycleTier, int] = {
    CycleTier.META: 0,
    CycleTier.MACRO: 1,
    CycleTier.MESO: 2,
    CycleTier.MICRO: 3,
}


class DelegationRequest(BaseModel):
    parent_cycle_id: str
    parent_tier: CycleTier
    child_cycle_id: str
    child_tier: CycleTier
    depth: int
    ancestry: Tuple[str, ...] = ()


class DelegationDecision(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    policy_id: Optional[str] = None


class DelegationBudget(BaseModel):
    """
    Shared population accounting for one cycle tree. Parent and children hold the same
    instance, so the caps apply to the tree rather than to each cycle independently.
    """

    max_depth: int = 4
    max_children_per_cycle: int = 8
    max_total_cycles: int = 32
    enforce_tier_descent: bool = True

    spawned: int = 0
    children_by_parent: Dict[str, int] = Field(default_factory=dict)
    refusals: List[str] = Field(default_factory=list)

    def record(self, request: DelegationRequest) -> None:
        self.spawned += 1
        self.children_by_parent[request.parent_cycle_id] = (
            self.children_by_parent.get(request.parent_cycle_id, 0) + 1
        )

    def children_of(self, parent_cycle_id: str) -> int:
        return self.children_by_parent.get(parent_cycle_id, 0)


class DelegationPolicy:
    """
    Default authorization policy. Subclass and override `authorize` to add
    domain rules; the caps below are the floor, not the ceiling.
    """

    def authorize(self, request: DelegationRequest, budget: DelegationBudget) -> DelegationDecision:
        if request.depth > budget.max_depth:
            return DelegationDecision(
                allowed=False,
                policy_id="DEL-001",
                reason=(
                    f"delegation depth {request.depth} exceeds max_depth {budget.max_depth}"
                ),
            )

        if budget.children_of(request.parent_cycle_id) >= budget.max_children_per_cycle:
            return DelegationDecision(
                allowed=False,
                policy_id="DEL-002",
                reason=(
                    f"cycle {request.parent_cycle_id} has already spawned "
                    f"{budget.max_children_per_cycle} children"
                ),
            )

        if budget.spawned >= budget.max_total_cycles:
            return DelegationDecision(
                allowed=False,
                policy_id="DEL-003",
                reason=(
                    f"cycle tree has reached its population cap of {budget.max_total_cycles}"
                ),
            )

        if request.child_cycle_id in request.ancestry or request.child_cycle_id == request.parent_cycle_id:
            return DelegationDecision(
                allowed=False,
                policy_id="DEL-004",
                reason=f"cycle {request.child_cycle_id} is already an ancestor; delegation would loop",
            )

        if budget.enforce_tier_descent:
            parent_rank = _TIER_RANK[request.parent_tier]
            child_rank = _TIER_RANK[request.child_tier]
            if child_rank <= parent_rank:
                return DelegationDecision(
                    allowed=False,
                    policy_id="DEL-005",
                    reason=(
                        f"{request.parent_tier.value} may not delegate to "
                        f"{request.child_tier.value}; delegation must descend the tier hierarchy"
                    ),
                )

        return DelegationDecision(allowed=True, policy_id="DEL-000")


def authorize(
    request: DelegationRequest,
    budget: DelegationBudget,
    policy: Optional[DelegationPolicy] = None,
) -> DelegationDecision:
    decision = (policy or DelegationPolicy()).authorize(request, budget)
    if decision.allowed:
        budget.record(request)
    else:
        budget.refusals.append(f"[{decision.policy_id}] {decision.reason}")
        logger.error(
            "Delegation refused by %s: %s (parent=%s depth=%d)",
            decision.policy_id,
            decision.reason,
            request.parent_cycle_id,
            request.depth,
        )
    return decision


def tier_rank(tier: CycleTier) -> int:
    return _TIER_RANK[tier]


def ancestry_of(parent_ancestry: Sequence[str], parent_cycle_id: str) -> Tuple[str, ...]:
    return tuple(parent_ancestry) + (parent_cycle_id,)
