from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from agentic_platform.domain.models import CodingContext
from agentic_platform.models.anthropic import AnthropicCodingModel, AnthropicResponseError
from agentic_platform.models.factory import create_coding_model
from agentic_platform.models.openai_compatible import TransportResponse
from agentic_platform.models.settings import AnthropicSettings
from agentic_platform.security.secret_resolution import EgressPolicy, SecretResolver
from agentic_platform.security.secrets import SecretReference
from agentic_platform.tasks.types import DevelopmentTask


@dataclass
class RecordingTransport:
    calls: list[tuple[str, dict[str, str], bytes, float]]
    response: TransportResponse

    def post(self, url: str, headers: dict[str, str], body: bytes, timeout: float) -> TransportResponse:
        self.calls.append((url, headers, body, timeout))
        return self.response


@dataclass
class RecordingResolver(SecretResolver):
    calls: list[SecretReference]

    def resolve(self, reference: SecretReference) -> str:
        self.calls.append(reference)
        return "resolved-anthropic-key"


def _settings(reference: SecretReference | None = None) -> AnthropicSettings:
    return AnthropicSettings(base_url="https://anthropic.example.internal/v1", model="coding-model", api_key_reference=reference, max_tokens=2048, timeout_seconds=9)


def _task() -> DevelopmentTask:
    return DevelopmentTask(artifact_type="service", artifact_name="ExampleService", operations=())


def _context() -> CodingContext:
    return CodingContext(service_base_class="Base", service_decorator="managed")


def _response(text: str) -> TransportResponse:
    return TransportResponse(200, json.dumps({"content": [{"type": "text", "text": text}]}).encode())


def test_anthropic_adapter_translates_provider_neutral_prompt_and_response() -> None:
    transport = RecordingTransport([], _response("{\"summary\":\"ok\",\"files\":[{\"path\":\"app/example.py\",\"content\":\"x = 1\"}]}"))
    model = AnthropicCodingModel(_settings(), transport)

    assert model.generate_change(_task(), _context()).summary == "ok"
    url, headers, raw_body, timeout = transport.calls[0]
    body = json.loads(raw_body)
    assert url == "https://anthropic.example.internal/v1/messages"
    assert headers["anthropic-version"] == "2023-06-01"
    assert "x-api-key" not in headers
    assert timeout == 9
    assert body["model"] == "coding-model"
    assert body["max_tokens"] == 2048
    assert body["temperature"] == 0
    assert body["system"]
    assert body["messages"][0]["role"] == "user"
    assert "ExampleService" in body["messages"][0]["content"]


def test_anthropic_adapter_authorizes_egress_before_resolving_secret() -> None:
    reference = SecretReference("vault", "tenants/example/anthropic", "api-key")
    resolver = RecordingResolver([])
    transport = RecordingTransport([], _response("{\"summary\":\"ok\",\"files\":[{\"path\":\"a.py\",\"content\":\"x\"}]}"))
    denied = AnthropicCodingModel(_settings(reference), transport, secret_resolver=resolver, egress_policy=EgressPolicy(frozenset({"https://other.example.internal"})))

    with pytest.raises(PermissionError, match="egress denied"):
        denied.generate_change(_task(), _context())
    assert resolver.calls == []
    assert transport.calls == []

    allowed = AnthropicCodingModel(_settings(reference), transport, secret_resolver=resolver, egress_policy=EgressPolicy(frozenset({"https://anthropic.example.internal"})))
    allowed.generate_change(_task(), _context())
    assert resolver.calls == [reference]
    assert transport.calls[0][1]["x-api-key"] == "resolved-anthropic-key"
    assert b"resolved-anthropic-key" not in transport.calls[0][2]


def test_anthropic_factory_routes_typed_settings_and_rejects_malformed_envelope() -> None:
    transport = RecordingTransport([], _response("not-json"))
    model = create_coding_model(_settings(), transport=transport)

    assert isinstance(model, AnthropicCodingModel)
    with pytest.raises(AnthropicResponseError, match="valid JSON"):
        model.generate_change(_task(), _context())


def test_anthropic_settings_fail_closed_for_invalid_limits_and_mixed_credentials() -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        AnthropicSettings("https://anthropic.example.internal", "model", max_tokens=0)
    with pytest.raises(ValueError, match="cannot be combined"):
        AnthropicSettings("https://anthropic.example.internal", "model", api_key="plaintext", api_key_reference=SecretReference("vault", "models/anthropic", "api-key"))
