from __future__ import annotations

from dataclasses import dataclass

import pytest

from agentic_platform.domain.models import ArtifactStructureContext, CodingContext
from agentic_platform.models.routing import TaskBasedCodingModelRouter, TaskModelRoute
from agentic_platform.models.gateway import FailureContext
from agentic_platform.tasks.types import DevelopmentTask, FileChange, GeneratedChange


@dataclass
class RecordingModel:
    name: str
    calls: list[tuple[str, DevelopmentTask]]

    def generate_change(self, task: DevelopmentTask, context: CodingContext) -> GeneratedChange:
        self.calls.append(("generate", task))
        return GeneratedChange((FileChange(f"app/{self.name}.py", "x = 1"),), self.name)

    def repair_change(
        self,
        task: DevelopmentTask,
        context: CodingContext,
        previous_change: GeneratedChange,
        failure_context: FailureContext,
    ) -> GeneratedChange:
        self.calls.append(("repair", task))
        return GeneratedChange((FileChange(f"app/{self.name}.py", "x = 2"),), self.name)


def _task(artifact_type: str) -> DevelopmentTask:
    return DevelopmentTask(artifact_type=artifact_type, artifact_name="Example", operations=())


def _context(artifact_type: str) -> CodingContext:
    return CodingContext(
        structure=ArtifactStructureContext(
            artifact_family=artifact_type,
            base_classes=("Base",),
            decorators=("managed",),
            imports=(),
            dependencies=(),
        )
    )


def test_router_selects_model_by_task_artifact_family_for_generation_and_repair() -> None:
    service = RecordingModel("service-model", [])
    controller = RecordingModel("controller-model", [])
    router = TaskBasedCodingModelRouter(
        (
            TaskModelRoute(frozenset({"service"}), service),
            TaskModelRoute(frozenset({"controller"}), controller),
        )
    )
    task = _task("controller")
    context = _context("controller")
    previous = GeneratedChange((FileChange("app/example.py", "broken"),), "initial")

    assert router.generate_change(task, context).summary == "controller-model"
    assert router.repair_change(task, context, previous, FailureContext("test", 1, ("pytest",), "failed")).summary == "controller-model"
    assert [kind for kind, _ in controller.calls] == ["generate", "repair"]
    assert service.calls == []


def test_router_uses_explicit_default_and_fails_closed_without_one() -> None:
    default = RecordingModel("default-model", [])
    route = TaskModelRoute(frozenset({"service"}), RecordingModel("service-model", []))

    assert TaskBasedCodingModelRouter((route,), default_model=default).generate_change(
        _task("worker"), _context("worker")
    ).summary == "default-model"

    with pytest.raises(LookupError, match="worker"):
        TaskBasedCodingModelRouter((route,)).generate_change(_task("worker"), _context("worker"))


def test_router_rejects_empty_or_overlapping_routes_before_model_access() -> None:
    model = RecordingModel("model", [])
    with pytest.raises(ValueError, match="at least one"):
        TaskModelRoute(frozenset(), model)
    with pytest.raises(ValueError, match="overlap"):
        TaskBasedCodingModelRouter(
            (
                TaskModelRoute(frozenset({"service", "controller"}), model),
                TaskModelRoute(frozenset({"controller"}), model),
            )
        )
