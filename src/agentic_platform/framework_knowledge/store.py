"""Ports shared by local and production structured rule stores."""
from __future__ import annotations

from typing import Protocol

from agentic_platform.domain.models import FrameworkRule, KnowledgeScope, RuleReview


class RuleKnowledgeStore(Protocol):
    """Persistence boundary consumed by rule retrieval and learning services."""

    def replace_rules(
        self,
        rules: list[FrameworkRule],
        repository_identity: str | None = None,
        *,
        scope: KnowledgeScope | None = None,
    ) -> None: ...

    def active_rules_for(
        self,
        prefix: str,
        *,
        scope: KnowledgeScope | None = None,
    ) -> list[FrameworkRule]: ...

    def append_rule_review(self, review: RuleReview) -> None: ...

    def rule_review_history(
        self,
        rule_kind: str,
        expected_value: str,
        *,
        scope: KnowledgeScope,
    ) -> list[RuleReview]: ...

    def close(self) -> None: ...
