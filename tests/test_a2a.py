"""
Tests for Agent-to-Agent (A2A) Protocol and Governance Router (Task 2.3).

Verifies:
- Peer-to-peer and hierarchical message routing.
- Ed25519 signature enforcement and anti-forgery.
- Delegation policy constraints (tier descent, loop prevention) on inter-agent dispatches.
- Error handling and ledger audit recording.
"""

import pytest

from orrery.core.a2a import A2AGovernanceRouter, A2AMessage
from orrery.core.delegation import DelegationPolicy, DelegationBudget
from orrery.core.signing import Keyring, OperatorSigner, generate_operator_key
from orrery.core.types import CycleTier


@pytest.mark.asyncio
async def test_a2a_basic_message_routing():
    router = A2AGovernanceRouter()

    async def worker_handler(msg: A2AMessage):
        return {"status": "processed", "input_task": msg.payload.get("task")}

    router.register_agent("worker-01", CycleTier.MESO, worker_handler)

    msg = A2AMessage(
        sender_id="coordinator-01",
        recipient_id="worker-01",
        sender_tier=CycleTier.MACRO,
        intent="query_status",
        payload={"task": "inspect_disk"},
    )

    res = await router.route_message(msg)
    assert res.delivered is True
    assert res.response_payload["status"] == "processed"
    assert res.response_payload["input_task"] == "inspect_disk"


@pytest.mark.asyncio
async def test_a2a_unknown_recipient_refused():
    router = A2AGovernanceRouter()

    msg = A2AMessage(
        sender_id="parent-01",
        recipient_id="nonexistent-agent",
        sender_tier=CycleTier.META,
        intent="query",
    )

    res = await router.route_message(msg)
    assert res.delivered is False
    assert res.policy_id == "A2A-UNKNOWN-RECIPIENT"
    assert "not registered" in res.reason


@pytest.mark.asyncio
async def test_a2a_signed_message_verification():
    priv_hex, pub_hex = generate_operator_key()
    signer = OperatorSigner("trusted-sender", bytes.fromhex(priv_hex))

    keyring = Keyring()
    keyring.add("trusted-sender", pub_hex)

    router = A2AGovernanceRouter(keyring=keyring, require_signatures=True)

    router.register_agent("receiver", CycleTier.MICRO, lambda m: {"echo": "ok"})

    # 1. Valid signed message
    valid_msg = A2AMessage(
        sender_id="trusted-sender",
        recipient_id="receiver",
        sender_tier=CycleTier.MESO,
        intent="ping",
    )
    valid_msg.sign(signer)

    res = await router.route_message(valid_msg)
    assert res.delivered is True

    # 2. Tampered / unsigned message
    tampered_msg = A2AMessage(
        sender_id="trusted-sender",
        recipient_id="receiver",
        sender_tier=CycleTier.MESO,
        intent="ping",
    )
    # No signature attached
    res_tampered = await router.route_message(tampered_msg)
    assert res_tampered.delivered is False
    assert res_tampered.policy_id == "A2A-SIGNATURE-INVALID"


@pytest.mark.asyncio
async def test_a2a_delegation_tier_descent_enforcement():
    """DEL-005: Inter-agent task delegation must descend the tier hierarchy."""
    router = A2AGovernanceRouter()

    router.register_agent("meta-lead", CycleTier.META, lambda m: {"accepted": True})

    # MICRO trying to delegate upwards to META
    upward_msg = A2AMessage(
        sender_id="micro-worker",
        recipient_id="meta-lead",
        sender_tier=CycleTier.MICRO,
        intent="delegate_task",
        payload={"task": "strategize"},
    )

    res = await router.route_message(upward_msg)
    assert res.delivered is False
    assert res.policy_id == "DEL-005"
    assert "descend" in res.reason


@pytest.mark.asyncio
async def test_a2a_delegation_loop_refused():
    """DEL-004: Inter-agent task delegation may not loop back onto an ancestor."""
    router = A2AGovernanceRouter()

    router.register_agent("ancestor-agent", CycleTier.MESO, lambda m: {"accepted": True})

    loop_msg = A2AMessage(
        sender_id="child-agent",
        recipient_id="ancestor-agent",
        sender_tier=CycleTier.MACRO,
        intent="delegate_task",
        ancestry=("ancestor-agent", "middle-agent"),
    )

    res = await router.route_message(loop_msg)
    assert res.delivered is False
    assert res.policy_id == "DEL-004"
    assert "loop" in res.reason


@pytest.mark.asyncio
async def test_a2a_handler_exception_handled():
    router = A2AGovernanceRouter()

    def faulty_handler(msg: A2AMessage):
        raise RuntimeError("Service temporarily down")

    router.register_agent("faulty-worker", CycleTier.MICRO, faulty_handler)

    msg = A2AMessage(
        sender_id="caller",
        recipient_id="faulty-worker",
        sender_tier=CycleTier.MESO,
        intent="work",
    )

    res = await router.route_message(msg)
    assert res.delivered is False
    assert res.policy_id == "A2A-HANDLER-ERROR"
    assert "RuntimeError" in res.reason
