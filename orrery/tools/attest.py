"""
Inspect and approve the running configuration: `python -m orrery.tools.attest`.

Signing here is an act of governance, not a build step. It says: I have read what these
limits currently are, and I approve the framework running with them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from orrery.core.attestation import (
    GovernanceError,
    attest,
    configuration_digest,
    evaluate,
    governed_configuration,
    load_attestation,
    save_attestation,
)
from orrery.core.config import load_settings


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m orrery.tools.attest",
        description="Show, verify, or sign the governed configuration.",
    )
    parser.add_argument("--settings", type=Path, help="Settings file. Defaults to the bundled one.")
    parser.add_argument("--output", type=Path, help="Where to write the attestation.")
    parser.add_argument(
        "--sign", action="store_true", help="Sign the running configuration with the operator key."
    )
    parser.add_argument("--note", default="", help="Why this configuration was approved.")
    parser.add_argument(
        "--show", action="store_true", help="Print the governed configuration being digested."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = load_settings(args.settings)
    target = Path(args.output or settings.governance.attestation_path)

    if args.show:
        print(json.dumps(governed_configuration(settings), indent=2))
        return 0

    digest = configuration_digest(settings)
    print(f"Governed configuration digest: {digest}")

    if args.sign:
        try:
            attestation = attest(settings, note=args.note)
        except GovernanceError as exc:
            print(exc, file=sys.stderr)
            return 2
        save_attestation(attestation, target)
        print(f"Signed by {attestation.approved_by} and written to {target}")
        return 0

    existing = load_attestation(target)
    if existing is None:
        print(f"No attestation at {target}. Run with --sign to approve this configuration.")
        return 1

    decision = evaluate(settings, target)
    print(f"Attestation: {'VALID' if decision.allowed else 'INVALID'} \u2014 {decision.reason}")
    if not settings.governance.require_attestation:
        print(
            "Note: governance.require_attestation is off, so this result is advisory. "
            "Nothing currently refuses to start on a failed attestation."
        )
    return 0 if decision.allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
