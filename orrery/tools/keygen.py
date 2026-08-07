"""
Generate an operator identity: `python -m orrery.tools.keygen --operator alice`.

The private key is written to a file rather than printed, because a secret echoed to a
terminal is a secret in a scrollback buffer, a screen recording, and a shell history.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

from orrery.core.signing import SigningError, generate_operator_key

DEFAULT_KEYRING = Path("config/operators.json")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m orrery.tools.keygen",
        description="Create an Ed25519 operator identity for approvals and attestations.",
    )
    parser.add_argument("--operator", required=True, help="Key id, e.g. the operator's name.")
    parser.add_argument(
        "--private-key",
        type=Path,
        help="Where to write the private key. Defaults to .keys/<operator>.key",
    )
    parser.add_argument(
        "--keyring",
        type=Path,
        default=DEFAULT_KEYRING,
        help=f"Public keyring to add this operator to. Default: {DEFAULT_KEYRING}",
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite an existing key for this operator."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    private_path = args.private_key or Path(".keys") / f"{args.operator}.key"
    if private_path.exists() and not args.force:
        print(
            f"{private_path} already exists. Refusing to overwrite an operator's private key "
            f"without --force: doing so would invalidate every approval it has signed.",
            file=sys.stderr,
        )
        return 2

    try:
        private_hex, public_hex = generate_operator_key()
    except SigningError as exc:
        print(exc, file=sys.stderr)
        return 2

    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_text(private_hex, encoding="utf-8")
    try:
        os.chmod(private_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass

    keyring_path: Path = args.keyring
    operators = {}
    if keyring_path.exists():
        loaded = json.loads(keyring_path.read_text(encoding="utf-8"))
        operators = loaded.get("operators", loaded) if isinstance(loaded, dict) else {}
    operators[args.operator] = public_hex

    keyring_path.parent.mkdir(parents=True, exist_ok=True)
    keyring_path.write_text(json.dumps({"operators": operators}, indent=2), encoding="utf-8")

    print(f"Operator:    {args.operator}")
    print(f"Private key: {private_path}  (keep this; the framework must never hold it)")
    print(f"Public key:  {public_hex}")
    print(f"Keyring:     {keyring_path}")
    print()
    print("To use this identity:")
    print(f"  ORRERY_OPERATOR_ID={args.operator}")
    print(f"  ORRERY_OPERATOR_PRIVATE_KEY={private_path}")
    print(f"  ORRERY_OPERATOR_KEYRING={keyring_path}")
    print()
    print(
        "On a machine that only verifies, set ORRERY_OPERATOR_KEYRING alone. Withholding the\n"
        "private key is the entire point: a process that cannot sign cannot forge consent."
    )
    if private_path.stat().st_mode & stat.S_IRWXO:
        print(
            "\nWARNING: this platform did not restrict the key file's permissions. "
            "Secure it yourself.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
