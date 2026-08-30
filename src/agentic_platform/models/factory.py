"""Composition root helpers for coding-model adapters."""
from __future__ import annotations

from agentic_platform.models.anthropic import AnthropicCodingModel
from agentic_platform.models.gateway import CodingModel
from agentic_platform.models.openai_compatible import HttpTransport, OpenAICompatibleCodingModel
from agentic_platform.models.settings import AnthropicSettings, OpenAICompatibleSettings
from agentic_platform.security.secret_resolution import EgressPolicy, SecretResolver


def create_coding_model(
    settings: OpenAICompatibleSettings | AnthropicSettings,
    *,
    transport: HttpTransport | None = None,
    secret_resolver: SecretResolver | None = None,
    egress_policy: EgressPolicy | None = None,
) -> CodingModel:
    """Build the configured provider-neutral coding-model port implementation."""
    adapter = AnthropicCodingModel if isinstance(settings, AnthropicSettings) else OpenAICompatibleCodingModel
    return adapter(
        settings,
        transport=transport,
        secret_resolver=secret_resolver,
        egress_policy=egress_policy,
    )
