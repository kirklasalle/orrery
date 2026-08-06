"""
Base Cognitive Cycle Interface with Child Tier Delegation.
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple, TYPE_CHECKING
import logging
from orrery.core.config import Settings, get_settings
from orrery.core.delegation import (
    DelegationBudget,
    DelegationPolicy,
    DelegationRequest,
    ancestry_of,
    authorize,
)
from orrery.core.types import StateContext, CycleTier, CyclePhase, CycleStatus, ExecutionReceipt
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.state import CheckpointManager

if TYPE_CHECKING:
    from orrery.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


class BaseCycle(ABC):
    """
    Abstract base class for all abstraction tiers (Meta, Macro, Meso, Micro).
    Supports hierarchical child cycle delegation and parent state synthesis.
    """

    def __init__(
        self,
        tier: CycleTier,
        context: Optional[StateContext] = None,
        dispatcher: Optional[CycleDispatcher] = None,
        checkpoint_manager: Optional[CheckpointManager] = None,
        settings: Optional[Settings] = None,
        delegation_policy: Optional[DelegationPolicy] = None,
    ):
        self.tier = tier
        self.settings = settings or get_settings()
        self.context = context or StateContext(tier=tier)
        self.context.tier = tier
        self.dispatcher = dispatcher or CycleDispatcher(
            checkpoint_manager=checkpoint_manager, settings=self.settings
        )

        # Position in the cycle tree. Reassigned by the parent at delegation time.
        self.depth: int = 0
        self.ancestry: Tuple[str, ...] = ()
        self.delegation_policy = delegation_policy or DelegationPolicy()
        self.delegation_budget = DelegationBudget(
            max_depth=self.settings.delegation.max_depth,
            max_children_per_cycle=self.settings.delegation.max_children_per_cycle,
            max_total_cycles=self.settings.delegation.max_total_cycles,
            enforce_tier_descent=self.settings.delegation.enforce_tier_descent,
        )
        self._register_tier_handlers()

    @property
    def checkpoint_manager(self) -> CheckpointManager:
        return self.dispatcher.checkpoint_manager

    def register_adapter(self, adapter: "BaseAdapter", name: Optional[str] = None) -> None:
        self.dispatcher.register_adapter(adapter, name=name)

    def spawn_child(self, cycle_cls, context: Optional[StateContext] = None) -> "BaseCycle":
        """
        Builds a child cycle that inherits this cycle's settings and delegation policy,
        so governance is not silently reset one tier down.
        """
        return cycle_cls(
            context=context,
            settings=self.settings,
            delegation_policy=self.delegation_policy,
        )

    def _register_tier_handlers(self) -> None:
        """
        Registers tier-specific phase handlers with the internal dispatcher.
        """
        self.dispatcher.register_handler(CyclePhase.PERCEPTION, self.perceive)
        self.dispatcher.register_handler(CyclePhase.PLANNING, self.plan)
        self.dispatcher.register_handler(CyclePhase.EXECUTION, self.execute)
        self.dispatcher.register_handler(CyclePhase.REFLECTION, self.reflect)

    async def dispatch_actions(self, context: StateContext) -> StateContext:
        """
        Routes this cycle's planned actions through the registered adapters.
        """
        return await self.dispatcher.dispatch_actions(context)

    async def run_cycle(self, timeout_seconds: Optional[float] = None) -> StateContext:
        """
        Executes the cycle across the 4 stages (Perception -> Planning -> Execution -> Reflection),
        bounded by this tier's configured time budget.
        """
        budget = timeout_seconds if timeout_seconds is not None else self.settings.timeout_for(self.tier)
        self.context = await self.dispatcher.run_full_cycle(self.context, timeout_seconds=budget)
        return self.context

    async def delegate_to_child(self, child_cycle: "BaseCycle") -> StateContext:
        """
        Delegates execution to a child-tier cycle, passing relevant parent context signals,
        running the child cycle to completion, and synthesizing receipts back into the parent context.

        Delegation is authorized before it runs. A refusal produces a failed receipt rather
        than an exception, so the parent's own reflection and backtracking handle it.
        """
        request = DelegationRequest(
            parent_cycle_id=self.context.cycle_id,
            parent_tier=self.tier,
            child_cycle_id=child_cycle.context.cycle_id,
            child_tier=child_cycle.tier,
            depth=self.depth + 1,
            ancestry=self.ancestry,
        )
        decision = authorize(request, self.delegation_budget, self.delegation_policy)
        self.dispatcher.ledger.append(
            "delegation.authorized" if decision.allowed else "delegation.refused",
            summary=decision.reason or f"{self.tier.value} -> {child_cycle.tier.value} permitted.",
            cycle_id=self.context.cycle_id,
            tier=self.tier.value,
            policy_id=decision.policy_id,
            child_cycle_id=child_cycle.context.cycle_id,
            child_tier=child_cycle.tier.value,
            depth=request.depth,
        )
        if not decision.allowed:
            return self._refuse_delegation(child_cycle, decision.policy_id, decision.reason)

        logger.info(f"[{self.tier.value} Cycle] Delegating task to child tier [{child_cycle.tier.value}]")

        # One checkpoint lineage, adapter set, and delegation budget across the tree.
        self.dispatcher.share_runtime_with(child_cycle.dispatcher)
        child_cycle.depth = request.depth
        child_cycle.ancestry = ancestry_of(self.ancestry, self.context.cycle_id)
        child_cycle.delegation_budget = self.delegation_budget

        # Link child goal & context variables
        child_cycle.context.goal = f"Child task delegated from {self.tier.value}: {self.context.goal}"
        child_cycle.context.variables.update(self.context.variables)

        # Run child cycle
        child_result = await child_cycle.run_cycle()

        # Bubble up execution receipts and hypotheses to parent
        self.context.execution_receipts.extend(child_result.execution_receipts)
        self.context.hypotheses.extend([f"[{child_cycle.tier.value}] {h}" for h in child_result.hypotheses])
        self.context.lessons.extend(
            [f"[{child_cycle.tier.value}] {lesson}" for lesson in child_result.lessons]
        )

        if child_result.status == CycleStatus.FAILED:
            logger.error(f"[{self.tier.value} Cycle] Child tier [{child_cycle.tier.value}] execution failed.")
            self.context.variables[f"child_{child_cycle.tier.value.lower()}_failed"] = True
            # A failed child must fail the parent's reflection, not vanish into a variable.
            self.context.execution_receipts.append(
                ExecutionReceipt(
                    action_id=child_result.cycle_id,
                    action_name=f"delegate_to_{child_cycle.tier.value.lower()}",
                    success=False,
                    error=(
                        f"Child {child_cycle.tier.value} cycle {child_result.cycle_id} failed after "
                        f"{child_result.backtrack_count} backtrack(s)."
                    ),
                )
            )

        return child_result

    def _refuse_delegation(
        self, child_cycle: "BaseCycle", policy_id: Optional[str], reason: Optional[str]
    ) -> StateContext:
        """
        Records a refused delegation as a failed receipt and a lesson, and returns the
        child's context untouched and FAILED. The child never runs.
        """
        message = f"Delegation refused by policy {policy_id}: {reason}"
        self.context.execution_receipts.append(
            ExecutionReceipt(
                action_id=child_cycle.context.cycle_id,
                action_name=f"delegate_to_{child_cycle.tier.value.lower()}",
                success=False,
                error=message,
            )
        )
        self.context.lessons.append(message)
        self.context.variables[f"child_{child_cycle.tier.value.lower()}_refused"] = policy_id
        child_cycle.context.status = CycleStatus.FAILED
        return child_cycle.context

    @abstractmethod
    async def perceive(self, context: Optional[StateContext] = None) -> StateContext:
        """Sensing and hypothesis generation."""
        pass

    @abstractmethod
    async def plan(self, context: Optional[StateContext] = None) -> StateContext:
        """Strategy formulation and constraint checking."""
        pass

    @abstractmethod
    async def execute(self, context: Optional[StateContext] = None) -> StateContext:
        """Action dispatching."""
        pass

    @abstractmethod
    async def reflect(self, context: Optional[StateContext] = None) -> StateContext:
        """Self-critique and verification."""
        pass
