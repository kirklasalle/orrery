"""
Compliance Standards and Control Mappings for Autonomous AI Governance.

Maps Orrery's 10 Governance Laws, cryptographic event ledger, multi-gate ladder,
and attestation engine to U.S. Federal (NIST AI RMF 1.0, OMB M-24-10),
State-level (Colorado SB 24-205, California AB 2013 / Safety Standards),
and International (EU AI Act Articles 12-15) regulatory frameworks.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ControlStatus(str, Enum):
    COMPLIANT = "COMPLIANT"
    PARTIAL = "PARTIAL"
    NON_COMPLIANT = "NON_COMPLIANT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ComplianceFramework(str, Enum):
    NIST_AI_RMF = "NIST_AI_RMF_1.0"
    OMB_M_24_10 = "OMB_M_24_10"
    COLORADO_SB_24_205 = "COLORADO_SB_24_205"
    CALIFORNIA_AI_ACT = "CALIFORNIA_AI_ACT"
    EU_AI_ACT = "EU_AI_ACT_ART_12_15"


class ComplianceControl(BaseModel):
    """A specific regulatory or framework control requirement."""

    control_id: str
    framework: ComplianceFramework
    function_or_category: str
    title: str
    description: str
    mapped_laws: List[str] = Field(default_factory=list)
    required_capabilities: List[str] = Field(default_factory=list)
    remediation_guidance: str = ""


# ---------------------------------------------------------------------------
# NIST AI Risk Management Framework (AI RMF 1.0 / NIST AI 100-1)
# ---------------------------------------------------------------------------
NIST_AI_RMF_CONTROLS: List[ComplianceControl] = [
    # GOVERN Function
    ComplianceControl(
        control_id="GOVERN-1.1",
        framework=ComplianceFramework.NIST_AI_RMF,
        function_or_category="GOVERN",
        title="Legal and Regulatory Compliance Requirements Identified",
        description="Legal and regulatory requirements involving AI are identified and mapped into organizational policies.",
        mapped_laws=["LAW1-INTERDICT", "LAW2-ENVELOPE", "LAW4-APPROVAL"],
        required_capabilities=["interdiction_rules", "sandbox_envelope", "approval_policy"],
        remediation_guidance="Define unambiguous interdiction rules in policies/interdiction.json and configure approval gates.",
    ),
    ComplianceControl(
        control_id="GOVERN-1.2",
        framework=ComplianceFramework.NIST_AI_RMF,
        function_or_category="GOVERN",
        title="Trustworthy AI System Policies Established",
        description="Policies and operational boundaries exist to govern autonomous action scopes and prevent unauthorized system actions.",
        mapped_laws=["LAW2-ENVELOPE", "LAW10-RATELIMIT"],
        required_capabilities=["envelope_gate", "rate_limiting"],
        remediation_guidance="Configure allowed paths and rate limit thresholds in Settings or cycle configuration.",
    ),
    ComplianceControl(
        control_id="GOVERN-2.1",
        framework=ComplianceFramework.NIST_AI_RMF,
        function_or_category="GOVERN",
        title="Accountability and Roles Defined",
        description="Personnel and operator roles are identified, with cryptographic attribution for configuration and system attestations.",
        mapped_laws=["LAW8-LEDGER", "LAW9-SIG"],
        required_capabilities=["ed25519_keyring", "signed_attestation"],
        remediation_guidance="Generate operator Ed25519 keypair and sign active charter and configuration using orrery.tools.attest.",
    ),
    ComplianceControl(
        control_id="GOVERN-3.1",
        framework=ComplianceFramework.NIST_AI_RMF,
        function_or_category="GOVERN",
        title="Organizational Policies and Directives Pinned",
        description="AI operational guidelines, safety charter, and permanent directives are cryptographically pinned against tampering.",
        mapped_laws=["LAW8-LEDGER", "LAW9-SIG"],
        required_capabilities=["charter_manifest"],
        remediation_guidance="Update and pin charter manifest using python -m orrery.tools.charter --update.",
    ),
    # MAP Function
    ComplianceControl(
        control_id="MAP-1.1",
        framework=ComplianceFramework.NIST_AI_RMF,
        function_or_category="MAP",
        title="Categorization of Action Context and Potential Risks",
        description="Intended autonomous actions and targets are mapped, contextualized, and categorized by risk severity.",
        mapped_laws=["LAW1-INTERDICT", "LAW2-ENVELOPE", "LAW3-QUARANTINE"],
        required_capabilities=["action_risk_classification", "quarantine_classifier"],
        remediation_guidance="Ensure all custom actions are classified with appropriate ActionRisk (READ_ONLY, REVERSIBLE, COMPENSABLE, IRREVERSIBLE).",
    ),
    ComplianceControl(
        control_id="MAP-2.1",
        framework=ComplianceFramework.NIST_AI_RMF,
        function_or_category="MAP",
        title="Boundary and Resource Limits Established",
        description="System boundaries, path traversals, program execution allowlists, and execution scopes are strictly demarcated.",
        mapped_laws=["LAW2-ENVELOPE", "LAW10-RATELIMIT"],
        required_capabilities=["sandbox_boundaries", "rate_limit_quotas"],
        remediation_guidance="Define strict path boundaries and program execution allowlists in adapter configurations.",
    ),
    # MEASURE Function
    ComplianceControl(
        control_id="MEASURE-1.1",
        framework=ComplianceFramework.NIST_AI_RMF,
        function_or_category="MEASURE",
        title="Continuous Invariant and Anomaly Monitoring",
        description="Runtime system behavior is continuously monitored against mathematical invariants, loop anomalies, and repetition.",
        mapped_laws=["LAW5-INVARIANT"],
        required_capabilities=["invariant_monitors", "anomaly_detectors"],
        remediation_guidance="Register InvariantGate monitors covering loop detection, failure repetition, and state drift.",
    ),
    ComplianceControl(
        control_id="MEASURE-2.1",
        framework=ComplianceFramework.NIST_AI_RMF,
        function_or_category="MEASURE",
        title="System Self-Critique and Goal Verification",
        description="Autonomous task completion claims are measured against empirical evidence, reflection thresholds, and out-of-band goal checks.",
        mapped_laws=["LAW6-RECEIPT", "LAW7-GOAL"],
        required_capabilities=["critique_engine", "goal_verification"],
        remediation_guidance="Calibrate theta_critique threshold and provide deterministic or LLM-as-judge goal verification checks.",
    ),
    ComplianceControl(
        control_id="MEASURE-3.1",
        framework=ComplianceFramework.NIST_AI_RMF,
        function_or_category="MEASURE",
        title="Immutable Audit Ledger and Cryptographic Traceability",
        description="All system decisions, gate verdicts, receipts, and state transitions are recorded into an append-only, hash-chained ledger.",
        mapped_laws=["LAW6-RECEIPT", "LAW8-LEDGER", "LAW9-SIG"],
        required_capabilities=["event_ledger", "hash_chaining"],
        remediation_guidance="Enable EventLedger with hash verification in LedgerSettings.",
    ),
    # MANAGE Function
    ComplianceControl(
        control_id="MANAGE-1.1",
        framework=ComplianceFramework.NIST_AI_RMF,
        function_or_category="MANAGE",
        title="Quarantine of Unknown or Unclassified Actions",
        description="Novel or ambiguous actions without explicit safety classifications are held in quarantine rather than executed.",
        mapped_laws=["LAW3-QUARANTINE"],
        required_capabilities=["quarantine_gate"],
        remediation_guidance="Enable QuarantineGate to hold unclassified actions until operator classification.",
    ),
    ComplianceControl(
        control_id="MANAGE-2.1",
        framework=ComplianceFramework.NIST_AI_RMF,
        function_or_category="MANAGE",
        title="Human Oversight and Approval for High-Risk Actions",
        description="Irreversible actions and high-risk operations require explicit human or operator cryptographic approval.",
        mapped_laws=["LAW4-APPROVAL"],
        required_capabilities=["approval_gate", "human_in_the_loop"],
        remediation_guidance="Configure ApprovalGate with irreversible=REQUIRE_APPROVAL policy.",
    ),
    ComplianceControl(
        control_id="MANAGE-3.1",
        framework=ComplianceFramework.NIST_AI_RMF,
        function_or_category="MANAGE",
        title="Fail-Safe Backtracking and State Rollback",
        description="Upon governance violation or critique failure, system rolls back to verified checkpoints with retained lessons.",
        mapped_laws=["LAW5-INVARIANT", "LAW7-GOAL"],
        required_capabilities=["state_checkpoints", "backtracking_engine"],
        remediation_guidance="Enable CheckpointManager with verified checkpoint validation.",
    ),
    ComplianceControl(
        control_id="MANAGE-4.1",
        framework=ComplianceFramework.NIST_AI_RMF,
        function_or_category="MANAGE",
        title="Emergency Stop / Kill-Switch Authority",
        description="Operators possess an external, non-bypassable kill switch to halt cycle dispatch immediately.",
        mapped_laws=["LAW1-INTERDICT", "LAW4-APPROVAL"],
        required_capabilities=["halt_file_switch"],
        remediation_guidance="Ensure halt_file path is configured and monitored across cycles.",
    ),
]

# ---------------------------------------------------------------------------
# White House OMB M-24-10 (Federal Agency AI Governance)
# ---------------------------------------------------------------------------
OMB_M_24_10_CONTROLS: List[ComplianceControl] = [
    ComplianceControl(
        control_id="OMB-AI-PREDEPLOY",
        framework=ComplianceFramework.OMB_M_24_10,
        function_or_category="PRE-DEPLOYMENT",
        title="Pre-Deployment Testing and Evaluation",
        description="Rigorous adversarial and boundary testing conducted prior to production deployment.",
        mapped_laws=["LAW5-INVARIANT", "LAW7-GOAL"],
        required_capabilities=["benchmark_suite", "adversarial_testing"],
        remediation_guidance="Execute full test suite and benchmark suite (orrery.bench) before deployment.",
    ),
    ComplianceControl(
        control_id="OMB-AI-MONITOR",
        framework=ComplianceFramework.OMB_M_24_10,
        function_or_category="RISK_MONITORING",
        title="Ongoing Performance and Invariant Monitoring",
        description="Continuous real-time tracking of AI system degradation, anomalous loops, and rate bursts.",
        mapped_laws=["LAW5-INVARIANT", "LAW10-RATELIMIT"],
        required_capabilities=["invariant_monitors", "rate_limiting", "opentelemetry"],
        remediation_guidance="Ensure telemetry spans and invariant gates are active in production.",
    ),
    ComplianceControl(
        control_id="OMB-AI-OVERSIGHT",
        framework=ComplianceFramework.OMB_M_24_10,
        function_or_category="OVERSIGHT",
        title="Meaningful Human Oversight and Intervention",
        description="Human operators retain override authority, approval mandates, and emergency intervention capability.",
        mapped_laws=["LAW4-APPROVAL", "LAW1-INTERDICT"],
        required_capabilities=["approval_gate", "halt_file_switch"],
        remediation_guidance="Configure ApprovalSettings with explicit human review required for irreversible actions.",
    ),
    ComplianceControl(
        control_id="OMB-AI-AUDIT",
        framework=ComplianceFramework.OMB_M_24_10,
        function_or_category="ACCOUNTABILITY",
        title="Verifiable Audit Trails and Provenance",
        description="Immutable logs of AI activity with cryptographic proof of authenticity and tamper detection.",
        mapped_laws=["LAW8-LEDGER", "LAW9-SIG"],
        required_capabilities=["event_ledger", "ed25519_keyring"],
        remediation_guidance="Maintain Ed25519-signed event ledger with verified cryptographic integrity.",
    ),
]

# ---------------------------------------------------------------------------
# Colorado Artificial Intelligence Act (SB 24-205)
# ---------------------------------------------------------------------------
COLORADO_SB_24_205_CONTROLS: List[ComplianceControl] = [
    ComplianceControl(
        control_id="CO-SB205-DUTY-CARE",
        framework=ComplianceFramework.COLORADO_SB_24_205,
        function_or_category="DUTY_OF_CARE",
        title="Duty of Reasonable Care to Protect Against Algorithmic Discrimination",
        description="Implement risk management policies to avoid discriminatory or unauthorized agent actions.",
        mapped_laws=["LAW1-INTERDICT", "LAW2-ENVELOPE", "LAW3-QUARANTINE"],
        required_capabilities=["interdiction_rules", "sandbox_boundaries"],
        remediation_guidance="Maintain explicit forbidden action patterns and boundary envelopes.",
    ),
    ComplianceControl(
        control_id="CO-SB205-IMPACT-ASSESS",
        framework=ComplianceFramework.COLORADO_SB_24_205,
        function_or_category="IMPACT_ASSESSMENT",
        title="Annual Governance and Risk Impact Assessment",
        description="Document system risk profiles, performance benchmarks, and known residual risks.",
        mapped_laws=["LAW7-GOAL", "LAW8-LEDGER"],
        required_capabilities=["compliance_auditor", "benchmark_suite"],
        remediation_guidance="Generate annual compliance reports via orrery.tools.compliance.",
    ),
    ComplianceControl(
        control_id="CO-SB205-LOGGING",
        framework=ComplianceFramework.COLORADO_SB_24_205,
        function_or_category="INCIDENT_MONITORING",
        title="Incident and Performance Logging",
        description="Continuous immutable recording of governance interventions, quarantine events, and refusals.",
        mapped_laws=["LAW8-LEDGER"],
        required_capabilities=["event_ledger"],
        remediation_guidance="Retain and regularly inspect ledger event files for governance interventions.",
    ),
]

# ---------------------------------------------------------------------------
# California AI Transparency & Safety (AB 2013 / Safety Directives)
# ---------------------------------------------------------------------------
CALIFORNIA_AI_CONTROLS: List[ComplianceControl] = [
    ComplianceControl(
        control_id="CA-AB2013-TRANSPARENCY",
        framework=ComplianceFramework.CALIFORNIA_AI_ACT,
        function_or_category="TRANSPARENCY",
        title="Operational Governance and Policy Disclosure",
        description="Public and verifiable documentation of agent boundaries, safety constraints, and active directives.",
        mapped_laws=["LAW9-SIG"],
        required_capabilities=["signed_attestation", "charter_manifest"],
        remediation_guidance="Publish signed attestation digest and verified GOVERNANCE.md.",
    ),
    ComplianceControl(
        control_id="CA-SAFETY-SHUTDOWN",
        framework=ComplianceFramework.CALIFORNIA_AI_ACT,
        function_or_category="SAFETY_CONTROLS",
        title="Reliable Emergency Shutdown Protocol",
        description="Capability to instantly revoke execution privileges and halt autonomous operation reliably.",
        mapped_laws=["LAW1-INTERDICT", "LAW4-APPROVAL"],
        required_capabilities=["halt_file_switch"],
        remediation_guidance="Ensure halt_file mechanism is integrated into operational runbooks.",
    ),
]

# ---------------------------------------------------------------------------
# EU AI Act (Articles 12-15 International Benchmark)
# ---------------------------------------------------------------------------
EU_AI_ACT_CONTROLS: List[ComplianceControl] = [
    ComplianceControl(
        control_id="EU-ACT-ART12",
        framework=ComplianceFramework.EU_AI_ACT,
        function_or_category="LOGGING",
        title="Article 12: Automatic Record-Keeping and Event Logging",
        description="High-risk AI systems must maintain automatic event recording throughout their lifecycle.",
        mapped_laws=["LAW8-LEDGER", "LAW6-RECEIPT"],
        required_capabilities=["event_ledger", "hash_chaining"],
        remediation_guidance="Ensure all execution phases write receipts to the tamper-evident ledger.",
    ),
    ComplianceControl(
        control_id="EU-ACT-ART13",
        framework=ComplianceFramework.EU_AI_ACT,
        function_or_category="TRANSPARENCY",
        title="Article 13: Transparency and Provision of Information",
        description="Operation of high-risk AI systems must be sufficiently transparent for deployers to interpret outputs.",
        mapped_laws=["LAW7-GOAL", "LAW9-SIG"],
        required_capabilities=["signed_attestation", "critique_reasoning"],
        remediation_guidance="Include detailed reasoning and critique recommendations with every cycle result.",
    ),
    ComplianceControl(
        control_id="EU-ACT-ART14",
        framework=ComplianceFramework.EU_AI_ACT,
        function_or_category="HUMAN_OVERSIGHT",
        title="Article 14: Human Oversight",
        description="High-risk AI systems must be designed to enable natural persons to oversee operation and intervene.",
        mapped_laws=["LAW4-APPROVAL", "LAW1-INTERDICT"],
        required_capabilities=["approval_gate", "halt_file_switch"],
        remediation_guidance="Enable ApprovalGate for all irreversible actions and maintain emergency halt file.",
    ),
    ComplianceControl(
        control_id="EU-ACT-ART15",
        framework=ComplianceFramework.EU_AI_ACT,
        function_or_category="ROBUSTNESS",
        title="Article 15: Accuracy, Robustness, and Cybersecurity",
        description="Systems must be resilient against errors, adversarial manipulation, and unauthorized changes.",
        mapped_laws=["LAW5-INVARIANT", "LAW9-SIG", "LAW10-RATELIMIT"],
        required_capabilities=["invariant_monitors", "rate_limiting", "charter_manifest"],
        remediation_guidance="Verify charter manifest integrity and enable invariant monitors.",
    ),
]

ALL_FRAMEWORKS: Dict[ComplianceFramework, List[ComplianceControl]] = {
    ComplianceFramework.NIST_AI_RMF: NIST_AI_RMF_CONTROLS,
    ComplianceFramework.OMB_M_24_10: OMB_M_24_10_CONTROLS,
    ComplianceFramework.COLORADO_SB_24_205: COLORADO_SB_24_205_CONTROLS,
    ComplianceFramework.CALIFORNIA_AI_ACT: CALIFORNIA_AI_CONTROLS,
    ComplianceFramework.EU_AI_ACT: EU_AI_ACT_CONTROLS,
}
