"""Composition root helpers for coding-model adapters."""
from __future__ import annotations

from agentic_platform.models.gateway import CodingModel
from agentic_platform.models.openai_compatible import HttpTransport, OpenAICompatibleCodingModel
from agentic_platform.models.settings import OpenAICompatibleSettings


def create_coding_model(
    settings: OpenAICompatibleSettings,
    *,
    transport: HttpTransport | None = None,
) -> CodingModel:
    """Build the configured provider-neutral coding-model port implementation."""
    return OpenAICompatibleCodingModel(settings, transport=transport)
