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
        policy_id="LAW1-PROHIBIT",
        law=1,
        status=EnforcementStatus.PARTIAL,
        predicate="Actions an operator has declared forbidden are refused, and no approval "
        "overrides them.",
        mechanism="InterdictionGate matches each action against operator-declared prohibitions "
        "by adapter, action name, and path before the approval gate runs, so a prohibited action "
        "cannot be authorized at execution time. This does not give Orrery a harm model: it "
        "refuses what someone who can judge harm has written down, and is only as good as what "
        "they thought to write.",
        test="tests/test_interdiction.py::test_a_prohibited_action_is_refused_even_with_approval",
    ),
    Policy(
        policy_id="LAW1-ENVELOPE",
        law=1,
        status=EnforcementStatus.PARTIAL,
        predicate="An action is judged by what it reaches, not by whether its name appears on "
        "a list.",
        mechanism="An adapter declares the boundary of what it will ever touch and which of its "
        "parameters name a location; a deployment declares what anything may touch here. Both "
        "must permit, so the effective envelope is their intersection and can only be narrower "
        "than either. A breach is a known violation, so it is refused rather than held. Off by "
        "default. Partial because reach is inferred from the values an action carries: an "
        "adapter that opens a socket or writes through a handle it already holds is outside an "
        "envelope's view, so this bounds where an action points, not what it does.",
        test="tests/test_envelope.py::test_an_action_nobody_enumerated_is_judged_by_where_it_lands",
    ),
    Policy(
        policy_id="LAW1-QUARANTINE",
        law=1,
        status=EnforcementStatus.PARTIAL,
        predicate="An action the framework cannot characterise is held, not guessed at.",
        mechanism="QuarantineGate holds any action whose target adapter never declared it, and "
        "releases it only against an operator Classification stating what the action is. A "
        "classification describes and never authorises: a released action still faces the risk "
        "and approval gates unchanged, so one classified IRREVERSIBLE still needs a token bound "
        "to each specific action. Partial because it is off by default; with quarantine "
        "disabled an undeclared action falls back to being treated as IRREVERSIBLE, which is a "
        "safe guess but still a guess.",
        test="tests/test_quarantine.py::test_a_classification_is_not_an_authorisation",
    ),
    Policy(
        policy_id="RISK-CLASS",
        law=1,
        status=EnforcementStatus.PARTIAL,
        predicate="An action's blast radius is classified before it runs, and the planner cannot "
        "understate it.",
        mechanism="Adapters declare an ActionRisk per action name. The dispatcher takes the stricter "
        "of the planner's declaration and the adapter's, so a plan cannot relabel a delete as "
        "harmless. Undeclared actions are treated as irreversible. This bounds the class of an "
        "action, not its content: a permitted write can still be harmful.",
        test="tests/test_filesystem_adapter.py::test_a_planner_cannot_downgrade_an_irreversible_action",
    ),
    Policy(
        policy_id="RISK-001",
        law=1,
        status=EnforcementStatus.PARTIAL,
        predicate="Nothing the framework cannot undo executes without explicit human authorization.",
        mechanism="ApprovalGate refuses IRREVERSIBLE actions carrying no ApprovalToken, and "
        "COMPENSABLE ones when configured. Refusals are ledgered. Covers only what adapters "
        "correctly classify as irreversible.",
        test="tests/test_filesystem_adapter.py::test_irreversible_action_is_refused_without_approval",
    ),
    Policy(
        policy_id="RISK-002",
        law=1,
        status=EnforcementStatus.ENFORCED,
        predicate="Consent granted for one action cannot authorize another.",
        mechanism="ApprovalToken is bound to a single action_id; the gate refuses any mismatch.",
        test="tests/test_filesystem_adapter.py::test_approval_cannot_be_replayed_against_another_action",
    ),
    Policy(
        policy_id="LAW2-OBEY",
        law=2,
        status=EnforcementStatus.NOT_ENFORCED,
        predicate="Orders from humans are obeyed unless they conflict with Law 1.",
        mechanism="None. There is no order-conflict evaluator; the goal string is executed as given.",
    ),
    Policy(
        policy_id="RISK-003",
        law=2,
        status=EnforcementStatus.PARTIAL,
        predicate="An authorization can be shown to have come from a human, not from the agent.",
        mechanism="Ed25519 per-operator signing when ORRERY_OPERATOR_ID and "
        "ORRERY_OPERATOR_PRIVATE_KEY are set: the framework holds only the public keyring, so it "
        "can verify an approval without being able to mint one, and a token's signing key must "
        "match the approver it names. HMAC via ORRERY_APPROVAL_KEY remains supported but proves "
        "custody of a shared secret rather than authorship. Partial because both are off by "
        "default, and an unsigned token documents intent rather than proving consent.",
        test="tests/test_signing.py::test_operator_signed_approval_verifies_and_a_forged_one_does_not",
    ),
    Policy(
        policy_id="RISK-005",
        law=2,
        status=EnforcementStatus.ENFORCED,
        predicate="When asymmetric proof is required, a shared-secret signature is not accepted "
        "in its place.",
        mechanism="With approval.require_asymmetric set, ApprovalGate refuses any token not "
        "carrying an Ed25519 operator signature, including a valid HMAC one, because HMAC cannot "
        "distinguish the operator from the agent process.",
        test="tests/test_signing.py::test_hmac_approval_is_refused_when_asymmetric_is_required",
    ),
    Policy(
        policy_id="RISK-004",
        law=2,
        status=EnforcementStatus.ENFORCED,
        predicate="Authorization goes stale; it does not stand indefinitely.",
        mechanism="ApprovalGate refuses tokens older than approval.ttl_seconds, and treats an "
        "unparseable grant time as expired.",
        test="tests/test_filesystem_adapter.py::test_expired_approval_is_refused",
    ),
    Policy(
        policy_id="LAW2-HALT",
        law=2,
        status=EnforcementStatus.ENFORCED,
        predicate="An operator instruction to stop takes precedence over the goal in progress.",
        mechanism="The dispatcher reads the halt file before every phase and stops the cycle as "
        "HALTED rather than FAILED, because an operator stopping work is not the work failing. "
        "The halt file is a protected path, so a running cycle cannot clear its own stop order.",
        test="tests/test_interdiction.py::test_a_halt_stops_the_cycle_and_cannot_be_cleared_by_it",
    ),
    Policy(
        policy_id="LAW3-SELF",
        law=3,
        status=EnforcementStatus.NOT_ENFORCED,
        predicate="Self-preservation is subordinate to Laws 1 and 2.",
        mechanism="None. Orrery has no self-preservation drive to subordinate.",
    ),
    Policy(
        policy_id="LAW3-SUBORDINATE",
        law=3,
        status=EnforcementStatus.ENFORCED,
        predicate="A cycle may not act on the machinery that audits or constrains it.",
        mechanism="InterdictionGate refuses any action whose path parameters reach the ledger, "
        "the checkpoint store, the attestation, the operator keyring, or the halt file — checked "
        "in both directions, since deleting a parent destroys a child. Orrery has no "
        "self-preservation drive to subordinate, but a cycle that could erase its own record or "
        "rewrite its own limits would have the means to act against an operator regardless of "
        "whether it had the motive.",
        test="tests/test_interdiction.py::test_an_action_cannot_reach_the_ledger",
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
        policy_id="LAW4-CONFORM",
        law=4,
        status=EnforcementStatus.ENFORCED,
        predicate="Subordinate systems are tested against the reporting contract, not trusted to "
        "honour it.",
        mechanism="The Adapter Conformance Kit (ADP-001..ADP-012) is run in CI against every "
        "bundled adapter: receipts must echo the request, unsupported actions must fail rather "
        "than raise or falsely succeed, and no adapter may stamp its own output as simulated.",
        test="tests/test_adapter_conformance.py::test_bundled_adapters_conform",
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
        policy_id="LAW7-REAL",
        law=7,
        status=EnforcementStatus.ENFORCED,
        predicate="At least one adapter's success claims are checked against the world, not "
        "against the framework's own bookkeeping.",
        mechanism="FileSystemAdapter performs real I/O inside a sandbox root, and its tests assert "
        "against the filesystem after the fact. The three legacy adapters remain simulations.",
        test="tests/test_filesystem_adapter.py::test_write_then_read_touches_the_real_filesystem",
    ),
    Policy(
        policy_id="LAW7-GOAL",
        law=7,
        status=EnforcementStatus.PARTIAL,
        predicate="A cycle does not certify a goal it has not checked.",
        mechanism="SelfCritiqueEngine accepts a goal_check that inspects the world. If it reports "
        "the goal unmet, reflection fails regardless of how many actions succeeded, and a check "
        "that raises counts as unverified. With no goal check supplied the result records "
        "goal_verified=None and says the score reflects adapter outcomes only. Partial because "
        "the check is the operator's to write: Orrery cannot infer what the goal means.",
        test="tests/test_critique.py::test_goal_check_overrides_a_passing_success_ratio",
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
        mechanism="Ed25519 signing with the configured operator identity, verified against a "
        "public keyring the framework cannot sign with; HMAC-SHA256 via ORRERY_CHECKPOINT_KEY "
        "when no operator key is present. integrity.require_asymmetric refuses HMAC-signed "
        "checkpoints outright. Partial because signing is off by default.",
        test="tests/test_signing.py::test_checkpoints_are_signed_with_the_operator_key",
    ),
    Policy(
        policy_id="LAW9-HINDSIGHT",
        law=9,
        status=EnforcementStatus.PARTIAL,
        predicate="The record of what was tried and abandoned is used, not merely kept.",
        mechanism="orrery/core/hindsight.py reads the ledger — which survives rollback, so it "
        "retains the attempts state discarded — and drafts prohibitions and classifications for "
        "recurring refusals, holds, and failures, each carrying the ledger sequences that "
        "justify it. Partial, and deliberately so: a proposal is inert. It has no signature and "
        "no path into enforcement, and a classification's risk is left unset because repetition "
        "shows an action recurs, never what it does. Enacting one is an operator act through the "
        "ordinary signing path.",
        test="tests/test_hindsight.py::test_a_proposal_is_inert",
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
        policy_id="RISK-000",
        law=9,
        status=EnforcementStatus.ENFORCED,
        predicate="Every refused action is recorded with the policy that refused it.",
        mechanism="execute_action appends an action.refused event carrying the deciding policy_id, "
        "the action's risk class, and the target adapter, before returning the failed receipt.",
        test="tests/test_filesystem_adapter.py::test_refused_action_is_recorded_in_the_ledger",
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
        policy_id="LAW10-RATELIMIT",
        law=10,
        status=EnforcementStatus.ENFORCED,
        predicate="Burst operations are capped before execution to prevent resource exhaustion.",
        mechanism="RateLimitGate checks sliding-window action frequency per adapter/action before "
        "dispatch; requests exceeding the configured ceiling are refused.",
        test="tests/test_ratelimit.py::test_burst_actions_exceeding_rate_limit_are_refused",
    ),
    Policy(
        policy_id="LAW10-CHARTER",
        law=10,
        status=EnforcementStatus.ENFORCED,
        predicate="The 10 Laws cannot be changed, or fall out of agreement with each other, "
        "without the change being visible.",
        mechanism="One charter document is canonical; the others are compared to it Law by Law, "
        "tolerant of case and punctuation and intolerant of word choice. Every charter file's "
        "digest is pinned in config/charter_manifest.json and checked in CI, and the combined "
        "charter digest is part of the configuration attestation, so approving a configuration "
        "approves the charter it runs under. This detects disagreement and unreviewed edits; it "
        "says nothing about whether the Laws are obeyed.",
        test="tests/test_charter.py::test_every_document_states_the_same_ten_laws",
    ),
    Policy(
        policy_id="LAW10-INVARIANT",
        law=10,
        status=EnforcementStatus.PARTIAL,
        predicate="Behaviour that is only pathological in aggregate is visible.",
        mechanism="InvariantMonitor evaluates operator-declared limits over a time window of "
        "the ledger, which retains attempts that backtracking discarded, and records a breach "
        "as a ledger event; configured to halt, it stops the cycle. Partial for two reasons and "
        "the second is not a technicality: it is off by default, and it is DETECTION. An "
        "invariant is evaluated after the breaching action has already run, so it can contain "
        "what follows but cannot prevent what happened.",
        test="tests/test_invariants.py::test_an_invariant_cannot_prevent_the_action_that_breached_it",
    ),
    Policy(
        policy_id="LAW10-APPROVAL",
        law=10,
        status=EnforcementStatus.PARTIAL,
        predicate="Core directives may only be modified with cryptographically secured "
        "Governance approval.",
        mechanism="The settings that bound Orrery's authority — approval, integrity, delegation, "
        "critique thresholds, simulated-adapter permission — are digested together with the "
        "governance registry itself, and config/attestation.json carries an operator's Ed25519 "
        "signature over that digest. With governance.require_attestation set, a dispatcher "
        "refuses to construct when the running configuration does not match a valid attestation. "
        "Partial, and narrowly so: this binds configuration and policy declarations, not the "
        "code. Anyone able to edit the source can delete the check.",
        test="tests/test_attestation.py::test_dispatcher_refuses_to_start_on_an_unattested_configuration",
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
    The strongest status any policy achieves for each Law. Several Laws have no runtime
    control at all; that is the honest headline, not a rounding error.
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
