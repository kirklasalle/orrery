"""
OpenTelemetry and structured observability integration for Orrery.

Provides:
- Native OpenTelemetry tracing across cycle phases, gate evaluations, and adapter execution.
- Fallback in-memory / JSON structured tracing when OpenTelemetry SDK is not installed.
- Standardized GenAI and Orrery semantic convention attributes:
    gen_ai.system = "orrery"
    orrery.cycle_id
    orrery.tier
    orrery.phase
    orrery.action_id
    orrery.action_name
    orrery.target_adapter
    orrery.risk
    orrery.gate_name
    orrery.gate_verdict
- Structured JSON log formatter with trace_id and span_id injection.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

# Check if opentelemetry is available
_HAS_OTEL = False
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode, Tracer
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    _HAS_OTEL = True
except ImportError:
    trace = None  # type: ignore
    Status = None  # type: ignore
    StatusCode = None  # type: ignore
    Tracer = None  # type: ignore
    TracerProvider = None  # type: ignore
    SimpleSpanProcessor = None  # type: ignore
    InMemorySpanExporter = None  # type: ignore


def has_opentelemetry() -> bool:
    """Returns True if the opentelemetry package is installed and importable."""
    return _HAS_OTEL


class FallbackSpan:
    """
    Lightweight fallback span used when OpenTelemetry is unavailable.
    Provides identical interface for setting attributes, recording exceptions, and timing.
    """

    def __init__(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        self.name = name
        self.attributes: Dict[str, Any] = attributes.copy() if attributes else {}
        self.events: List[Dict[str, Any]] = []
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        self.status: str = "UNSET"
        self.error_description: Optional[str] = None
        self.span_id: str = f"span_{int(self.start_time * 1000):x}"
        self.trace_id: str = f"trace_{int(self.start_time * 1000):x}"

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_attributes(self, attributes: Dict[str, Any]) -> None:
        self.attributes.update(attributes)

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })

    def set_status(self, status: Any, description: Optional[str] = None) -> None:
        self.status = str(status)
        self.error_description = description

    def record_exception(self, exception: BaseException) -> None:
        self.add_event("exception", {
            "exception.type": type(exception).__name__,
            "exception.message": str(exception),
        })
        self.status = "ERROR"
        self.error_description = str(exception)

    def end(self) -> None:
        self.end_time = time.time()

    def duration_ms(self) -> float:
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "attributes": self.attributes,
            "events": self.events,
            "duration_ms": self.duration_ms(),
            "status": self.status,
            "error_description": self.error_description,
        }


class StructuredLogFormatter(logging.Formatter):
    """
    JSON log formatter that formats log records into machine-readable JSON,
    incorporating OpenTelemetry trace and span contexts when available.
    """

    def format(self, record: logging.LogRecord) -> str:
        data: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Inject OpenTelemetry context if active
        if _HAS_OTEL and trace is not None:
            current_span = trace.get_current_span()
            span_context = current_span.get_span_context() if current_span else None
            if span_context and span_context.is_valid:
                data["trace_id"] = f"{span_context.trace_id:032x}"
                data["span_id"] = f"{span_context.span_id:016x}"

        # Inject extra attributes passed in record
        if hasattr(record, "cycle_id"):
            data["cycle_id"] = record.cycle_id
        if hasattr(record, "action_name"):
            data["action_name"] = record.action_name
        if hasattr(record, "policy_id"):
            data["policy_id"] = record.policy_id

        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)

        return json.dumps(data)


# Global tracer registry
_TRACER = None
_IN_MEMORY_EXPORTER = None


def setup_in_memory_telemetry() -> Optional[Any]:
    """
    Sets up an in-memory OpenTelemetry tracer provider for test inspection.
    Returns the InMemorySpanExporter instance, or None if OTel is not installed.
    """
    global _TRACER, _IN_MEMORY_EXPORTER
    if not _HAS_OTEL:
        return None

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer("orrery", "1.0.0")
    _IN_MEMORY_EXPORTER = exporter
    return exporter


def get_tracer(name: str = "orrery"):
    """
    Returns an OpenTelemetry tracer instance if available, or None.
    """
    global _TRACER
    if not _HAS_OTEL:
        return None
    if _TRACER is None:
        _TRACER = trace.get_tracer(name, "1.0.0")
    return _TRACER


@contextmanager
def trace_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
    record_exceptions: bool = True,
) -> Iterator[Any]:
    """
    Context manager that wraps execution in an OpenTelemetry span.
    If OpenTelemetry is unavailable, falls back to a FallbackSpan object.
    
    Standard semantic convention:
    - Sets 'gen_ai.system': 'orrery'
    """
    all_attrs = {"gen_ai.system": "orrery"}
    if attributes:
        all_attrs.update(attributes)

    if _HAS_OTEL and trace is not None:
        tracer = get_tracer()
        with tracer.start_as_current_span(name) as span:
            for k, v in all_attrs.items():
                if v is not None:
                    span.set_attribute(k, v)
            try:
                yield span
            except Exception as exc:
                if record_exceptions:
                    span.record_exception(exc)
                    if Status is not None and StatusCode is not None:
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
    else:
        fallback = FallbackSpan(name, all_attrs)
        try:
            yield fallback
        except Exception as exc:
            if record_exceptions:
                fallback.record_exception(exc)
            raise
        finally:
            fallback.end()
