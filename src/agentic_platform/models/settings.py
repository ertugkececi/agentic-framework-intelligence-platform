"""Configuration for provider-neutral OpenAI-compatible coding endpoints."""
from __future__ import annotations

from dataclasses import dataclass
from os import environ
from typing import Mapping
from urllib.parse import urlparse

from agentic_platform.security.secrets import SecretReference


@dataclass(frozen=True)
class OpenAICompatibleSettings:
    """Connection settings for a Chat Completions-compatible endpoint.

    Environment variables are deliberately capability-oriented rather than named
    after a model vendor, so local and hosted compatible endpoints share one
    adapter: ``CODING_MODEL_BASE_URL``, ``CODING_MODEL_NAME``, optional
    ``CODING_MODEL_API_KEY``, and optional ``CODING_MODEL_TIMEOUT_SECONDS``.
    """

    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: float = 60.0
    api_key_reference: SecretReference | None = None

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if not self.model.strip():
            raise ValueError("model must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self.api_key_reference is not None and not isinstance(self.api_key_reference, SecretReference):
            raise TypeError("api_key_reference must be a SecretReference")
        if self.api_key and self.api_key_reference is not None:
            raise ValueError("api_key and api_key_reference cannot be combined")

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    @classmethod
    def from_environment(cls, values: Mapping[str, str] | None = None) -> "OpenAICompatibleSettings":
        source = environ if values is None else values
        base_url = source.get("CODING_MODEL_BASE_URL", "").strip()
        model = source.get("CODING_MODEL_NAME", "").strip()
        if not base_url:
            raise ValueError("CODING_MODEL_BASE_URL is required")
        if not model:
            raise ValueError("CODING_MODEL_NAME is required")
        timeout_text = source.get("CODING_MODEL_TIMEOUT_SECONDS", "60")
        try:
            timeout_seconds = float(timeout_text)
        except ValueError as error:
            raise ValueError("CODING_MODEL_TIMEOUT_SECONDS must be a number") from error
        api_key = source.get("CODING_MODEL_API_KEY") or None
        return cls(base_url=base_url, model=model, api_key=api_key, timeout_seconds=timeout_seconds)


@dataclass(frozen=True)
class AnthropicSettings:
    """Connection settings for the native Anthropic Messages API."""

    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: float = 60.0
    api_key_reference: SecretReference | None = None
    max_tokens: int = 4096
    api_version: str = "2023-06-01"

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if not self.model.strip():
            raise ValueError("model must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if isinstance(self.max_tokens, bool) or not isinstance(self.max_tokens, int) or self.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        if not self.api_version.strip():
            raise ValueError("api_version must not be empty")
        if self.api_key_reference is not None and not isinstance(self.api_key_reference, SecretReference):
            raise TypeError("api_key_reference must be a SecretReference")
        if self.api_key and self.api_key_reference is not None:
            raise ValueError("api_key and api_key_reference cannot be combined")

    @property
    def messages_url(self) -> str:
        return self.base_url.rstrip("/") + "/messages"


@dataclass(frozen=True)
class LocalInferenceSettings:
    """Connection settings for an on-premise native chat endpoint.

    This credential-free contract targets local or air-gapped inference servers
    exposing the non-streaming /api/chat JSON API.
    """

    base_url: str
    model: str
    timeout_seconds: float = 60.0
    max_tokens: int = 4096

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("base_url must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain a query or fragment")
        if not self.model.strip():
            raise ValueError("model must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if isinstance(self.max_tokens, bool) or not isinstance(self.max_tokens, int) or self.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")

    @property
    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + "/api/chat"
