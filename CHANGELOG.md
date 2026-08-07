# Changelog

All notable changes to the **Orrery** framework (formerly *Cognition Cycles*) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **The charter gate would have failed every Linux CI run.** `config/charter_manifest.json`
  pinned SHA-256 over raw file *bytes*, and the charter documents are stored LF but check out
  CRLF on Windows — so a manifest pinned on one platform mismatches on the other and the build
  fails with a spurious "has changed since it was pinned". Digests are now taken over
  normalised content: a charter does not change meaning because a checkout added carriage
  returns. Pinned by `test_the_digest_does_not_depend_on_line_endings`.
- `tests/test_process_adapter.py` resolved its interpreter as `Path(sys.executable).name`,
  which is not always on `PATH` — CI images vary between `python`, `python3`, and
  `python3.10`, and `ProcessAdapter` resolves an allowlisted program by name.

### Added

- **Hindsight — the ledger proposes, the operator disposes.** `orrery/core/hindsight.py` and
  `LAW9-HINDSIGHT`.
  - Every constraint in this framework is enumerative and they all share one wall: somebody
    has to think of the rule in advance. Fail-closed defaults route around that wall; they do
    not remove it. The ledger removes it from the other side. Because it lives outside
    rewindable state it **retains the attempts backtracking erased**, and a framework that
    stores history inside agent state destroys exactly this data.
  - Orrery now reads its own past and drafts prohibitions and classifications for actions that
    recur across cycles — repeatedly refused and never permitted, repeatedly held, repeatedly
    failed — each carrying the ledger sequences that justify it. `python -m orrery.tools.propose`.
  - **A proposal is inert.** No signature, no store, no path into enforcement. Enacting one is
    an operator act through the ordinary signing path, and
    `test_a_proposal_is_inert` exists to keep it that way.
  - **A classification proposal leaves the risk unset**, because repetition shows that an
    action recurs and says nothing about what it does. Filling it in would fabricate the one
    judgement only a human can make.
  - A signal must recur across several *cycles*, not merely several times: twenty refusals
    inside one loop is an incident, not a tendency, and governance drafted from it would encode
    the wrong thing.
  - The honest limit: a pattern is not a judgement. Repetition is a reason to look, not a
    reason to forbid, and Orrery cannot distinguish a dangerous action from one nobody has
    authorised yet.

## [0.2.0] - 2026-08-07

The release that made the governance claims executable. Gate 3a through 3i: a real adapter,
a falsifiable benchmark, operator signing, configuration attestation, charter integrity, and
five gates between a planned action and a performed one — each with the limits it does *not*
cover asserted in tests rather than promised in prose.

### Breaking

- **Simulated adapters moved out of the installed package.** `OpenClawAdapter`,
  `HermesAdapter`, and `WindowsOSAdapter` now live in `examples/simulated/`. `orrery.adapters`
  contains only adapters that touch the world. Nobody should import a simulation by reflex
  while scanning the package for integrations.
- **`adapters.allow_simulated` now defaults to `false`.** A fresh install does not accept
  fabricated receipts without being asked. Registering a simulated adapter is a deliberate act.
- `execute_action` gained gates, so an action that previously ran may now be refused:
  undeclared actions are `IRREVERSIBLE` rather than inheriting the planner's optimism, and
  interdiction, envelope, and quarantine all run before approval.
- `CycleStatus.HALTED` is new. Code branching on cycle status must handle it — an operator
  stopping work is not the work failing, and the ledger no longer conflates them.
- `Settings` gained `governance`, `interdiction`, `quarantine`, `envelope`, and `invariants`
  blocks. Existing files load unchanged; every new control is off by default.

### Added

- Public-repository essentials: [SECURITY.md](SECURITY.md), which states the threat model and
  is explicit that **the security boundary is the process, not the gate ladder**, and
  [CONTRIBUTING.md](CONTRIBUTING.md), which explains the property nobody guesses — four
  documents are checked against the code in CI, so a pull request that changes behaviour
  updates the governance claim in the same commit.
- A quickstart above the fold in the README, because a stranger could not previously tell in
  ten seconds what running this looks like.

### Fixed

- **`LAW7-SIM` was enforced by a test that never exercised it.**
  `test_ledger_records_simulation_adapters` registered a *real* adapter and asserted
  `is_simulation is False`. It now registers a simulation and checks the ledger records it as
  one, and a second test covers the refusal path. This is the third policy found shipping with
  a test that asserted less than its name — after `RISK-CLASS` and the critique's goal check —
  and the pattern is now called out in CONTRIBUTING.md.
- `.quarantine/` is gitignored. It is runtime state and names the parameters a deployment's
  adapters take. The classifications themselves stay in version control, because those are
  governance decisions.

### Added

- **Gate 3i — adversarial review, a hardened profile, and pricing the benchmark's oracle.**
  - `tests/test_adversarial.py`. Orrery is meant to be embedded by people we will never meet,
    running adapters we will never see, so the threat model that matters is not a careless
    adapter but a **hostile** one. Each gate is attacked from that position, and **several
    tests assert that an attack still succeeds** — deliberately, because a defence whose
    limits are undocumented gets trusted past them. A tripwire test fails the build if
    GOVERNANCE.md ever stops describing those limits.
  - `config/hardened.yaml` and `tests/test_hardened_profile.py`. The shipped defaults enforce
    almost nothing; this is the other end of the range, and it exists to be *run* rather than
    admired. The first thing it does is **refuse to start** until an operator signs for the
    configuration, which is the intended behaviour rather than a misconfiguration.
  - A fourth benchmark arm, `unverified`, which keeps rollback and lessons and drops only the
    goal check. The harness hands every cycle a correct oracle that a real deployment would
    have to write itself; this **prices that assumption instead of merely disclosing it**.
    Measured: the goal check is worth 2 of 12 runs, and is the difference between 0 and 2
    false successes. `--strict` gates on the shipped configuration, since the `unverified`
    arm's false successes are the measurement, not a defect.

### Fixed

- **A hostile adapter could neutralise `LAW3-SUBORDINATE` by lying about its own root.**
  Relative paths were resolved under `adapter.root`, which is the adapter's own assertion
  about where it lives, so naming a decoy sandbox made every relative path resolve somewhere
  harmless while the real work happened elsewhere. Candidates are now resolved under **both**
  the claimed root and the process directory. Found by probing the gates as an attacker rather
  than as a user.
- **Under envelope enforcement, an adapter claiming a root in an unrelated tree is now
  refused outright.** A decoy root must at least touch the permitted region before it is
  trusted to resolve anything, so the lie has to be told inside the boundary, where it buys
  nothing. Overlap is checked in both directions: a sandbox *containing* the permitted region
  is the ordinary case, and the first version of this check wrongly refused it — caught by four
  existing tests before it could ship.
- GOVERNANCE.md's `LAW3-SUBORDINATE` prose still described the old behaviour, saying paths
  "arrive in named parameters" two gates after that stopped being true.

### Security

- The limits that remain, now asserted rather than described. **A misdeclared risk defeats the
  approval gate** — an adapter declaring `erase_everything: READ_ONLY` is believed, which is
  why envelopes and prohibitions never consult an adapter's opinion of its own risk.
  **Quarantine defends against under-declaration, not mis-declaration** — an adapter that
  declares everything is never held. **An adapter that names no path is outside every path
  gate**, because reach is inferred from the values an action carries. **`is_simulation` is
  self-reported** and a simulation claiming to be real is undetectable from inside.
- None of these is fixable from within the framework, and all of them are the same fact stated
  four ways: these gates constrain **actions**, not adapter implementations. An adapter doing
  its real work without routing it through an action is outside all of them.

### Added

- **Gate 3h — ledger invariants: the violations that do not exist in any single action.**
  - `orrery/core/invariants.py` and `LAW10-INVARIANT` (`PARTIAL`, off by default). Every other
    control examines one action at a time, and a whole class of harm is invisible at that
    resolution. No individual file read is exfiltration; ten thousand in three seconds is. No
    single refusal is alarming; forty in a minute is a planner probing its boundaries. The
    shape *is* the violation, and the shape only exists across events.
  - Evaluated over the **ledger**, which turns out to be the right substrate for a reason
    worth stating: it is append-only and immune to rollback, so it retains the attempts
    backtracking discarded. A runaway loop that tries the same destructive thing forty times
    and rewinds after each one leaves nothing in `StateContext` and forty entries here. This
    is the second concrete payoff for having built Law 9 the way it was built.
  - Operator-declared limits over a time window, filtered by event type, policy ID, and
    ledger data fields, with `max_events` for volume and `max_distinct` for breadth. A breach
    is recorded as an `invariant.breached` ledger event, once per window rather than once per
    action, and `on_breach: halt` stops the cycle. A rule that sets no limit is dropped rather
    than kept, because a configuration that looks like it covers something it does not is
    worse than an empty one.

### Security

- **`LAW10-INVARIANT` is detection, not prevention, and that is not a technicality.** An
  invariant is evaluated *after* the breaching action has already been dispatched. Set to
  halt, it stops the *next* action — containment, which is worth having. Anything describing
  it as preventing exfiltration would be false, and
  `test_an_invariant_cannot_prevent_the_action_that_breached_it` exists to keep the claim
  honest: it asserts that the fourth action ran and only then did anything notice.
- **This does not give Law 8 a foothold, and none is claimed.** Distributional fairness is the
  one Law that would naturally live at this resolution, and a bias detector needs a domain
  model Orrery does not have and cannot infer. Invariants are *where* such a control would go
  if an operator supplied the grouping. Orrery ships none, and `LAW8-EQUITY` stays
  `NOT_ENFORCED`.
- An invariant sees only what the ledger records — event types, policy IDs, action names,
  adapters, risk classes, approvers, outcomes. **Not parameter values.** It can count
  `read_file` actions and cannot tell you which files. Widening that is a privacy decision
  about the audit trail, not a feature request here.

### Changed

- The README now documents the full **gate ladder** — interdiction, envelope, quarantine,
  approval, invariants — and states outright that almost every safety control is off by
  default, since that is better said than discovered.
- The PRD's coverage figure re-measured against the current tree: 90% of `orrery/`, 2,966
  statements, 308 tests. It had gone stale by 410 statements over the course of these gates —
  the same defect it was corrected for two gates ago, and the reason it carries a date.

### Added

- **Gate 3g — effect envelopes: judging an action by what it reaches.**
  - `orrery/core/envelope.py` and `LAW1-ENVELOPE` (`PARTIAL`, off by default). Every other
    control in Orrery is enumerative — it matches a list of action names, paths, or adapters
    written in advance — and is therefore silent about an action invented next year. An
    envelope inverts that: it declares the **region that may be reached**, so a brand-new
    action is judged by where it lands and nobody has to have heard of it.
  - **Two declarations, both must permit.** The adapter declares what it will ever touch — a
    claim by whoever wrote the code, checkable against the implementation. The deployment
    declares what anything may touch here — the operator's boundary, which holds regardless of
    what an adapter claims about itself. The effective envelope is their **intersection**, and
    can only ever be narrower than either: an adapter cannot widen the operator's boundary with
    a generous self-declaration, and an operator cannot grant an adapter reach its author never
    intended.
  - A breach is refused outright rather than quarantined, because it is a **known** violation.
    Quarantine is for "I cannot characterise this"; an envelope breach is the opposite — the
    action is perfectly well characterised and lands somewhere it may not.
  - `FileSystemAdapter` and `ProcessAdapter` now declare their sandbox roots as their own
    envelopes, so a deployment can narrow an adapter without the adapter knowing anything about
    that deployment.

### Changed

- **Adapters declare which parameters name a location (`target_params`), and silence under
  envelope enforcement is refusal.** This is not the enumeration problem returning, and the
  asymmetry with protected paths is deliberate. Protection asks "does this reach a *forbidden*
  place?", so scanning every value is safe — a false positive costs a rare refusal, and it
  closes the hole where a parameter nobody had named slipped past. An envelope asks the
  opposite — "is everything this touches *inside* the permitted region?" — where over-scanning
  is fatal: a test caught the first implementation refusing a `write_file` because the file's
  **contents** were not a directory. So the adapter states its own signature, which its author
  knows, and an adapter that states nothing is refused rather than waved through.
- `strings_in` and `resolve_under` are now shared between the interdiction and envelope gates,
  so both see exactly the same values rather than drifting apart.

### Added

- **Gate 3f — quarantine: what to do with an action the framework cannot characterise.**
  - `orrery/core/quarantine.py` and `LAW1-QUARANTINE` (`PARTIAL`, off by default). Every
    control in Orrery until now was *enumerative* — it matched a list somebody wrote in
    advance — so an action nobody anticipated fell through every gate. An action whose adapter
    never declared it is now **held** rather than guessed at: it does not run, does not
    silently fail, and does not vanish.
  - **Releasing a held action requires a `Classification`, not a permission.** Approval and
    quarantine answer different questions: `RISK-001` answers "this is `IRREVERSIBLE`, may I?",
    where the system understands the action perfectly well and needs only consent. Quarantine
    answers "I cannot characterise this at all." Routing unknowns through the approval gate
    would have quietly eroded what an `ApprovalToken` means, from *a human authorised this
    specific irreversible action* to *somebody clicked yes on something nobody understood*.
  - **A classification never authorises**, and `test_a_classification_is_not_an_authorisation`
    exists to keep it that way. A classification is necessarily broad — it describes a *kind*
    of action — where an `ApprovalToken` is deliberately narrow: one `action_id`, single use,
    expiring. If those collapsed into one object the broad thing would inherit the narrow
    thing's authority, and this would be a permission cache with a governance label on it. A
    released action faces the risk and approval gates unchanged; one classified `IRREVERSIBLE`
    still needs a token bound to each specific action.
  - Classifications are signable with the operator's Ed25519 key, and the signing key must
    match the operator the statement names — the same rule as approvals. "I said this was
    reversible" is auditable in a way "I clicked yes" is not.
  - The review queue records parameter **keys but never values**: a reviewer needs to know an
    action carried a `patient_record` parameter, not what was in it. Records outlive the cycle
    so an operator can classify at leisure, and the queue is append-only, so a growing one is
    visible rather than silently discarded. A queue that grows means the adapters are
    under-declaring; the durable fix is to declare them, not to classify forever.
  - `python -m orrery.tools.quarantine` to review and classify.
  - `execute_action` is now an explicit gate ladder — **forbidden, then unknown, then needing
    consent** — with a shared refusal path, since each gate answers a different question and
    none may answer an earlier one's.

### Fixed

- **`RISK-CLASS` documented a fail-safe the dispatcher did not implement.** GOVERNANCE.md has
  claimed "undeclared actions are treated as irreversible" since Gate 3a, and
  `BaseAdapter.risk_for()` implemented exactly that — **while never being called on the
  execution path.** `effective_risk()` read `declared_risks` directly and fell back to the
  *planner's* risk, which defaults to `REVERSIBLE`. Undeclared actions had been sailing
  through as reversible the whole time, in the one place the guarantee mattered. Pinned by
  `tests/test_dispatcher.py::test_an_undeclared_action_is_treated_as_irreversible`.
  - Fixing it required a distinction that was being collapsed: an adapter declaring nothing
    has made **no claim**, which is not the same as claiming an action is dangerous. So
    undeclared *and* unclassified is assumed `IRREVERSIBLE`, while undeclared *but classified*
    defers to the operator who actually looked — otherwise quarantine could never release
    anything and the mechanism would be dead on arrival.
  - `tests/conftest.py`'s `StubAdapter` declared no vocabulary, which is what let the gap hide.
    It now declares one and refuses actions outside it, like a conformant adapter;
    `UndeclaredAdapter` exists separately to model the defect the conformance kit is meant to
    catch.
- **Protected paths failed open on any parameter name nobody had thought of.**
  `InterdictionGate` inspected only parameters called `path`, `source`, `destination`, `cwd`,
  or `directory`, so an adapter whose parameter happened to be called `target_file` walked
  straight past `LAW3-SUBORDINATE` and could delete the ledger. It now scans **every**
  parameter value, recursively through lists and dicts, with no opt-out and no cooperation
  required from the adapter — the whole point is defending against adapters nobody vetted.
  This was shipped in Gate 3d and found the next day by asking how a Law gets invoked by an
  action nobody anticipated.

### Added

- **Gate 3e — the charter stops being three documents that can quietly disagree.**
  - `orrery/core/charter.py` and `LAW10-CHARTER` (`ENFORCED`). The 10 Laws are written out in
    full in **three** documents, which is a drift machine, and it had already drifted — see
    Fixed below. `AGENTIC_PRIME_DIRECTIVE.md` is now designated canonical, the others are
    compared to it Law by Law, and every charter file's digest is pinned in
    `config/charter_manifest.json`. Both are CI gates. Editing a Law fails the build until
    somebody re-pins it deliberately, which is the entire point: the tool does not re-pin
    automatically, because a manifest that maintained itself would defend nothing.
  - Comparison is deliberately **tolerant of presentation and intolerant of meaning**. Case,
    whitespace, curly quotes, and dash style are normalized away, because "An intelligence
    System" and "An Intelligence System" are the same Law. "Conforms to" and "violates" are not.
  - The combined charter digest is folded into the configuration attestation, so approving a
    configuration approves the charter it runs under and rewriting a Law invalidates the
    signature.
  - `python -m orrery.tools.charter` with `--show` and `--update`.
  - 14 new tests. 253 total.

### Fixed

- **The Fourth Law still forbade compliance in one of the three charter documents.** When
  "conforms to" was corrected to "violates" — as originally written, the Law required systems to
  prevent each other from *obeying* the first three — the fix was applied to
  `AGENTIC_PRIME_DIRECTIVE.md` and `AGENTIC_SACRED_COVENANT.md` and not to
  `Permanent_Active_Directives.txt`, leaving the charter internally contradictory with nothing
  in the project able to notice. Corrected, and now pinned by
  `tests/test_charter.py::test_the_fourth_law_forbids_violation_not_compliance`. This is
  audit finding M-9 and the demonstration of M-10 in the same defect.
- **M-9 — governance document defects.** `AGENTIC_PRIME_DIRECTIVE.md` carried contradictory
  dates in its header (June 28) and footer (August 3); the header now agrees.
  `AGENTIC_SACRED_COVENANT.md` §3.1 "Runtime Enforcement" was a single bullet claiming
  "integrity verification at boot" with nothing behind it; it now names the five mechanisms that
  actually enforce the covenant, each with its policy ID, **and states plainly what it does not
  enforce**.
- **M-3 — the PRD's coverage claim was stale by 1,176 statements.** It asserted 90% over 1,380
  statements and 156 tests; the measured figure is 90% over 2,556 statements and 253 tests. A
  document claiming a number it has not re-measured is the exact defect this project exists to
  refuse.
- **M-4 — coverage measures the wrong thing.** The finding stands and is now answered rather
  than argued with: the PRD points at the benchmark as the load-bearing evidence and says
  outright that this project has already shipped 85% line coverage alongside a critique that
  certified goals it never checked.

### Changed

- Audit findings M-2, M-5, M-6, M-7, M-8 marked resolved in
  [docs/audit_2026-08-06.md](docs/audit_2026-08-06.md), and Gate 3 items 14, 15, and 17 closed.
  Item 16 stays **🟡 partial**: `orrery/bench` exists and can falsify the thesis, but Orrery has
  still not been run against OSWorld, SWE-bench, or τ-bench and claims nothing about them.

### Added

- **Gate 3d — the audit trail stops being defended by nobody having attacked it.**
  - `orrery/core/interdiction.py`. Three of the ten Laws describe judgements Orrery cannot
    make, and this does not pretend otherwise — `LAW1-HARM`, `LAW2-OBEY`, and `LAW3-SELF`
    remain `NOT_ENFORCED`. What it adds is narrower, and each piece closes a hole rather than
    a philosophical gap.
  - **`LAW3-SUBORDINATE` (`ENFORCED`) — a cycle may not act on the machinery that audits or
    constrains it.** This was a live vulnerability, not a hypothetical: a `FileSystemAdapter`
    rooted at the project directory could `delete_tree(".ledger")` — or simply
    `delete_tree(".")` — and the append-only log that all of Law 9 rests on was protected by
    nothing but the absence of a plan to attack it. The ledger, checkpoint store, attestation,
    operator keyring, and halt file are now refused, with containment checked in **both**
    directions, since deleting a parent destroys a child just as thoroughly.
  - **`LAW2-HALT` (`ENFORCED`) — an operator stop outranks the goal in progress.** Checked
    before every phase and recorded as the new `CycleStatus.HALTED` rather than `FAILED`,
    because an operator stopping work is not the work failing and the ledger should not
    conflate them. The halt file is itself a protected path, so a cycle cannot revoke its own
    stop order.
  - **`LAW1-PROHIBIT` (`PARTIAL`) — operator-declared refusals.** Evaluated *before* the
    approval gate, because an `ApprovalToken` answers "may I do this irreversible thing?" and
    the point of a prohibition is that the question is not open at execution time. This gives
    Orrery no harm model; it gives somebody who can judge harm a place to write it down, and is
    only ever as good as what they thought to forbid. A prohibition naming no adapter, action,
    or path is rejected at construction — a rule that matches everything is almost always a typo.
  - Prohibitions and protected paths are part of the attestation digest, so deleting a
    prohibition breaks the signature exactly like loosening any other limit.
  - 16 new tests. 239 total.

### Changed

- **Governance headline: 3 of the 10 Laws without runtime control → 2.** Only Laws 5 and 8
  remain, on judicial authority and equity, and neither is evaluable by an engine that makes no
  content decisions. Law 3 moved to `ENFORCED` for a reason worth stating precisely: Orrery
  still has no self-preservation drive to subordinate, and inventing one in order to suppress it
  would be theatre. What is enforced is the *consequence* the Law exists to prevent — a system
  able to erase its own record or rewrite its own limits has the means to act against an
  operator whether or not it has the motive.
- **The old project name is gone from every live artifact.**
  `.antigravity/workflows/cognition_cycle.yaml` → `orrery_cycle.yaml` (workflow `name` is now
  `orrery_cycle_v2`; nothing in `orrery/` or `tests/` reads it), and the simulated OpenClaw
  adapter's `X-Cognition-Tier` header is now `X-Orrery-Tier`. The references that remain are
  deliberate: CHANGELOG history, and `docs/competitive_landscape_2026.md`, whose analysis of the
  **Cognition AI naming collision** is the finding that caused the rename and would be destroyed
  by editing it.
- `docs/market_research_audit.md` moved to `docs/archive/`. It was already banner-marked
  SUPERSEDED — DO NOT CITE for carrying market figures traceable to no published source.

### Security

- **The archived walkthroughs no longer publish a local disk path.** Their `file:///d:/Projects/...`
  link targets are stripped; every word of prose is untouched, because rewriting a historical
  record to describe a present it never described is falsification, not cleanup. Closes the
  disclosure half of audit finding M-7.
- Interdiction is enforced at the **action** boundary, where paths arrive in named parameters.
  An adapter that hides a path where the gate does not look, or reaches the filesystem by some
  other route, is outside its reach. It constrains actions, not adapters.

### Added

- **Gate 3c — signatures that prove authorship, and a configuration that cannot be loosened
  quietly.**
  - `orrery/core/signing.py` — **Ed25519 per-operator signing**. The distinction it draws is
    the point: HMAC proves *custody* of a shared secret, and the agent process holds that
    secret too, so an HMAC on an approval cannot tell a human operator apart from the code
    asking for permission. Ed25519 separates signing from verifying — the operator keeps a
    private key the framework never sees, the framework keeps only public keys. A signature is
    stored as `algorithm:key_id:value`; bare hex is still read as a legacy HMAC, so existing
    checkpoints and ledgers remain verifiable.
  - Approval tokens are signed with the operator key when one is configured, and **the signing
    key must match the approver the token names** — otherwise any keyholder could issue
    approvals in a colleague's name. `RISK-005` refuses a *valid* HMAC token when
    `approval.require_asymmetric` is set, because the right answer from the wrong kind of
    evidence is still the wrong kind of evidence. `integrity.require_asymmetric` does the same
    for checkpoints.
  - `orrery/core/attestation.py` — **`LAW10-APPROVAL` moves from `NOT_ENFORCED` to `PARTIAL`.**
    The settings that bound Orrery's authority (approval, integrity, delegation, critique
    thresholds, simulated-adapter permission) are digested together with the governance
    registry itself and signed by an operator. With `governance.require_attestation` set, a
    dispatcher **refuses to construct** when the running configuration does not match a valid
    attestation — checked before the dispatcher is usable, because a control checked afterwards
    is not a control. Storage paths are deliberately excluded: an attestation that broke on
    every path change would be re-signed reflexively, which is worse than not having one.
  - `orrery/tools/keygen.py` and `orrery/tools/attest.py` — operator CLIs, kept out of the
    library because a cycle engine should not carry the code that mints keys. The private key
    is written to a file, never printed; a secret echoed to a terminal is a secret in a
    scrollback buffer, a screen recording, and a shell history.
  - `orrery/adapters/process.py` — **`ProcessAdapter`, the second real adapter**, and the most
    dangerous thing in the repository. It runs allowlisted programs with `shell=False` and an
    argument *list*: a command string is refused rather than split, because splitting
    reintroduces quoting rules and quoting rules are where injection lives. Working directories
    are sandbox-confined, output is bounded, every run has a wall-clock timeout, and the child
    inherits no environment by default so it cannot read the operator's keys. `run_program` is
    declared `IRREVERSIBLE` — the adapter cannot know what a program did, so it assumes the
    worst it could do — which means the approval gate refuses arbitrary code execution without
    explicit consent. A non-zero exit code produces a **failed** receipt; counting a failing
    build as a success is how a passing reflection score gets fabricated.
  - 50 new tests. 223 total.

### Changed

- **`LAW9-SIGN` and `RISK-003` remain `PARTIAL`, but for one reason instead of two.** Both were
  partial because signing was off by default *and* because a shared symmetric key proves
  custody rather than authorship. The second reason is gone. Only the deployment default
  remains, and that is a choice an operator makes, not a limit of the design.
- Chose `ProcessAdapter` over making `WindowsOSAdapter` real. A desktop UI driver is
  Windows-only and cannot be exercised on the Linux half of CI, so its "real" claim would go
  unverified on every second run — which is the class of claim the last three gates existed to
  remove. `openclaw`, `hermes`, and `windows_os` remain simulations and still say so.

### Security

- **Attestation binds configuration and policy declarations. It does not bind the code.**
  Anyone able to edit `orrery/core/approval.py` can delete the check, and no amount of signing
  inside a program defends against an attacker who controls that program. This raises the cost
  of a silent configuration change; it is not a substitute for controlling who can deploy.
- `cryptography` is an optional dependency (`orrery[signing]`). When it is absent and a policy
  requires asymmetric proof, Orrery raises rather than falling back to HMAC — a silent
  downgrade from authorship to custody is exactly the kind of quiet weakening this release
  exists to prevent.
- `.keys/` and `*.key` are gitignored. The public keyring is safe to commit; a leaked private
  key forges consent retroactively.

### Added

- **Gate 3b — the reliability claim becomes falsifiable.**
  - `orrery/bench/` — a benchmark harness whose purpose is to be capable of proving Orrery
    wrong. Six tasks run against the real `FileSystemAdapter`, and **every run is graded by
    reading the sandbox afterwards, never by trusting a receipt**. Each task's first attempt
    fails for a reason the adapter or a governance policy genuinely produces: a real
    `FileExistsError`, a real sandbox refusal, a real `RISK-001` approval denial. No faults
    are injected to make backtracking look good.
  - **Three arms share one attempt budget.** `single_pass` (no rollback), `blind_retry`
    (rollback with lessons discarded on every rewind), and `backtrack` (rollback with lessons
    retained). The comparison that counts is against `blind_retry`, not `single_pass` —
    beating `single_pass` would show only that retrying beats not retrying. Task planners may
    branch on `context.lessons` and nothing else, so in the control every attempt repeats the
    first one exactly. `BenchReport.verdict()` returns `NOT_SUPPORTED` when the treatment fails
    to beat the control.
  - **Result: `backtrack` verifies 10 of 12 runs; `blind_retry` and `single_pass` verify 0 —
    and `backtrack` spends barely half the attempts doing it**, because blind retry burns its
    whole budget re-running plans it has already watched fail. Work is counted from the
    ledger rather than from `execution_receipts`, since rollback discards the receipts of
    exactly the attempts whose cost we are trying to measure. This is the first concrete use
    of Law 9 beyond audit.
  - `python -m orrery.bench` with `--list`, `--trials`, `--task`, `--json`, and `--strict`.
    Run in CI, and the report is uploaded as an artifact.

- **`LAW7-GOAL` — a critique that can check the world instead of only its own paperwork.**
  `SelfCritiqueEngine` accepts a `goal_check` returning a `GoalVerification`. It is
  authoritative and can only veto: no success ratio, however high, overrules a report that the
  goal is unmet, the reason is pushed into `recommendations` so it survives rollback as a
  lesson, and a check that raises counts as unverified rather than as consent. Registered
  `PARTIAL`, not `ENFORCED`, because writing the check is the operator's job — Orrery cannot
  infer what a goal means, and a framework that guessed would be back to certifying its own work.

### Fixed

- **Reflection passed plans that never reached their goal.** Found by the benchmark's
  `silent_partial_failure` task, which failed in *all three* arms: three of four actions
  succeed, `SelfCritiqueEngine` scores 0.75 against a 0.70 threshold, passes, and the cycle
  reports `COMPLETED` while a file it claims to have read does not exist. **Backtracking cannot
  repair what reflection never flags.** Success ratio over receipts measures adapter behaviour,
  not goal attainment. With a goal check wired in, reflection now refuses, the backtrack fires,
  and the informed retry creates the missing file. The underlying limit has not been abolished,
  only made visible and overridable: a critique with no goal check now records
  `goal_verified=None` and states in its own reasoning that the score reflects adapter outcomes
  only. Pinned by `tests/test_critique.py::test_success_ratio_alone_passes_a_plan_that_did_not_reach_its_goal`.
- **A reflection phase that produced no critique was treated as a pass.** `evaluate()` returned
  early without recording anything when a plan produced zero receipts, and the dispatcher's
  fallback assumed `score=1.0, passed=True`. A cycle that executed nothing therefore reported
  `COMPLETED`. Both halves are fixed: the barren result is recorded, and the dispatcher's
  fallback now fails, because no critique means nothing was checked — not that nothing was wrong.
- **`meta_skills.critique.strict_mode` was dead config.** It has been present in
  `config/settings.yaml` and `CritiqueSettings` while no code read it. It is now wired through
  the dispatcher: with it on, any failed action fails reflection regardless of the ratio.

### Changed

- The benchmark result is scoped to these six tasks under this planner, and the harness hands
  each cycle a correct goal check that a real deployment would have to write itself. Orrery has
  **not** been run against OSWorld, SWE-bench, or τ-bench, and the harness makes no claim about
  them.
- **Documentation that described a project that no longer exists has been archived, not
  quietly corrected.** The three July 2026 session walkthroughs moved to `docs/archive/` with
  dated filenames and a banner on each stating what in them is wrong: the `src/` layout, the
  dead `cognition-cycles` repository URL, the machine-local `file:///d:/Projects/...` links,
  and the "world-class production release" at v1.0.0 that `[0.1.0]` already retracts. Their
  bodies are untouched — rewriting a historical record is worse than labelling it. Closes
  audit finding M-7.
- `adapters.active` in `config/settings.yaml` listed the three simulated adapters, omitted
  `filesystem`, and was read by no code at all. Replaced with `allow_simulated`, which is the
  key the dispatcher actually consults.
- Removed the stale `cognition_cycles.egg-info/` build artifact, left over from before the
  rename, whose `top_level.txt` still claimed `src`, `docs`, and `config` as importable
  packages.

### Added

- **Gate 3a — the first real adapter, and a gate on what cannot be undone.**
  - `orrery/adapters/filesystem.py` — `FileSystemAdapter`, the **first non-simulation adapter**.
    It reads, writes, appends, moves, and deletes real files inside a sandbox root, refusing
    absolute paths and any `..` traversal that escapes it. `perceive_environment` reports real
    disk usage and directory contents. All I/O runs on a worker thread. This matters beyond the
    adapter itself: risk classification was theatre until `delete_file` existed and could
    genuinely destroy something.
  - `ActionRisk` (`READ_ONLY` / `REVERSIBLE` / `COMPENSABLE` / `IRREVERSIBLE`) and `ApprovalToken`
    on `ActionPayload`. Adapters declare a risk per action name via `declared_risks`; an action
    the adapter does not declare is treated as `IRREVERSIBLE`, not as harmless.
  - `orrery/core/approval.py` — `ApprovalGate` refuses `IRREVERSIBLE` actions that carry no
    approval (`RISK-001`), tokens minted for a different action (`RISK-002`), unsigned tokens when
    signing is required (`RISK-003`), and expired tokens (`RISK-004`). Every refusal is appended
    to the ledger as `action.refused` with the deciding policy ID (`RISK-000`).
  - `CycleDispatcher` takes the **stricter** of the planner's declared risk and the adapter's, so
    a plan cannot relabel a delete as harmless to slip past the gate (`RISK-CLASS`).
  - `orrery/adapters/conformance.py` — the **Adapter Conformance Kit** (`ADP-001`…`ADP-012`),
    run in CI against every bundled adapter and offered to third-party adapter authors. It
    verifies that receipts echo the request, that unsupported actions fail rather than raise or
    falsely succeed, that failed receipts carry an error, and that no adapter stamps its own
    output as `simulated`.
  - `approval` settings block in `config/settings.yaml` (`require_for_irreversible`,
    `require_for_compensable`, `require_signed`, `ttl_seconds`).
  - 43 new tests. Coverage is now 90% of `orrery/` (1380 statements, 156 tests).

### Fixed

- **The three simulated adapters reported success for actions they do not implement.** The
  conformance kit caught this on its first run: `OpenClawAdapter`, `HermesAdapter`, and
  `WindowsOSAdapter` returned `success=True` for *any* `action_name`, including nonsense. A
  simulation that fabricates success for unimplemented work is indistinguishable from a broken
  integration, and is exactly what Law 7 forbids. All three now publish an action vocabulary and
  return a failed receipt for anything outside it.

### Changed

- **Governance headline: 5 of the 10 Laws without runtime control → 3.** Laws 1 and 2 moved from
  `NOT_ENFORCED` to `PARTIAL`, and Law 4 to `ENFORCED`. Read this narrowly. Orrery still has no
  harm model and cannot judge whether an action is *good*; what it can now do is refuse to perform
  an action it cannot undo unless a human authorized that exact action. That bounds the class of
  what happens without consent, not the content of what is consented to.

### Security

- **An unsigned `ApprovalToken` is an assertion, not a proof.** Without `ORRERY_APPROVAL_KEY` set
  and `approval.require_signed` enabled, any code running in the same process can mint a token.
  Unsigned approval is a record for the audit trail, not a security control. Even with signing on,
  a shared symmetric key proves custody, not authorship.

### Added

- **Gate 2 — governance stops being a document.**
  - `GOVERNANCE.md` maps all 10 Laws to policy IDs, runtime predicates, mechanisms, and tests.
    It is checked against `orrery/core/governance.py` by `tests/test_governance.py` in CI, so the
    document cannot claim an enforcement the code does not implement, and a policy marked
    `ENFORCED` without a test fails the build. It states plainly how many of the 10 Laws have
    no runtime control.
  - `orrery/core/ledger.py` — an append-only, hash-linked `EventLedger` (Law 9). Phase
    transitions, action outcomes, critiques, rollbacks, adapter registrations, and delegation
    decisions are recorded as JSONL. It lives outside the rewindable `StateContext` and exposes
    no delete, update, or truncate operation, so backtracking rewinds state while the record of
    the erased attempts survives.
  - `orrery/core/delegation.py` — delegation is authorized before it runs (Law 10), against
    depth (`DEL-001`), per-parent fan-out (`DEL-002`), tree population (`DEL-003`), ancestry
    loops (`DEL-004`), and tier ordering (`DEL-005`). A refusal produces a failed receipt rather
    than an exception, so the parent's own reflection handles it. Subclass `DelegationPolicy`
    for site rules; `spawn_child` propagates it so governance is not reset one tier down.
  - `orrery/core/integrity.py` — checkpoints are SHA-256 hash-linked and verified on load; an
    edited checkpoint file is refused rather than restored. Optional HMAC-SHA256 signing via
    `ORRERY_CHECKPOINT_KEY`, and `integrity.require_signature` to refuse unsigned checkpoints.
  - `CheckpointManager.verify_chain()`, `EventLedger.verify()`, and `purge_cycle()`.
  - `.github/workflows/ci.yml` — tests on Linux and Windows across Python 3.10–3.12, plus a
    separate governance conformance gate.

### Fixed

- **Unbounded checkpoint growth (H-5).** In-memory eviction previously dropped the oldest entry
  regardless of whether a cycle still needed it, and never touched `_cycle_history` or disk.
  Eviction now protects each cycle's chain head, disk retention is bounded per cycle by
  `max_checkpoints_on_disk_per_cycle`, and pruning truncates the chain without rewriting a link,
  so the surviving chain still verifies and reports itself as truncated.

### Changed

- **Gate 1 — the core is now honest.** Execution no longer fabricates results.
  - Every hardcoded `success=True` was removed from the dispatcher and from all four tiers.
  - `CycleDispatcher` gained an adapter registry. Actions route to `action.target_adapter`;
    an unregistered target or a raising adapter produces a **failed** receipt with an explicit
    error. An unwired framework now reports `FAILED` instead of silent success. This is a
    **behavioural break**: callers must register an adapter to get a passing cycle.
  - Backtracking learns. `StateContext` gained rollback-immune `lessons` and `attempt_log`;
    `backtrack()` carries them forward and keeps `step_count` monotonic (Law 9). The default
    planner consumes lessons and emits a distinct plan per attempt, replacing the previous
    behaviour of retrying an identical plan three times.
  - `config/settings.yaml` is loaded for the first time, by the new `orrery.core.config`.
    `max_cycle_iterations`, per-tier timeouts, the critique threshold, and checkpoint storage
    settings are now applied rather than decorative. `ORRERY_SETTINGS` overrides the path.
  - `run_full_cycle` is bounded by a step budget and an `asyncio.wait_for` wall-clock budget.
  - `delegate_to_child` shares one checkpoint manager, critique engine, and adapter set across
    the cycle tree, making cross-tier rewind possible; a failed child now appends a failed
    `delegate_to_<tier>` receipt so it fails the parent's reflection instead of being swallowed.
  - Bundled adapters declare `is_simulation`. Registering one logs a warning and tags its
    receipts with `simulated: True`.
- **BREAKING — Project renamed** from *Cognition Cycles* to **Orrery**. The distribution is now
  `orrery` and the import root moved from `src` to `orrery`. Update all imports:
  `from src.core.types import ...` → `from orrery.core.types import ...`.
- Documentation, configuration (`config/settings.yaml`), and repository URLs rebranded. Dated
  analysis documents are annotated rather than rewritten.

### Security

- **Path traversal in checkpoint persistence (CRITICAL)**. `cycle_id` and `checkpoint_id` were
  interpolated into filesystem paths without validation, allowing writes outside the storage
  directory. Fixed at two layers: strict UUID validation at the model boundary (with
  `validate_assignment=True`, so mutation is also covered) and path containment in
  `CheckpointManager`. Checkpoint files are now written with `0o600` permissions.

### Added

- `LICENSE` (MIT) and OSI license metadata.
- `tests/test_security.py` — 37 regression cases covering traversal, absolute paths, and
  malformed-identifier rejection on both construction and assignment.

### Fixed

- Missing `Optional` import in the adapter base class — a latent `ImportError` on the declared
  Python 3.10 target, masked by the workspace's Python 3.14 deferred annotations.

## [0.1.0] - 2026-07-31

> **Correction.** This entry was originally published as `1.0.0`. The package has always
> declared `0.1.0` in `pyproject.toml` and `orrery.__version__`, and a release whose core
> execution path reported unconditional success was not a 1.0. The heading is corrected to
> match the code; the content below is unchanged.

### Added

- **Cycle Dispatcher State Machine**: 4-phase state machine driving `PERCEPTION`, `PLANNING`, `EXECUTION`, and `REFLECTION`.
- **4-Tier Abstraction Hierarchy**: `MetaCycle`, `MacroCycle`, `MesoCycle`, and `MicroCycle` implementations with parent-child delegation.
- **State Checkpointing & Disk Persistence**: In-memory and disk-backed `.checkpoints/` snapshot serialization and rewind logic in `CheckpointManager`.
- **Agent Self-Critique Engine**: `SelfCritiqueEngine` with configurable evaluation gates and reflection threshold ($\theta = 0.70$).
- **Automated Backtracking**: State rewind mechanism returning execution to `PLANNING` upon reflection gate failures.
- **Platform Adapters**:
  - `OpenClawAdapter`: Prism Refraction routing core task dispatcher.
  - `HermesAdapter`: Console and LLM backend reasoning harness interface.
  - `WindowsOSAdapter`: Desktop UI automation and screen state verification controller.
- **Antigravity v2 Integration**: Environment rules (`.antigravity/rules.md`) and workflow orchestration (`.antigravity/workflows/cognition_cycle.yaml`).
- **Comprehensive Documentation**: PRD (`docs/PRD.md`), Architecture Specification (`docs/architecture.md`), Setup Guide (`docs/setup_guide.md`), and Market Research Audit (`docs/market_research_audit.md`).
- **End-to-End Executable Demo**: `examples/demo_cycle.py` demonstrating multi-tier cognitive delegation and failover recovery.
- **Complete Test Suite**: Pytest unit test coverage across dispatcher, tiers, meta-skills, and platform adapters.
