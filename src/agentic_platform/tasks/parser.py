"""Deterministic grammar for the initial development-request PoC."""
from __future__ import annotations

import re

from agentic_platform.tasks.types import DevelopmentTask, OperationSpec, ParameterSpec


class TaskParseError(ValueError):
    """Raised when a request does not satisfy the supported task grammar."""


TASK_PATTERN = re.compile(
    r"^Create (?P<artifact>[A-Z][A-Za-z0-9]*Service)"
    r"(?: with method (?P<method>[a-z][A-Za-z0-9_]*)\((?P<parameters>[^)]*)\))?$"
)


def parse_development_task(request: str) -> DevelopmentTask:
    """Parse a bounded service creation request into a typed task."""
    match = TASK_PATTERN.fullmatch(request.strip())
    if match is None:
        raise TaskParseError("Expected: Create <Name>Service [with method name(parameters)]")

    method_name = match.group("method")
    parameters = _parse_parameters(match.group("parameters")) if method_name else ()
    operations = (OperationSpec(method_name, parameters),) if method_name else ()
    return DevelopmentTask("service", match.group("artifact"), operations)


def _parse_parameters(raw_parameters: str | None) -> tuple[ParameterSpec, ...]:
    if not raw_parameters:
        return ()
    return tuple(ParameterSpec(name.strip()) for name in raw_parameters.split(",") if name.strip())
