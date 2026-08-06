"""
The governance registry: the single source of truth for which of the 10 Laws this
framework actually enforces at runtime, and by what mechanism.

Every entry names a test. A policy with no test is not enforcement, it is intent, and
must be recorded as such. GOVERNANCE.md is checked against this registry in CI, so the
document cannot drift into claiming more than the code does.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Optional, Tuple

from pydantic import BaseModel


class EnforcementStatus(str, Enum):
    ENFORCED = "ENFORCED"        # A runtime control refuses or records the behaviour.
    PARTIAL = "PARTIAL"          # A control exists but does not cover the Law's full scope.
    NOT_ENFORCED = "NOT_ENFORCED"  # No runtime control. Stated here so it is not mistaken for one.


class Policy(BaseModel):
    policy_id: str
    law: int
    status: EnforcementStatus
    predicate: str
    mechanism: str
    test: Optional[str] = None


POLICIES: Tuple[Policy, ...] = (
    Policy(
        policy_id="LAW1-HARM",
        law=1,
        status=EnforcementStatus.NOT_ENFORCED,
        predicate="No action may cause physical or psychological harm.",
        mechanism="None. Orrery has no harm model and cannot evaluate this. It belongs to the "
        "adapter and the operator, not the cycle engine.",
    ),
    Policy(
        policy_id="LAW2-OBEY",
        law=2,
        status=EnforcementStatus.NOT_ENFORCED,
        predicate="Orders from humans are obeyed unless they conflict with Law 1.",
        mechanism="None. There is no order-conflict evaluator; the goal string is executed as given.",
    ),
    Policy(
        policy_id="LAW3-SELF",
        law=3,
        status=EnforcementStatus.NOT_ENFORCED,
        predicate="Self-preservation is subordinate to Laws 1 and 2.",
        mechanism="None. Orrery has no self-preservation drive to subordinate.",
    ),
    Policy(
        policy_id="LAW4-ADAPTER",
        law=4,
        status=EnforcementStatus.PARTIAL,
        predicate="Subordinate systems are held to the same reporting rules as the cycle itself.",
        mechanism="Every adapter call produces a receipt. An adapter that raises, or that is not "
        "registered, yields a failed receipt; no subordinate system can report success on the "
        "cycle's behalf without executing.",
        test="tests/test_dispatcher.py::test_adapter_exception_becomes_failed_receipt",
    ),
    Policy(
        policy_id="LAW5-JUDICIAL",
        law=5,
        status=EnforcementStatus.NOT_ENFORCED,
        predicate="No judicial authority or interpretation of human law.",
        mechanism="None. This is a constraint on deployment, not something the engine can detect.",
    ),
    Policy(
        policy_id="LAW6-PATH",
        law=6,
        status=EnforcementStatus.ENFORCED,
        predicate="Identifiers interpolated into filesystem paths cannot escape the storage root.",
        mechanism="Canonical-UUID validation on cycle and checkpoint identifiers, plus path "
        "resolution checked against the storage root.",
        test="tests/test_security.py",
    ),
    Policy(
        policy_id="LAW6-PERM",
        law=6,
        status=EnforcementStatus.ENFORCED,
        predicate="Persisted state and audit records are readable only by their owner.",
        mechanism="Checkpoint files and the ledger are chmod 0600 on creation.",
        test="tests/test_security.py",
    ),
    Policy(
        policy_id="LAW7-NOFAKE",
        law=7,
        status=EnforcementStatus.ENFORCED,
        predicate="The framework never reports success for work it did not perform.",
        mechanism="No code path constructs a successful receipt without an adapter having executed. "
        "Unrouted actions fail explicitly.",
        test="tests/test_dispatcher.py::test_unregistered_adapter_fails_rather_than_reporting_success",
    ),
    Policy(
        policy_id="LAW7-SIM",
        law=7,
        status=EnforcementStatus.ENFORCED,
        predicate="Simulated work is distinguishable from real work.",
        mechanism="Adapters declare is_simulation; registration is logged and ledgered, and their "
        "receipts are tagged simulated=True.",
        test="tests/test_ledger.py::test_ledger_records_simulation_adapters",
    ),
    Policy(
        policy_id="LAW8-EQUITY",
        law=8,
        status=EnforcementStatus.NOT_ENFORCED,
        predicate="No systemic bias in decisions.",
        mechanism="None. Orrery makes no content decisions and has no fairness instrumentation.",
    ),
    Policy(
        policy_id="LAW9-LEDGER",
        law=9,
        status=EnforcementStatus.ENFORCED,
        predicate="Every phase transition, action, and critique is recorded for audit.",
        mechanism="EventLedger receives an event per phase entry, per action outcome, and per "
        "critique, persisted as JSONL.",
        test="tests/test_ledger.py::test_ledger_persists_to_disk_and_reloads",
    ),
    Policy(
        policy_id="LAW9-APPEND",
        law=9,
        status=EnforcementStatus.ENFORCED,
        predicate="The audit record is append-only and survives rollback.",
        mechanism="EventLedger exposes no delete, update, or truncate operation, lives outside the "
        "rewindable StateContext, and records each rollback as an event.",
        test="tests/test_ledger.py::test_ledger_survives_backtracking",
    ),
    Policy(
        policy_id="LAW9-CHAIN",
        law=9,
        status=EnforcementStatus.ENFORCED,
        predicate="Altering past state is detectable.",
        mechanism="Checkpoints and ledger events are SHA-256 hash-linked; verification runs on "
        "load and refuses a checkpoint whose digest does not match.",
        test="tests/test_integrity.py::test_edited_checkpoint_file_is_refused_on_load",
    ),
    Policy(
        policy_id="LAW9-SIGN",
        law=9,
        status=EnforcementStatus.PARTIAL,
        predicate="The audit record is cryptographically attributable.",
        mechanism="HMAC-SHA256 signing when ORRERY_CHECKPOINT_KEY is set. Off by default, and a "
        "shared symmetric key proves custody, not authorship.",
        test="tests/test_integrity.py::test_signature_is_required_when_configured",
    ),
    Policy(
        policy_id="LAW9-MONO",
        law=9,
        status=EnforcementStatus.ENFORCED,
        predicate="The record of work never moves backwards, even when the work is rewound.",
        mechanism="backtrack() takes max() on step_count and carries lessons and attempt_log across "
        "the rollback.",
        test="tests/test_dispatcher.py::test_step_count_never_regresses_across_backtracking",
    ),
    Policy(
        policy_id="DEL-001",
        law=10,
        status=EnforcementStatus.ENFORCED,
        predicate="Sub-agent delegation may not exceed the configured depth.",
        mechanism="DelegationPolicy refuses requests deeper than delegation.max_depth.",
        test="tests/test_delegation.py::test_depth_cap_refuses_delegation",
    ),
    Policy(
        policy_id="DEL-002",
        law=10,
        status=EnforcementStatus.ENFORCED,
        predicate="A cycle may not spawn unbounded children.",
        mechanism="Per-parent fan-out cap in the shared DelegationBudget.",
        test="tests/test_delegation.py::test_fan_out_cap_refuses_delegation",
    ),
    Policy(
        policy_id="DEL-003",
        law=10,
        status=EnforcementStatus.ENFORCED,
        predicate="A cycle tree may not exceed its total population cap.",
        mechanism="Tree-wide spawn counter in the shared DelegationBudget.",
        test="tests/test_delegation.py::test_population_cap_refuses_delegation",
    ),
    Policy(
        policy_id="DEL-004",
        law=10,
        status=EnforcementStatus.ENFORCED,
        predicate="Delegation may not loop back onto an ancestor.",
        mechanism="Ancestry set carried down the tree and checked before authorization.",
        test="tests/test_delegation.py::test_ancestry_loop_is_refused",
    ),
    Policy(
        policy_id="DEL-005",
        law=10,
        status=EnforcementStatus.ENFORCED,
        predicate="Delegation must descend the tier hierarchy.",
        mechanism="Tier rank comparison; sideways and upward delegation are refused.",
        test="tests/test_delegation.py::test_delegation_must_descend_the_tier_hierarchy",
    ),
    Policy(
        policy_id="LAW10-BUDGET",
        law=10,
        status=EnforcementStatus.ENFORCED,
        predicate="A cycle may not run without bound.",
        mechanism="run_full_cycle enforces a step budget and an asyncio wall-clock budget; both "
        "exhaustion paths mark the cycle FAILED.",
        test="tests/test_dispatcher.py::test_run_full_cycle_honours_step_budget",
    ),
    Policy(
        policy_id="LAW10-APPROVAL",
        law=10,
        status=EnforcementStatus.NOT_ENFORCED,
        predicate="Core directives may only be modified with cryptographically secured "
        "Governance approval.",
        mechanism="None. Settings and policies are ordinary files; there is no signed-approval "
        "workflow and no attestation of the running configuration.",
    ),
    Policy(
        policy_id="DEL-000",
        law=10,
        status=EnforcementStatus.ENFORCED,
        predicate="Every delegation, permitted or refused, is recorded with the deciding policy.",
        mechanism="authorize() logs refusals and BaseCycle ledgers every decision with its "
        "policy_id.",
        test="tests/test_ledger.py::test_delegation_decisions_reach_the_ledger",
    ),
)

POLICY_INDEX: Dict[str, Policy] = {policy.policy_id: policy for policy in POLICIES}


def enforced() -> Tuple[Policy, ...]:
    return tuple(p for p in POLICIES if p.status is EnforcementStatus.ENFORCED)


def unenforced() -> Tuple[Policy, ...]:
    return tuple(p for p in POLICIES if p.status is EnforcementStatus.NOT_ENFORCED)


def coverage_by_law() -> Dict[int, EnforcementStatus]:
    """
    The strongest status any policy achieves for each Law. Six of the ten Laws have no
    runtime control at all; that is the honest headline, not a rounding error.
    """
    order = {
        EnforcementStatus.NOT_ENFORCED: 0,
        EnforcementStatus.PARTIAL: 1,
        EnforcementStatus.ENFORCED: 2,
    }
    best: Dict[int, EnforcementStatus] = {}
    for policy in POLICIES:
        if policy.law not in best or order[policy.status] > order[best[policy.law]]:
            best[policy.law] = policy.status
    return best
