"""Domain contracts; provider and transport independent."""
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
class FrameworkRule:
    kind: str
    expected_value: str
    confidence: float
    support_count: int
    conflict_count: int
    evidence: tuple[Evidence, ...]
    metadata: Mapping[str, str] = field(default_factory=dict)
    origin: RuleOrigin = RuleOrigin.DETERMINISTIC_INFERRED
    status: RuleStatus = RuleStatus.ACTIVE
    framework_version: str = "1.0"
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ImportSpec:
    module: str
    symbol: str


@dataclass(frozen=True)
class CodeExample:
    source_path: str
    symbol: str
    snippet: str


@dataclass(frozen=True)
class CodingContext:
    service_base_class: str
    service_decorator: str
    imports: tuple[ImportSpec, ...]
    logger_class: str
    logger_attribute: str
    logger_method: str
    examples: tuple[CodeExample, ...]


@dataclass(frozen=True)
class CommandResult:
    passed: bool
    command: tuple[str, ...]
    output: str


@dataclass(frozen=True)
class ValidationFinding:
    rule_kind: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class ValidationReport:
    passed: bool
    findings: tuple[ValidationFinding, ...] = ()
