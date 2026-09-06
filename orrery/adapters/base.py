"""
Base Adapter Abstract Interface.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Mapping, Optional, Tuple, TYPE_CHECKING
from orrery.core.types import ActionPayload, ActionRisk, ExecutionReceipt, StateContext

if TYPE_CHECKING:
    from orrery.core.envelope import EffectEnvelope


class BaseAdapter(ABC):
    """
    Abstract Base Class for external environment and platform adapters.
    """

    # True when the adapter fabricates results instead of touching a real system.
    is_simulation: ClassVar[bool] = False

    # Risk class per supported action name. Anything unlisted is treated as irreversible.
    declared_risks: ClassVar[Mapping[str, ActionRisk]] = {}

    # The boundary of what this adapter will ever reach. Set on the instance when the
    # boundary depends on construction, as a sandbox root does.
    effect_envelope: Optional["EffectEnvelope"] = None

    # Which parameters name a location. None means undeclared, which envelope enforcement
    # refuses; an empty tuple states that this adapter's actions name none.
    target_params: ClassVar[Optional[Tuple[str, ...]]] = None

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}

    @classmethod
    def risk_for(cls, action_name: str) -> ActionRisk:
        return cls.declared_risks.get(action_name, ActionRisk.IRREVERSIBLE)

    @abstractmethod
    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        """
        Senses the platform state/environment and returns normalized observation signals.
        """
        pass

    @abstractmethod
    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        """
        Dispatches an action payload to the target platform engine and returns an execution receipt.
        """
        pass

    def _receipt(
        self,
        action: ActionPayload,
        success: bool,
        output: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> ExecutionReceipt:
        """
        Builds a receipt for an adapter action. Shared by all concrete adapters so receipt
        construction is uniform across the framework.
        """
        return ExecutionReceipt(
            action_id=action.action_id,
            action_name=action.action_name,
            success=success,
            output=output,
            error=error,
        )
