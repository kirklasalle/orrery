"""
Base Cognitive Cycle Interface with Child Tier Delegation.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
import logging
from orrery.core.types import StateContext, CycleTier, CyclePhase, CycleStatus
from orrery.core.dispatcher import CycleDispatcher

logger = logging.getLogger(__name__)


class BaseCycle(ABC):
    """
    Abstract base class for all abstraction tiers (Meta, Macro, Meso, Micro).
    Supports hierarchical child cycle delegation and parent state synthesis.
    """

    def __init__(self, tier: CycleTier, context: Optional[StateContext] = None):
        self.tier = tier
        self.context = context or StateContext(tier=tier)
        self.context.tier = tier
        self.dispatcher = CycleDispatcher()
        self._register_tier_handlers()

    def _register_tier_handlers(self) -> None:
        """
        Registers tier-specific phase handlers with the internal dispatcher.
        """
        self.dispatcher.register_handler(CyclePhase.PERCEPTION, self.perceive)
        self.dispatcher.register_handler(CyclePhase.PLANNING, self.plan)
        self.dispatcher.register_handler(CyclePhase.EXECUTION, self.execute)
        self.dispatcher.register_handler(CyclePhase.REFLECTION, self.reflect)

    async def run_cycle(self) -> StateContext:
        """
        Executes the cycle across the 4 stages (Perception -> Planning -> Execution -> Reflection).
        """
        self.context = await self.dispatcher.run_full_cycle(self.context)
        return self.context

    async def delegate_to_child(self, child_cycle: "BaseCycle") -> StateContext:
        """
        Delegates execution to a child-tier cycle, passing relevant parent context signals,
        running the child cycle to completion, and synthesizing receipts back into the parent context.
        """
        logger.info(f"[{self.tier.value} Cycle] Delegating task to child tier [{child_cycle.tier.value}]")
        
        # Link child goal & context variables
        child_cycle.context.goal = f"Child task delegated from {self.tier.value}: {self.context.goal}"
        child_cycle.context.variables.update(self.context.variables)

        # Run child cycle
        child_result = await child_cycle.run_cycle()

        # Bubble up execution receipts and hypotheses to parent
        self.context.execution_receipts.extend(child_result.execution_receipts)
        self.context.hypotheses.extend([f"[{child_cycle.tier.value}] {h}" for h in child_result.hypotheses])
        
        if child_result.status == CycleStatus.FAILED:
            logger.error(f"[{self.tier.value} Cycle] Child tier [{child_cycle.tier.value}] execution failed.")
            self.context.variables[f"child_{child_cycle.tier.value.lower()}_failed"] = True

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
