"""Ports shared by local and production structured rule stores."""
from __future__ import annotations

from typing import Protocol

from agentic_platform.domain.models import FrameworkRule, KnowledgeScope


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

    def close(self) -> None: ...
