"""
Tests for CycleDispatcher state machine transitions across 4 phases.
"""

import asyncio
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.types import ActionPayload, ActionRisk, StateContext, CyclePhase, CycleStatus, CycleTier
from tests.conftest import StubAdapter, UndeclaredAdapter


def _dispatcher_with_adapter(**kwargs) -> CycleDispatcher:
    dispatcher = CycleDispatcher()
    dispatcher.register_adapter(StubAdapter(**kwargs), name="default")
    return dispatcher


def test_an_undeclared_action_is_treated_as_irreversible():
    """
    RISK-CLASS. GOVERNANCE.md has claimed "undeclared actions are treated as irreversible"
    since Gate 3a, and `BaseAdapter.risk_for()` implemented it — but the dispatcher read
    `declared_risks` directly and fell back to the *planner's* risk, which defaults to
    REVERSIBLE. Undeclared actions were sailing through as reversible while the governance
    document said the opposite.
    """

    async def run():
        dispatcher = CycleDispatcher()
        adapter = UndeclaredAdapter()
        dispatcher.register_adapter(adapter, name="undeclared")

        action = ActionPayload(action_name="do_something_nobody_declared", target_adapter="undeclared")
        assert action.risk is ActionRisk.REVERSIBLE, "the planner's optimistic default"

        receipt = await dispatcher.execute_action(action)

        assert action.risk is ActionRisk.IRREVERSIBLE, "an unclassified action is not a safe one"
        assert not receipt.success
        assert "RISK-001" in receipt.error

    asyncio.run(run())


def test_a_declared_risk_is_not_inflated_to_irreversible():
    """
    The fail-safe applies to silence, not to every action. An adapter that says READ_ONLY is
    believed.
    """

    async def run():
        dispatcher = _dispatcher_with_adapter()
        action = ActionPayload(action_name="anything", target_adapter="default")

        receipt = await dispatcher.execute_action(action)

        assert action.risk is ActionRisk.REVERSIBLE
        assert receipt.success, receipt.error

    asyncio.run(run())


def test_dispatcher_single_step_transitions():
    async def run():
        context = StateContext(goal="Test transition pipeline", tier=CycleTier.META)
        dispatcher = _dispatcher_with_adapter()

        # Step 1: PERCEPTION -> PLANNING
        assert context.current_phase == CyclePhase.PERCEPTION
        context = await dispatcher.step(context)
        assert context.current_phase == CyclePhase.PLANNING
        assert len(context.hypotheses) > 0

        # Step 2: PLANNING -> EXECUTION
        context = await dispatcher.step(context)
        assert context.current_phase == CyclePhase.EXECUTION
        assert len(context.planned_actions) > 0

        # Step 3: EXECUTION -> REFLECTION
        context = await dispatcher.step(context)
        assert context.current_phase == CyclePhase.REFLECTION
        assert len(context.execution_receipts) > 0

        # Step 4: REFLECTION -> COMPLETED
        context = await dispatcher.step(context)
        assert context.status == CycleStatus.COMPLETED
        assert len(context.critiques) > 0
        assert context.critiques[-1].passed is True

    asyncio.run(run())


def test_dispatcher_run_full_cycle():
    async def run():
        context = StateContext(goal="Test full cycle run", tier=CycleTier.MACRO)
        dispatcher = _dispatcher_with_adapter()

        final_context = await dispatcher.run_full_cycle(context)
        assert final_context.status == CycleStatus.COMPLETED
        assert final_context.step_count == 4

    asyncio.run(run())


def test_unregistered_adapter_fails_rather_than_reporting_success():
    """An action with nowhere to run must not produce a successful receipt."""

    async def run():
        context = StateContext(goal="No adapter is registered", tier=CycleTier.MICRO)
        dispatcher = CycleDispatcher()

        final_context = await dispatcher.run_full_cycle(context)

        assert final_context.status == CycleStatus.FAILED
        assert all(not r.success for r in final_context.execution_receipts)
        assert any("No adapter registered" in (r.error or "") for r in final_context.execution_receipts)

    asyncio.run(run())


def test_adapter_exception_becomes_failed_receipt():
    async def run():
        context = StateContext(goal="Adapter raises", tier=CycleTier.MICRO)
        dispatcher = _dispatcher_with_adapter(raises=True)

        final_context = await dispatcher.run_full_cycle(context)

        assert final_context.status == CycleStatus.FAILED
        assert any("RuntimeError" in (r.error or "") for r in final_context.execution_receipts)

    asyncio.run(run())


def test_backtracking_varies_the_plan_and_retains_lessons():
    """Backtracking must inform the next attempt, not repeat the previous one verbatim."""

    async def run():
        context = StateContext(goal="Always fails", tier=CycleTier.MICRO)
        dispatcher = _dispatcher_with_adapter(succeed=False)

        final_context = await dispatcher.run_full_cycle(context)

        assert final_context.status == CycleStatus.FAILED
        assert final_context.backtrack_count == final_context.max_backtracks

        # Each attempt is recorded and survives the rollback that discarded its receipts.
        assert len(final_context.attempt_log) == final_context.max_backtracks + 1
        assert len(final_context.lessons) == final_context.max_backtracks + 1

        # The planner saw those lessons and did not resubmit an identical plan.
        tried = {record.attempted_actions[0] for record in final_context.attempt_log}
        assert len(tried) > 1

    asyncio.run(run())


def test_step_count_never_regresses_across_backtracking():
    """Law 9: the record of work done is append-only, even when the work is rewound."""

    async def run():
        context = StateContext(goal="Always fails", tier=CycleTier.MICRO)
        dispatcher = _dispatcher_with_adapter(succeed=False)

        observed = []
        while context.status not in (CycleStatus.COMPLETED, CycleStatus.FAILED):
            context = await dispatcher.step(context)
            observed.append(context.step_count)

        assert observed == sorted(observed)

    asyncio.run(run())


def test_run_full_cycle_honours_step_budget():
    async def run():
        context = StateContext(goal="Always fails", tier=CycleTier.MICRO)
        context.max_backtracks = 10_000
        dispatcher = _dispatcher_with_adapter(succeed=False)

        final_context = await dispatcher.run_full_cycle(context, max_steps=12)

        assert final_context.status == CycleStatus.FAILED
        assert final_context.step_count <= 12
        assert any("step budget" in lesson for lesson in final_context.lessons)

    asyncio.run(run())
