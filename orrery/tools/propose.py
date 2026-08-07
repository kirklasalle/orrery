"""
Read the ledger's abandoned attempts and draft constraints:
`python -m orrery.tools.propose`.

Everything printed is inert. Enacting a proposal is an operator action through the ordinary
signing path, and nothing here writes a rule.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from orrery.core.config import load_settings
from orrery.core.hindsight import propose, read_ledger
from orrery.core.interdiction import Prohibition
from orrery.core.quarantine import ClassificationStore


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m orrery.tools.propose",
        description="Draft constraints from what past cycles tried and abandoned.",
    )
    parser.add_argument("--settings", type=Path, help="Settings file. Defaults to the bundled one.")
    parser.add_argument("--ledger", type=Path, help="Ledger JSONL. Defaults to the configured one.")
    parser.add_argument("--min-occurrences", type=int, default=3)
    parser.add_argument("--min-cycles", type=int, default=2)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = load_settings(args.settings)
    path = args.ledger or Path(settings.ledger.storage_dir) / "events.jsonl"

    events = read_ledger(path)
    if not events:
        print(f"No ledger history at {path}. Nothing to learn from yet.")
        return 0

    known = set(ClassificationStore.from_file(Path(settings.quarantine.store)).keys)
    for rule in settings.interdiction.prohibitions:
        prohibition = Prohibition(**rule.model_dump())
        for adapter in prohibition.adapters or [""]:
            for action in prohibition.actions or [""]:
                known.add(f"{adapter}:{action}")

    proposals = propose(
        events,
        min_occurrences=args.min_occurrences,
        min_cycles=args.min_cycles,
        known=known,
    )

    print(f"Read {len(events)} ledger event(s) from {path}.\n")
    if not proposals:
        print("No pattern recurs often enough across enough cycles to be worth proposing.")
        return 0

    print(f"{len(proposals)} proposed constraint(s), drafted from what past cycles abandoned:\n")
    for proposal in proposals:
        print(proposal.render())
        print()

    print(
        "These are drafts. Nothing above is in force, and none of it is signed.\n"
        "A pattern shows an action recurs; it does not show what the action does, which is\n"
        "why a classification's risk is left for you to set. Discarding a proposal is a\n"
        "perfectly good answer."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
