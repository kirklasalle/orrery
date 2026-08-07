"""
Base Adapter Abstract Interface.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Mapping, Optional
from orrery.core.types import ActionPayload, ActionRisk, ExecutionReceipt, StateContext


class BaseAdapter(ABC):
    """
    Abstract Base Class for external environment and platform adapters.
    """

    # True when the adapter fabricates results instead of touching a real system.
    is_simulation: ClassVar[bool] = False

    # Risk class per supported action name. Anything unlisted is treated as irreversible.
    declared_risks: ClassVar[Mapping[str, ActionRisk]] = {}

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
