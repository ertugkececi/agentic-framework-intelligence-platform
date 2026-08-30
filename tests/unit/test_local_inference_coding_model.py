from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from agentic_platform.domain.models import CodingContext
from agentic_platform.models.factory import create_coding_model
from agentic_platform.models.local_inference import LocalInferenceCodingModel, LocalInferenceResponseError
from agentic_platform.models.openai_compatible import TransportResponse
from agentic_platform.models.settings import LocalInferenceSettings
from agentic_platform.tasks.types import DevelopmentTask


@dataclass
class RecordingTransport:
    response: TransportResponse
    calls: list[tuple[str, dict[str, str], bytes, float]]

    def post(self, url: str, headers: dict[str, str], body: bytes, timeout: float) -> TransportResponse:
        self.calls.append((url, headers, body, timeout))
        return self.response


def _task() -> DevelopmentTask:
    return DevelopmentTask(artifact_type="service", artifact_name="ExampleService", operations=())


def _context() -> CodingContext:
    return CodingContext(service_base_class="Base", service_decorator="managed")


def _response(content: str) -> TransportResponse:
    return TransportResponse(200, json.dumps({"message": {"role": "assistant", "content": content}, "done": True}).encode())


def test_local_adapter_uses_native_non_streaming_json_contract_without_credentials() -> None:
    transport = RecordingTransport(_response('{"summary":"ok","files":[{"path":"app/example.py","content":"x = 1"}]}'), [])
    settings = LocalInferenceSettings("http://inference.platform.internal:11434", "code-model", timeout_seconds=30, max_tokens=2048)

    model = create_coding_model(settings, transport=transport)

    assert isinstance(model, LocalInferenceCodingModel)
    assert model.generate_change(_task(), _context()).summary == "ok"
    url, headers, raw_body, timeout = transport.calls[0]
    body = json.loads(raw_body)
    assert url == "http://inference.platform.internal:11434/api/chat"
    assert timeout == 30
    assert headers == {"Content-Type": "application/json", "Accept": "application/json"}
    assert body["model"] == "code-model"
    assert body["stream"] is False
    assert body["format"] == "json"
    assert body["options"] == {"temperature": 0, "num_predict": 2048}
    assert body["messages"][0]["role"] == "system"
    assert "ExampleService" in body["messages"][1]["content"]


def test_local_settings_and_response_fail_closed() -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        LocalInferenceSettings("http://inference.platform.internal", "model", max_tokens=0)
    with pytest.raises(ValueError, match="credentials"):
        LocalInferenceSettings("http://user:password@inference.platform.internal", "model")

    model = LocalInferenceCodingModel(
        LocalInferenceSettings("http://inference.platform.internal", "model"),
        RecordingTransport(TransportResponse(200, b'{"done":true}'), []),
    )
    with pytest.raises(LocalInferenceResponseError, match="message.content"):
        model.generate_change(_task(), _context())
