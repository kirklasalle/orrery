"""
Tests for OpenTelemetry tracing and structured logging (Task 2.1).

Verifies:
- Native OpenTelemetry tracer initialization and in-memory export.
- Fallback span behavior when OpenTelemetry is mocked as unavailable.
- StructuredLogFormatter JSON output with trace_id / span_id injection.
- CycleDispatcher emitting trace spans across phases, actions, and cycles.
"""

import json
import logging
from unittest.mock import patch
import pytest

from orrery.core import telemetry
from orrery.core.telemetry import (
    FallbackSpan,
    StructuredLogFormatter,
    get_tracer,
    has_opentelemetry,
    setup_in_memory_telemetry,
    trace_span,
)
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.config import Settings
from orrery.core.types import ActionPayload, ActionRisk, StateContext
from orrery.adapters.base import BaseAdapter, ExecutionReceipt


class TelemetryTestAdapter(BaseAdapter):
    is_simulation = True
    declared_risks = {"telemetry_test_action": ActionRisk.READ_ONLY}

    async def perceive_environment(self, context: StateContext) -> dict:
        return {}

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        return self._receipt(action=action, success=True, output="telemetry_ok")


def test_has_opentelemetry():
    """Confirms opentelemetry package is detected in the environment."""
    assert has_opentelemetry() is True
    assert get_tracer() is not None


def test_fallback_span_operations():
    """Verifies FallbackSpan behaves correctly when OpenTelemetry is unavailable."""
    span = FallbackSpan("fallback.test", {"initial.attr": 123})
    assert span.name == "fallback.test"
    assert span.attributes["initial.attr"] == 123
    assert span.status == "UNSET"

    span.set_attribute("added.attr", "hello")
    span.set_attributes({"bulk.attr1": "a", "bulk.attr2": "b"})
    assert span.attributes["added.attr"] == "hello"
    assert span.attributes["bulk.attr1"] == "a"

    span.add_event("checkpoint_saved", {"cp_id": "cp_001"})
    assert len(span.events) == 1
    assert span.events[0]["name"] == "checkpoint_saved"

    span.set_status("OK")
    assert span.status == "OK"

    err = ValueError("Something failed")
    span.record_exception(err)
    assert span.status == "ERROR"
    assert span.error_description == "Something failed"

    span.end()
    assert span.duration_ms() >= 0.0

    d = span.to_dict()
    assert d["name"] == "fallback.test"
    assert d["attributes"]["added.attr"] == "hello"
    assert len(d["events"]) == 2  # checkpoint_saved + exception


def test_trace_span_fallback_mode():
    """Verifies trace_span yields FallbackSpan when _HAS_OTEL is False."""
    with patch("orrery.core.telemetry._HAS_OTEL", False):
        with trace_span("fallback.context", {"key": "val"}) as span:
            assert isinstance(span, FallbackSpan)
            span.set_attribute("inside", True)

        assert span.attributes["key"] == "val"
        assert span.attributes["inside"] is True


def test_trace_span_fallback_exception_handling():
    """Verifies trace_span in fallback mode records exceptions properly."""
    with patch("orrery.core.telemetry._HAS_OTEL", False):
        with pytest.raises(RuntimeError):
            with trace_span("fallback.fail") as span:
                raise RuntimeError("Boom!")

        assert span.status == "ERROR"
        assert "Boom!" in span.error_description


def test_structured_log_formatter():
    """Verifies StructuredLogFormatter outputs valid JSON and injects metadata."""
    formatter = StructuredLogFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=42,
        msg="Execution cycle started",
        args=(),
        exc_info=None,
    )
    record.cycle_id = "cycle_abc123"
    record.action_name = "fs:read"
    record.policy_id = "LAW9-LEDGER"

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test_logger"
    assert parsed["message"] == "Execution cycle started"
    assert parsed["cycle_id"] == "cycle_abc123"
    assert parsed["action_name"] == "fs:read"
    assert parsed["policy_id"] == "LAW9-LEDGER"


def test_structured_log_formatter_with_exception():
    """Verifies StructuredLogFormatter includes formatted exceptions."""
    formatter = StructuredLogFormatter()
    try:
        raise ValueError("Formatted error")
    except ValueError:
        import sys
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test_logger",
        level=logging.ERROR,
        pathname="test.py",
        lineno=10,
        msg="An error occurred",
        args=(),
        exc_info=exc_info,
    )
    formatted = formatter.format(record)
    parsed = json.loads(formatted)
    assert "exception" in parsed
    assert "ValueError: Formatted error" in parsed["exception"]


@pytest.mark.asyncio
async def test_opentelemetry_traces_dispatcher_action():
    """Verifies that executing an action produces an OpenTelemetry span in memory."""
    exporter = setup_in_memory_telemetry()
    if exporter is None:
        pytest.skip("OpenTelemetry SDK not installed")

    exporter.clear()

    dispatcher = CycleDispatcher(
        settings=Settings(allow_simulated_adapters=True),
    )
    adapter = TelemetryTestAdapter(name="telemetry_adapter")
    dispatcher.register_adapter(adapter)

    action = ActionPayload(
        action_name="telemetry_test_action",
        target_adapter="telemetry_adapter",
        risk=ActionRisk.READ_ONLY,
    )

    receipt = await dispatcher.execute_action(action)
    assert receipt.success is True

    # Check exported spans
    spans = exporter.get_finished_spans()
    span_names = [s.name for s in spans]
    assert any("orrery.action.telemetry_test_action" in name for name in span_names)

    action_span = next(s for s in spans if "orrery.action.telemetry_test_action" in s.name)
    assert action_span.attributes["gen_ai.system"] == "orrery"
    assert action_span.attributes["orrery.action_name"] == "telemetry_test_action"
    assert action_span.attributes["orrery.target_adapter"] == "telemetry_adapter"
    assert action_span.attributes["orrery.risk"] == "READ_ONLY"
