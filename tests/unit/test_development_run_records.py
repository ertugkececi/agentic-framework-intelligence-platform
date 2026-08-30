from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from agentic_platform.domain.models import CommandResult, ValidationReport
from agentic_platform.orchestration.graph import DevelopmentService, FrameworkLearningService
from agentic_platform.orchestration.run_records import DevelopmentRunRecordStore
from agentic_platform.security.policy import poc_grant


class _Observer:
    def __init__(self) -> None:
        self.calls = []

    def record(self, record, *, retry_count: int, generated_bytes: int) -> None:
        self.calls.append((record, retry_count, generated_bytes))


ROOT = Path(__file__).resolve().parents[2]
TASK = "Create RecordedService with method run()"


def _passing(*args) -> CommandResult:
    return CommandResult(True, ("check",), "passed")


def test_successful_run_persists_reproducible_identity_and_artifact_hashes(tmp_path: Path) -> None:
    repository = tmp_path / "customer-repo"
    shutil.copytree(ROOT / "examples/sample_customer_repo", repository)
    FrameworkLearningService().learn(tmp_path, repository)

    result = DevelopmentService(
        build_runner=_passing,
        test_runner=_passing,
        validator=lambda *args: ValidationReport(True),
    ).run(tmp_path, repository, TASK, run_id="recorded-run-001", grant=poc_grant(repository))

    store = DevelopmentRunRecordStore(DevelopmentService.run_record_database_path(tmp_path))
    try:
        record = store.get("recorded-run-001")
    finally:
        store.close()

    assert result["status"] == "succeeded"
    assert record is not None
    assert record.run_id == "recorded-run-001"
    assert record.status == "succeeded"
    assert len(record.repository_revision) == 64
    assert record.task_hash == hashlib.sha256(TASK.encode("utf-8")).hexdigest()
    assert record.model_identity.endswith("DeterministicPythonCodingModel")
    assert record.knowledge_rule_ids
    assert tuple(artifact.path for artifact in record.artifacts) == tuple(result["generated_files"])
    for artifact in record.artifacts:
        content = (repository / artifact.path).read_bytes()
        assert artifact.content_hash == hashlib.sha256(content).hexdigest()
        assert artifact.size == len(content)
    assert record.identity == result["run_record_identity"]


def test_successful_run_emits_telemetry_after_audit_persistence(tmp_path: Path) -> None:
    repository = tmp_path / "customer-repo"
    shutil.copytree(ROOT / "examples/sample_customer_repo", repository)
    FrameworkLearningService().learn(tmp_path, repository)
    observer = _Observer()

    result = DevelopmentService(
        build_runner=_passing, test_runner=_passing,
        validator=lambda *args: ValidationReport(True), observer=observer,
    ).run(tmp_path, repository, TASK, run_id="observed-run-001", grant=poc_grant(repository))

    assert result["status"] == "succeeded"
    assert len(observer.calls) == 1
    record, retries, generated_bytes = observer.calls[0]
    assert record.identity == result["run_record_identity"]
    assert retries == result["retry_count"]
    assert generated_bytes == sum(artifact.size for artifact in record.artifacts)
    store = DevelopmentRunRecordStore(DevelopmentService.run_record_database_path(tmp_path))
    try:
        assert store.get(record.run_id) == record
    finally:
        store.close()


def test_run_record_store_rejects_reusing_run_id_for_different_inputs(tmp_path: Path) -> None:
    from agentic_platform.orchestration.run_records import DevelopmentRunRecord

    store = DevelopmentRunRecordStore(tmp_path / "records.sqlite")
    first = DevelopmentRunRecord(
        run_id="same-run", repository_revision="a" * 64, task_hash="b" * 64,
        model_identity="model-a", retry_budget=1, knowledge_rule_ids=(), artifacts=(), status="failed",
    )
    second = DevelopmentRunRecord(
        run_id="same-run", repository_revision="c" * 64, task_hash="b" * 64,
        model_identity="model-a", retry_budget=1, knowledge_rule_ids=(), artifacts=(), status="failed",
    )
    try:
        store.save(first)
        try:
            store.save(second)
        except ValueError as error:
            assert "different inputs" in str(error)
        else:
            raise AssertionError("run identity reuse must fail closed")
    finally:
        store.close()
