"""
Tests for GovernancePipeline / Gates SDK (Task 2.5).

Verifies:
- Standalone execution without cognitive cycle dispatcher.
- Gate evaluation order (Interdiction -> Envelope -> Quarantine -> RateLimit -> Approval).
- Dynamic rule addition (prohibitions, rate limits).
- Audit ledger recording and receipt generation.
"""

import pytest

from orrery.adapters.filesystem import FileSystemAdapter
from orrery.core.config import Settings
from orrery.core.ledger import EventLedger
from orrery.core.types import ActionPayload, ActionRisk
from orrery.gates.pipeline import GovernancePipeline


@pytest.fixture
def sandbox_pipeline(tmp_path):
    storage_dir = tmp_path / "sandbox"
    adapter = FileSystemAdapter(root=str(storage_dir))
    ledger = EventLedger(storage_dir=str(tmp_path / "ledger"), persist=False)
    pipeline = GovernancePipeline(
        settings=Settings(allow_simulated_adapters=True),
        ledger=ledger,
    )
    return pipeline, adapter


@pytest.mark.asyncio
async def test_governance_pipeline_allows_safe_action(sandbox_pipeline):
    pipeline, adapter = sandbox_pipeline

    action = ActionPayload(
        action_name="read_file",
        target_adapter="filesystem",
        params={"path": "nonexistent.txt"},
        risk=ActionRisk.READ_ONLY,
    )

    verdict = pipeline.evaluate(action, adapter)
    assert verdict.allowed is True
    assert verdict.gate_name == "AllGates"


@pytest.mark.asyncio
async def test_governance_pipeline_refuses_prohibited_path(sandbox_pipeline):
    pipeline, adapter = sandbox_pipeline

    pipeline.add_prohibition(
        reason="Security test prohibition",
        paths=["secret.key"],
    )

    action = ActionPayload(
        action_name="read_file",
        target_adapter="filesystem",
        params={"path": "secret.key"},
        risk=ActionRisk.READ_ONLY,
    )

    verdict = pipeline.evaluate(action, adapter)
    assert verdict.allowed is False
    assert verdict.gate_name == "InterdictionGate"
    assert "Security test prohibition" in verdict.reason

    receipt = await pipeline.execute(action, adapter)
    assert receipt.success is False
    assert "InterdictionGate" in receipt.error


@pytest.mark.asyncio
async def test_governance_pipeline_refuses_irreversible_without_approval(sandbox_pipeline):
    pipeline, adapter = sandbox_pipeline

    delete_action = ActionPayload(
        action_name="delete_file",
        target_adapter="filesystem",
        params={"path": "target.txt"},
    )

    verdict = pipeline.evaluate(delete_action, adapter)
    assert verdict.allowed is False
    assert verdict.gate_name == "ApprovalGate"
    assert verdict.policy_id == "RISK-001"


@pytest.mark.asyncio
async def test_governance_pipeline_refuses_rate_limit_burst(sandbox_pipeline):
    pipeline, adapter = sandbox_pipeline

    pipeline.add_rate_limit(
        name="max_reads",
        action="read_file",
        max_calls=2,
        window_seconds=60.0,
    )

    action = ActionPayload(
        action_name="read_file",
        target_adapter="filesystem",
        params={"path": "data.txt"},
        risk=ActionRisk.READ_ONLY,
    )

    # 1 and 2 allowed
    assert pipeline.evaluate(action, adapter).allowed is True
    assert pipeline.evaluate(action, adapter).allowed is True

    # 3rd is refused
    verdict3 = pipeline.evaluate(action, adapter)
    assert verdict3.allowed is False
    assert verdict3.gate_name == "RateLimitGate"
    assert verdict3.policy_id == "LAW10-RATELIMIT"
    assert "exceeded" in verdict3.reason


@pytest.mark.asyncio
async def test_governance_pipeline_ledgers_actions(sandbox_pipeline):
    pipeline, adapter = sandbox_pipeline

    # Create file first
    write_action = ActionPayload(
        action_name="write_file",
        target_adapter="filesystem",
        params={"path": "ledger_test.txt", "content": "audited data"},
        risk=ActionRisk.COMPENSABLE,
    )

    receipt = await pipeline.execute(write_action, adapter)
    assert receipt.success is True

    # Inspect ledger
    events = pipeline.ledger.events
    assert len(events) >= 1
    last_event = events[-1]
    assert last_event.event_type == "action.executed"
    assert last_event.data.get("action_name") == "write_file"
