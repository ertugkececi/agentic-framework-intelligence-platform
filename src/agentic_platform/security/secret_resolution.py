"""Fail-closed secret resolution and outbound endpoint policy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from agentic_platform.security.secrets import SecretReference


class SecretResolutionError(RuntimeError):
    """A secret reference could not be safely resolved."""


class SecretResolver(Protocol):
    """Provider-neutral boundary implemented by Vault/Kubernetes adapters."""

    def resolve(self, reference: SecretReference) -> str:
        """Resolve one identifier-only reference at the transport boundary."""


@dataclass(frozen=True)
class EgressPolicy:
    """Exact HTTP(S) origins authorized for outbound provider traffic."""

    allowed_origins: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_origins, frozenset):
            raise TypeError("allowed_origins must be a frozenset")
        for origin in self.allowed_origins:
            if not isinstance(origin, str) or self._origin(origin) != origin:
                raise ValueError("allowed egress origin must be a canonical HTTP(S) origin")
        object.__setattr__(self, "allowed_origins", frozenset(self.allowed_origins))

    @classmethod
    def for_url(cls, url: str) -> "EgressPolicy":
        """Create an exact-origin policy for a configured endpoint."""
        return cls(frozenset({cls._origin(url)}))

    def require_url(self, url: str) -> None:
        """Deny URLs whose canonical origin is not explicitly authorized."""
        try:
            origin = self._origin(url)
        except (TypeError, ValueError) as error:
            raise PermissionError("egress denied: invalid endpoint URL") from error
        if origin not in self.allowed_origins:
            raise PermissionError(f"egress denied for origin: {origin}")

    @staticmethod
    def _origin(url: str) -> str:
        if not isinstance(url, str):
            raise TypeError("URL must be a string")
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("URL must have a credential-free HTTP(S) origin")
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError("URL port is invalid") from error
        default_port = 80 if parsed.scheme == "http" else 443
        port_suffix = f":{port}" if port is not None and port != default_port else ""
        return f"{parsed.scheme}://{parsed.hostname}{port_suffix}"


def resolve_secret(reference: SecretReference, resolver: SecretResolver | None) -> str:
    """Resolve and validate a value without placing it in configuration state."""
    if not isinstance(reference, SecretReference):
        raise TypeError("reference must be a SecretReference")
    if resolver is None:
        raise SecretResolutionError("secret reference requires a resolver")
    try:
        value = resolver.resolve(reference)
    except Exception as error:
        raise SecretResolutionError("secret provider resolution failed") from error
    if not isinstance(value, str) or not value.strip():
        raise SecretResolutionError("resolved secret must be a non-empty string")
    if chr(13) in value or chr(10) in value:
        raise SecretResolutionError("resolved secret must not contain line breaks")
    return value
