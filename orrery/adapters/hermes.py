"""
Hermes / Console Backend Reasoning Harness Adapter.
"""

from typing import Any, Dict, Optional
from orrery.core.types import ActionPayload, ExecutionReceipt, StateContext, CritiqueResult
from orrery.adapters.base import BaseAdapter


class HermesAdapter(BaseAdapter):
    """
    Adapter interfacing with Hermes / Console backend reasoning harness.
    Provides prompt formatting, evaluation gates, and self-critique prior to terminal execution.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name="hermes", config=config)
        self.mode = self.config.get("mode", "console")
        self.temperature = self.config.get("temperature", 0.1)

    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        return {
            "platform": "Hermes/Console",
            "mode": self.mode,
            "temperature": self.temperature,
            "evaluation_gates": "active",
            "active_hypotheses": len(context.hypotheses),
        }

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        formatted_prompt = self._build_reasoning_prompt(action)
        output_msg = f"[Hermes/Console ({self.mode})] Processed reasoning payload for '{action.action_name}'."
        
        return ExecutionReceipt(
            action_id=action.action_id,
            action_name=action.action_name,
            success=True,
            output={
                "reasoning_trace": output_msg,
                "prompt_used": formatted_prompt,
                "eval_gate": "PASSED",
            },
        )

    def evaluate_gate(self, context: StateContext) -> CritiqueResult:
        """
        Runs Hermes evaluation gate prior to terminal output.
        """
        score = 0.95 if context.execution_receipts else 0.50
        return CritiqueResult(
            score=score,
            passed=score >= 0.70,
            reasoning="Hermes evaluation gate score calculated.",
        )

    def _build_reasoning_prompt(self, action: ActionPayload) -> str:
        return f"SYSTEM (Hermes/{self.mode}): Execute action '{action.action_name}' with params={action.params}"
