# Governance

Orrery's charter is the [10 Laws for Intelligence Systems](AGENTIC_PRIME_DIRECTIVE.md),
authored by Kirk LaSalle. This document records, without flattery, which of those Laws
Orrery enforces **at runtime** and which it merely aspires to.

The table below is generated from [orrery/core/governance.py](orrery/core/governance.py)
and checked against it by [tests/test_governance.py](tests/test_governance.py) in CI. The
document cannot claim more than the code implements, because the build fails if it does.

## The headline

**2 of the 10 Laws have no runtime control in Orrery at all.**

Laws 5 and 8 concern judicial authority and equity. Neither can be evaluated by a cycle
engine that makes no content decisions and does not know what its adapters mean in the
world. They are constraints on *deployment* — on the adapters you write and the goals you
give — and listing them here as "enforced" would be exactly the kind of unearned claim Law
7 forbids.

Laws 1 and 2 moved from ❌ to ⚠️ when the risk classification and approval gate landed.
Read that change narrowly. Orrery still has no harm model and cannot judge whether an
action is *good*. What it can now do is refuse to perform an action it cannot undo unless
a human explicitly authorized that exact action, and refuse outright what an operator has
declared forbidden. That bounds the **class** of what happens without consent; it says
nothing about the content of what is consented to. A permitted file write can still be
catastrophic.

Law 3 moved to ✅ for a reason that is not the obvious one. Orrery has no
self-preservation drive to subordinate, and adding one to then suppress it would be
theatre. What it now enforces is the consequence the Law exists to prevent: a cycle cannot
act on the ledger, checkpoints, attestation, keyring, or halt file that audit and
constrain it. A system that could erase its own record or rewrite its own limits would
have the *means* to act against an operator whether or not it had the motive.

What Orrery *can* enforce, it does: the mechanical Laws. Law 6 (data), Law 7 (no
deception), Law 9 (auditability), and Law 10 (operational boundaries) have runtime
controls with tests behind them.

## Enforcement status by Law

| Law | Subject | Status |
| --- | --- | --- |
| 1 | Harm prevention | ⚠️ Partial |
| 2 | Obedience | ⚠️ Partial |
| 3 | Self-preservation | ✅ Enforced |
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
| `LAW1-PROHIBIT` | ⚠️ Partial | Actions an operator has declared forbidden are refused, and no approval overrides them. | `InterdictionGate` matches each action against operator-declared prohibitions by adapter, action name, and path **before** the approval gate runs, so a prohibited action cannot be authorized at execution time. | `test_a_prohibited_action_is_refused_even_with_approval` |
| `LAW1-QUARANTINE` | ⚠️ Partial | An action the framework cannot characterise is held, not guessed at. | `QuarantineGate` holds any action its adapter never declared, releasing it only against an operator `Classification` stating what the action *is*. Off by default; when off, an undeclared action falls back to being treated as `IRREVERSIBLE`. | `test_a_classification_is_not_an_authorisation` |
| `LAW1-ENVELOPE` | ⚠️ Partial | An action is judged by what it reaches, not by whether its name appears on a list. | An adapter declares the boundary of what it will ever touch and which parameters name a location; a deployment declares what anything may touch here. Both must permit, so the effective envelope is their **intersection**. A breach is refused, not held. Off by default. | `test_an_action_nobody_enumerated_is_judged_by_where_it_lands` |
| `RISK-CLASS` | ⚠️ Partial | An action's blast radius is classified before it runs, and the planner cannot understate it. | Adapters declare an `ActionRisk` per action name. The dispatcher takes the **stricter** of the planner's declaration and the adapter's, so a plan cannot relabel a delete as harmless. Undeclared actions are treated as irreversible. | `test_a_planner_cannot_downgrade_an_irreversible_action` |
| `RISK-001` | ⚠️ Partial | Nothing the framework cannot undo executes without explicit human authorization. | `ApprovalGate` refuses `IRREVERSIBLE` actions carrying no `ApprovalToken`, and `COMPENSABLE` ones when configured. Refusals are ledgered with the deciding policy. | `test_irreversible_action_is_refused_without_approval` |
| `RISK-002` | ✅ Enforced | Consent granted for one action cannot authorize another. | `ApprovalToken` is bound to a single `action_id`; the gate refuses any mismatch. | `test_approval_cannot_be_replayed_against_another_action` |

`RISK-001` is partial because it inherits the adapter's honesty. The gate refuses what is
*classified* irreversible; an adapter that misclassifies a destructive action as reversible
walks straight through it. That is why unlisted actions default to `IRREVERSIBLE` and why
the conformance kit (`LAW4-CONFORM`) checks risk declarations.

`LAW1-PROHIBIT` does **not** give Orrery a harm model. It gives an operator — who can judge
harm — somewhere to write the judgement down, and guarantees the framework will not
negotiate with it at execution time. An `ApprovalToken` answers "may I do this irreversible
thing?"; a prohibition means the question is not open. It is only ever as good as what the
operator thought to forbid, which is why it is Partial and always will be.

`LAW1-QUARANTINE` answers a different question again, and the distinction is load-bearing.
Approval answers a *known* question — "this is `IRREVERSIBLE`, may I?" — where the system
understands the action and needs only consent. Quarantine answers an *unknown*: "I cannot
characterise this at all." Routing unknowns through the approval gate would quietly erode
what an `ApprovalToken` means, from *a human authorised this specific irreversible action*
to *somebody clicked yes on something nobody understood*.

So releasing a held action requires a **classification** — a statement of what the action
is, signable by an operator — rather than a permission. **A classification never
authorises.** It is necessarily broad (it describes a *kind* of action) where an
`ApprovalToken` is deliberately narrow (one `action_id`, single use, expiring); if the two
collapsed into one object, the broad thing would inherit the narrow thing's authority and
this would become a permission cache with a governance label on it. A released action faces
the risk and approval gates unchanged. Review the queue with
`python -m orrery.tools.quarantine`.

Unclassified is not the same as unclassifiable-but-probably-fine: an adapter that declares
nothing has made **no claim**, which is different from claiming an action is dangerous. So
an undeclared *and* unclassified action is assumed `IRREVERSIBLE`, while an undeclared but
classified one defers to the operator who actually looked. Pinned by
`test_an_undeclared_action_is_treated_as_irreversible`, which had to be written because the
rule was documented here for two gates before the dispatcher actually implemented it.

`LAW1-ENVELOPE` is the only control here that is not enumerative. Every other one matches
against a list somebody wrote in advance — action names, paths, adapters — and is therefore
silent about an action invented next year. An envelope inverts that: it declares the region
that may be reached, so a brand-new action is judged by **where it lands**, and nobody has
to have heard of it.

The adapter's declaration is a claim by whoever wrote the code, checkable against the
implementation. The deployment's is the operator's boundary, and holds regardless of what an
adapter claims about itself. Their intersection can only ever be narrower than either: an
adapter cannot widen the operator's boundary with a generous self-declaration, and an
operator cannot grant an adapter reach its author never intended.

Two honest limits. First, **reach is inferred from the values an action carries**, so Orrery
sees filesystem paths and nothing else — an adapter that opens a socket or writes through a
handle it already holds is outside an envelope's view. This bounds where an action *points*,
not what it does. Second, an adapter must declare which parameters name a location, and
silence under enforcement is refusal. That is not the enumeration problem returning: unlike
protected paths, which scan every value because over-scanning a *denylist* is safe, an
allowlist cannot over-scan — the contents of a file being written are not a path and would
be refused for not living inside a directory.

### Law 2 — Obedience

| Policy | Status | Predicate | Mechanism | Test |
| --- | --- | --- | --- | --- |
| `LAW2-OBEY` | ❌ Not enforced | Orders are obeyed unless they conflict with Law 1. | None. The goal string is executed as given; there is no conflict evaluator. | — |
| `LAW2-HALT` | ✅ Enforced | An operator instruction to stop takes precedence over the goal in progress. | The dispatcher reads the halt file before every phase and stops the cycle as `HALTED` — not `FAILED`, because an operator stopping work is not the work failing. The halt file is a protected path, so a running cycle cannot clear its own stop order. | `test_a_halt_stops_the_cycle_and_cannot_be_cleared_by_it` |
| `RISK-003` | ⚠️ Partial | An authorization can be shown to have come from a human, not from the agent. | Ed25519 per-operator signing when `ORRERY_OPERATOR_ID` and `ORRERY_OPERATOR_PRIVATE_KEY` are set, verified against a public keyring the framework cannot sign with; a token's signing key must match the approver it names. HMAC via `ORRERY_APPROVAL_KEY` remains supported. | `test_operator_signed_approval_verifies_and_a_forged_one_does_not` |
| `RISK-005` | ✅ Enforced | When asymmetric proof is required, a shared-secret signature is not accepted in its place. | With `approval.require_asymmetric` set, the gate refuses any token without an Ed25519 operator signature — including a *valid* HMAC one. | `test_hmac_approval_is_refused_when_asymmetric_is_required` |
| `RISK-004` | ✅ Enforced | Authorization goes stale; it does not stand indefinitely. | The gate refuses tokens older than `approval.ttl_seconds`, and treats an unparseable grant time as expired. | `test_expired_approval_is_refused` |

`RISK-003` is **off by default**, and that remains the sharpest limit in the approval
mechanism: with no signing configured, any code running in the same process can mint a
token. An unsigned `ApprovalToken` documents intent. It does not prove consent.

The two signing modes do not prove the same thing, and the difference is the whole point.
HMAC proves *custody* of a shared secret — and the agent process holds that secret too, so
it cannot distinguish a human operator from the code asking for permission. Ed25519
separates signing from verifying: the operator keeps a private key the framework never
sees, and the framework keeps only public keys. Only in that configuration is "a human
approved this" something Orrery can substantiate rather than merely repeat.

Create an identity with `python -m orrery.tools.keygen --operator <name>`. On any machine
that only needs to *verify*, set `ORRERY_OPERATOR_KEYRING` alone and withhold the private
key: a process that cannot sign cannot forge consent.

### Law 3 — Self-preservation

| Policy | Status | Predicate | Mechanism | Test |
| --- | --- | --- | --- | --- |
| `LAW3-SELF` | ❌ Not enforced | Self-preservation is subordinate to Laws 1 and 2. | None. Orrery has no self-preservation drive to subordinate. | — |
| `LAW3-SUBORDINATE` | ✅ Enforced | A cycle may not act on the machinery that audits or constrains it. | `InterdictionGate` refuses any action whose values reach the ledger, the checkpoint store, the attestation, the operator keyring, or the halt file — checked in **both** directions, since deleting a parent destroys a child, and resolved under both the adapter's claimed root and the process directory, since that root is the adapter's own assertion. | `test_an_action_cannot_reach_the_ledger` |

These two say different things and both are true. Orrery has no drive to preserve itself,
so there is nothing to subordinate and `LAW3-SELF` stays ❌. But the *capability* the Law
guards against is real and was, until recently, entirely undefended: a `FileSystemAdapter`
rooted at the project directory could `delete_tree(".ledger")`, and the append-only audit
log that Law 9 rests on was protected by nothing but the absence of a plan to attack it.

**Every** parameter value is examined, recursively through lists and dicts — not a list of
parameter names. An earlier version checked only `path`, `source`, `destination`, `cwd`, and
`directory`, so an adapter whose parameter happened to be called `target_file` walked
straight past this. There is no opt-out and adapters are not consulted, because the point is
defending against adapters nobody vetted. For the same reason a relative path is resolved
under the adapter's claimed root *and* the process directory: a decoy sandbox would
otherwise make every path look harmless.

The honest limit: this is enforced at the **action** boundary, so reach is inferred from the
values an action carries. An adapter that holds a handle, opens a socket, or hard-codes a
destination names nothing, and there is nothing to check. It constrains actions, not
adapters. `tests/test_adversarial.py` asserts that limit rather than leaving it to be
discovered.

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
| `LAW7-GOAL` | 🟡 Partial | A cycle does not certify a goal it has not checked. | `SelfCritiqueEngine` accepts a `goal_check` that inspects the world; if it reports the goal unmet, reflection fails regardless of how many actions succeeded, and a check that raises counts as unverified. With no goal check supplied, the result records `goal_verified=None` and states that the score reflects adapter outcomes only. | `test_goal_check_overrides_a_passing_success_ratio` |

`LAW7-GOAL` is Partial for a reason worth stating plainly. Success ratio over receipts
measures whether adapters obeyed, not whether anything was accomplished: a plan in which
three of four actions succeed scores 0.75, clears the 0.70 threshold, and reports
`COMPLETED` for a goal it never reached. The benchmark suite
(`silent_partial_failure`) demonstrates exactly that. The goal check closes it, but only
when an operator supplies one — Orrery cannot infer what a goal means, and a framework
that guessed would be back to certifying its own work.

The `openclaw`, `hermes`, and `windows_os` adapters are **simulations**. They declare it,
Orrery marks their output, and they now live in `examples/simulated/` rather than in the
package, refused registration unless `adapters.allow_simulated` is switched on. Any
benchmark run against them measures the state machine, not the world.

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
| `LAW9-SIGN` | ⚠️ Partial | The audit record is cryptographically attributable. | Ed25519 signing with the configured operator identity, verified against a public keyring; HMAC-SHA256 via `ORRERY_CHECKPOINT_KEY` when no operator key is present. `integrity.require_asymmetric` refuses HMAC-signed checkpoints outright. | `test_checkpoints_are_signed_with_the_operator_key` |
| `LAW9-MONO` | ✅ Enforced | The record of work never moves backwards, even when work is rewound. | `backtrack()` takes `max()` on `step_count` and carries `lessons` and `attempt_log` across the rollback. | `test_step_count_never_regresses_across_backtracking` |
| `LAW9-HINDSIGHT` | ⚠️ Partial | The record of what was tried and abandoned is used, not merely kept. | `hindsight.py` reads the ledger and drafts prohibitions and classifications for recurring refusals, holds, and failures, each carrying the sequences that justify it. **A proposal is inert** — unsigned, unenforced, and with a classification's risk left unset. | `test_a_proposal_is_inert` |
| `RISK-000` | ✅ Enforced | Every refused action is recorded with the policy that refused it. | `execute_action` appends an `action.refused` event carrying the deciding `policy_id`, the action's risk class, and the target adapter, before returning the failed receipt. | `test_refused_action_is_recorded_in_the_ledger` |

`LAW9-SIGN` remains partial for one honest reason: signing is **off by default**, and an
unsigned hash chain stops corruption and casual editing but not an attacker, who can
recompute the whole chain. The second reason is gone. Per-operator Ed25519 signing is now
implemented, so an enabled chain is attributable to a person rather than to whoever held a
shared secret.

`LAW9-HINDSIGHT` exists because every other control here is enumerative and shares one
wall: somebody has to think of the rule in advance. The ledger removes that wall from the
other side. Because it lives outside rewindable state it retains what backtracking erased,
and an action a cycle keeps trying and keeps being refused is evidence no other framework
retains — one that stores history inside agent state destroys exactly this data.

Two properties keep it from being an agent granting itself authority. **A proposal is
inert**: no signature, no store, no path into enforcement, and enacting one is an operator
act through the ordinary signing path. **A proposal carries its evidence**, so it is an
argument to check rather than a verdict to trust. A classification's risk is deliberately
left unset, because repetition shows an action recurs and says nothing about what it does.

The limit: a pattern is not a judgement. Repetition is a reason to look, not a reason to
forbid, and Orrery cannot tell a dangerous action from one nobody has authorised yet. Read
the drafts with `python -m orrery.tools.propose`.

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
| `LAW10-INVARIANT` | ⚠️ Partial | Behaviour that is only pathological in aggregate is visible. | `InvariantMonitor` evaluates operator-declared limits over a window of the ledger and records a breach as a ledger event; configured to halt, it stops the cycle. Off by default, and **detection rather than prevention**. | `test_an_invariant_cannot_prevent_the_action_that_breached_it` |
| `LAW10-APPROVAL` | ⚠️ Partial | Core directives may only be modified with cryptographically secured Governance approval. | The settings that bound Orrery's authority — approval, integrity, delegation, critique thresholds, interdiction, simulated-adapter permission — are digested together with the governance registry and the charter, and `config/attestation.json` carries an operator's Ed25519 signature over that digest. With `governance.require_attestation` set, a dispatcher refuses to construct on an unattested configuration. | `test_dispatcher_refuses_to_start_on_an_unattested_configuration` |
| `LAW10-CHARTER` | ✅ Enforced | The 10 Laws cannot be changed, or fall out of agreement with each other, without the change being visible. | One charter document is canonical; the others are compared to it Law by Law. Every charter file's digest is pinned in `config/charter_manifest.json` and checked in CI, and the combined charter digest is folded into the attestation. | `test_every_document_states_the_same_ten_laws` |

`LAW10-CHARTER` exists because the 10 Laws are written out in full in **three** documents,
which is a drift machine — and it had already drifted. When the Fourth Law's "conforms to"
was corrected to "violates" (as written, it forbade *compliance*), the fix landed in two
documents and not the third, and nothing noticed. Comparison is deliberately tolerant of
case, whitespace, and dash style and intolerant of word choice: "An intelligence System"
and "An Intelligence System" are the same Law; a different verb is not.

It detects disagreement and unreviewed edits. It says nothing about whether the Laws are
*obeyed* — that is what the rest of this document is for, and it is candid that 2 of the 10
have no runtime control at all. Check with `python -m orrery.tools.charter`; re-pin a
deliberate change with `--update`.

`LAW10-APPROVAL` is partial, and narrowly so. **It binds configuration and policy
declarations, not the code.** An attestation makes loosening a limit an attributable act
rather than a quiet edit: change `require_for_irreversible` to `false` and the digest no
longer matches, so the framework refuses to start until somebody signs for that decision.
Downgrading a policy in the registry breaks it the same way. But anyone able to edit
`orrery/core/approval.py` can delete the check entirely, and no amount of signing inside a
program defends against an attacker who controls that program. This raises the cost of a
silent configuration change. It is not a substitute for controlling who can deploy.

Approve a configuration with `python -m orrery.tools.attest --sign`; inspect exactly what
is covered with `--show`.

`LAW10-INVARIANT` covers the violations that do not exist in any single action. No
individual file read is exfiltration; ten thousand in three seconds is. No single refusal is
alarming; forty in a minute is a planner probing its boundaries. The shape *is* the
violation, and the shape only exists across events.

The ledger is the right substrate for this because it is append-only and immune to rollback:
a runaway loop that tries the same destructive thing forty times and rewinds after each one
leaves nothing in `StateContext` and forty entries here.

**It is Partial for two reasons, and the second is not a technicality.** It is off by
default — and it is *detection*. An invariant is evaluated after the breaching action has
already been dispatched. Set to halt, it stops the *next* action, which is containment and
worth having; anything describing it as preventing exfiltration would be false. An invariant
also sees only what the ledger records — event types, policy IDs, action names, adapters,
risk classes, approvers, outcomes — and not parameter values, so it can count `read_file`
actions and cannot tell you which files.

**This does not give Law 8 a foothold.** Distributional fairness is the one Law that would
naturally live at this resolution, and a bias detector needs a domain model Orrery does not
have and cannot infer. This is where such a control would go if an operator supplied the
grouping. Orrery ships none, and `LAW8-EQUITY` remains ❌.

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
