"""
Tests for OpenRouter Adapter and LLM-as-a-Judge Goal Verification (Law 7).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest

from orrery.adapters.openrouter import OpenRouterAdapter
from orrery.core.critique import SelfCritiqueEngine
from orrery.core.judge import LLMGoalJudge, create_openrouter_goal_check
from orrery.core.types import ActionPayload, ActionRisk, CycleTier, ExecutionReceipt, StateContext


def test_openrouter_adapter_risk_classification():
    adapter = OpenRouterAdapter()
    action = ActionPayload(
        action_name="chat_completion",
        params={"messages": [{"role": "user", "content": "hi"}]},
        tier=CycleTier.MICRO,
        target_adapter="openrouter",
    )
    assert adapter.classify_risk(action) == ActionRisk.READ_ONLY


def test_openrouter_adapter_unknown_action():
    adapter = OpenRouterAdapter()
    action = ActionPayload(
        action_name="destroy_world",
        params={},
        tier=CycleTier.MICRO,
        target_adapter="openrouter",
    )
    receipt = adapter.execute(action)
    assert not receipt.success
    assert "unknown action" in receipt.error


def test_openrouter_adapter_model_allowlist_enforcement():
    adapter = OpenRouterAdapter(allowed_models=["openai/gpt-4o-mini"])
    action = ActionPayload(
        action_name="chat_completion",
        params={
            "model": "meta-llama/llama-3-70b-instruct",
            "messages": [{"role": "user", "content": "test"}],
        },
        tier=CycleTier.MICRO,
        target_adapter="openrouter",
    )
    receipt = adapter.execute(action)
    assert not receipt.success
    assert "not permitted by model allowlist" in receipt.error


def test_openrouter_adapter_max_tokens_budget_enforcement():
    adapter = OpenRouterAdapter(max_tokens_limit=500)
    action = ActionPayload(
        action_name="chat_completion",
        params={
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": "test"}],
        },
        tier=CycleTier.MICRO,
        target_adapter="openrouter",
    )
    receipt = adapter.execute(action)
    assert not receipt.success
    assert "exceeds adapter limit" in receipt.error


def test_openrouter_adapter_simulation_mode():
    adapter = OpenRouterAdapter(is_simulation=True)

    # chat_completion
    action_chat = ActionPayload(
        action_name="chat_completion",
        params={"messages": [{"role": "user", "content": "Evaluate plan outcome."}]},
        tier=CycleTier.MICRO,
        target_adapter="openrouter",
    )
    receipt_chat = adapter.execute(action_chat)
    assert receipt_chat.success
    assert "choices" in receipt_chat.output
    assert receipt_chat.output.get("simulated") is True

    # generate_text
    action_gen = ActionPayload(
        action_name="generate_text",
        params={"prompt": "Summarize the state."},
        tier=CycleTier.MICRO,
        target_adapter="openrouter",
    )
    receipt_gen = adapter.execute(action_gen)
    assert receipt_gen.success
    assert "choices" in receipt_gen.output


def test_openrouter_adapter_mocked_http_call():
    adapter = OpenRouterAdapter(api_key="sk-or-mock-key")
    action = ActionPayload(
        action_name="chat_completion",
        params={"messages": [{"role": "user", "content": "hello"}]},
        tier=CycleTier.MICRO,
        target_adapter="openrouter",
    )

    mock_response_data = {
        "id": "gen-123",
        "choices": [{"message": {"role": "assistant", "content": "world"}}],
        "usage": {"total_tokens": 15},
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        receipt = adapter.execute(action)

    assert receipt.success
    assert receipt.output["choices"][0]["message"]["content"] == "world"


def test_llm_goal_judge_successful_verification():
    adapter = OpenRouterAdapter(is_simulation=True)
    judge = LLMGoalJudge(adapter=adapter, min_confidence=0.70)

    context = StateContext(
        planned_actions=[
            ActionPayload(
                action_name="write_file",
                params={"path": "report.txt"},
                tier=CycleTier.MICRO,
                target_adapter="filesystem",
            )
        ],
        execution_receipts=[
            ExecutionReceipt(
                action_id="act-1",
                action_name="write_file",
                success=True,
                execution_time_seconds=0.01,
            )
        ],
    )

    verdict = judge.verify_goal(context, goal="Ensure report.txt exists.")
    assert verdict.verified is True
    assert "confidence" in verdict.detail.lower()


def test_llm_goal_judge_rejection():
    # Adapter returns an explicit failure verdict
    adapter = OpenRouterAdapter(is_simulation=True)

    def _mock_execute(action: ActionPayload) -> ExecutionReceipt:
        return ExecutionReceipt(
            action_id=action.action_id,
            action_name=action.action_name,
            success=True,
            execution_time_seconds=0.01,
            output={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "verified": False,
                                "confidence": 0.90,
                                "detail": "Destination file is completely empty.",
                                "identified_defects": ["missing content", "zero byte file"],
                            })
                        }
                    }
                ]
            },
        )

    adapter.execute = _mock_execute
    judge = LLMGoalJudge(adapter=adapter)

    context = StateContext()
    verdict = judge.verify_goal(context, goal="Write comprehensive report.")
    assert verdict.verified is False
    assert "refused goal attainment" in verdict.detail
    assert "missing content" in verdict.detail


def test_llm_goal_judge_low_confidence_fails_closed():
    adapter = OpenRouterAdapter(is_simulation=True)

    def _mock_execute(action: ActionPayload) -> ExecutionReceipt:
        return ExecutionReceipt(
            action_id=action.action_id,
            action_name=action.action_name,
            success=True,
            execution_time_seconds=0.01,
            output={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "verified": True,
                                "confidence": 0.50,  # Below 0.70 threshold!
                                "detail": "Maybe it succeeded, but I cannot be sure.",
                                "identified_defects": [],
                            })
                        }
                    }
                ]
            },
        )

    adapter.execute = _mock_execute
    judge = LLMGoalJudge(adapter=adapter, min_confidence=0.70)

    context = StateContext()
    verdict = judge.verify_goal(context, goal="Verify transaction.")
    # Must fail closed because confidence 0.50 < 0.70
    assert verdict.verified is False
    assert "below required threshold" in verdict.detail


def test_llm_goal_judge_integration_with_self_critique_engine():
    """
    Validates Law 7: A plan with 100% action success ratio is STILL refused
    if the LLM goal judge vetoes goal satisfaction.
    """
    adapter = OpenRouterAdapter(is_simulation=True)

    # Mock judge veto
    adapter.execute = lambda action: ExecutionReceipt(
        action_id=action.action_id,
        action_name=action.action_name,
        success=True,
        execution_time_seconds=0.01,
        output={
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "verified": False,
                            "confidence": 0.95,
                            "detail": "Data was written to the wrong partition.",
                        })
                    }
                }
            ]
        },
    )

    goal_check = create_openrouter_goal_check(adapter=adapter, goal="Partition dataset correctly.")
    engine = SelfCritiqueEngine(threshold=0.80, goal_check=goal_check)

    context = StateContext(
        planned_actions=[
            ActionPayload(
                action_name="write_partition",
                params={"dest": "/tmp/a"},
                tier=CycleTier.MICRO,
                target_adapter="filesystem",
            )
        ],
        # Action succeeded! 100% success ratio!
        execution_receipts=[
            ExecutionReceipt(
                action_id="act-partition",
                action_name="write_partition",
                success=True,
                execution_time_seconds=0.02,
            )
        ],
    )

    critique = engine.evaluate(context)

    # Despite 1.0 success ratio, critique MUST fail because goal check vetoed!
    assert critique.score == 1.0
    assert critique.passed is False
    assert critique.goal_verified is False
    assert "the goal is not met" in critique.reasoning
    assert "wrong partition" in critique.verification_detail


@pytest.mark.asyncio
async def test_openrouter_perceive_environment_and_execute_action_async():
    adapter = OpenRouterAdapter(is_simulation=True)
    context = StateContext()
    env = await adapter.perceive_environment(context)
    assert env["adapter"] == "openrouter"
    assert env["is_simulation"] is True

    action = ActionPayload(
        action_name="chat_completion",
        params={"messages": [{"role": "user", "content": "hi"}]},
        tier=CycleTier.MICRO,
        target_adapter="openrouter",
    )
    receipt = await adapter.execute_action(action)
    assert receipt.success


def test_openrouter_http_and_connection_errors():
    adapter = OpenRouterAdapter(api_key="sk-test-key")
    action = ActionPayload(
        action_name="chat_completion",
        params={"messages": [{"role": "user", "content": "hi"}]},
        tier=CycleTier.MICRO,
        target_adapter="openrouter",
    )

    import urllib.error
    # Test HTTP 401 Unauthorized
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)):
        receipt = adapter.execute(action)
        assert not receipt.success
        assert "HTTP 401" in receipt.error

    # Test URLError connection failed
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        receipt = adapter.execute(action)
        assert not receipt.success
        assert "connection error" in receipt.error.lower()

    # Test Generic Exception
    with patch("urllib.request.urlopen", side_effect=RuntimeError("Unexpected crash")):
        receipt = adapter.execute(action)
        assert not receipt.success
        assert "OpenRouter request failed" in receipt.error


def test_openrouter_invalid_messages_type():
    adapter = OpenRouterAdapter(is_simulation=True)
    action = ActionPayload(
        action_name="chat_completion",
        params={"messages": "not-a-list"},
        tier=CycleTier.MICRO,
        target_adapter="openrouter",
    )
    receipt = adapter.execute(action)
    assert not receipt.success
    assert "must be a list of message dicts" in receipt.error


def test_llm_goal_judge_empty_choices_and_corrupt_json():
    adapter = OpenRouterAdapter(is_simulation=True)

    # Empty choices test
    adapter.execute = lambda act: ExecutionReceipt(
        action_id=act.action_id,
        action_name=act.action_name,
        success=True,
        execution_time_seconds=0.01,
        output={"choices": []},
    )
    judge = LLMGoalJudge(adapter=adapter)
    verdict = judge.verify_goal(StateContext())
    assert verdict.verified is False
    assert "empty response choices" in verdict.detail

    # Corrupt JSON content test
    adapter.execute = lambda act: ExecutionReceipt(
        action_id=act.action_id,
        action_name=act.action_name,
        success=True,
        execution_time_seconds=0.01,
        output={"choices": [{"message": {"content": "not-valid-json{"}}]},
    )
    verdict = judge.verify_goal(StateContext())
    assert verdict.verified is False
    assert "Failed to parse" in verdict.detail
