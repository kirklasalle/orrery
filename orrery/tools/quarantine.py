"""
Review held actions and classify them: `python -m orrery.tools.quarantine`.

Classifying is a statement of *what an action is*, not permission to run it. An action
classified `IRREVERSIBLE` still needs its own approval token before it executes.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from orrery.core.config import load_settings
from orrery.core.quarantine import (
    Classification,
    ClassificationStore,
    QuarantineGate,
    sign_classification,
)
from orrery.core.signing import signer_from_env
from orrery.core.types import ActionRisk


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m orrery.tools.quarantine",
        description="List actions held for classification, and classify them.",
    )
    parser.add_argument("--settings", type=Path, help="Settings file. Defaults to the bundled one.")
    parser.add_argument(
        "--classify",
        metavar="ADAPTER:ACTION",
        help="Record what a held action is. Requires --risk.",
    )
    parser.add_argument(
        "--risk",
        choices=[risk.value for risk in ActionRisk],
        help="The risk class this action actually carries.",
    )
    parser.add_argument("--note", default="", help="Why it carries that risk.")
    parser.add_argument("--by", default="", help="Operator name. Defaults to the signing key id.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = load_settings(args.settings)
    store_path = Path(settings.quarantine.store)
    store = ClassificationStore.from_file(store_path)
    gate = QuarantineGate(
        enabled=True, store=store, record_path=settings.quarantine.record_path
    )

    if args.classify:
        if not args.risk:
            print("--classify requires --risk.", file=sys.stderr)
            return 2
        if ":" not in args.classify:
            print("--classify expects ADAPTER:ACTION, e.g. notes:purge_notes.", file=sys.stderr)
            return 2

        adapter, action_name = args.classify.split(":", 1)
        signer = signer_from_env()
        classification = Classification(
            adapter=adapter,
            action_name=action_name,
            risk=ActionRisk(args.risk),
            note=args.note,
            classified_by=args.by or (signer.key_id if signer else ""),
            classified_at=datetime.now(timezone.utc).isoformat(),
        )
        if not classification.classified_by:
            print(
                "No operator identity. Set ORRERY_OPERATOR_ID, or pass --by to record an "
                "unsigned classification.",
                file=sys.stderr,
            )
            return 2

        store.add(sign_classification(classification))
        store.save(store_path)

        signed = "signed" if classification.signature else "UNSIGNED"
        print(f"Classified {classification.key} as {classification.risk.value} ({signed}).")
        print(f"Recorded in {store_path} by {classification.classified_by}.")
        print()
        print(
            "This describes the action; it does not authorise it. If you classified it "
            "COMPENSABLE or IRREVERSIBLE, it still needs an approval token bound to each "
            "specific action before it will run."
        )
        return 0

    if not settings.quarantine.enabled:
        print("Note: quarantine.enabled is off, so nothing is currently being held.\n")

    pending = gate.pending()
    if not pending:
        print(f"Nothing held for classification. ({len(store.keys)} classification(s) on file.)")
        return 0

    print(f"{len(pending)} action(s) held for classification:\n")
    for record in pending:
        print(f"  {record.key}")
        print(f"    reason:     {record.reason}")
        print(f"    parameters: {', '.join(record.parameter_keys) or '(none)'}")
        print(f"    first seen: {record.first_seen}")
        print(
            f"    classify:   python -m orrery.tools.quarantine "
            f"--classify {record.key} --risk <RISK> --note \"...\""
        )
        print()
    print(
        "A growing queue means the adapters are under-declaring. The durable fix is to add "
        "these to the adapter's declared_risks, not to classify them one by one forever."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
