"""
Macro-Cycle Abstraction Tier.
"""

from typing import Optional
from src.core.types import StateContext, CycleTier, CyclePhase, ActionPayload, ExecutionReceipt
from src.cycles.base import BaseCycle


class MacroCycle(BaseCycle):
    """
    Macro-Cycles manage multi-step workflow orchestration, sub-task sequence planning,
    and major milestone tracking.
    """

    def __init__(self, context: Optional[StateContext] = None):
        super().__init__(tier=CycleTier.MACRO, context=context)

    async def perceive(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        ctx.hypotheses.append(f"[MACRO] Workflow sub-task sequence parsing for: {ctx.goal}")
        self.context = ctx
        return ctx

    async def plan(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        ctx.planned_actions.append(
            ActionPayload(
                action_name="execute_macro_milestone",
                params={"milestone": "phase_1_setup"},
                tier=CycleTier.MACRO,
            )
        )
        self.context = ctx
        return ctx

    async def execute(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        for action in ctx.planned_actions:
            if not any(r.action_id == action.action_id for r in ctx.execution_receipts):
                ctx.execution_receipts.append(
                    ExecutionReceipt(
                        action_id=action.action_id,
                        action_name=action.action_name,
                        success=True,
                        output=f"[MACRO] Executed milestone {action.action_name}",
                    )
                )
        self.context = ctx
        return ctx

    async def reflect(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        self.dispatcher.critique_engine.evaluate(ctx)
        self.context = ctx
        return ctx
