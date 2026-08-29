"""Typed domain contracts for framework intelligence and retrieval."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Mapping


class RuleOrigin(StrEnum):
    DETERMINISTIC_INFERRED = "deterministic_inferred"
    LLM_INFERRED = "llm_inferred"
    HUMAN_APPROVED = "human_approved"
    HUMAN_EDITED = "human_edited"


class RuleStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Evidence:
    source_path: str
    symbol: str
    observation: str
    polarity: str = "support"


@dataclass(frozen=True)
class KnowledgeScope:
    """Complete tenant and framework-version boundary for stored knowledge."""

    customer_id: str
    framework_id: str
    framework_version_id: str
    project_id: str
    module_id: str | None = None

    def __post_init__(self) -> None:
        required = (
            ("customer_id", self.customer_id),
            ("framework_id", self.framework_id),
            ("framework_version_id", self.framework_version_id),
            ("project_id", self.project_id),
        )
        for name, value in required:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.module_id is not None and (
            not isinstance(self.module_id, str) or not self.module_id.strip()
        ):
            raise ValueError("module_id must be None or a non-empty string")

    @property
    def hierarchy(self) -> tuple[str, str, str, str, str | None]:
        return (
            self.customer_id,
            self.framework_id,
            self.framework_version_id,
            self.project_id,
            self.module_id,
        )


@dataclass(frozen=True)
class FrameworkRule:
    kind: str
    expected_value: str
    confidence: float
    support_count: int
    conflict_count: int
    evidence: tuple[Evidence, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)
    origin: RuleOrigin = RuleOrigin.DETERMINISTIC_INFERRED
    status: RuleStatus = RuleStatus.CANDIDATE
    framework_version: str = "1.0"
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scope: KnowledgeScope | None = None


@dataclass(frozen=True)
class ImportSpec:
    module: str
    symbol: str
    alias: str | None = None

    @property
    def local_name(self) -> str:
        return self.alias or self.symbol


@dataclass(frozen=True)
class CodeExample:
    source_path: str
    symbol: str
    snippet: str
    score: int = 0
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceDependency:
    attribute: str
    class_name: str
    import_module: str | None
    methods: tuple[str, ...]
    constructor_arguments: tuple[str, ...]


@dataclass(frozen=True)
class SourceIndexEntry:
    source_path: str
    symbol: str
    snippet: str
    tokens: tuple[str, ...]
    dependencies: tuple[SourceDependency, ...]


@dataclass(frozen=True)
class SourceIndex:
    entries: tuple[SourceIndexEntry, ...]


@dataclass(frozen=True)
class UnresolvedDependencyCandidate:
    source_path: str
    attribute: str
    class_name: str
    import_module: str | None
    methods: tuple[str, ...]
    constructor_arguments: tuple[str, ...]
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class InvocationRequirement:
    """A learned dependency call whose argument shapes are safe to render."""

    method_name: str
    argument_shapes: tuple[str, ...]
    supported: bool


@dataclass(frozen=True)
class DependencyContext:
    attribute: str
    class_name: str | None
    import_module: str | None
    methods: tuple[str, ...]
    constructor_arguments: tuple[str, ...]
    type_pattern: str | None = None
    required: bool = True
    required_invocations: tuple[InvocationRequirement, ...] = ()


@dataclass(frozen=True)
class ArtifactStructureContext:
    """Language-neutral structure and dependencies for one artifact family."""

    artifact_family: str
    base_classes: tuple[str, ...]
    decorators: tuple[str, ...]
    imports: tuple[ImportSpec, ...]
    dependencies: tuple[DependencyContext, ...]


@dataclass(frozen=True, init=False)
class CodingContext:
    """Bounded coding context with a legacy service construction projection."""

    structure: ArtifactStructureContext
    examples: tuple[CodeExample, ...]
    unresolved_dependencies: tuple[UnresolvedDependencyCandidate, ...]

    def __init__(
        self,
        service_base_class: str | None = None,
        service_decorator: str | None = None,
        imports: tuple[ImportSpec, ...] = (),
        dependencies: tuple[DependencyContext, ...] = (),
        examples: tuple[CodeExample, ...] = (),
        unresolved_dependencies: tuple[UnresolvedDependencyCandidate, ...] = (),
        *,
        structure: ArtifactStructureContext | None = None,
    ) -> None:
        if structure is None:
            if service_base_class is None or service_decorator is None:
                raise TypeError("service_base_class and service_decorator are required")
            structure = ArtifactStructureContext(
                artifact_family="service",
                base_classes=(service_base_class,),
                decorators=(service_decorator,),
                imports=imports,
                dependencies=dependencies,
            )
        elif service_base_class is not None or service_decorator is not None or imports or dependencies:
            raise TypeError("structure cannot be combined with legacy service structure arguments")
        object.__setattr__(self, "structure", structure)
        object.__setattr__(self, "examples", examples)
        object.__setattr__(self, "unresolved_dependencies", unresolved_dependencies)

    @property
    def service_base_class(self) -> str:
        return self.structure.base_classes[0]

    @property
    def service_decorator(self) -> str:
        return self.structure.decorators[0]

    @property
    def imports(self) -> tuple[ImportSpec, ...]:
        return self.structure.imports

    @property
    def dependencies(self) -> tuple[DependencyContext, ...]:
        return self.structure.dependencies


@dataclass(frozen=True)
class CommandResult:
    passed: bool
    command: tuple[str, ...]
    output: str
    timed_out: bool = False


@dataclass(frozen=True)
class ValidationFinding:
    rule_kind: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class ValidationReport:
    passed: bool
    findings: tuple[ValidationFinding, ...] = ()
