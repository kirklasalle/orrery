"""
Tests for Formal Soundness Verification of Gate Composition (Theorems 1-5).
"""

import pytest
from orrery.verification.soundness import (
    GateSoundnessVerifier,
    ActionPayloadFuzzer,
    TrackingMockAdapter,
)


@pytest.fixture
def verifier() -> GateSoundnessVerifier:
    return GateSoundnessVerifier(seed=1337)


def test_thm_01_non_bypassability(verifier: GateSoundnessVerifier) -> None:
    res = verifier.verify_non_bypassability(iterations=100)
    assert res.passed is True
    assert res.violations_count == 0
    assert res.iterations == 100


def test_thm_02_monotonic_ordering(verifier: GateSoundnessVerifier) -> None:
    res = verifier.verify_monotonic_ordering(iterations=75)
    assert res.passed is True
    assert res.violations_count == 0


def test_thm_03_risk_monotonicity_and_immutability(verifier: GateSoundnessVerifier) -> None:
    res = verifier.verify_risk_non_deescalation(iterations=75)
    assert res.passed is True
    assert res.violations_count == 0


def test_thm_04_audit_ledger_completeness(verifier: GateSoundnessVerifier) -> None:
    res = verifier.verify_ledger_completeness(iterations=60)
    assert res.passed is True
    assert res.violations_count == 0


def test_thm_05_state_backtracking_soundness(verifier: GateSoundnessVerifier) -> None:
    res = verifier.verify_state_backtracking_soundness(iterations=30)
    assert res.passed is True
    assert res.violations_count == 0


def test_full_soundness_report(verifier: GateSoundnessVerifier) -> None:
    report = verifier.run_full_verification(iterations=40)
    assert report.is_sound is True
    assert report.passed_properties == 5
    assert report.total_properties == 5
    summary = report.summary_markdown()
    assert "PASSED (SOUND)" in summary
    assert "`THM-01`" in summary
    assert "`THM-05`" in summary


def test_failure_report_markdown() -> None:
    from orrery.verification.soundness import SoundnessReport, PropertyVerificationResult
    res = PropertyVerificationResult(
        theorem_id="THM-FAIL",
        theorem_name="Failing Theorem",
        passed=False,
        iterations=10,
        violations_count=1,
        failure_cases=["Simulated gate bypass failure"],
        description="Test description",
    )
    report = SoundnessReport(
        total_properties=1,
        passed_properties=0,
        is_sound=False,
        execution_time_seconds=0.1,
        results=[res],
    )
    summary = report.summary_markdown()
    assert "FAILED (UNSOUND)" in summary
    assert "### Violation Details" in summary
    assert "Simulated gate bypass failure" in summary


def test_tracking_mock_adapter_methods() -> None:
    from orrery.core.types import StateContext, ActionPayload
    adapter = TrackingMockAdapter()
    assert adapter.perceive_environment(StateContext(goal="test")) == {"status": "ok"}
    receipt = adapter.execute(ActionPayload(action_name="safe_read"))
    assert receipt.success is True
    assert len(adapter.executed_actions) == 1


def test_cli_verify_soundness(tmp_path) -> None:
    import sys
    from unittest.mock import patch
    from orrery.tools.verify_soundness import main

    out_file = tmp_path / "soundness_report.json"
    test_args = ["verify_soundness", "--iterations", "10", "--output", str(out_file)]
    with patch.object(sys, "argv", test_args):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 0
    assert out_file.exists()

