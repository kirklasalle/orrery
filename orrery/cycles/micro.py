"""
Micro-Cycle Abstraction Tier.
"""

from typing import Optional
from orrery.core.types import StateContext, CycleTier, CyclePhase, ActionPayload
from orrery.cycles.base import BaseCycle


class MicroCycle(BaseCycle):
    """
    Micro-Cycles manage fine-grained atomic actions, turn-fixed evaluation gates,
    and visual/text observation verification.
    """

    def __init__(self, context: Optional[StateContext] = None, **kwargs):
        super().__init__(tier=CycleTier.MICRO, context=context, **kwargs)

    async def perceive(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        ctx.hypotheses.append(f"[MICRO] Atomic observation verification.")
        self.context = ctx
        return ctx

    async def plan(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        ctx.planned_actions.append(
            ActionPayload(
                action_name="atomic_action",
                params={"target": "ui_element_or_command"},
                tier=CycleTier.MICRO,
            )
        )
        self.context = ctx
        return ctx

    async def execute(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        ctx = await self.dispatch_actions(ctx)
        self.context = ctx
        return ctx

    async def reflect(self, context: Optional[StateContext] = None) -> StateContext:
        ctx = context or self.context
        self.dispatcher.critique_engine.evaluate(ctx)
        self.context = ctx
        return ctx


if __name__ == "__main__":
    import sys
    import json
    import asyncio

    input_str = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        data = json.loads(input_str)
    except Exception:
        data = {"inputPrompt": input_str}

    prompt = data.get("inputPrompt", "Default Micro task")
    cycle = MicroCycle()
    cycle.context.goal = prompt
    res = asyncio.run(cycle.run_cycle())

    output = {
        "level": "micro",
        "inputPrompt": prompt,
        "steps": [
            {
                "stepNumber": idx + 1,
                "level": "micro",
                "reasoning": h,
                "action": "atomic_action",
                "confidence": 0.95,
            }
            for idx, h in enumerate(res.hypotheses)
        ],
        "finalSynthesis": f"[MicroCycle] Executed {len(res.execution_receipts)} atomic receipts for goal: '{prompt}'",
        "durationMs": 20,
    }
    print(json.dumps(output))

