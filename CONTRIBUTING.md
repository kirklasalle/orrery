# Contributing

Ordinary things first: fork, branch, `pip install -e ".[dev]"`, `pytest`, open a pull
request. Python 3.10 is the floor and CI runs 3.10–3.12 on Linux and Windows.

The rest of this file covers the part of Orrery that nobody guesses.

## The documentation is executable

Four documents are checked against the code in CI. They are not descriptions of the code;
they are claims the build refuses to let drift.

| Document | Gate | Fails when |
| --- | --- | --- |
| [GOVERNANCE.md](GOVERNANCE.md) | `tests/test_governance.py` | It lists a policy the registry doesn't have, or the registry has one it doesn't list; a policy marked `ENFORCED` names no test; a named test doesn't exist. |
| The three charter documents | `python -m orrery.tools.charter` | The 10 Laws disagree between them, or one was edited without re-pinning `config/charter_manifest.json`. |
| [README.md](README.md) benchmark claims | `python -m orrery.bench --strict` | The shipped configuration reports success the filesystem doesn't confirm, or informed rollback stops beating the blind-retry control. |
| The documented security limits | `tests/test_adversarial.py` | A limit stops being described in GOVERNANCE.md, or a gate is hardened past one without the docs following. |

**So a pull request that changes behaviour updates the governance claim in the same
commit.** That is not bureaucracy — it is the only reason anyone should believe what this
repository says about itself.

## What gets a change rejected

- **A claim without a mechanism.** If GOVERNANCE.md would say a Law is enforced, a runtime
  predicate and a test have to exist. `NOT_ENFORCED` is an acceptable answer and appears
  throughout; an unearned `ENFORCED` is not.
- **Widening a documented limit quietly.** If you close one of the gaps in
  `tests/test_adversarial.py`, invert the test and update the docs in the same change.
  Don't delete it.
- **Fabricated success.** No code path may construct a successful `ExecutionReceipt` without
  an adapter having executed. This is Law 7 and it is the reason the project exists.
- **A test that asserts less than its name.** Two policies have shipped here with tests that
  didn't test them (`RISK-CLASS` and `LAW7-SIM`). Both were found later and both were real
  defects. Name a test for what it checks.

## Writing an adapter

Adapters are third-party code inside the trust boundary, so the contract matters. Declare
`declared_risks` for every action you support, `target_params` for every parameter naming a
location, and `effect_envelope` for the region you will ever touch. Anything undeclared is
treated as `IRREVERSIBLE` or quarantined, which is the intended cost of silence.

Run the conformance kit against your adapter before proposing it:

```python
from orrery.adapters.conformance import run_conformance
report = run_conformance(MyAdapter(), sample_action="...", sample_params={...})
assert report.passed, report.summary
```

If it fabricates results, set `is_simulation = True` and put it in `examples/simulated/`.
The installed package contains only adapters that touch the world.

## Governance changes

Changes to the 10 Laws are not code review. Edit the canonical document
([AGENTIC_PRIME_DIRECTIVE.md](AGENTIC_PRIME_DIRECTIVE.md)), bring the other two into
agreement, re-pin with `python -m orrery.tools.charter --update`, and say what changed and
why in [CHANGELOG.md](CHANGELOG.md). The manifest deliberately does not update itself.

## Reporting a vulnerability

See [SECURITY.md](SECURITY.md). Please don't open a public issue for one.
