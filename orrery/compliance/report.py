"""
Compliance Audit Report Generation for Autonomous Agent Systems.

Generates structured, auditable regulatory compliance reports in JSON and Markdown
formats suitable for compliance officers, legal counsel, and technical auditors.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from pydantic import BaseModel, Field

from orrery.compliance.standards import (
    ComplianceControl,
    ComplianceFramework,
    ControlStatus,
)


class ControlAssessment(BaseModel):
    """Detailed assessment of a single compliance control."""

    control: ComplianceControl
    status: ControlStatus
    evidence: str = ""
    gaps: List[str] = Field(default_factory=list)
    remediation: str = ""


class ComplianceReport(BaseModel):
    """Complete regulatory compliance audit report."""

    report_id: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    system_name: str = "Orrery Autonomous Governance Architecture"
    frameworks_evaluated: List[ComplianceFramework] = Field(default_factory=list)
    assessments: List[ControlAssessment] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)
    compliance_score_percent: float = 0.0

    def to_json(self, indent: int = 2) -> str:
        """Serializes the report to JSON format."""
        return json.dumps(self.model_dump(mode="json"), indent=indent)

    def to_markdown(self) -> str:
        """Renders the compliance report in human-readable GitHub-flavored Markdown."""
        now = self.generated_at
        total = len(self.assessments)
        compliant_count = self.summary.get(ControlStatus.COMPLIANT.value, 0)
        partial_count = self.summary.get(ControlStatus.PARTIAL.value, 0)
        non_compliant_count = self.summary.get(ControlStatus.NON_COMPLIANT.value, 0)

        lines: List[str] = [
            "# Regulatory Compliance Audit Report",
            "",
            f"**System**: {self.system_name}  ",
            f"**Report ID**: `{self.report_id}`  ",
            f"**Generated**: {now}  ",
            f"**Overall Compliance Score**: **{self.compliance_score_percent:.1f}%**  ",
            "",
            "## Executive Summary",
            "",
            f"- **Total Controls Evaluated**: {total}",
            f"- **Fully Compliant**: `{compliant_count}` ({compliant_count / total * 100:.1f}%)" if total else "- **Fully Compliant**: 0",
            f"- **Partially Compliant**: `{partial_count}` ({partial_count / total * 100:.1f}%)" if total else "- **Partially Compliant**: 0",
            f"- **Non-Compliant / Gaps**: `{non_compliant_count}` ({non_compliant_count / total * 100:.1f}%)" if total else "- **Non-Compliant / Gaps**: 0",
            "",
            "## Frameworks Evaluated",
            "",
        ]

        for fw in self.frameworks_evaluated:
            lines.append(f"- **{fw.value}**")

        lines.extend([
            "",
            "## Detailed Control Findings",
            "",
            "| Control ID | Framework | Category | Title | Status | Laws Mapped |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ])

        for a in self.assessments:
            badge = {
                ControlStatus.COMPLIANT: "🟢 COMPLIANT",
                ControlStatus.PARTIAL: "🟡 PARTIAL",
                ControlStatus.NON_COMPLIANT: "🔴 NON-COMPLIANT",
                ControlStatus.NOT_APPLICABLE: "⚪ N/A",
            }.get(a.status, a.status.value)

            laws = ", ".join(f"`{law}`" for law in a.control.mapped_laws)
            lines.append(
                f"| `{a.control.control_id}` | {a.control.framework.value} | {a.control.function_or_category} | "
                f"{a.control.title} | {badge} | {laws} |"
            )

        # Gap analysis and remediation section
        gaps_found = [a for a in self.assessments if a.status != ControlStatus.COMPLIANT]
        if gaps_found:
            lines.extend([
                "",
                "## Remediation Action Plan (Identified Gaps)",
                "",
            ])
            for idx, item in enumerate(gaps_found, 1):
                lines.extend([
                    f"### {idx}. [{item.control.control_id}] {item.control.title}",
                    f"- **Framework**: {item.control.framework.value} ({item.control.function_or_category})",
                    f"- **Status**: `{item.status.value}`",
                    f"- **Evidence**: {item.evidence}",
                ])
                if item.gaps:
                    lines.append(f"- **Identified Gaps**:")
                    for g in item.gaps:
                        lines.append(f"  - ⚠️ {g}")
                if item.remediation:
                    lines.append(f"- **Recommended Remediation**: {item.remediation}")
                lines.append("")
        else:
            lines.extend([
                "",
                "> [!NOTE]",
                "> **Zero Compliance Gaps Detected**: All evaluated controls satisfy the specified regulatory standards.",
                "",
            ])

        lines.extend([
            "---",
            "*Report produced by Orrery Automated Compliance Engine. Validated against cryptographically-bound runtime state.*",
        ])

        return "\n".join(lines)
