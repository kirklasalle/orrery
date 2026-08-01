"""
Base Cognitive Cycle Interface.
"""

from abc import ABC, abstractmethod
from typing import Optional
from src.core.types import StateContext, CycleTier, CyclePhase
from src.core.dispatcher import CycleDispatcher


class BaseCycle(ABC):
    """
    Abstract base class for all abstraction tiers (Meta, Macro, Meso, Micro).
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
        Executes the cycle across the 4 stages.
        """
        self.context = await self.dispatcher.run_full_cycle(self.context)
        return self.context

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
