from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from agentic_platform.domain.models import (
    CodeExample,
    CodingContext,
    DependencyContext,
    ImportSpec,
    UnresolvedDependencyCandidate,
)
from agentic_platform.models.prompt import build_coding_messages
from agentic_platform.models.factory import create_coding_model
from agentic_platform.models.openai_compatible import (
    ModelHTTPError,
    ModelResponseError,
    ModelTimeoutError,
    OpenAICompatibleCodingModel,
    OpenAICompatibleSettings,
    TransportResponse,
    parse_generated_change,
)
from agentic_platform.orchestration.graph import FailureContext
from agentic_platform.tasks.types import DevelopmentTask, FileChange, GeneratedChange, OperationSpec, ParameterSpec


@dataclass
class MockTransport:
    response: TransportResponse | Exception
    calls: list[tuple[str, dict[str, str], bytes, float]]

    def post(self, url: str, headers: dict[str, str], body: bytes, timeout: float) -> TransportResponse:
        self.calls.append((url, headers, body, timeout))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def task() -> DevelopmentTask:
    return DevelopmentTask(
        artifact_type="service",
        artifact_name="AccountService",
        operations=(OperationSpec("get_account", (ParameterSpec("account_id"),)),),
    )


def context() -> CodingContext:
    return CodingContext(
        service_base_class="BaseService",
        service_decorator="business_service",
        imports=(ImportSpec("app.framework", "BaseService"),),
        dependencies=(DependencyContext("logger", "Logger", "app.logging", (), ("__name__",)),),
        examples=(CodeExample("app/example.py", "ExampleService", "class ExampleService: pass"),),
    )


def settings() -> OpenAICompatibleSettings:
    return OpenAICompatibleSettings(
        base_url="https://models.example.internal/v1",
        model="coding-model",
        api_key="test-key",
        timeout_seconds=12.5,
    )


def test_prompt_includes_unresolved_dependencies_as_constraints() -> None:
    constrained_context = CodingContext(
        service_base_class="BaseService",
        service_decorator="business_service",
        imports=(),
        dependencies=(),
        examples=(),
        unresolved_dependencies=(
            UnresolvedDependencyCandidate(
                source_path="app/example.py",
                attribute="store",
                class_name="CustomerStore",
                import_module="app.store",
                methods=("load",),
                constructor_arguments=(),
                score=9,
                reasons=("observed in task-specific example",),
            ),
        ),
    )

    prompt = json.loads(build_coding_messages(task(), constrained_context)[1]["content"])

    assert prompt["coding_context"]["unresolved_dependencies"][0]["attribute"] == "store"
    assert prompt["coding_context"]["unresolved_dependencies"][0]["reasons"] == ["observed in task-specific example"]


def completion(content: str) -> TransportResponse:
    return TransportResponse(200, json.dumps({"choices": [{"message": {"content": content}}]}).encode())


def test_model_posts_provider_neutral_prompt_and_parses_generated_change() -> None:
    transport = MockTransport(
        completion('{"summary":"Add account service","files":[{"path":"app/account_service.py","content":"class AccountService: pass\\n"}]}'),
        [],
    )

    change = OpenAICompatibleCodingModel(settings(), transport).generate_change(task(), context())

    assert change.summary == "Add account service"
    assert [(item.path, item.content) for item in change.files] == [("app/account_service.py", "class AccountService: pass\n")]
    url, headers, body, timeout = transport.calls[0]
    request = json.loads(body)
    assert url == "https://models.example.internal/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-key"
    assert timeout == 12.5
    assert request["model"] == "coding-model"
    assert request["response_format"] == {"type": "json_object"}
    assert "AccountService" in request["messages"][1]["content"]
    assert "BaseService" in request["messages"][1]["content"]


def test_model_posts_repair_prompt_with_previous_change_and_failure_context() -> None:
    transport = MockTransport(
        completion('{"summary":"Repair account service","files":[{"path":"app/account_service.py","content":"class AccountService: pass\\n"}]}'),
        [],
    )
    previous = GeneratedChange((FileChange("app/account_service.py", "broken"),), "Initial account service")
    failure = FailureContext("build", 1, ("pytest",), "NameError: AccountService")

    change = OpenAICompatibleCodingModel(settings(), transport).repair_change(task(), context(), previous, failure)

    assert change.summary == "Repair account service"
    request = json.loads(transport.calls[0][2])
    repair_request = json.loads(request["messages"][1]["content"])["repair_request"]
    assert repair_request["previous_change"]["summary"] == "Initial account service"
    assert repair_request["previous_change"]["files"] == [{"path": "app/account_service.py", "content": "broken"}]
    assert repair_request["failure"] == {
        "stage": "build",
        "attempt": 1,
        "command": ["pytest"],
        "output": "NameError: AccountService",
    }


def test_model_factory_builds_openai_compatible_adapter_with_injected_transport() -> None:
    transport = MockTransport(completion('{"summary":"ok","files":[{"path":"app/a.py","content":"x = 1"}]}'), [])

    model = create_coding_model(settings(), transport=transport)

    assert model.generate_change(task(), context()).summary == "ok"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ('{"summary":"ok","files":[]}', "at least one file"),
        ('{"summary":"","files":[{"path":"a.py","content":"x"}]}', "summary"),
        ('{"summary":"ok","files":[{"path":"a.py","content":3}]}', "content"),
        ("not json", "valid JSON"),
    ],
)
def test_parser_rejects_invalid_generated_change_payloads(payload: str, message: str) -> None:
    with pytest.raises(ModelResponseError, match=message):
        parse_generated_change(payload)


def test_model_translates_transport_timeout() -> None:
    model = OpenAICompatibleCodingModel(settings(), MockTransport(TimeoutError("slow"), []))

    with pytest.raises(ModelTimeoutError, match="12.5"):
        model.generate_change(task(), context())


def test_model_raises_sanitized_http_error() -> None:
    model = OpenAICompatibleCodingModel(settings(), MockTransport(TransportResponse(429, b'{"error":"rate limited"}'), []))

    with pytest.raises(ModelHTTPError, match="429"):
        model.generate_change(task(), context())


def test_model_rejects_malformed_completion_envelope() -> None:
    model = OpenAICompatibleCodingModel(settings(), MockTransport(TransportResponse(200, b'{"choices": []}'), []))

    with pytest.raises(ModelResponseError, match="choices"):
        model.generate_change(task(), context())
