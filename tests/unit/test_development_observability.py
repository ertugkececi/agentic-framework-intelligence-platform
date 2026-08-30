from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from agentic_platform.orchestration.observability import OpenTelemetryDevelopmentObserver
from agentic_platform.orchestration.run_records import DevelopmentRunRecord, DevelopmentRunRecordStore


class _Span:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}

    def set_attribute(self, name: str, value: object) -> None:
        self.attributes[name] = value


class _Tracer:
    def __init__(self) -> None:
        self.names: list[str] = []
        self.spans: list[_Span] = []

    @contextmanager
    def start_as_current_span(self, name: str):
        self.names.append(name)
        span = _Span()
        self.spans.append(span)
        yield span


class _Instrument:
    def __init__(self) -> None:
        self.calls: list[tuple[float, dict[str, object]]] = []

    def add(self, value: float, attributes: dict[str, object]) -> None:
        self.calls.append((value, attributes))

    def record(self, value: float, attributes: dict[str, object]) -> None:
        self.calls.append((value, attributes))


class _Meter:
    def __init__(self) -> None:
        self.counter = _Instrument()
        self.histogram = _Instrument()

    def create_counter(self, name: str, **kwargs) -> _Instrument:
        assert name == "development.runs"
        return self.counter

    def create_histogram(self, name: str, **kwargs) -> _Instrument:
        assert name == "development.generated_bytes"
        return self.histogram


def _record(run_id: str, *, status: str = "succeeded") -> DevelopmentRunRecord:
    return DevelopmentRunRecord(
        run_id=run_id, repository_revision="a" * 64, task_hash="b" * 64,
        model_identity="provider/model", retry_budget=2, knowledge_rule_ids=(),
        artifacts=(), status=status,
    )


def test_otel_observer_emits_bounded_run_trace_and_metrics() -> None:
    tracer = _Tracer()
    meter = _Meter()
    observer = OpenTelemetryDevelopmentObserver(tracer=tracer, meter=meter)

    observer.record(_record("run-001"), retry_count=1, generated_bytes=42)

    expected = {
        "run.id": "run-001",
        "run.status": "succeeded",
        "model.identity": "provider/model",
        "repository.revision": "a" * 64,
        "retry.count": 1,
    }
    metric_attributes = {
        "run.status": "succeeded",
        "model.identity": "provider/model",
    }
    assert tracer.names == ["development.run"]
    assert tracer.spans[0].attributes == expected
    assert meter.counter.calls == [(1, metric_attributes)]
    assert meter.histogram.calls == [(42, metric_attributes)]
    assert "task" not in " ".join(expected)


def test_audit_replay_is_deterministic_and_detects_tampering(tmp_path: Path) -> None:
    store = DevelopmentRunRecordStore(tmp_path / "records.sqlite")
    try:
        store.save(_record("run-b", status="failed"))
        store.save(_record("run-a"))
        replay = store.replay()
        assert tuple(record.run_id for record in replay) == ("run-a", "run-b")
        assert replay == store.replay()

        store.connection.execute(
            "UPDATE development_run_record SET payload_json = ? WHERE run_id = ?",
            (_record("other").to_json(), "run-a"),
        )
        store.connection.commit()
        try:
            store.replay()
        except ValueError as error:
            assert "identity mismatch" in str(error)
        else:
            raise AssertionError("tampered audit replay must fail closed")
    finally:
        store.close()
