"""
Meso-Cycle Abstraction Tier.
"""

from typing import Optional
from src.core.types import StateContext, CycleTier, CyclePhase, ActionPayload, ExecutionReceipt
from src.cycles.base import BaseCycle
from src.cycles.micro import MicroCycle


class MesoCycle(BaseCycle):
    """
    Meso-Cycles manage context-bound execution loops, tool sequence management,
    and operational domain logic.
    """

    def __init__(self, context: Optional[StateContext] = None):
        super().__init__(tier=CycleTier.MESO, context=context)

    async def perceive(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        ctx.hypotheses.append(f"[MESO] Operational context and tool state sensing.")
        self.context = ctx
        return ctx

    async def plan(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        ctx.planned_actions.append(
            ActionPayload(
                action_name="dispatch_tool_sequence",
                params={"tool_chain": ["adapter_query", "state_update"]},
                tier=CycleTier.MESO,
            )
        )
        self.context = ctx
        return ctx

    async def execute(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        
        # 1. Execute meso tool sequence action
        for action in ctx.planned_actions:
            if not any(r.action_id == action.action_id for r in ctx.execution_receipts):
                ctx.execution_receipts.append(
                    ExecutionReceipt(
                        action_id=action.action_id,
                        action_name=action.action_name,
                        success=True,
                        output=f"[MESO] Dispatched tool sequence {action.action_name}",
                    )
                )

        # 2. Delegate atomic action to child MicroCycle
        micro_child = MicroCycle()
        await self.delegate_to_child(micro_child)

        self.context = ctx
        return ctx

    async def reflect(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        self.dispatcher.critique_engine.evaluate(ctx)
        self.context = ctx
        return ctx
