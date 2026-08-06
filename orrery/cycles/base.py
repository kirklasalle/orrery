"""
Base Cognitive Cycle Interface with Child Tier Delegation.
"""

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING
import logging
from orrery.core.config import Settings, get_settings
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
    ):
        self.tier = tier
        self.settings = settings or get_settings()
        self.context = context or StateContext(tier=tier)
        self.context.tier = tier
        self.dispatcher = dispatcher or CycleDispatcher(
            checkpoint_manager=checkpoint_manager, settings=self.settings
        )
        self._register_tier_handlers()

    @property
    def checkpoint_manager(self) -> CheckpointManager:
        return self.dispatcher.checkpoint_manager

    def register_adapter(self, adapter: "BaseAdapter", name: Optional[str] = None) -> None:
        self.dispatcher.register_adapter(adapter, name=name)

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
        """
        logger.info(f"[{self.tier.value} Cycle] Delegating task to child tier [{child_cycle.tier.value}]")

        # One checkpoint lineage and adapter set across the tree, so the whole tree is rewindable.
        self.dispatcher.share_runtime_with(child_cycle.dispatcher)

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
