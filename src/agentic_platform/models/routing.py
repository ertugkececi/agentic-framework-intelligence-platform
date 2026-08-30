"""Deterministic task-based routing for provider-neutral coding models."""
from __future__ import annotations

from dataclasses import dataclass

from agentic_platform.domain.models import CodingContext
from agentic_platform.models.gateway import CodingModel, FailureContext
from agentic_platform.tasks.types import DevelopmentTask, GeneratedChange


@dataclass(frozen=True)
class TaskModelRoute:
    """Bind one coding model to an explicit set of artifact families."""

    artifact_types: frozenset[str]
    model: CodingModel

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_types, frozenset):
            raise TypeError("artifact_types must be a frozenset")
        if not self.artifact_types:
            raise ValueError("a task model route requires at least one artifact type")
        if any(not isinstance(value, str) or not value.strip() or value != value.strip() for value in self.artifact_types):
            raise ValueError("artifact types must be non-empty normalized strings")


class TaskBasedCodingModelRouter:
    """Route generation and repair by immutable task classification.

    Routing is deterministic and configured before model access. Overlap is
    rejected rather than resolved by declaration order, and unmatched tasks are
    denied unless the composition root supplies an explicit default model.
    """

    def __init__(
        self,
        routes: tuple[TaskModelRoute, ...],
        *,
        default_model: CodingModel | None = None,
    ) -> None:
        if not isinstance(routes, tuple) or not routes:
            raise ValueError("task model routing requires at least one route")
        owners: dict[str, CodingModel] = {}
        for route in routes:
            if not isinstance(route, TaskModelRoute):
                raise TypeError("routes must contain TaskModelRoute values")
            overlap = route.artifact_types.intersection(owners)
            if overlap:
                raise ValueError("task model routes overlap for: " + ", ".join(sorted(overlap)))
            owners.update((artifact_type, route.model) for artifact_type in route.artifact_types)
        self._models_by_artifact_type = owners
        self._default_model = default_model

    def generate_change(self, task: DevelopmentTask, context: CodingContext) -> GeneratedChange:
        return self._select(task).generate_change(task, context)

    def repair_change(
        self,
        task: DevelopmentTask,
        context: CodingContext,
        previous_change: GeneratedChange,
        failure_context: FailureContext,
    ) -> GeneratedChange:
        return self._select(task).repair_change(task, context, previous_change, failure_context)

    def _select(self, task: DevelopmentTask) -> CodingModel:
        model = self._models_by_artifact_type.get(task.artifact_type, self._default_model)
        if model is None:
            raise LookupError(f"no coding model route for artifact type {task.artifact_type!r}")
        return model
