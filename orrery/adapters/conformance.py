"""
Adapter Conformance Kit.

Orrery's honesty guarantees stop at the adapter boundary. Everything the framework promises
about failure reporting depends on adapters returning truthful receipts, and nothing in the
type system compels that. This kit is the check.

Run it against any adapter, bundled or third-party:

    from orrery.adapters.conformance import run_conformance

    report = run_conformance(MyAdapter(...), sample_action="read_file", sample_params={...})
    assert report.passed, report.summary
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from orrery.adapters.base import BaseAdapter
from orrery.core.types import ActionPayload, ActionRisk, ExecutionReceipt, StateContext


class ConformanceCheck(BaseModel):
    check_id: str
    description: str
    passed: bool
    detail: str = ""
    # False when the check could not be applied. Skipped checks never mask a failure,
    # but they are kept in the report so a weakened result is visible rather than silent.
    applicable: bool = True


class ConformanceReport(BaseModel):
    adapter: str
    is_simulation: bool
    checks: List[ConformanceCheck] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks if check.applicable)

    @property
    def failures(self) -> List[ConformanceCheck]:
        return [check for check in self.checks if check.applicable and not check.passed]

    @property
    def skipped(self) -> List[ConformanceCheck]:
        return [check for check in self.checks if not check.applicable]

    @property
    def summary(self) -> str:
        if self.passed:
            note = f" ({len(self.skipped)} skipped)" if self.skipped else ""
            return f"{self.adapter}: {len(self.checks)} check(s) passed{note}."
        return f"{self.adapter}: " + "; ".join(
            f"[{c.check_id}] {c.description} -- {c.detail}" for c in self.failures
        )


def _check(
    check_id: str,
    description: str,
    passed: bool,
    detail: str = "",
    applicable: bool = True,
) -> ConformanceCheck:
    return ConformanceCheck(
        check_id=check_id,
        description=description,
        passed=passed,
        detail=detail,
        applicable=applicable,
    )


async def _run(
    adapter: BaseAdapter,
    sample_action: str,
    sample_params: Optional[Dict[str, Any]],
) -> ConformanceReport:
    report = ConformanceReport(
        adapter=getattr(adapter, "name", type(adapter).__name__),
        is_simulation=bool(getattr(adapter, "is_simulation", False)),
    )

    report.checks.append(
        _check("ADP-001", "Adapter declares a non-empty name", bool(getattr(adapter, "name", "")))
    )

    is_sim = getattr(type(adapter), "is_simulation", None)
    report.checks.append(
        _check(
            "ADP-002",
            "is_simulation is declared as a class-level bool",
            isinstance(is_sim, bool),
            f"got {is_sim!r}",
        )
    )

    risks = getattr(adapter, "declared_risks", {})
    bad_risks = {name: risk for name, risk in dict(risks).items() if not isinstance(risk, ActionRisk)}
    report.checks.append(
        _check(
            "ADP-003",
            "Every declared risk is an ActionRisk member",
            not bad_risks,
            f"invalid: {bad_risks}",
        )
    )

    report.checks.append(
        _check(
            "ADP-004",
            "execute_action and perceive_environment are coroutines",
            inspect.iscoroutinefunction(adapter.execute_action)
            and inspect.iscoroutinefunction(adapter.perceive_environment),
        )
    )

    # An adapter must answer for work it was asked to do, even work it cannot do. This is only
    # decidable when the adapter publishes an action vocabulary; one that publishes none is
    # already penalised elsewhere, because risk_for() then treats every action as irreversible.
    declares_vocabulary = bool(risks)
    unknown = ActionPayload(action_name="__orrery_conformance_unsupported__", target_adapter=adapter.name)
    try:
        unknown_receipt = await adapter.execute_action(unknown)
        raised = None
    except Exception as exc:
        unknown_receipt, raised = None, f"{type(exc).__name__}: {exc}"

    report.checks.append(
        _check(
            "ADP-005",
            "An unsupported action returns a failed receipt rather than raising",
            unknown_receipt is not None
            and isinstance(unknown_receipt, ExecutionReceipt)
            and not unknown_receipt.success,
            raised
            or (
                "adapter declares no action vocabulary, so unsupported actions are undecidable"
                if not declares_vocabulary
                else f"receipt: {unknown_receipt}"
            ),
            applicable=declares_vocabulary,
        )
    )

    if unknown_receipt is not None:
        report.checks.append(
            _check(
                "ADP-006",
                "A failed receipt carries a non-empty error",
                bool(unknown_receipt.error),
                applicable=declares_vocabulary,
            )
        )
        report.checks.append(
            _check(
                "ADP-007",
                "The receipt echoes the requested action_id",
                unknown_receipt.action_id == unknown.action_id,
                f"{unknown_receipt.action_id} != {unknown.action_id}",
            )
        )

    action = ActionPayload(
        action_name=sample_action,
        params=dict(sample_params or {}),
        target_adapter=adapter.name,
    )
    try:
        receipt = await adapter.execute_action(action)
        sample_error = None
    except Exception as exc:
        receipt, sample_error = None, f"{type(exc).__name__}: {exc}"

    report.checks.append(
        _check(
            "ADP-008",
            "A supported action returns an ExecutionReceipt without raising",
            isinstance(receipt, ExecutionReceipt),
            sample_error or f"got {type(receipt).__name__}",
        )
    )

    if isinstance(receipt, ExecutionReceipt):
        report.checks.append(
            _check(
                "ADP-009",
                "The receipt echoes the requested action_id and action_name",
                receipt.action_id == action.action_id and receipt.action_name == action.action_name,
                f"{receipt.action_id}/{receipt.action_name}",
            )
        )
        report.checks.append(
            _check(
                "ADP-010",
                "A successful receipt carries no error",
                not (receipt.success and receipt.error),
            )
        )
        # Only the dispatcher may add the simulation tag; an adapter claiming it is misreporting.
        tagged = isinstance(receipt.output, dict) and "simulated" in receipt.output
        report.checks.append(
            _check(
                "ADP-011",
                "The adapter does not stamp its own output as simulated",
                not tagged,
                "output contains a 'simulated' key",
            )
        )

    try:
        observation = await adapter.perceive_environment(StateContext(goal="conformance probe"))
        perceive_error = None
    except Exception as exc:
        observation, perceive_error = None, f"{type(exc).__name__}: {exc}"

    report.checks.append(
        _check(
            "ADP-012",
            "perceive_environment returns a dict without raising",
            isinstance(observation, dict),
            perceive_error or f"got {type(observation).__name__}",
        )
    )

    return report


def run_conformance(
    adapter: BaseAdapter,
    sample_action: str,
    sample_params: Optional[Dict[str, Any]] = None,
) -> ConformanceReport:
    """
    Synchronous entry point. `sample_action` must be an action the adapter supports.
    """
    return asyncio.run(_run(adapter, sample_action, sample_params))
