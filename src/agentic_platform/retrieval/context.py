"""Rule selection and deterministic task-aware coding-context assembly."""
from __future__ import annotations

import ast
from fnmatch import fnmatchcase
import re
from pathlib import Path

from agentic_platform.domain.models import (
    ArtifactStructureContext,
    CodeExample,
    CodingContext,
    DependencyContext,
    FrameworkRule,
    ImportSpec,
    InvocationRequirement,
    KnowledgeScope,
    SourceDependency,
    SourceIndex,
    SourceIndexEntry,
    UnresolvedDependencyCandidate,
)
from agentic_platform.tasks.types import DevelopmentTask


class AmbiguousFrameworkRuleError(ValueError):
    pass


class UnsupportedInvocationRequirementError(ValueError):
    """Raised when active learned dependency behavior cannot be rendered safely."""

    pass


_TOKEN_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_NON_ALPHANUMERIC = re.compile(r"[^A-Za-z0-9]+")


def tokenize_identifier(value: str) -> tuple[str, ...]:
    """Split arbitrary camel/snake/kebab identifiers without domain vocabulary."""
    normalized = _TOKEN_BOUNDARY.sub(" ", value)
    normalized = _NON_ALPHANUMERIC.sub(" ", normalized)
    return tuple(token.lower() for token in normalized.split() if token)


def select_rule(rules: list[FrameworkRule], kind: str) -> FrameworkRule:
    candidates = [rule for rule in rules if rule.kind == kind]
    if not candidates:
        raise ValueError(f"Missing active rule: {kind}")
    ranked = sorted(
        candidates,
        key=lambda rule: (rule.confidence, rule.support_count, -rule.conflict_count),
        reverse=True,
    )
    if len(ranked) > 1 and _rule_rank(ranked[0]) == _rule_rank(ranked[1]):
        raise AmbiguousFrameworkRuleError(kind)
    return ranked[0]


def retrieve_artifact_structure(
    rules: list[FrameworkRule],
    artifact_family: str,
) -> ArtifactStructureContext:
    """Select required structural rules for an explicit artifact family."""
    base = select_rule(rules, f"{artifact_family}.base_class")
    decorator = select_rule(rules, f"{artifact_family}.required_decorator")
    imports = (
        ImportSpec(
            base.metadata["import_module"],
            base.metadata.get("import_symbol", base.expected_value),
            base.metadata.get("import_alias"),
        ),
        ImportSpec(
            decorator.metadata["import_module"],
            decorator.metadata.get("import_symbol", decorator.expected_value),
            decorator.metadata.get("import_alias"),
        ),
    )
    return ArtifactStructureContext(
        artifact_family=artifact_family,
        base_classes=(base.expected_value,),
        decorators=(decorator.expected_value,),
        imports=imports,
        dependencies=(),
    )


def build_source_index(repository: Path) -> SourceIndex:
    """Create a stable structural source index for framework-shaped classes."""
    entries: list[SourceIndexEntry] = []
    for path in sorted(repository.rglob("*.py")):
        if "tests" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = _imports(tree)
        relative = path.relative_to(repository).as_posix()
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or not (node.bases or node.decorator_list):
                continue
            dependencies = _source_dependencies(node, imports)
            identity = (relative, node.name)
            entries.append(
                SourceIndexEntry(
                    relative,
                    node.name,
                    ast.get_source_segment(source, node) or "",
                    tuple(token for value in identity for token in tokenize_identifier(value)),
                    dependencies,
                )
            )
    return SourceIndex(tuple(entries))


def retrieve_controller_context(
    store,
    repository: Path,
    task: DevelopmentTask | None = None,
    *,
    scope: KnowledgeScope | None = None,
):
    """Retrieve controller coding context mirroring the service path."""
    rules = store.active_rules_for("controller", scope=scope)
    structure = retrieve_artifact_structure(rules, "controller")
    imports = list(structure.imports)

    index = build_source_index(repository)
    examples = _rank_examples(index, task)
    return rules, CodingContext(
        structure=ArtifactStructureContext(
            artifact_family=structure.artifact_family,
            base_classes=structure.base_classes,
            decorators=structure.decorators,
            imports=tuple(imports),
            dependencies=(),
        ),
        examples=examples,
        unresolved_dependencies=(),
    )


def retrieve_service_context(
    store,
    repository: Path,
    task: DevelopmentTask | None = None,
    *,
    scope: KnowledgeScope | None = None,
):
    rules = (
        store.active_rules_for("service", scope=scope)
        + store.active_rules_for("dependency", scope=scope)
    )
    structure = retrieve_artifact_structure(rules, "service")
    imports = list(structure.imports)
    dependencies = []
    for rule in (item for item in rules if item.kind == "dependency.constructor"):
        types = rule.metadata["concrete_types"]
        modules = rule.metadata["import_modules"]
        concrete = types[0] if len(types) == 1 else None
        module = modules[0] if len(modules) == 1 else None
        import_metadata = rule.metadata.get("concrete_imports", {}).get(concrete, {}) if concrete else {}
        required_invocations = tuple(
            InvocationRequirement(
                item["method_name"],
                tuple(item["argument_shapes"]),
                bool(item["supported"]),
            )
            for item in rule.metadata.get("required_invocations", [])
        )
        if concrete and any(not item.supported for item in required_invocations):
            raise UnsupportedInvocationRequirementError(rule.expected_value)
        dependencies.append(
            DependencyContext(
                rule.expected_value,
                concrete,
                module,
                tuple(rule.metadata["usage_methods"]),
                tuple(rule.metadata["constructor_arguments"]),
                rule.metadata.get("type_pattern"),
                required_invocations=required_invocations if concrete else (),
            )
        )
        if concrete and module:
            imports.append(
                ImportSpec(
                    module,
                    import_metadata.get("symbol", concrete),
                    import_metadata.get("alias"),
                )
            )

    index = build_source_index(repository)
    examples = _rank_examples(index, task)
    resolved_attributes = {item.attribute for item in dependencies if item.class_name is not None}
    type_patterns = {
        item.attribute: item.type_pattern
        for item in dependencies
        if item.class_name is None and item.type_pattern is not None
    }
    unresolved = _unresolved_candidates(index, task, resolved_attributes, type_patterns)
    return rules, CodingContext(
        structure=ArtifactStructureContext(
            artifact_family=structure.artifact_family,
            base_classes=structure.base_classes,
            decorators=structure.decorators,
            imports=tuple(imports),
            dependencies=tuple(dependencies),
        ),
        examples=examples,
        unresolved_dependencies=unresolved,
    )


def _rank_examples(index: SourceIndex, task: DevelopmentTask | None) -> tuple[CodeExample, ...]:
    task_tokens = _task_tokens(task)
    ranked = []
    for entry in index.entries:
        score, reasons = _score(entry.tokens, task_tokens)
        ranked.append((score, reasons, entry))
    ranked.sort(key=lambda item: (-item[0], item[2].source_path, item[2].symbol))
    return tuple(
        CodeExample(entry.source_path, entry.symbol, entry.snippet, score, reasons)
        for score, reasons, entry in ranked[:6]
    )


def _unresolved_candidates(
    index: SourceIndex,
    task: DevelopmentTask | None,
    resolved_attributes: set[str],
    type_patterns: dict[str, str],
) -> tuple[UnresolvedDependencyCandidate, ...]:
    if task is None:
        return ()
    task_tokens = _task_tokens(task)
    ranked = [( *_score(entry.tokens, task_tokens), entry) for entry in index.entries]
    highest_score = max((score for score, _, _ in ranked), default=0)
    if highest_score == 0:
        return ()
    candidates = []
    for score, reasons, entry in ranked:
        if score != highest_score:
            continue
        for dependency in entry.dependencies:
            if dependency.attribute not in resolved_attributes:
                pattern = type_patterns.get(dependency.attribute)
                if pattern is not None and not fnmatchcase(dependency.class_name, pattern):
                    continue
                candidate_reasons = reasons
                if pattern is not None:
                    candidate_reasons = (*reasons, f"matched type pattern: {pattern}")
                candidates.append(
                    UnresolvedDependencyCandidate(
                        entry.source_path,
                        dependency.attribute,
                        dependency.class_name,
                        dependency.import_module,
                        dependency.methods,
                        dependency.constructor_arguments,
                        score,
                        candidate_reasons,
                    )
                )
    return tuple(sorted(candidates, key=lambda item: (item.source_path, item.attribute, item.class_name)))


def _task_tokens(task: DevelopmentTask | None) -> tuple[str, ...]:
    if task is None:
        return ()
    values = [task.artifact_name]
    for operation in task.operations:
        values.append(operation.name)
        values.extend(parameter.name for parameter in operation.parameters)
    return tuple(token for value in values for token in tokenize_identifier(value))


def _score(source_tokens: tuple[str, ...], task_tokens: tuple[str, ...]) -> tuple[int, tuple[str, ...]]:
    source_vocabulary = set(source_tokens)
    matched = tuple(sorted(set(task_tokens).intersection(source_vocabulary)))
    return 10 * len(matched), tuple(f"matched task token: {token}" for token in matched)


def _source_dependencies(service: ast.ClassDef, imports: dict[str, str]) -> tuple[SourceDependency, ...]:
    initializer = next((node for node in service.body if isinstance(node, ast.FunctionDef) and node.name == "__init__"), None)
    if initializer is None:
        return ()
    dependencies = []
    for node in ast.walk(initializer):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)):
            continue
        arguments = tuple(_argument_value(argument) for argument in node.value.args)
        for target in node.targets:
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                dependencies.append(
                    SourceDependency(
                        target.attr,
                        node.value.func.id,
                        imports.get(node.value.func.id),
                        tuple(sorted(_calls(service, target.attr))),
                        arguments,
                    )
                )
    return tuple(sorted(dependencies, key=lambda item: item.attribute))


def _calls(service: ast.ClassDef, attribute: str) -> set[str]:
    return {
        node.func.attr
        for node in ast.walk(service)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "self"
        and node.func.value.attr == attribute
    }


def _argument_value(argument: ast.expr) -> str:
    if isinstance(argument, ast.Name) and argument.id == "__name__":
        return "__name__"
    if isinstance(argument, ast.Constant):
        return repr(argument.value)
    return "unsupported"


def _imports(tree: ast.Module) -> dict[str, str]:
    return {
        alias.asname or alias.name: node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
    }


def _rule_rank(rule: FrameworkRule) -> tuple[float, int, int]:
    return rule.confidence, rule.support_count, rule.conflict_count
