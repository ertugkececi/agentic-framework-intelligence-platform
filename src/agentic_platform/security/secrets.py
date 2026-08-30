"""Secret-reference contracts and shared output redaction."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]*")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\s*[=:]\s*)([^\s,;]+)",
)
_SECRET_JSON_ASSIGNMENT = re.compile(
    r'(?i)(")([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)("\s*:\s*)(")(?:\\.|[^"\\])*(")',
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[^\s,;]+"),
    re.compile(r"(?i)\bhttps?://[^\s/@:]+:[^\s/@]+@"),
)
_REDACTED = "[REDACTED]"


@dataclass(frozen=True)
class SecretReference:
    """Identifier-only reference to a secret held by an external provider."""

    provider: str
    path: str
    key: str
    version: str | None = None

    def __post_init__(self) -> None:
        for name in ("provider", "key"):
            value = getattr(self, name)
            if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
                raise ValueError(f"{name} must be a lowercase secret identifier")
        if not isinstance(self.path, str) or not self.path or "\\" in self.path:
            raise ValueError("path must be a relative POSIX secret path")
        path = PurePosixPath(self.path)
        if (
            path.is_absolute()
            or str(path) != self.path
            or any(_IDENTIFIER.fullmatch(part) is None for part in path.parts)
        ):
            raise ValueError("path must be a canonical relative POSIX secret path without traversal")
        if self.version is not None and (
            not isinstance(self.version, str) or _IDENTIFIER.fullmatch(self.version) is None
        ):
            raise ValueError("version must be None or a lowercase secret identifier")


class SecretRedactor:
    """Mask registered secret values and common credential-bearing structures."""

    def __init__(self, secret_values: Iterable[str] = ()) -> None:
        values: list[str] = []
        for value in secret_values:
            if not isinstance(value, str):
                raise TypeError("secret values must be strings")
            if len(value) < 4:
                raise ValueError("registered secret values must contain at least 4 characters")
            values.append(value)
        self._secret_values = tuple(sorted(set(values), key=lambda value: (-len(value), value)))

    def redact(self, output: str) -> str:
        if not isinstance(output, str):
            raise TypeError("output must be a string")
        redacted = output
        for value in self._secret_values:
            redacted = redacted.replace(value, _REDACTED)
        redacted = _SECRET_JSON_ASSIGNMENT.sub(
            lambda match: (
                f"{match.group(1)}{match.group(2)}{match.group(3)}"
                f"{match.group(4)}{_REDACTED}{match.group(5)}"
            ),
            redacted,
        )
        redacted = _SECRET_ASSIGNMENT.sub(
            lambda match: f"{match.group(1)}{_REDACTED}", redacted,
        )
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(_REDACTED, redacted)
        return redacted
