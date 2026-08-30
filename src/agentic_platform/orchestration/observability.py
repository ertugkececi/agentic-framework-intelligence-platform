"""OpenTelemetry-compatible run telemetry with bounded audit attributes."""
from __future__ import annotations

from typing import ContextManager, Protocol

from agentic_platform.orchestration.run_records import DevelopmentRunRecord


class Span(Protocol):
    def set_attribute(self, name: str, value: object) -> None: ...


class Tracer(Protocol):
    def start_as_current_span(self, name: str) -> ContextManager[Span]: ...


class MetricInstrument(Protocol):
    def add(self, value: float, attributes: dict[str, object]) -> None: ...

    def record(self, value: float, attributes: dict[str, object]) -> None: ...


class Meter(Protocol):
    def create_counter(self, name: str, **kwargs: object) -> MetricInstrument: ...

    def create_histogram(self, name: str, **kwargs: object) -> MetricInstrument: ...


class DevelopmentObserver(Protocol):
    def record(
        self, record: DevelopmentRunRecord, *, retry_count: int, generated_bytes: int
    ) -> None: ...


class OpenTelemetryDevelopmentObserver:
    """Emit run outcomes through injected OpenTelemetry API objects.

    Attributes intentionally contain identities and bounded numbers only; task text,
    prompts, generated source, credentials, and provider responses never cross this
    observability boundary.
    """

    def __init__(self, *, tracer: Tracer, meter: Meter) -> None:
        self._tracer = tracer
        self._runs = meter.create_counter(
            "development.runs", description="Completed development run outcomes"
        )
        self._generated_bytes = meter.create_histogram(
            "development.generated_bytes", unit="By",
            description="Generated artifact bytes per persisted run",
        )

    def record(
        self, record: DevelopmentRunRecord, *, retry_count: int, generated_bytes: int
    ) -> None:
        if not isinstance(record, DevelopmentRunRecord):
            raise TypeError("record must be a DevelopmentRunRecord")
        if retry_count < 0 or generated_bytes < 0:
            raise ValueError("observability measurements must not be negative")
        attributes: dict[str, object] = {
            "run.id": record.run_id,
            "run.status": record.status,
            "model.identity": record.model_identity,
            "repository.revision": record.repository_revision,
            "retry.count": retry_count,
        }
        metric_attributes: dict[str, object] = {
            "run.status": record.status,
            "model.identity": record.model_identity,
        }
        with self._tracer.start_as_current_span("development.run") as span:
            for name, value in attributes.items():
                span.set_attribute(name, value)
            self._runs.add(1, attributes=metric_attributes)
            self._generated_bytes.record(generated_bytes, attributes=metric_attributes)
