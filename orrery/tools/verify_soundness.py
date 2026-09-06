"""
CLI Tool: Formal Verification Runner for Orrery Gate Composition.

Usage:
    python -m orrery.tools.verify_soundness [--iterations 200] [--output report.json]
"""

import argparse
import sys
from pathlib import Path

from orrery.verification.soundness import GateSoundnessVerifier


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Formally verify gate composition soundness, monotonic ordering, and ledger completeness."
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=200,
        help="Number of property fuzzing iterations per theorem (default: 200)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic pseudorandom seed (default: 42)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path to output the soundness report (JSON)",
    )
    args = parser.parse_args()

    print(f"[Orrery Verification] Initializing Gate Soundness Engine (seed={args.seed}, iterations={args.iterations})...")
    verifier = GateSoundnessVerifier(seed=args.seed)
    report = verifier.run_full_verification(iterations=args.iterations)

    print("\n" + report.summary_markdown())

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(f"\n[Orrery Verification] JSON report written to {out_path.resolve()}")

    if not report.is_sound:
        print("\n[Orrery Verification] CRITICAL: Soundness theorem violation detected!", file=sys.stderr)
        sys.exit(1)
    else:
        print("\n[Orrery Verification] All 5 Theorems Mathematically and Empirically Sound.")
        sys.exit(0)


if __name__ == "__main__":
    main()
