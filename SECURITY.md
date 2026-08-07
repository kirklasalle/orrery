# Security Policy

## Reporting a vulnerability

Report suspected vulnerabilities through
[GitHub's private security advisory form](https://github.com/kirklasalle/orrery/security/advisories/new).
Please do not open a public issue for a suspected vulnerability.

Include what you did, what happened, and what you expected. A failing test against
`tests/` is the most useful possible report.

You should get an acknowledgement within **7 days**. If a report is valid we will agree a
disclosure timeline with you; if it is out of scope (see below) we will say so plainly and
explain why rather than leaving it unanswered.

Orrery is pre-1.0 and maintained by one person. Only `main` is supported. There is no
backport policy, because there is nothing to backport to.

## Scope

**Orrery has had no external security review.** What follows is the maintainer's own threat
model, published so you can disagree with it.

### In scope

- A way to reach the ledger, checkpoints, attestation, operator keyring, or halt file
  through an ordinary action, defeating `LAW3-SUBORDINATE`.
- A way to execute an action that lies outside a declared effect envelope
  (`LAW1-ENVELOPE`) or matches an operator prohibition (`LAW1-PROHIBIT`).
- Forging, replaying, or transferring an `ApprovalToken` or a `Classification`; making the
  approval gate accept an unsigned or wrongly-signed one when signing is required.
- Passing off an attestation for a configuration that is not the one running, or editing a
  charter document without `python -m orrery.tools.charter` noticing.
- Editing ledger or checkpoint history without verification failing.
- Escaping `FileSystemAdapter`'s sandbox root, or running a non-allowlisted program through
  `ProcessAdapter` — including via argument injection, since it takes an argument list and
  never a shell string.
- Any path where Orrery reports `COMPLETED` for work it did not perform. Law 7 is the point
  of the project, and a fabricated success is a security bug here even when nothing is
  breached.

### Out of scope, by design

**The security boundary is the process, not the gate ladder.** Adapters are ordinary Python
objects running with the dispatcher's privileges. Every gate inspects an *action*; an
adapter that does its work without routing it through one is outside all of them, and no
in-process check can change that.

So the following are known, documented, and not vulnerabilities:

- **A hostile adapter bypassing the gates** by performing side effects directly instead of
  through actions.
- **An adapter misdeclaring its own risk** — declaring a delete `READ_ONLY`. The approval
  gate believes it. Envelopes and prohibitions deliberately do not consult it.
- **An adapter that declares every action**, and is therefore never quarantined. Quarantine
  defends against under-declaration, not mis-declaration.
- **An adapter lying about `is_simulation`.** It is self-reported and unverifiable from
  inside the process.
- **Anything reachable only with write access to the source tree.** Attestation binds
  configuration and policy declarations, not code; whoever can edit `approval.py` can
  delete the check.
- **Controls being off.** Signing, attestation, quarantine, envelopes, and invariants ship
  disabled. That is a documented default, not a flaw — see `config/hardened.yaml`.

These limits are not merely asserted in prose. `tests/test_adversarial.py` attacks each
gate from a hostile adapter's position and **asserts the attacks that still succeed**, so a
change that closes one of them will fail the build until the documentation catches up.

If you find something in the out-of-scope list that is *worse than documented* — a bypass
that needs no hostile adapter, or one that survives the hardened profile — that is in scope
and we want to hear about it.

## Running untrusted adapters

Don't, in the same process. If you must run adapter code you do not trust, isolate it at
the operating system level — a container, a jail, a restricted user, seccomp — and treat
Orrery's gates as defence in depth *inside* that boundary rather than as the boundary.
Orrery bounds what a cycle asks for. Only the OS bounds what a process can do.
