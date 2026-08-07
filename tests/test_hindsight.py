"""
Tests for hindsight: proposing constraints from abandoned attempts.

The two that matter most are `test_a_proposal_is_inert` and
`test_a_classification_proposal_leaves_the_risk_unset`. Together they are the reason this
is not an agent granting itself authority.
"""

import json
from pathlib import Path

from orrery.core.hindsight import (
    KIND_CLASSIFICATION,
    KIND_PROHIBITION,
    propose,
    read_ledger,
)
from orrery.core.ledger import EventLedger


def _ledger(tmp_path) -> EventLedger:
    return EventLedger(storage_dir=str(tmp_path / "ledger"), persist=True)


def _record(ledger, event_type, cycle, action="purge_notes", adapter="notes"):
    ledger.append(
        event_type,
        cycle_id=cycle,
        action_name=action,
        adapter=adapter,
        action_id="x",
    )


CYCLES = ("c1", "c2", "c3")


def test_a_repeatedly_refused_action_is_proposed_for_prohibition(tmp_path):
    ledger = _ledger(tmp_path)
    for cycle in CYCLES:
        _record(ledger, "action.refused", cycle)

    proposals = propose(ledger.events)

    assert len(proposals) == 1
    assert proposals[0].kind == KIND_PROHIBITION
    assert proposals[0].key == "notes:purge_notes"
    assert "never once permitted" in proposals[0].reason
    assert proposals[0].evidence.occurrences == 3
    assert proposals[0].evidence.cycles == 3


def test_an_action_that_ever_succeeded_is_not_proposed_for_prohibition(tmp_path):
    ledger = _ledger(tmp_path)
    for cycle in CYCLES:
        _record(ledger, "action.refused", cycle)
    _record(ledger, "action.executed", "c4")

    assert propose(ledger.events) == []


def test_a_repeatedly_held_action_is_proposed_for_classification(tmp_path):
    ledger = _ledger(tmp_path)
    for cycle in CYCLES:
        _record(ledger, "action.quarantined", cycle)

    proposals = propose(ledger.events)

    assert len(proposals) == 1
    assert proposals[0].kind == KIND_CLASSIFICATION
    assert "never declares it" in proposals[0].reason


def test_a_classification_proposal_leaves_the_risk_unset(tmp_path):
    """
    Repetition shows an action recurs. It says nothing about what the action *does*, so
    filling in a risk here would be fabricating the one judgement only a human can make.
    """
    ledger = _ledger(tmp_path)
    for cycle in CYCLES:
        _record(ledger, "action.quarantined", cycle)

    proposal = propose(ledger.events)[0]

    assert proposal.risk is None
    assert "--risk <RISK>" in proposal.command()


def test_a_consistently_failing_action_is_proposed(tmp_path):
    ledger = _ledger(tmp_path)
    for cycle in CYCLES:
        _record(ledger, "action.failed", cycle)

    proposals = propose(ledger.events)

    assert proposals[0].kind == KIND_PROHIBITION
    assert "never succeeded" in proposals[0].reason


def test_one_runaway_cycle_is_a_mistake_not_a_pattern(tmp_path):
    """
    Twenty refusals inside a single cycle is one loop misbehaving. Governance drafted from
    that would encode an incident rather than a tendency.
    """
    ledger = _ledger(tmp_path)
    for _ in range(20):
        _record(ledger, "action.refused", "one-cycle")

    assert propose(ledger.events) == []


def test_infrequent_signals_are_not_proposed(tmp_path):
    ledger = _ledger(tmp_path)
    for cycle in ("c1", "c2"):
        _record(ledger, "action.refused", cycle)

    assert propose(ledger.events, min_occurrences=3) == []


def test_already_governed_actions_are_not_proposed_again(tmp_path):
    ledger = _ledger(tmp_path)
    for cycle in CYCLES:
        _record(ledger, "action.refused", cycle)

    assert propose(ledger.events, known=["notes:purge_notes"]) == []


def test_a_proposal_is_inert(tmp_path):
    """
    The property that keeps this from being an agent writing its own rules. A proposal has
    no signature, no store, and no path into enforcement; it renders a command an operator
    may choose to run.
    """
    ledger = _ledger(tmp_path)
    for cycle in CYCLES:
        _record(ledger, "action.refused", cycle)

    proposal = propose(ledger.events)[0]

    assert not hasattr(proposal, "signature")
    assert not hasattr(proposal, "classified_by")
    assert "python -m orrery.tools" in proposal.command() or "settings" in proposal.command()
    assert Path(tmp_path / "classifications.json").exists() is False


def test_evidence_names_the_ledger_entries_that_justify_it(tmp_path):
    ledger = _ledger(tmp_path)
    for cycle in CYCLES:
        _record(ledger, "action.refused", cycle)

    proposal = propose(ledger.events)[0]

    assert proposal.evidence.sequences == [0, 1, 2]
    assert "events 0, 1, 2" in proposal.evidence.summary


def test_history_survives_the_rollback_that_erased_it(tmp_path):
    """
    Why this is possible here and not elsewhere: the ledger is outside rewindable state, so
    abandoned attempts are still on disk to be read back.
    """
    ledger = _ledger(tmp_path)
    for cycle in CYCLES:
        _record(ledger, "action.refused", cycle)
        ledger.append("cycle.backtracked", cycle_id=cycle)

    reloaded = read_ledger(Path(ledger.path))

    assert len(reloaded) == 6
    assert propose(reloaded)[0].kind == KIND_PROHIBITION


def test_an_unreadable_line_is_skipped_not_fatal(tmp_path):
    ledger = _ledger(tmp_path)
    for cycle in CYCLES:
        _record(ledger, "action.refused", cycle)
    with open(ledger.path, "a", encoding="utf-8") as handle:
        handle.write("{not json\n")

    assert len(read_ledger(Path(ledger.path))) == 3


def test_a_missing_ledger_is_empty(tmp_path):
    assert read_ledger(tmp_path / "absent.jsonl") == []


def test_the_cli_reports_and_never_writes(tmp_path, capsys):
    from orrery.tools import propose as propose_cli

    ledger = _ledger(tmp_path)
    for cycle in CYCLES:
        _record(ledger, "action.refused", cycle)

    settings = tmp_path / "settings.yaml"
    settings.write_text(
        f"quarantine:\n  store: {json.dumps(str(tmp_path / 'classifications.json'))}\n",
        encoding="utf-8",
    )

    result = propose_cli.main(
        ["--settings", str(settings), "--ledger", str(ledger.path)]
    )
    printed = capsys.readouterr().out

    assert result == 0
    assert "notes:purge_notes" in printed
    assert "These are drafts" in printed
    assert not (tmp_path / "classifications.json").exists()
