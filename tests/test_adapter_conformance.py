"""
Every bundled adapter must pass the Adapter Conformance Kit.

The kit is also the contract offered to third-party adapter authors, so it is run here
against the simulations and the real adapter alike.
"""

import pytest

from orrery.adapters.conformance import run_conformance
from orrery.adapters.filesystem import FileSystemAdapter
from orrery.adapters.hermes import HermesAdapter
from orrery.adapters.openclaw import OpenClawAdapter
from orrery.adapters.windows_os import WindowsOSAdapter
from orrery.core.types import ActionRisk
from tests.conftest import StubAdapter


@pytest.mark.parametrize(
    "factory, action, params",
    [
        (OpenClawAdapter, "route_task", {}),
        (HermesAdapter, "evaluate_gate", {}),
        (WindowsOSAdapter, "click_element", {"target": "button"}),
        (StubAdapter, "anything", {}),
    ],
    ids=["openclaw", "hermes", "windows_os", "stub"],
)
def test_bundled_adapters_conform(factory, action, params):
    report = run_conformance(factory(), sample_action=action, sample_params=params)
    assert report.passed, report.summary


def test_filesystem_adapter_conforms(tmp_path):
    adapter = FileSystemAdapter(root=str(tmp_path / "sandbox"))
    report = run_conformance(
        adapter, sample_action="write_file", sample_params={"path": "probe.txt", "content": "x"}
    )
    assert report.passed, report.summary


def test_conformance_catches_an_adapter_that_raises(tmp_path):
    adapter = StubAdapter(raises=True)
    report = run_conformance(adapter, sample_action="anything")

    assert not report.passed
    failed = {check.check_id for check in report.failures}
    assert "ADP-008" in failed


def test_an_adapter_without_a_vocabulary_gets_a_visibly_weaker_report():
    """
    Skipping a check must be recorded, not silently treated as a pass.
    """
    report = run_conformance(StubAdapter(), sample_action="anything")

    assert report.passed
    assert {check.check_id for check in report.skipped} == {"ADP-005", "ADP-006"}
    assert "skipped" in report.summary


def test_a_real_adapter_has_nothing_skipped(tmp_path):
    report = run_conformance(
        FileSystemAdapter(root=str(tmp_path / "sandbox")),
        sample_action="write_file",
        sample_params={"path": "probe.txt", "content": "x"},
    )

    assert report.skipped == []


def test_only_the_real_adapter_declares_itself_real(tmp_path):
    assert FileSystemAdapter.is_simulation is False
    assert all(a.is_simulation for a in (OpenClawAdapter, HermesAdapter, WindowsOSAdapter))


def test_unknown_actions_default_to_irreversible():
    assert FileSystemAdapter.risk_for("something_nobody_declared") is ActionRisk.IRREVERSIBLE
    assert FileSystemAdapter.risk_for("read_file") is ActionRisk.READ_ONLY
