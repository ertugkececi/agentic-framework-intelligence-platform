from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from agentic_platform.domain.models import CodingContext
from agentic_platform.models.openai_compatible import (
    OpenAICompatibleCodingModel,
    TransportResponse,
)
from agentic_platform.models.settings import OpenAICompatibleSettings
from agentic_platform.security.secrets import SecretReference
from agentic_platform.security.secret_resolution import (
    EgressPolicy,
    SecretResolutionError,
    SecretResolver,
)
from agentic_platform.tasks.types import DevelopmentTask


@dataclass
class RecordingResolver(SecretResolver):
    value: str
    calls: list[SecretReference]

    def resolve(self, reference: SecretReference) -> str:
        self.calls.append(reference)
        return self.value


@dataclass
class RecordingTransport:
    calls: list[tuple[str, dict[str, str], bytes, float]]

    def post(self, url: str, headers: dict[str, str], body: bytes, timeout: float) -> TransportResponse:
        self.calls.append((url, headers, body, timeout))
        content = json.dumps({"summary": "ok", "files": [{"path": "app/a.py", "content": "x = 1"}]})
        return TransportResponse(200, json.dumps({"choices": [{"message": {"content": content}}]}).encode())


def _task() -> DevelopmentTask:
    return DevelopmentTask(artifact_type="service", artifact_name="ExampleService", operations=())


def _context() -> CodingContext:
    return CodingContext(service_base_class="Base", service_decorator="managed")


def test_model_resolves_reference_only_after_exact_endpoint_egress_authorization() -> None:
    reference = SecretReference("vault", "tenants/example/model", "api-key", "1")
    resolver = RecordingResolver("resolved-provider-secret", [])
    transport = RecordingTransport([])
    settings = OpenAICompatibleSettings(
        base_url="https://models.example.internal/v1",
        model="coding-model",
        api_key_reference=reference,
    )
    model = OpenAICompatibleCodingModel(
        settings,
        transport,
        secret_resolver=resolver,
        egress_policy=EgressPolicy(frozenset({"https://models.example.internal"})),
    )

    assert model.generate_change(_task(), _context()).summary == "ok"

    assert resolver.calls == [reference]
    assert transport.calls[0][1]["Authorization"] == "Bearer resolved-provider-secret"
    assert "resolved-provider-secret" not in transport.calls[0][2].decode()


def test_denied_egress_fails_before_secret_resolution_or_transport() -> None:
    reference = SecretReference("vault", "tenants/example/model", "api-key")
    resolver = RecordingResolver("resolved-provider-secret", [])
    transport = RecordingTransport([])
    model = OpenAICompatibleCodingModel(
        OpenAICompatibleSettings(
            base_url="https://public.example.test/v1",
            model="coding-model",
            api_key_reference=reference,
        ),
        transport,
        secret_resolver=resolver,
        egress_policy=EgressPolicy(frozenset({"https://models.example.internal"})),
    )

    with pytest.raises(PermissionError, match="egress denied"):
        model.generate_change(_task(), _context())

    assert resolver.calls == []
    assert transport.calls == []


def test_reference_requires_resolver_and_resolution_rejects_invalid_values() -> None:
    reference = SecretReference("vault", "tenants/example/model", "api-key")
    settings = OpenAICompatibleSettings(
        base_url="https://models.example.internal/v1",
        model="coding-model",
        api_key_reference=reference,
    )
    policy = EgressPolicy(frozenset({"https://models.example.internal"}))

    with pytest.raises(SecretResolutionError, match="resolver"):
        OpenAICompatibleCodingModel(settings, RecordingTransport([]), egress_policy=policy).generate_change(_task(), _context())

    resolver = RecordingResolver(" ", [])
    with pytest.raises(SecretResolutionError, match="non-empty"):
        OpenAICompatibleCodingModel(
            settings, RecordingTransport([]), secret_resolver=resolver, egress_policy=policy,
        ).generate_change(_task(), _context())


def test_egress_policy_rejects_paths_credentials_and_noncanonical_origins() -> None:
    for origin in (
        "https://example.test/path",
        "https://user:pass@example.test",
        "https://example.test/",
        "HTTP://example.test",
    ):
        with pytest.raises(ValueError, match="origin"):
            EgressPolicy(frozenset({origin}))

    policy = EgressPolicy(frozenset({"https://example.test:8443"}))
    policy.require_url("https://example.test:8443/v1/chat/completions")
    with pytest.raises(PermissionError, match="egress denied"):
        policy.require_url("https://example.test/v1/chat/completions")


def test_plaintext_and_reference_credentials_cannot_be_combined() -> None:
    with pytest.raises(ValueError, match="cannot be combined"):
        OpenAICompatibleSettings(
            base_url="https://models.example.internal",
            model="coding-model",
            api_key="legacy-key",
            api_key_reference=SecretReference("vault", "models/coding", "api-key"),
        )


def test_resolver_failure_is_sanitized() -> None:
    class FailingResolver:
        def resolve(self, reference: SecretReference) -> str:
            raise SecretResolutionError("provider leaked resolved-provider-secret")

    reference = SecretReference("vault", "tenants/example/model", "api-key")
    settings = OpenAICompatibleSettings(
        base_url="https://models.example.internal/v1",
        model="coding-model",
        api_key_reference=reference,
    )
    model = OpenAICompatibleCodingModel(
        settings,
        RecordingTransport([]),
        secret_resolver=FailingResolver(),
        egress_policy=EgressPolicy(frozenset({"https://models.example.internal"})),
    )

    with pytest.raises(SecretResolutionError) as failure:
        model.generate_change(_task(), _context())

    assert str(failure.value) == "secret provider resolution failed"
    assert "resolved-provider-secret" not in str(failure.value)
