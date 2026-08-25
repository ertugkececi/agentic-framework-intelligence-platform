"""Provider-neutral deterministic coding model for test workflows."""
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Protocol

from agentic_platform.domain.models import CodingContext
from agentic_platform.tasks.types import DevelopmentTask, FileChange, GeneratedChange

if TYPE_CHECKING:
    from agentic_platform.orchestration.graph import FailureContext


class CodingModel(Protocol):
    def generate_change(
        self,
        task: DevelopmentTask,
        context: CodingContext,
    ) -> GeneratedChange:
        """Return a structured proposal without writing to the filesystem."""

    def repair_change(
        self,
        task: DevelopmentTask,
        context: CodingContext,
        previous_change: GeneratedChange,
        failure_context: FailureContext,
    ) -> GeneratedChange:
        """Return a revised structured proposal using the failed proposal and evidence."""


class DeterministicPythonCodingModel:
    """Test model that derives source only from task and bounded context."""

    def generate_change(
        self,
        task: DevelopmentTask,
        context: CodingContext,
    ) -> GeneratedChange:
        import_lines = self._render_imports(context)
        initializer = self._render_initializer(context)
        method = self._render_operation(task)
        source = (
            f"{import_lines}\n\n@{context.service_decorator}\n"
            f"class {task.artifact_name}({context.service_base_class}):\n"
            f"{initializer}\n\n{method}"
        )
        filename = self._snake_case(task.artifact_name)
        test = (
            f"from app.{filename} import {task.artifact_name}\n\n"
            "def test_generated_artifact_imports():\n"
            f"    assert {task.artifact_name}() is not None\n"
        )
        return GeneratedChange(
            (FileChange(f"app/{filename}.py", source), FileChange(f"tests/test_{filename}.py", test)),
            f"Create {task.artifact_name}",
        )

    def repair_change(
        self,
        task: DevelopmentTask,
        context: CodingContext,
        previous_change: GeneratedChange,
        failure_context: FailureContext,
    ) -> GeneratedChange:
        """Deterministic fallback has no adaptive behavior, but honors the repair port."""
        return self.generate_change(task, context)

    def _render_imports(self, context: CodingContext) -> str:
        grouped: dict[str, list[str]] = defaultdict(list)
        for item in context.imports:
            grouped[item.module].append(item.symbol)
        return "\n".join(
            f"from {module} import {', '.join(sorted(set(symbols)))}"
            for module, symbols in sorted(grouped.items())
        )

    def _render_initializer(self, context: CodingContext) -> str:
        dependencies = [dependency for dependency in context.dependencies if dependency.class_name]
        if not dependencies:
            return "    def __init__(self) -> None:\n        pass"
        assignments = "\n".join(
            f"        self.{dependency.attribute} = {dependency.class_name}"
            f"({', '.join(dependency.constructor_arguments)})"
            for dependency in dependencies
        )
        return f"    def __init__(self) -> None:\n{assignments}"

    def _render_operation(self, task: DevelopmentTask) -> str:
        if not task.operations:
            return "    pass"
        operation = task.operations[0]
        parameters = ", ".join(parameter.name for parameter in operation.parameters)
        suffix = f", {parameters}" if parameters else ""
        return f"    def {operation.name}(self{suffix}):\n        return None"

    @staticmethod
    def _snake_case(value: str) -> str:
        return "".join(f"_{character.lower()}" if character.isupper() else character for character in value).lstrip("_")
