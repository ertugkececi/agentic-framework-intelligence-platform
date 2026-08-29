"""Python implementation of the typed source parser port."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from agentic_platform.domain.models import Evidence, ImportSpec
from agentic_platform.framework_learning.inventory import SourceFile
from agentic_platform.framework_learning.observations import (
    ConstructorDependencyObservation,
    InvocationObservation,
    ObservationBatch,
    StructuralClassObservation,
)
from agentic_platform.framework_learning.parser import SourceParseError, SourceParser


@dataclass(frozen=True)
class ParsedPythonModule:
    """Python AST and normalized structural import observations."""

    source_file: SourceFile
    module: ast.Module
    imports: Mapping[str, ImportSpec]


class PythonAstParser(SourceParser[ParsedPythonModule]):
    """Parse inventoried Python source using the standard-library AST."""

    def parse(self, repository: Path, source_file: SourceFile) -> ParsedPythonModule:
        source = (repository / source_file.relative_path).read_text(encoding="utf-8")
        try:
            module = ast.parse(source, filename=source_file.relative_path)
        except SyntaxError as error:
            raise SourceParseError(source_file.relative_path, error.msg) from error
        imports = {
            alias.asname or alias.name: ImportSpec(node.module, alias.name, alias.asname)
            for node in module.body
            if isinstance(node, ast.ImportFrom) and node.module
            for alias in node.names
        }
        return ParsedPythonModule(source_file, module, MappingProxyType(imports))


class PythonControllerObservationExtractor:
    """Translate Python controller AST details into language-neutral observations."""

    def extract(self, parsed: ParsedPythonModule) -> ObservationBatch:
        observations = []
        controllers = [
            node
            for node in parsed.module.body
            if isinstance(node, ast.ClassDef)
            and node.name.endswith("Controller")
            and (node.bases or node.decorator_list)
        ]
        for controller in controllers:
            for kind, nodes in (
                ("controller.base_class", controller.bases),
                ("controller.required_decorator", controller.decorator_list),
            ):
                for node in nodes:
                    name = self._name(node)
                    if name:
                        observations.append(
                            StructuralClassObservation(
                                kind,
                                name,
                                Evidence(parsed.source_file.relative_path, controller.name, name),
                                parsed.imports.get(name),
                            )
                        )
        return ObservationBatch(len(controllers), tuple(observations))

    @staticmethod
    def _name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""


class PythonServiceObservationExtractor:
    """Translate Python service AST details into language-neutral observations."""

    def extract(self, parsed: ParsedPythonModule) -> ObservationBatch:
        observations = []
        services = [
            node
            for node in parsed.module.body
            if isinstance(node, ast.ClassDef)
            and node.name.endswith("Service")
            and (node.bases or node.decorator_list)
        ]
        for service in services:
            for kind, nodes in (
                ("service.base_class", service.bases),
                ("service.required_decorator", service.decorator_list),
            ):
                for node in nodes:
                    name = self._name(node)
                    if name:
                        observations.append(
                            StructuralClassObservation(
                                kind,
                                name,
                                Evidence(parsed.source_file.relative_path, service.name, name),
                                parsed.imports.get(name),
                            )
                        )
            for attribute, (class_name, arguments) in self._dependencies(service).items():
                invocations = tuple(
                    InvocationObservation(method_name, argument_shapes)
                    for method_name, argument_shapes in sorted(self._calls(service, attribute))
                )
                observations.append(
                    ConstructorDependencyObservation(
                        attribute,
                        class_name,
                        Evidence(parsed.source_file.relative_path, service.name, attribute),
                        parsed.imports.get(class_name),
                        arguments,
                        invocations,
                    )
                )
        return ObservationBatch(len(services), tuple(observations))

    @staticmethod
    def _dependencies(service: ast.ClassDef) -> dict[str, tuple[str, tuple[str, ...]]]:
        dependencies: dict[str, tuple[str, tuple[str, ...]]] = {}
        initializer = next(
            (node for node in service.body if isinstance(node, ast.FunctionDef) and node.name == "__init__"),
            None,
        )
        for node in ast.walk(initializer) if initializer else ():
            if not (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
            ):
                continue
            arguments = tuple(PythonServiceObservationExtractor._constructor_argument(item) for item in node.value.args)
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    dependencies[target.attr] = (node.value.func.id, arguments)
        return dependencies

    @staticmethod
    def _calls(service: ast.ClassDef, attribute: str) -> set[tuple[str, tuple[str, ...]]]:
        calls: set[tuple[str, tuple[str, ...]]] = set()
        for node in ast.walk(service):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "self"
                and node.func.value.attr == attribute
            ):
                continue
            calls.add(
                (
                    node.func.attr,
                    tuple(PythonServiceObservationExtractor._invocation_shape(item) for item in node.args),
                )
            )
        return calls

    @staticmethod
    def _constructor_argument(argument: ast.expr) -> str:
        if isinstance(argument, ast.Name) and argument.id == "__name__":
            return "__name__"
        if isinstance(argument, ast.Constant):
            return repr(argument.value)
        return "unsupported"

    @staticmethod
    def _invocation_shape(argument: ast.expr) -> str:
        if isinstance(argument, ast.Constant):
            if isinstance(argument.value, str):
                return "string_literal"
            if isinstance(argument.value, bool):
                return "boolean_literal"
            if isinstance(argument.value, int):
                return "integer_literal"
            if isinstance(argument.value, float):
                return "float_literal"
            if argument.value is None:
                return "none_literal"
        if isinstance(argument, ast.Dict) and not argument.keys:
            return "empty_mapping"
        if isinstance(argument, (ast.List, ast.Tuple)) and not argument.elts:
            return "empty_sequence"
        return "unsupported"

    @staticmethod
    def _name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""