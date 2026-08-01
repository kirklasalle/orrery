"""
Meta-Cycle Abstraction Tier.
"""

from typing import Optional
from src.core.types import StateContext, CycleTier, CyclePhase, ActionPayload, ExecutionReceipt
from src.cycles.base import BaseCycle


class MetaCycle(BaseCycle):
    """
    Meta-Cycles manage high-level system strategy, long-term state evolution,
    agent goal alignment, and cross-agent coordination.
    """

    def __init__(self, context: Optional[StateContext] = None):
        super().__init__(tier=CycleTier.META, context=context)

    async def perceive(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        ctx.hypotheses.append(f"[META] Global strategic context for: {ctx.goal}")
        self.context = ctx
        return ctx

    async def plan(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        ctx.variables["strategy"] = "Hierarchical meta-level decomposition"
        ctx.planned_actions.append(
            ActionPayload(
                action_name="meta_strategy_alignment",
                params={"strategy": "meta_alignment"},
                tier=CycleTier.META,
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
                        output=f"[META] Aligned action {action.action_name}",
                    )
                )
        self.context = ctx
        return ctx

    async def reflect(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        self.dispatcher.critique_engine.evaluate(ctx)
        self.context = ctx
        return ctx
