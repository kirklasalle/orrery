"""
Check or re-pin the charter: `python -m orrery.tools.charter`.

Re-pinning is a deliberate act. The manifest exists so that editing one of the 10 Laws
cannot happen quietly, and a tool that re-pinned automatically would defeat its own purpose.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from orrery.core.charter import (
    CANONICAL_DOCUMENT,
    CHARTER_DOCUMENTS,
    build_manifest,
    charter_digest,
    extract_laws,
    save_manifest,
    verify_charter,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m orrery.tools.charter",
        description="Verify that every charter document states the same 10 Laws, unchanged.",
    )
    parser.add_argument("--root", type=Path, help="Repository root. Defaults to the installed one.")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Re-pin the current charter documents in config/charter_manifest.json.",
    )
    parser.add_argument("--show", action="store_true", help="Print the canonical 10 Laws.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.show:
        from orrery.core.charter import REPO_ROOT

        base = Path(args.root or REPO_ROOT)
        laws = extract_laws((base / CANONICAL_DOCUMENT).read_text(encoding="utf-8"))
        for number in sorted(laws):
            print(f"{number}. {laws[number]}\n")
        return 0

    if args.update:
        manifest = build_manifest(args.root)
        path = save_manifest(manifest, args.root)
        print(f"Pinned {len(manifest['documents'])} charter document(s) in {path}:")
        for name, digest in sorted(manifest["documents"].items()):
            marker = " (canonical)" if name == CANONICAL_DOCUMENT else ""
            print(f"  {name}{marker}\n    {digest}")
        print(
            "\nRe-pinning records that this charter text is the one intended. If a Law changed, "
            "say so in the CHANGELOG."
        )
        return 0

    result = verify_charter(args.root)
    print(f"Canonical document: {CANONICAL_DOCUMENT}")
    print(f"Charter digest:     {charter_digest(args.root)}")
    print(f"Documents:          {', '.join(CHARTER_DOCUMENTS)}")
    print()

    if result.verified:
        print(f"Charter: CONSISTENT — {result.summary}")
        return 0

    print(f"Charter: INCONSISTENT — {result.summary}", file=sys.stderr)
    for item in result.drift:
        print(f"\nLaw {item.law} disagrees between {CANONICAL_DOCUMENT} and {item.document}:", file=sys.stderr)
        print(f"  canonical: {item.canonical_text}", file=sys.stderr)
        print(f"  {item.document}: {item.document_text}", file=sys.stderr)
    if result.digest_mismatches or result.unpinned_documents:
        print(
            "\nRun with --update to re-pin, once you are satisfied the change was intended.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
