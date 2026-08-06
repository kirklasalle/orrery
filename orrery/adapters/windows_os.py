"""
Windows OS Desktop Automation Agent Adapter.
"""

from typing import Any, ClassVar, Dict, Optional
import asyncio
from orrery.core.types import ActionPayload, ExecutionReceipt, StateContext
from orrery.adapters.base import BaseAdapter


class WindowsOSAdapter(BaseAdapter):
    """
    Adapter acting as executive controller for desktop automation.
    Uses micro-cycle reflection to verify screen state changes and UI element interactions.

    SIMULATION: performs no screen capture, input injection, or OS calls.
    """

    is_simulation: ClassVar[bool] = True

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name="windows_os", config=config)
        self.verify_screen_state = self.config.get("screen_state_verification", True)
        self.action_delay_ms = self.config.get("action_delay_ms", 10)

    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        return {
            "platform": "Windows OS",
            "screen_state": "focused",
            "active_window": "Orrery Desktop Controller",
            "display_resolution": "1920x1080",
            "verification_active": self.verify_screen_state,
        }

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        target = action.params.get("target", "desktop_ui")
        
        # Simulate OS interaction delay if specified
        if self.action_delay_ms > 0:
            await asyncio.sleep(self.action_delay_ms / 1000.0)

        screen_delta_verified = True if self.verify_screen_state else False
        output_msg = f"[Windows OS Agent] Executed action '{action.action_name}' on target '{target}'."
        
        return ExecutionReceipt(
            action_id=action.action_id,
            action_name=action.action_name,
            success=True,
            output={
                "message": output_msg,
                "target": target,
                "screen_delta_verified": screen_delta_verified,
            },
        )
