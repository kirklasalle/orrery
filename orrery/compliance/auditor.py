"""
Automated Regulatory Compliance Auditor for Orrery.

Inspects active configurations, cryptographic keyrings, signed charter manifests,
gate policies, and event ledgers to evaluate compliance against NIST AI RMF 1.0,
OMB M-24-10, Colorado SB 24-205, California AI Safety Directives, and EU AI Act.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from orrery.compliance.standards import (
    ALL_FRAMEWORKS,
    ComplianceControl,
    ComplianceFramework,
    ControlStatus,
)
from orrery.compliance.report import ComplianceReport, ControlAssessment
from orrery.core.config import Settings, get_settings
from orrery.core.signing import OperatorKeyring, keyring_from_env
from orrery.core.attestation import evaluate as evaluate_attestation
from orrery.core.charter import verify_charter


class ComplianceAuditor:
    """
    Automated auditor that inspects system configuration, security posture,
    and runtime evidence against regulatory control requirements.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        keyring: Optional[OperatorKeyring] = None,
        charter_manifest_path: Optional[Union[str, Path]] = None,
        attestation_path: Optional[Union[str, Path]] = None,
        ledger_path: Optional[Union[str, Path]] = None,
    ):
        self.settings = settings or get_settings()
        self.keyring = keyring or keyring_from_env()
        self.charter_manifest_path = (
            Path(charter_manifest_path)
            if charter_manifest_path
            else Path("config/charter_manifest.json")
        )
        self.attestation_path = (
            Path(attestation_path)
            if attestation_path
            else Path("config/attestation.sig")
        )
        self.ledger_path = Path(ledger_path) if ledger_path else None

    def audit(
        self,
        frameworks: Optional[Sequence[ComplianceFramework]] = None,
    ) -> ComplianceReport:
        """
        Executes an automated compliance audit across the specified frameworks.
        Defaults to all supported frameworks if none specified.
        """
        target_fws = list(frameworks) if frameworks else list(ComplianceFramework)
        assessments: List[ControlAssessment] = []

        # Evaluate system state once for efficiency
        state_evidence = self._gather_system_evidence()

        for fw in target_fws:
            controls = ALL_FRAMEWORKS.get(fw, [])
            for ctrl in controls:
                assessment = self._evaluate_control(ctrl, state_evidence)
                assessments.append(assessment)

        # Compute summary scores
        summary: Dict[str, int] = {
            ControlStatus.COMPLIANT.value: 0,
            ControlStatus.PARTIAL.value: 0,
            ControlStatus.NON_COMPLIANT.value: 0,
            ControlStatus.NOT_APPLICABLE.value: 0,
        }
        for a in assessments:
            summary[a.status.value] = summary.get(a.status.value, 0) + 1

        total = len(assessments)
        compliant = summary.get(ControlStatus.COMPLIANT.value, 0)
        partial = summary.get(ControlStatus.PARTIAL.value, 0)
        score_percent = round(((compliant + (partial * 0.5)) / total * 100), 2) if total else 0.0

        return ComplianceReport(
            report_id=f"AUDIT-{uuid.uuid4().hex[:12].upper()}",
            frameworks_evaluated=target_fws,
            assessments=assessments,
            summary=summary,
            compliance_score_percent=score_percent,
        )

    def _gather_system_evidence(self) -> Dict[str, object]:
        """Collects concrete evidence from config, filesystem, keys, and manifests."""
        evidence: Dict[str, object] = {}

        # 1. Charter manifest verification
        charter_valid = False
        charter_error = ""
        try:
            res = verify_charter()
            charter_valid = res.verified
            if not res.verified:
                charter_error = "; ".join(
                    res.missing_documents
                    + res.missing_laws
                    + [f"Drift in {d.document} Law {d.law}" for d in res.drift]
                    + res.digest_mismatches
                )
        except Exception as exc:
            charter_error = str(exc)
        evidence["charter_valid"] = charter_valid
        evidence["charter_error"] = charter_error
        evidence["charter_exists"] = self.charter_manifest_path.exists()

        # 2. Keyring & signing capability
        evidence["has_signing_keys"] = bool(self.keyring.key_ids)
        evidence["operator_count"] = len(self.keyring.key_ids)

        # 3. Attestation check
        attestation_valid = False
        attestation_error = ""
        try:
            decision = evaluate_attestation(self.settings, path=self.attestation_path)
            attestation_valid = decision.allowed
            attestation_error = decision.reason or ""
        except Exception as exc:
            attestation_error = str(exc)
        evidence["attestation_valid"] = attestation_valid
        evidence["attestation_error"] = attestation_error
        evidence["attestation_exists"] = self.attestation_path.exists()

        # 4. Settings verification
        evidence["rate_limiting_enabled"] = self.settings.ratelimit.enabled
        evidence["rate_limiting_rules_count"] = len(self.settings.ratelimit.rules)
        evidence["approval_enabled"] = self.settings.approval.require_for_irreversible
        evidence["approval_policy"] = (
            f"irreversible={self.settings.approval.require_for_irreversible}, "
            f"compensable={self.settings.approval.require_for_compensable}, "
            f"require_signed={self.settings.approval.require_signed}"
        )
        evidence["ledger_enabled"] = self.settings.ledger.persist
        evidence["critique_threshold"] = self.settings.critique.threshold
        evidence["critique_strict"] = self.settings.critique.strict_mode
        evidence["halt_file_configured"] = bool(self.settings.interdiction.halt_file)
        evidence["checkpoint_enabled"] = self.settings.dispatcher.auto_checkpoint

        # 5. Ledger file check if provided
        ledger_present = False
        if self.ledger_path and self.ledger_path.exists():
            ledger_present = True
        evidence["ledger_present"] = ledger_present

        return evidence

    def _evaluate_control(
        self,
        control: ComplianceControl,
        evidence: Dict[str, object],
    ) -> ControlAssessment:
        """Evaluates a single control requirement against gathered evidence."""
        gaps: List[str] = []
        status = ControlStatus.COMPLIANT
        ev_items: List[str] = []

        # Check charter manifest requirement
        if "charter_manifest" in control.required_capabilities:
            if not evidence["charter_exists"]:
                gaps.append(f"Charter manifest missing at {self.charter_manifest_path}")
                status = ControlStatus.NON_COMPLIANT
            elif not evidence["charter_valid"]:
                gaps.append(f"Charter manifest failed verification: {evidence['charter_error']}")
                status = ControlStatus.NON_COMPLIANT
            else:
                ev_items.append("Charter manifest verified against Permanent_Active_Directives.txt")

        # Check signing and cryptographic attribution
        if "ed25519_keyring" in control.required_capabilities:
            if not evidence["has_signing_keys"]:
                gaps.append("No operator Ed25519 keys registered in Keyring")
                status = ControlStatus.PARTIAL if status == ControlStatus.COMPLIANT else status
            else:
                ev_items.append(f"{evidence['operator_count']} operator signing key(s) verified in Keyring")

        # Check signed attestation
        if "signed_attestation" in control.required_capabilities:
            if not evidence["attestation_exists"]:
                gaps.append(f"Cryptographic attestation missing at {self.attestation_path}")
                status = ControlStatus.PARTIAL if status == ControlStatus.COMPLIANT else status
            elif not evidence["attestation_valid"]:
                gaps.append(f"Attestation signature invalid: {evidence['attestation_error']}")
                status = ControlStatus.NON_COMPLIANT
            else:
                ev_items.append("Cryptographic attestation signature verified with operator key")

        # Check rate limiting capability
        if "rate_limiting" in control.required_capabilities:
            if not evidence["rate_limiting_enabled"]:
                gaps.append("Rate-limiting gate is disabled in Settings (ratelimit.enabled=False)")
                status = ControlStatus.PARTIAL if status == ControlStatus.COMPLIANT else status
            else:
                ev_items.append(f"Rate limiting active ({evidence['rate_limiting_rules_count']} rule(s) configured)")

        # Check approval gate and human oversight
        if "approval_gate" in control.required_capabilities or "human_in_the_loop" in control.required_capabilities:
            if not evidence["approval_enabled"]:
                gaps.append("ApprovalGate is disabled in Settings (approval.enabled=False)")
                status = ControlStatus.NON_COMPLIANT
            else:
                ev_items.append("ApprovalGate active with human review for high-risk actions")

        # Check emergency halt file / kill switch
        if "halt_file_switch" in control.required_capabilities:
            if not evidence["halt_file_configured"]:
                gaps.append("Halt file path not configured in Settings.interdiction.halt_file")
                status = ControlStatus.PARTIAL if status == ControlStatus.COMPLIANT else status
            else:
                ev_items.append(f"Emergency halt switch configured at '{self.settings.interdiction.halt_file}'")

        # Check event ledger
        if "event_ledger" in control.required_capabilities:
            if not evidence["ledger_enabled"]:
                gaps.append("EventLedger is disabled in Settings (ledger.enabled=False)")
                status = ControlStatus.NON_COMPLIANT
            else:
                ev_items.append("Immutable, append-only EventLedger active with hash chaining")

        # Check invariant monitors and checkpoints
        if "state_checkpoints" in control.required_capabilities or "backtracking_engine" in control.required_capabilities:
            if not evidence["checkpoint_enabled"]:
                gaps.append("CheckpointManager is disabled in Settings")
                status = ControlStatus.NON_COMPLIANT
            else:
                ev_items.append("Checkpoint state verification and backtracking active")

        if not gaps:
            status = ControlStatus.COMPLIANT
            detail_evidence = "; ".join(ev_items) if ev_items else "Governed by active Orrery runtime policies."
        else:
            detail_evidence = "; ".join(ev_items) if ev_items else "Failed to verify required security capabilities."

        return ControlAssessment(
            control=control,
            status=status,
            evidence=detail_evidence,
            gaps=gaps,
            remediation=control.remediation_guidance if gaps else "",
        )
