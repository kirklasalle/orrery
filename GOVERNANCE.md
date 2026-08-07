# Governance

Orrery's charter is the [10 Laws for Intelligence Systems](AGENTIC_PRIME_DIRECTIVE.md),
authored by Kirk LaSalle. This document records, without flattery, which of those Laws
Orrery enforces **at runtime** and which it merely aspires to.

The table below is generated from [orrery/core/governance.py](orrery/core/governance.py)
and checked against it by [tests/test_governance.py](tests/test_governance.py) in CI. The
document cannot claim more than the code implements, because the build fails if it does.

## The headline

**3 of the 10 Laws have no runtime control in Orrery at all.**

Laws 3, 5, and 8 concern self-preservation, judicial authority, and equity. None of them
can be evaluated by a cycle engine that does not know what its adapters do in the world.
They are constraints on *deployment* — on the adapters you write and the goals you give —
and listing them here as "enforced" would be exactly the kind of unearned claim Law 7
forbids.

Laws 1 and 2 moved from ❌ to ⚠️ when the risk classification and approval gate landed.
Read that change narrowly. Orrery still has no harm model and cannot judge whether an
action is *good*. What it can now do is refuse to perform an action it cannot undo unless
a human explicitly authorized that exact action. That bounds the **class** of what happens
without consent; it says nothing about the content of what is consented to. A permitted
file write can still be catastrophic.

What Orrery *can* enforce, it does: the mechanical Laws. Law 6 (data), Law 7 (no
deception), Law 9 (auditability), and Law 10 (operational boundaries) have runtime
controls with tests behind them.

## Enforcement status by Law

| Law | Subject | Status |
| --- | --- | --- |
| 1 | Harm prevention | ⚠️ Partial |
| 2 | Obedience | ⚠️ Partial |
| 3 | Self-preservation | ❌ Not enforced |
| 4 | Laws bind subordinate systems | ✅ Enforced |
| 5 | No judicial authority | ❌ Not enforced |
| 6 | Data integrity and confidentiality | ✅ Enforced |
| 7 | No deception | ✅ Enforced |
| 8 | Equity and neutrality | ❌ Not enforced |
| 9 | Transparent, auditable ledger | ✅ Enforced |
| 10 | Operational boundaries | ✅ Enforced |

## Policy registry

Each policy is a predicate the runtime can actually evaluate, the mechanism that evaluates
it, and the test that proves the mechanism works.

### Law 1 — Harm prevention

| Policy | Status | Predicate | Mechanism | Test |
| --- | --- | --- | --- | --- |
| `LAW1-HARM` | ❌ Not enforced | No action may cause physical or psychological harm. | None. Orrery has no harm model. This belongs to the adapter and the operator. | — |
| `RISK-CLASS` | ⚠️ Partial | An action's blast radius is classified before it runs, and the planner cannot understate it. | Adapters declare an `ActionRisk` per action name. The dispatcher takes the **stricter** of the planner's declaration and the adapter's, so a plan cannot relabel a delete as harmless. Undeclared actions are treated as irreversible. | `test_a_planner_cannot_downgrade_an_irreversible_action` |
| `RISK-001` | ⚠️ Partial | Nothing the framework cannot undo executes without explicit human authorization. | `ApprovalGate` refuses `IRREVERSIBLE` actions carrying no `ApprovalToken`, and `COMPENSABLE` ones when configured. Refusals are ledgered with the deciding policy. | `test_irreversible_action_is_refused_without_approval` |
| `RISK-002` | ✅ Enforced | Consent granted for one action cannot authorize another. | `ApprovalToken` is bound to a single `action_id`; the gate refuses any mismatch. | `test_approval_cannot_be_replayed_against_another_action` |

`RISK-001` is partial because it inherits the adapter's honesty. The gate refuses what is
*classified* irreversible; an adapter that misclassifies a destructive action as reversible
walks straight through it. That is why unlisted actions default to `IRREVERSIBLE` and why
the conformance kit (`LAW4-CONFORM`) checks risk declarations.

### Law 2 — Obedience

| Policy | Status | Predicate | Mechanism | Test |
| --- | --- | --- | --- | --- |
| `LAW2-OBEY` | ❌ Not enforced | Orders are obeyed unless they conflict with Law 1. | None. The goal string is executed as given; there is no conflict evaluator. | — |
| `RISK-003` | ⚠️ Partial | An authorization can be shown to have come from a human, not from the agent. | HMAC-SHA256 token signing when `ORRERY_APPROVAL_KEY` is set and `approval.require_signed` is on. | `test_signed_approval_passes_and_a_forged_one_does_not` |
| `RISK-004` | ✅ Enforced | Authorization goes stale; it does not stand indefinitely. | The gate refuses tokens older than `approval.ttl_seconds`, and treats an unparseable grant time as expired. | `test_expired_approval_is_refused` |

`RISK-003` is **off by default**, and this is the sharpest limit in the whole approval
mechanism: without `ORRERY_APPROVAL_KEY`, any code running in the same process can mint a
token. An unsigned `ApprovalToken` documents intent. It does not prove consent. Treat it as
a record for the audit trail, not as a security control, until signing is enabled — and
even then a shared symmetric key proves custody, not authorship.

### Law 3 — Self-preservation

| Policy | Status | Predicate | Mechanism |
|---|---|---|---|
| `LAW3-SELF` | ❌ Not enforced | Self-preservation is subordinate to Laws 1 and 2. | None. Orrery has no self-preservation drive to subordinate. |

### Law 4 — Laws bind subordinate systems

| Policy | Status | Predicate | Mechanism | Test |
| --- | --- | --- | --- | --- |
| `LAW4-ADAPTER` | ⚠️ Partial | Subordinate systems are held to the same reporting rules as the cycle. | Every adapter call produces a receipt; an adapter that raises or is unregistered yields a *failed* receipt. Nothing can report success on the cycle's behalf without executing. | `test_adapter_exception_becomes_failed_receipt` |
| `LAW4-CONFORM` | ✅ Enforced | Subordinate systems are tested against the reporting contract, not trusted to honour it. | The Adapter Conformance Kit (`ADP-001`…`ADP-012`) runs in CI against every bundled adapter: receipts must echo the request, unsupported actions must fail rather than raise or falsely succeed, and no adapter may stamp its own output as `simulated`. | `test_bundled_adapters_conform` |

`LAW4-ADAPTER` stays partial because Orrery governs how subordinate systems *report*, not
what they *do*. The conformance kit narrows the gap but does not close it: it verifies the
shape of an adapter's honesty, not its substance.

Running the kit against your own adapter:

```python
from orrery.adapters.conformance import run_conformance

report = run_conformance(MyAdapter(), sample_action="read_thing", sample_params={"id": "1"})
assert report.passed, report.summary
```

An adapter that publishes no `declared_risks` cannot be checked for unsupported-action
handling, so `ADP-005` and `ADP-006` are recorded as **skipped** rather than passed, and
`risk_for()` treats every one of its actions as `IRREVERSIBLE`. Declaring a vocabulary is
how an adapter earns proportionate risk treatment.

### Law 5 — No judicial authority

| Policy | Status | Predicate | Mechanism |
|---|---|---|---|
| `LAW5-JUDICIAL` | ❌ Not enforced | No judicial authority or interpretation of human law. | None. A deployment constraint, not something the engine can detect. |

### Law 6 — Data integrity and confidentiality

| Policy | Status | Predicate | Mechanism | Test |
| --- | --- | --- | --- | --- |
| `LAW6-PATH` | ✅ Enforced | Identifiers in filesystem paths cannot escape the storage root. | Canonical-UUID validation on cycle and checkpoint IDs, plus path resolution checked against the storage root. | `tests/test_security.py` |
| `LAW6-PERM` | ✅ Enforced | Persisted state and audit records are owner-readable only. | Checkpoint files and the ledger are `chmod 0600` on creation. | `tests/test_security.py` |

`LAW6-PERM` is a POSIX guarantee. On Windows, `os.chmod` does not restrict ACLs; treat
the checkpoint and ledger directories as sensitive and secure them at the filesystem level.

### Law 7 — No deception

| Policy | Status | Predicate | Mechanism | Test |
| --- | --- | --- | --- | --- |
| `LAW7-NOFAKE` | ✅ Enforced | The framework never reports success for work it did not perform. | No code path constructs a successful receipt without an adapter having executed. Unrouted actions fail explicitly. | `test_unregistered_adapter_fails_rather_than_reporting_success` |
| `LAW7-SIM` | ✅ Enforced | Simulated work is distinguishable from real work. | Adapters declare `is_simulation`; registration is logged and ledgered, and receipts are tagged `simulated: True`. | `test_ledger_records_simulation_adapters` |
| `LAW7-REAL` | ✅ Enforced | At least one adapter's success claims are checked against the world, not against the framework's own bookkeeping. | `FileSystemAdapter` performs real I/O inside a sandbox root, and its tests assert against the filesystem after the fact. | `test_write_then_read_touches_the_real_filesystem` |

The bundled `openclaw`, `hermes`, and `windows_os` adapters are **simulations**. They
declare it, and Orrery marks their output. Any benchmark run against them measures the
state machine, not the world.

`FileSystemAdapter` is the exception: it is real. It reads, writes, moves, and deletes
actual files inside a sandbox root it refuses to escape, and `delete_file` is the first
action in this codebase that can genuinely destroy something. Risk classification was
theatre until that existed.

### Law 8 — Equity and neutrality

| Policy | Status | Predicate | Mechanism |
|---|---|---|---|
| `LAW8-EQUITY` | ❌ Not enforced | No systemic bias in decisions. | None. Orrery makes no content decisions and has no fairness instrumentation. |

### Law 9 — Transparent, auditable ledger

| Policy | Status | Predicate | Mechanism | Test |
| --- | --- | --- | --- | --- |
| `LAW9-LEDGER` | ✅ Enforced | Every phase transition, action, and critique is recorded. | `EventLedger` receives an event per phase entry, action outcome, and critique, persisted as JSONL. | `test_ledger_persists_to_disk_and_reloads` |
| `LAW9-APPEND` | ✅ Enforced | The audit record is append-only and survives rollback. | The ledger exposes no delete, update, or truncate operation, lives outside the rewindable `StateContext`, and records each rollback as an event. | `test_ledger_survives_backtracking` |
| `LAW9-CHAIN` | ✅ Enforced | Altering past state is detectable. | Checkpoints and ledger events are SHA-256 hash-linked; verification runs on load and refuses a checkpoint whose digest does not match. | `test_edited_checkpoint_file_is_refused_on_load` |
| `LAW9-SIGN` | ⚠️ Partial | The audit record is cryptographically attributable. | HMAC-SHA256 signing when `ORRERY_CHECKPOINT_KEY` is set. | `test_signature_is_required_when_configured` |
| `LAW9-MONO` | ✅ Enforced | The record of work never moves backwards, even when work is rewound. | `backtrack()` takes `max()` on `step_count` and carries `lessons` and `attempt_log` across the rollback. | `test_step_count_never_regresses_across_backtracking` |
| `RISK-000` | ✅ Enforced | Every refused action is recorded with the policy that refused it. | `execute_action` appends an `action.refused` event carrying the deciding `policy_id`, the action's risk class, and the target adapter, before returning the failed receipt. | `test_refused_action_is_recorded_in_the_ledger` |

`LAW9-SIGN` is partial for two honest reasons. Signing is **off by default**, and an
unsigned hash chain stops corruption and casual editing but not an attacker, who can
recompute the whole chain. Even when enabled, a shared symmetric key proves *custody*, not
*authorship*: anyone holding the key can produce a valid signature. Asymmetric,
per-operator signing is not implemented.

### Law 10 — Operational boundaries

| Policy | Status | Predicate | Mechanism | Test |
| --- | --- | --- | --- | --- |
| `DEL-000` | ✅ Enforced | Every delegation, permitted or refused, is recorded with the deciding policy. | `authorize()` logs refusals; `BaseCycle` ledgers every decision with its `policy_id`. | `test_delegation_decisions_reach_the_ledger` |
| `DEL-001` | ✅ Enforced | Delegation may not exceed the configured depth. | `DelegationPolicy` refuses requests deeper than `delegation.max_depth`. | `test_depth_cap_refuses_delegation` |
| `DEL-002` | ✅ Enforced | A cycle may not spawn unbounded children. | Per-parent fan-out cap in the shared `DelegationBudget`. | `test_fan_out_cap_refuses_delegation` |
| `DEL-003` | ✅ Enforced | A cycle tree may not exceed its population cap. | Tree-wide spawn counter in the shared `DelegationBudget`. | `test_population_cap_refuses_delegation` |
| `DEL-004` | ✅ Enforced | Delegation may not loop back onto an ancestor. | Ancestry set carried down the tree, checked before authorization. | `test_ancestry_loop_is_refused` |
| `DEL-005` | ✅ Enforced | Delegation must descend the tier hierarchy. | Tier rank comparison; sideways and upward delegation are refused. | `test_delegation_must_descend_the_tier_hierarchy` |
| `LAW10-BUDGET` | ✅ Enforced | A cycle may not run without bound. | `run_full_cycle` enforces a step budget and an `asyncio` wall-clock budget; both exhaustion paths mark the cycle `FAILED`. | `test_run_full_cycle_honours_step_budget` |
| `LAW10-APPROVAL` | ❌ Not enforced | Core directives may only be modified with cryptographically secured Governance approval. | None. Settings and policies are ordinary files. There is no signed-approval workflow and no attestation of the running configuration. | |

`LAW10-APPROVAL` is the most significant remaining gap in a Law that is otherwise well
covered. Orrery bounds what a cycle tree may *do*; it does not yet verify that the rules
it is bounding by are the ones Governance approved.

## Configuring enforcement

All limits live in [config/settings.yaml](config/settings.yaml) and are loaded at startup.
Override the path with `ORRERY_SETTINGS`.

```yaml
delegation:
  max_depth: 4
  max_children_per_cycle: 8
  max_total_cycles: 32
  enforce_tier_descent: true

ledger:
  persist: true
  storage_dir: ".ledger"

meta_skills:
  integrity:
    verify_on_load: true
    require_signature: false
```

To enable signing:

```bash
export ORRERY_CHECKPOINT_KEY="<a high-entropy secret>"
# then set meta_skills.integrity.require_signature: true
```

With `require_signature: true`, loading an unsigned or mis-signed checkpoint raises
`IntegrityError` rather than returning `None`. Rotating the key invalidates every existing
signature; there is no re-signing tool.

## Extending policy

Subclass `DelegationPolicy` to add site-specific rules, and pass it to any cycle:

```python
from orrery.core.delegation import DelegationDecision, DelegationPolicy

class BusinessHoursOnly(DelegationPolicy):
    def authorize(self, request, budget):
        decision = super().authorize(request, budget)
        if decision.allowed and not within_business_hours():
            return DelegationDecision(
                allowed=False, policy_id="SITE-001", reason="outside approved hours"
            )
        return decision

cycle = MetaCycle(delegation_policy=BusinessHoursOnly())
```

Children inherit the parent's policy via `spawn_child`, so governance is not silently
reset one tier down.

## Reading the audit trail

```python
from orrery.core.ledger import EventLedger

events = EventLedger.read(Path(".ledger/events.jsonl"))
for event in events:
    print(event.sequence, event.event_type, event.policy_id, event.summary)
```

Verify the chain with `ledger.verify()` for the live ledger, or
`manager.verify_chain(cycle_id)` for a cycle's checkpoints.
