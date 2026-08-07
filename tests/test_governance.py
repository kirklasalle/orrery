"""
Governance conformance gate.

These tests do not check behaviour; they check that the project's governance claims and
its code cannot drift apart. If a policy is declared ENFORCED, a test must exist for it.
If GOVERNANCE.md lists a policy, the registry must too, and vice versa.
"""

import re
from pathlib import Path

import pytest

from orrery.core.governance import (
    POLICIES,
    POLICY_INDEX,
    EnforcementStatus,
    coverage_by_law,
    enforced,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_DOC = REPO_ROOT / "GOVERNANCE.md"

# Policy IDs the runtime emits into the ledger or refuses with.
_SOURCE_POLICY_IDS = {
    "LAW7-SIM",
    "LAW9-LEDGER",
    "LAW9-APPEND",
    "DEL-000",
    "DEL-001",
    "DEL-002",
    "DEL-003",
    "DEL-004",
    "DEL-005",
    "RISK-000",
    "RISK-001",
    "RISK-002",
    "RISK-003",
    "RISK-004",
}


def test_policy_ids_are_unique():
    ids = [policy.policy_id for policy in POLICIES]
    assert len(ids) == len(set(ids))


def test_every_enforced_policy_names_a_test():
    missing = [p.policy_id for p in enforced() if not p.test]
    assert not missing, f"ENFORCED without a test is a claim, not a control: {missing}"


@pytest.mark.parametrize("policy", [p for p in POLICIES if p.test], ids=lambda p: p.policy_id)
def test_named_test_targets_exist(policy):
    path_part, _, node = policy.test.partition("::")
    target = REPO_ROOT / path_part
    assert target.exists(), f"{policy.policy_id} names a missing test file: {path_part}"
    if node:
        assert f"def {node}(" in target.read_text(encoding="utf-8"), (
            f"{policy.policy_id} names a missing test function: {node}"
        )


def test_unenforced_policies_declare_no_mechanism_they_do_not_have():
    for policy in POLICIES:
        if policy.status is EnforcementStatus.NOT_ENFORCED:
            assert policy.mechanism.startswith("None"), (
                f"{policy.policy_id} is NOT_ENFORCED but describes a mechanism"
            )
            assert policy.test is None


def test_policy_ids_used_at_runtime_are_registered():
    unregistered = _SOURCE_POLICY_IDS - set(POLICY_INDEX)
    assert not unregistered, f"runtime emits unregistered policy IDs: {unregistered}"


def test_governance_document_matches_the_registry():
    assert GOVERNANCE_DOC.exists(), "GOVERNANCE.md is the published form of the registry"
    text = GOVERNANCE_DOC.read_text(encoding="utf-8")

    documented = set(re.findall(r"\b((?:LAW\d+|DEL|RISK)-[A-Z0-9]+)\b", text))
    registered = set(POLICY_INDEX)

    assert registered - documented == set(), f"undocumented policies: {registered - documented}"
    assert documented - registered == set(), f"documented but unimplemented: {documented - registered}"


def test_governance_document_states_the_unenforced_law_count():
    """
    The headline number must be in the document, so nobody has to read the registry to
    learn how much of the charter is aspiration.
    """
    text = GOVERNANCE_DOC.read_text(encoding="utf-8")
    coverage = coverage_by_law()
    without_control = sum(1 for status in coverage.values() if status is EnforcementStatus.NOT_ENFORCED)

    assert f"{without_control} of the 10 Laws have no runtime control" in text


def test_all_ten_laws_appear_in_the_registry():
    assert set(coverage_by_law()) == set(range(1, 11))
