"""
Cycle Dispatcher Multi-Stage State Machine.
"""

import logging
from typing import Callable, Dict, Optional, Awaitable, Any
from orrery.core.types import (
    CyclePhase,
    CycleStatus,
    StateContext,
    CritiqueResult,
    ActionPayload,
    ExecutionReceipt,
)
from orrery.core.state import CheckpointManager
from orrery.core.critique import SelfCritiqueEngine

logger = logging.getLogger(__name__)

# Type for async phase handlers
PhaseHandler = Callable[[StateContext], Awaitable[StateContext]]


class CycleDispatcher:
    """
    Multi-stage state machine that orchestrates transitions across:
    PERCEPTION -> PLANNING -> EXECUTION -> REFLECTION
    """

    def __init__(
        self,
        checkpoint_manager: Optional[CheckpointManager] = None,
        critique_engine: Optional[SelfCritiqueEngine] = None,
    ):
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.critique_engine = critique_engine or SelfCritiqueEngine()
        self._phase_handlers: Dict[CyclePhase, PhaseHandler] = {}
        
        # Register default handlers
        self._register_default_handlers()

    def register_handler(self, phase: CyclePhase, handler: PhaseHandler) -> None:
        """
        Registers a custom handler for a given phase.
        """
        self._phase_handlers[phase] = handler

    def _register_default_handlers(self) -> None:
        self.register_handler(CyclePhase.PERCEPTION, self._default_perception_handler)
        self.register_handler(CyclePhase.PLANNING, self._default_planning_handler)
        self.register_handler(CyclePhase.EXECUTION, self._default_execution_handler)
        self.register_handler(CyclePhase.REFLECTION, self._default_reflection_handler)

    async def step(self, context: StateContext) -> StateContext:
        """
        Executes a single step transition in the state machine based on current_phase.
        """
        context.status = CycleStatus.IN_PROGRESS
        context.step_count += 1

        current_phase = context.current_phase
        handler = self._phase_handlers.get(current_phase)
        
        if not handler:
            raise ValueError(f"No handler registered for phase: {current_phase}")

        logger.info(f"[Cycle {context.cycle_id}] Entering phase: {current_phase} (Tier: {context.tier})")

        # Create checkpoint before transition if executing or planning
        if current_phase in (CyclePhase.PERCEPTION, CyclePhase.PLANNING):
            self.checkpoint_manager.create_checkpoint(context)

        # Execute phase handler
        updated_context = await handler(context)

        # Determine next transition phase
        if current_phase == CyclePhase.PERCEPTION:
            updated_context.current_phase = CyclePhase.PLANNING
        elif current_phase == CyclePhase.PLANNING:
            updated_context.current_phase = CyclePhase.EXECUTION
        elif current_phase == CyclePhase.EXECUTION:
            updated_context.current_phase = CyclePhase.REFLECTION
        elif current_phase == CyclePhase.REFLECTION:
            critique = updated_context.critiques[-1] if updated_context.critiques else CritiqueResult(score=1.0, passed=True)
            if critique.passed:
                updated_context.status = CycleStatus.COMPLETED
            else:
                # Trigger backtracking if reflection fails and under max retry threshold
                if updated_context.backtrack_count < updated_context.max_backtracks:
                    logger.warning(f"[Cycle {context.cycle_id}] Reflection score low ({critique.score}). Triggering backtrack.")
                    updated_context = self.checkpoint_manager.backtrack(updated_context)
                else:
                    logger.error(f"[Cycle {context.cycle_id}] Max backtracks reached. Marking cycle as FAILED.")
                    updated_context.status = CycleStatus.FAILED

        return updated_context

    async def run_full_cycle(self, context: StateContext) -> StateContext:
        """
        Runs the dispatcher continuously through all 4 phases until completion or failure.
        """
        while context.status not in (CycleStatus.COMPLETED, CycleStatus.FAILED):
            context = await self.step(context)
        return context

    # Default handlers
    async def _default_perception_handler(self, context: StateContext) -> StateContext:
        if not context.hypotheses:
            context.hypotheses.append(f"Primary hypothesis for goal: {context.goal}")
        return context

    async def _default_planning_handler(self, context: StateContext) -> StateContext:
        if not context.planned_actions:
            context.planned_actions.append(
                ActionPayload(
                    action_name="default_execute_goal",
                    params={"goal": context.goal},
                    tier=context.tier,
                )
            )
        return context

    async def _default_execution_handler(self, context: StateContext) -> StateContext:
        for action in context.planned_actions:
            receipt = ExecutionReceipt(
                action_id=action.action_id,
                action_name=action.action_name,
                success=True,
                output=f"Executed {action.action_name} successfully",
            )
            context.execution_receipts.append(receipt)
        return context

    async def _default_reflection_handler(self, context: StateContext) -> StateContext:
        self.critique_engine.evaluate(context)
        return context
