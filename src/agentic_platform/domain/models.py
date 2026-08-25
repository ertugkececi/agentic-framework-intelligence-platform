"""Domain contracts; provider and transport independent."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


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
    origin: RuleOrigin = RuleOrigin.DETERMINISTIC_INFERRED
    status: RuleStatus = RuleStatus.ACTIVE
    framework_version: str = "1.0"
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
