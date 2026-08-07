"""
Cycle Dispatcher Multi-Stage State Machine.
"""

import asyncio
import logging
from typing import Callable, Dict, Mapping, Optional, Awaitable, Any, TYPE_CHECKING
from orrery.core.config import Settings, get_settings
from orrery.core.approval import ApprovalGate
from orrery.core.types import (
    AttemptRecord,
    ActionRisk,
    CyclePhase,
    CycleStatus,
    StateContext,
    CritiqueResult,
    ActionPayload,
    ExecutionReceipt,
)
from orrery.core.state import CheckpointManager
from orrery.core.critique import SelfCritiqueEngine
from orrery.core.ledger import EventLedger

if TYPE_CHECKING:
    from orrery.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)

# Type for async phase handlers
PhaseHandler = Callable[[StateContext], Awaitable[StateContext]]

_RISK_SEVERITY = {
    ActionRisk.READ_ONLY: 0,
    ActionRisk.REVERSIBLE: 1,
    ActionRisk.COMPENSABLE: 2,
    ActionRisk.IRREVERSIBLE: 3,
}


class CycleDispatcher:
    """
    Multi-stage state machine that orchestrates transitions across:
    PERCEPTION -> PLANNING -> EXECUTION -> REFLECTION
    """

    def __init__(
        self,
        checkpoint_manager: Optional[CheckpointManager] = None,
        critique_engine: Optional[SelfCritiqueEngine] = None,
        settings: Optional[Settings] = None,
        ledger: Optional[EventLedger] = None,
        approval_gate: Optional[ApprovalGate] = None,
    ):
        self.settings = settings or get_settings()
        self.checkpoint_manager = checkpoint_manager or CheckpointManager(
            max_checkpoints=self.settings.checkpointing.max_checkpoints_in_memory,
            storage_dir=self.settings.checkpointing.storage_dir,
            max_checkpoints_on_disk_per_cycle=self.settings.checkpointing.max_checkpoints_on_disk_per_cycle,
            verify_on_load=self.settings.integrity.verify_on_load,
            require_signature=self.settings.integrity.require_signature,
        )
        self.critique_engine = critique_engine or SelfCritiqueEngine(
            threshold=self.settings.critique.threshold
        )
        self.ledger = ledger or EventLedger(
            storage_dir=self.settings.ledger.storage_dir,
            persist=self.settings.ledger.persist,
        )
        self.approval_gate = approval_gate or ApprovalGate(
            require_approval_for_irreversible=self.settings.approval.require_for_irreversible,
            require_approval_for_compensable=self.settings.approval.require_for_compensable,
            require_signed_approval=self.settings.approval.require_signed,
            approval_ttl_seconds=self.settings.approval.ttl_seconds,
        )
        self._adapters: Dict[str, "BaseAdapter"] = {}
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

    @property
    def adapters(self) -> Mapping[str, "BaseAdapter"]:
        return dict(self._adapters)

    def register_adapter(self, adapter: "BaseAdapter", name: Optional[str] = None) -> None:
        """
        Registers an adapter under its own name, or an explicit alias.
        """
        key = name or adapter.name
        if getattr(adapter, "is_simulation", False):
            if not self.settings.allow_simulated_adapters:
                raise ValueError(
                    f"Adapter {key!r} is a simulation and simulated adapters are disabled."
                )
            logger.warning("Adapter %r is a SIMULATION: its receipts describe no real work.", key)
        self._adapters[key] = adapter
        self.ledger.append(
            "adapter.registered",
            summary=f"Adapter {key!r} registered.",
            policy_id="LAW7-SIM",
            adapter=key,
            is_simulation=bool(getattr(adapter, "is_simulation", False)),
        )

    def share_runtime_with(self, other: "CycleDispatcher") -> None:
        """
        Gives another dispatcher this one's checkpoint lineage, critique engine, ledger,
        and adapters, so a cycle tree can be rewound and audited as a single unit.
        """
        other.checkpoint_manager = self.checkpoint_manager
        other.critique_engine = self.critique_engine
        other.ledger = self.ledger
        other.approval_gate = self.approval_gate
        for key, adapter in self._adapters.items():
            other._adapters.setdefault(key, adapter)

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
        self.ledger.append(
            "cycle.phase_entered",
            summary=f"Entered {current_phase.value}.",
            cycle_id=context.cycle_id,
            tier=context.tier.value,
            policy_id="LAW9-LEDGER",
            step=context.step_count,
        )

        # Create checkpoint before transition if executing or planning
        if self.settings.dispatcher.auto_checkpoint and current_phase in (
            CyclePhase.PERCEPTION,
            CyclePhase.PLANNING,
        ):
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
            self.ledger.append(
                "critique.evaluated",
                summary=critique.reasoning,
                cycle_id=context.cycle_id,
                tier=context.tier.value,
                policy_id="LAW9-LEDGER",
                score=critique.score,
                passed=critique.passed,
            )
            if critique.passed:
                updated_context.status = CycleStatus.COMPLETED
            else:
                self._record_attempt(updated_context, critique)
                # Trigger backtracking if reflection fails and under max retry threshold
                if updated_context.backtrack_count < updated_context.max_backtracks:
                    logger.warning(f"[Cycle {context.cycle_id}] Reflection score low ({critique.score}). Triggering backtrack.")
                    updated_context = self.checkpoint_manager.backtrack(updated_context)
                    # Rollback rewinds state; the ledger records that it happened.
                    self.ledger.append(
                        "cycle.backtracked",
                        summary=f"Rolled back after scoring {critique.score:.2f}.",
                        cycle_id=context.cycle_id,
                        tier=context.tier.value,
                        policy_id="LAW9-APPEND",
                        attempt=updated_context.backtrack_count,
                        restored_checkpoint=updated_context.active_checkpoint_id,
                    )
                else:
                    logger.error(f"[Cycle {context.cycle_id}] Max backtracks reached. Marking cycle as FAILED.")
                    updated_context.status = CycleStatus.FAILED

        return updated_context

    async def run_full_cycle(
        self,
        context: StateContext,
        max_steps: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> StateContext:
        """
        Runs the dispatcher through the 4 phases until completion, failure, or budget exhaustion.
        """
        limit = max_steps if max_steps is not None else self.settings.dispatcher.max_cycle_iterations

        async def _drive() -> StateContext:
            nonlocal context
            while context.status not in (CycleStatus.COMPLETED, CycleStatus.FAILED):
                if context.step_count >= limit:
                    logger.error(
                        "[Cycle %s] Step budget of %d exhausted without reaching a terminal state.",
                        context.cycle_id,
                        limit,
                    )
                    context.lessons.append(f"Cycle halted: exceeded step budget of {limit}.")
                    context.status = CycleStatus.FAILED
                    break
                context = await self.step(context)
            return context

        if timeout_seconds is None:
            return await _drive()

        try:
            return await asyncio.wait_for(_drive(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            logger.error(
                "[Cycle %s] Wall-clock budget of %.1fs exhausted; marking cycle FAILED.",
                context.cycle_id,
                timeout_seconds,
            )
            context.lessons.append(f"Cycle halted: exceeded {timeout_seconds:.1f}s time budget.")
            context.status = CycleStatus.FAILED
            return context

    async def dispatch_actions(self, context: StateContext) -> StateContext:
        """
        Executes every planned action that has not already produced a receipt.
        """
        for action in context.planned_actions:
            if any(r.action_id == action.action_id for r in context.execution_receipts):
                continue
            receipt = await self.execute_action(action)
            context.execution_receipts.append(receipt)
            self.ledger.append(
                "action.executed" if receipt.success else "action.failed",
                summary=f"{action.action_name} via {action.target_adapter}: "
                + ("succeeded" if receipt.success else receipt.error or "failed"),
                cycle_id=context.cycle_id,
                tier=context.tier.value,
                policy_id="LAW9-LEDGER",
                action_id=action.action_id,
                action_name=action.action_name,
                adapter=action.target_adapter,
                risk=action.risk.value,
                approved_by=action.approval.approver if action.approval else None,
                success=receipt.success,
            )
        return context

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        """
        Routes a single action to its target adapter and returns the resulting receipt.
        """
        adapter = self._adapters.get(action.target_adapter)
        if adapter is None:
            # Nothing ran, so nothing succeeded. Report that rather than inventing a result.
            return ExecutionReceipt(
                action_id=action.action_id,
                action_name=action.action_name,
                success=False,
                error=(
                    f"No adapter registered for target {action.target_adapter!r}; "
                    f"action {action.action_name!r} was not executed."
                ),
            )

        action.risk = self.effective_risk(action, adapter)
        decision = self.approval_gate.evaluate(action)
        if not decision.allowed:
            logger.error("Action %r refused by %s: %s", action.action_name, decision.policy_id, decision.reason)
            self.ledger.append(
                "action.refused",
                summary=f"{action.action_name} refused: {decision.reason}",
                policy_id=decision.policy_id,
                action_id=action.action_id,
                action_name=action.action_name,
                adapter=action.target_adapter,
                risk=action.risk.value,
            )
            return ExecutionReceipt(
                action_id=action.action_id,
                action_name=action.action_name,
                success=False,
                error=f"Refused by policy {decision.policy_id}: {decision.reason}",
            )

        try:
            receipt = await adapter.execute_action(action)
        except Exception as exc:
            logger.exception("Adapter %r raised while executing %r.", adapter.name, action.action_name)
            return ExecutionReceipt(
                action_id=action.action_id,
                action_name=action.action_name,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )

        if getattr(adapter, "is_simulation", False):
            receipt.output = {"simulated": True, "adapter": adapter.name, "result": receipt.output}
        return receipt

    @staticmethod
    def effective_risk(action: ActionPayload, adapter: "BaseAdapter") -> ActionRisk:
        """
        The stricter of what the planner declared and what the adapter declares, so a planner
        cannot downgrade a delete into something harmless.
        """
        declared = getattr(adapter, "declared_risks", {}).get(action.action_name)
        if declared is None:
            return action.risk
        return max(action.risk, declared, key=lambda risk: _RISK_SEVERITY[risk])

    def _record_attempt(self, context: StateContext, critique: CritiqueResult) -> None:
        """
        Preserves a failed attempt so it survives the rollback that is about to discard it.
        """
        failed = [r.action_name for r in context.execution_receipts if not r.success]
        record = AttemptRecord(
            attempt=context.backtrack_count + 1,
            step_number=context.step_count,
            tier=context.tier,
            score=critique.score,
            reasoning=critique.reasoning,
            attempted_actions=[a.action_name for a in context.planned_actions],
            failed_actions=failed,
            recommendations=list(critique.recommendations),
        )
        context.attempt_log.append(record)
        context.lessons.append(
            f"Attempt {record.attempt} scored {critique.score:.2f}; "
            f"failed actions: {', '.join(failed) or 'none'}. "
            + " ".join(critique.recommendations)
        )

    # Default handlers
    async def _default_perception_handler(self, context: StateContext) -> StateContext:
        if not context.hypotheses:
            context.hypotheses.append(f"Primary hypothesis for goal: {context.goal}")
        return context

    async def _default_planning_handler(self, context: StateContext) -> StateContext:
        if context.planned_actions:
            return context

        attempt = context.backtrack_count
        params: Dict[str, Any] = {"goal": context.goal}
        if context.lessons:
            params["lessons"] = list(context.lessons)

        context.planned_actions.append(
            ActionPayload(
                action_name=(
                    "default_execute_goal"
                    if attempt == 0
                    else f"default_execute_goal_attempt_{attempt + 1}"
                ),
                params=params,
                tier=context.tier,
            )
        )
        return context

    async def _default_execution_handler(self, context: StateContext) -> StateContext:
        return await self.dispatch_actions(context)

    async def _default_reflection_handler(self, context: StateContext) -> StateContext:
        self.critique_engine.evaluate(context)
        return context
