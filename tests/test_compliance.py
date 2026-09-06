"""
Tests for Orrery Regulatory Compliance Module.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from orrery.compliance import (
    ALL_FRAMEWORKS,
    ComplianceAuditor,
    ComplianceFramework,
    ComplianceReport,
    ControlStatus,
)
from orrery.compliance.standards import ComplianceControl
from orrery.core.config import (
    ApprovalSettings,
    DispatcherSettings,
    InterdictionSettings,
    LedgerSettings,
    RateLimitRuleConfig,
    RateLimitSettings,
    Settings,
)
from orrery.core.signing import OperatorKeyring, OperatorSigner
from orrery.tools.compliance import main as compliance_cli_main


def test_compliance_standards_catalog_integrity():
    """Validates that all frameworks contain properly formed controls with mapped laws."""
    assert len(ALL_FRAMEWORKS) == 5
    for fw, controls in ALL_FRAMEWORKS.items():
        assert len(controls) > 0
        for ctrl in controls:
            assert isinstance(ctrl, ComplianceControl)
            assert ctrl.control_id
            assert ctrl.title
            assert ctrl.description
            assert ctrl.function_or_category
            assert len(ctrl.mapped_laws) > 0
            assert ctrl.remediation_guidance


def test_compliance_auditor_default_audit():
    """Audits the default runtime configuration."""
    auditor = ComplianceAuditor()
    report = auditor.audit()

    assert isinstance(report, ComplianceReport)
    assert report.report_id.startswith("AUDIT-")
    assert len(report.frameworks_evaluated) == 5
    assert len(report.assessments) > 0
    assert report.compliance_score_percent > 50.0
    assert report.summary[ControlStatus.COMPLIANT.value] > 0


def test_compliance_auditor_framework_filtering():
    """Tests auditing a specific framework (e.g. NIST AI RMF only)."""
    auditor = ComplianceAuditor()
    report = auditor.audit(frameworks=[ComplianceFramework.NIST_AI_RMF])

    assert len(report.frameworks_evaluated) == 1
    assert report.frameworks_evaluated[0] == ComplianceFramework.NIST_AI_RMF
    assert all(a.control.framework == ComplianceFramework.NIST_AI_RMF for a in report.assessments)


def test_compliance_auditor_with_hardened_settings(tmp_path: Path):
    """Tests that a fully hardened system receives high compliance scores."""
    # Create an operator key
    seed = b"\x01" * 32
    signer = OperatorSigner("compliance-officer", seed)
    keyring = OperatorKeyring({"compliance-officer": signer.public_key_hex()})

    settings = Settings(
        ratelimit=RateLimitSettings(
            enabled=True,
            rules=[RateLimitRuleConfig(name="burst_protection", max_calls=100, window_seconds=60.0)],
        ),
        approval=ApprovalSettings(require_for_irreversible=True),
        interdiction=InterdictionSettings(halt_file=".halt"),
        ledger=LedgerSettings(persist=True),
        dispatcher=DispatcherSettings(auto_checkpoint=True),
    )

    auditor = ComplianceAuditor(settings=settings, keyring=keyring)
    report = auditor.audit(frameworks=[ComplianceFramework.OMB_M_24_10])

    assert report.summary[ControlStatus.NON_COMPLIANT.value] == 0
    assert report.compliance_score_percent >= 75.0


def test_compliance_auditor_gap_identification():
    """Verifies that disabled security controls are flagged as gaps."""
    # Artificially disable approval and rate limiting
    settings = Settings(
        ratelimit=RateLimitSettings(enabled=False),
        approval=ApprovalSettings(require_for_irreversible=False),
        ledger=LedgerSettings(persist=False),
    )

    auditor = ComplianceAuditor(settings=settings)
    report = auditor.audit(frameworks=[ComplianceFramework.NIST_AI_RMF])

    # Should detect disabled approval and ledger
    gaps = [g for a in report.assessments for g in a.gaps]
    assert any("ApprovalGate is disabled" in g for g in gaps)
    assert any("EventLedger is disabled" in g for g in gaps)
    assert any("Rate-limiting gate is disabled" in g for g in gaps)


def test_compliance_report_export_json_and_markdown(tmp_path: Path):
    """Verifies report serialization to both JSON and Markdown formats."""
    auditor = ComplianceAuditor()
    report = auditor.audit(frameworks=[ComplianceFramework.COLORADO_SB_24_205])

    # JSON export
    raw_json = report.to_json(indent=2)
    parsed = json.loads(raw_json)
    assert parsed["report_id"] == report.report_id
    assert parsed["compliance_score_percent"] == report.compliance_score_percent
    assert len(parsed["assessments"]) == len(report.assessments)

    # Markdown export
    md = report.to_markdown()
    assert "# Regulatory Compliance Audit Report" in md
    assert "COLORADO_SB_24_205" in md
    assert "| Control ID |" in md


def test_compliance_cli_invocation(tmp_path: Path, monkeypatch):
    """Tests running the compliance CLI with various flags."""
    out_md = tmp_path / "compliance_report.md"
    out_json = tmp_path / "compliance_report.json"

    # Markdown output to file
    ret = compliance_cli_main(["--framework", "nist", "--format", "markdown", "--output", str(out_md)])
    assert ret == 0
    assert out_md.exists()
    assert "# Regulatory Compliance Audit Report" in out_md.read_text(encoding="utf-8")

    # JSON output to file
    ret = compliance_cli_main(["--framework", "california", "--format", "json", "--output", str(out_json)])
    assert ret == 0
    assert out_json.exists()
    assert "CALIFORNIA_AI_ACT" in out_json.read_text(encoding="utf-8")

    # Strict mode test (should return 0 when no NON_COMPLIANT controls exist)
    ret_strict = compliance_cli_main(["--framework", "omb", "--strict"])
    assert ret_strict == 0


def test_compliance_auditor_missing_charter_and_ledger_file(tmp_path: Path):
    """Tests auditing when charter manifest is missing and a ledger path is provided."""
    ledger_file = tmp_path / "test_ledger.jsonl"
    ledger_file.write_text('{"event": "init"}\n', encoding="utf-8")

    auditor = ComplianceAuditor(
        charter_manifest_path=tmp_path / "nonexistent_manifest.json",
        attestation_path=tmp_path / "nonexistent.sig",
        ledger_path=ledger_file,
    )
    report = auditor.audit(frameworks=[ComplianceFramework.NIST_AI_RMF])

    # Charter manifest missing should be marked NON_COMPLIANT
    non_comp = [a for a in report.assessments if a.status == ControlStatus.NON_COMPLIANT]
    assert len(non_comp) > 0
    assert any(a.control.control_id == "GOVERN-3.1" for a in non_comp)

    # Remediation markdown should render gap details
    md = report.to_markdown()
    assert "Remediation Action Plan" in md
    assert "Charter manifest missing" in md
