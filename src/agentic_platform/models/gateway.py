"""Provider-neutral deterministic coding model for test workflows."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

from agentic_platform.domain.models import CodingContext
from agentic_platform.tasks.types import DevelopmentTask, FileChange, GeneratedChange, ParameterSpec

class CodingModelError(RuntimeError):
    """Provider-neutral boundary for failures while producing a coding change."""


@dataclass(frozen=True)
class FailureContext:
    """Compact, bounded evidence passed from a failed check to a repair attempt."""

    stage: str
    attempt: int
    command: tuple[str, ...]
    output: str


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
        method = self._render_operations(task, context)
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
        grouped: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        for item in context.imports:
            grouped[item.module].append((item.symbol, item.alias))
        return "\n".join(
            f"from {module} import {', '.join(self._render_import(symbol, alias) for symbol, alias in sorted(set(symbols)))}"
            for module, symbols in sorted(grouped.items())
        )

    @staticmethod
    def _render_import(symbol: str, alias: str | None) -> str:
        return f"{symbol} as {alias}" if alias else symbol

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

    def _render_operations(self, task: DevelopmentTask, context: CodingContext) -> str:
        if not task.operations:
            return "    pass"
        return "\n\n".join(self._render_operation(operation.name, operation.parameters, context) for operation in task.operations)

    def _render_operation(
        self,
        name: str,
        parameters: tuple[ParameterSpec, ...],
        context: CodingContext,
    ) -> str:
        parameter_names = ", ".join(parameter.name for parameter in parameters)
        suffix = f", {parameter_names}" if parameter_names else ""
        invocations = [
            f"        self.{dependency.attribute}.{requirement.method_name}"
            f"({', '.join(self._render_argument(shape, name) for shape in requirement.argument_shapes)})"
            for dependency in context.dependencies
            for requirement in dependency.required_invocations
        ]
        body = [*invocations, "        return None"]
        return f"    def {name}(self{suffix}):\n" + "\n".join(body)

    @staticmethod
    def _render_argument(shape: str, operation_name: str) -> str:
        values = {
            "string_literal": repr(f"{operation_name} invoked"),
            "integer_literal": "0",
            "float_literal": "0.0",
            "boolean_literal": "True",
            "none_literal": "None",
            "empty_mapping": "{}",
            "empty_sequence": "[]",
        }
        try:
            return values[shape]
        except KeyError as error:
            raise CodingModelError(f"Unsupported learned invocation argument shape: {shape}") from error

    @staticmethod
    def _snake_case(value: str) -> str:
        return "".join(f"_{character.lower()}" if character.isupper() else character for character in value).lstrip("_")
