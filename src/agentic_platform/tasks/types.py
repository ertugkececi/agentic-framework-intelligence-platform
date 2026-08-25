"""Typed task and generated-change contracts."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterSpec:
    name: str


@dataclass(frozen=True)
class OperationSpec:
    name: str
    parameters: tuple[ParameterSpec, ...]


@dataclass(frozen=True)
class DevelopmentTask:
    artifact_type: str
    artifact_name: str
    operations: tuple[OperationSpec, ...]


@dataclass(frozen=True)
class FileChange:
    path: str
    content: str


@dataclass(frozen=True)
class GeneratedChange:
    files: tuple[FileChange, ...]
    summary: str
