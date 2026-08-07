"""
Prism Refraction & OpenClaw Platform Adapter.
"""

from typing import Any, ClassVar, Dict, Mapping, Optional
from orrery.core.types import ActionPayload, ActionRisk, ExecutionReceipt, StateContext
from orrery.adapters.base import BaseAdapter


class OpenClawAdapter(BaseAdapter):
    """
    Adapter interfacing with Prism Refraction routing core and OpenClaw state engine.
    Dispatches tasks from Meta-Cycles to Micro-Cycles with full checkpointing.

    SIMULATION: performs no network or routing-core I/O.
    """

    is_simulation: ClassVar[bool] = True

    declared_risks: ClassVar[Mapping[str, ActionRisk]] = {
        "route_task": ActionRisk.REVERSIBLE,
        "query_routing_table": ActionRisk.READ_ONLY,
        "cancel_task": ActionRisk.REVERSIBLE,
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name="openclaw", config=config)
        self.routing_core = self.config.get("routing_core", "prism_refraction")
        self.state_engine = self.config.get("state_engine", "enabled")

    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        return {
            "platform": "OpenClaw",
            "routing_core": self.routing_core,
            "state_engine": self.state_engine,
            "active_cycle_tier": context.tier.value,
            "status": "ready",
        }

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        # An adapter that reports success for actions it does not implement is lying, and a
        # simulation that lies is indistinguishable from a broken integration.
        if action.action_name not in self.declared_risks:
            return ExecutionReceipt(
                action_id=action.action_id,
                action_name=action.action_name,
                success=False,
                error=(
                    f"OpenClawAdapter does not implement action {action.action_name!r}. "
                    f"Supported: {sorted(self.declared_risks)}."
                ),
            )

        headers = self._build_protocol_headers(action)
        output_msg = f"[OpenClaw/{self.routing_core}] Dispatched action '{action.action_name}' successfully."
        
        return ExecutionReceipt(
            action_id=action.action_id,
            action_name=action.action_name,
            success=True,
            output={
                "message": output_msg,
                "protocol_headers": headers,
                "routing_status": "OK",
            },
        )

    def _build_protocol_headers(self, action: ActionPayload) -> Dict[str, str]:
        return {
            "X-OpenClaw-Routing": self.routing_core,
            "X-Orrery-Tier": action.tier.value,
            "X-Action-ID": action.action_id,
        }
