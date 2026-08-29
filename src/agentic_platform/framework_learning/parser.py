"""Typed source parser port for repository learning adapters."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypeVar

from agentic_platform.framework_learning.inventory import SourceFile


ParsedSourceT_co = TypeVar("ParsedSourceT_co", covariant=True)


class SourceParseError(ValueError):
    """An inventoried source file could not be parsed."""

    def __init__(self, relative_path: str, detail: str) -> None:
        self.relative_path = relative_path
        super().__init__(f"could not parse {relative_path}: {detail}")


class SourceParser(Protocol[ParsedSourceT_co]):
    """Parse an inventoried source file into a language-specific model."""

    def parse(self, repository: Path, source_file: SourceFile) -> ParsedSourceT_co:
        """Parse one source file from the repository."""
        ...
