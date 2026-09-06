"""
CLI Tool: Orrery Compliance Auditor.

Usage:
    python -m orrery.tools.compliance [--framework all|nist|omb|colorado|california|eu]
                                     [--format markdown|json]
                                     [--output <path>]
                                     [--strict]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from orrery.compliance import (
    ComplianceAuditor,
    ComplianceFramework,
    ControlStatus,
)


FRAMEWORK_CHOICES = {
    "all": None,
    "nist": [ComplianceFramework.NIST_AI_RMF],
    "omb": [ComplianceFramework.OMB_M_24_10],
    "colorado": [ComplianceFramework.COLORADO_SB_24_205],
    "california": [ComplianceFramework.CALIFORNIA_AI_ACT],
    "eu": [ComplianceFramework.EU_AI_ACT],
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m orrery.tools.compliance",
        description="Run automated regulatory compliance audit on the active Orrery configuration.",
    )
    parser.add_argument(
        "--framework",
        choices=list(FRAMEWORK_CHOICES.keys()),
        default="all",
        help="Regulatory framework to evaluate (default: all).",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Report output format (default: markdown).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional file path to save the generated report.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero status code if any non-compliant controls are detected.",
    )

    args = parser.parse_args(argv)

    auditor = ComplianceAuditor()
    target_fws = FRAMEWORK_CHOICES[args.framework]
    report = auditor.audit(frameworks=target_fws)

    if args.format == "json":
        content = report.to_json(indent=2)
    else:
        content = report.to_markdown()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(f"Compliance report written to {args.output}")
    else:
        print(content)

    non_compliant = report.summary.get(ControlStatus.NON_COMPLIANT.value, 0)
    if args.strict and non_compliant > 0:
        print(f"\n[STRICT MODE] Audit failed: {non_compliant} non-compliant control(s) found.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
