"""OpenAI Chat Completions-compatible implementation of the coding-model port."""
from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agentic_platform.domain.models import CodingContext
from agentic_platform.models.gateway import CodingModel
from agentic_platform.models.prompt import build_coding_messages, build_repair_messages
from agentic_platform.models.settings import OpenAICompatibleSettings
from agentic_platform.tasks.types import DevelopmentTask, FileChange, GeneratedChange


class CodingModelError(RuntimeError):
    """Base error raised by the external coding-model adapter."""


class ModelTimeoutError(CodingModelError):
    """The model endpoint did not respond before the configured timeout."""


class ModelHTTPError(CodingModelError):
    """The model endpoint returned a non-success HTTP status."""


class ModelTransportError(CodingModelError):
    """The adapter could not reach the configured model endpoint."""


class ModelResponseError(CodingModelError):
    """The endpoint response did not satisfy the expected structured contract."""


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    body: bytes


class HttpTransport(Protocol):
    """Minimal synchronous transport seam for testing and alternate HTTP stacks."""

    def post(self, url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> TransportResponse: ...


class UrllibHttpTransport:
    """Standard-library HTTP transport; no provider SDK is required."""

    def post(self, url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> TransportResponse:
        request = Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                return TransportResponse(response.status, response.read())
        except HTTPError as error:
            return TransportResponse(error.code, error.read())


def parse_generated_change(content: str) -> GeneratedChange:
    """Validate the model's JSON output before allowing it into the domain."""
    try:
        document = json.loads(content)
    except (TypeError, json.JSONDecodeError) as error:
        raise ModelResponseError("model response must be valid JSON") from error
    if not isinstance(document, dict):
        raise ModelResponseError("model response must be a JSON object")

    summary = document.get("summary")
    files = document.get("files")
    if not isinstance(summary, str) or not summary.strip():
        raise ModelResponseError("model response summary must be a non-empty string")
    if not isinstance(files, list) or not files:
        raise ModelResponseError("model response files must contain at least one file")

    parsed_files: list[FileChange] = []
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise ModelResponseError(f"model response files[{index}] must be an object")
        path = item.get("path")
        file_content = item.get("content")
        if not isinstance(path, str) or not path.strip():
            raise ModelResponseError(f"model response files[{index}].path must be a non-empty string")
        if not isinstance(file_content, str):
            raise ModelResponseError(f"model response files[{index}].content must be a string")
        parsed_files.append(FileChange(path=path, content=file_content))
    return GeneratedChange(files=tuple(parsed_files), summary=summary)


class OpenAICompatibleCodingModel(CodingModel):
    """Generate typed changes through any OpenAI Chat Completions-compatible API."""

    def __init__(self, settings: OpenAICompatibleSettings, transport: HttpTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport or UrllibHttpTransport()

    def generate_change(self, task: DevelopmentTask, context: CodingContext) -> GeneratedChange:
        return self._request_change(build_coding_messages(task, context))

    def repair_change(
        self,
        task: DevelopmentTask,
        context: CodingContext,
        previous_change: GeneratedChange,
        failure_context: object,
    ) -> GeneratedChange:
        return self._request_change(build_repair_messages(task, context, previous_change, failure_context))

    def _request_change(self, messages: list[dict[str, str]]) -> GeneratedChange:
        payload = {
            "model": self._settings.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key}"
        try:
            response = self._transport.post(
                self._settings.chat_completions_url,
                headers,
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                self._settings.timeout_seconds,
            )
        except (TimeoutError, socket.timeout) as error:
            raise ModelTimeoutError(f"model request timed out after {self._settings.timeout_seconds:g} seconds") from error
        except URLError as error:
            raise ModelTransportError("unable to reach coding model endpoint") from error
        except OSError as error:
            raise ModelTransportError("coding model transport failed") from error

        if not 200 <= response.status_code < 300:
            raise ModelHTTPError(f"coding model endpoint returned HTTP {response.status_code}")
        return parse_generated_change(_completion_content(response.body))


def _completion_content(body: bytes) -> str:
    try:
        envelope = json.loads(body.decode("utf-8"))
        choices = envelope["choices"]
        content = choices[0]["message"]["content"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        raise ModelResponseError("model response must contain choices[0].message.content") from error
    if not isinstance(content, str):
        raise ModelResponseError("model response choices[0].message.content must be a string")
    return content
