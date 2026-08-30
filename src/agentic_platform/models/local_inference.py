"""Native local and air-gapped implementation of the coding-model port."""
from __future__ import annotations

import json
import socket
from urllib.error import URLError

from agentic_platform.domain.models import CodingContext
from agentic_platform.models.gateway import CodingModel, CodingModelError, FailureContext
from agentic_platform.models.openai_compatible import (
    HttpTransport,
    ModelHTTPError,
    ModelResponseError,
    ModelTimeoutError,
    ModelTransportError,
    UrllibHttpTransport,
    parse_generated_change,
)
from agentic_platform.models.prompt import build_coding_messages, build_repair_messages
from agentic_platform.models.settings import LocalInferenceSettings
from agentic_platform.security.secret_resolution import EgressPolicy
from agentic_platform.tasks.types import DevelopmentTask, GeneratedChange


class LocalInferenceResponseError(CodingModelError):
    """The local inference response did not satisfy the structured contract."""


class LocalInferenceCodingModel(CodingModel):
    """Generate typed changes using a credential-free native chat API."""

    def __init__(
        self,
        settings: LocalInferenceSettings,
        transport: HttpTransport | None = None,
        *,
        egress_policy: EgressPolicy | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport or UrllibHttpTransport()
        self._egress_policy = egress_policy or EgressPolicy.for_url(settings.base_url)

    def generate_change(self, task: DevelopmentTask, context: CodingContext) -> GeneratedChange:
        return self._request_change(build_coding_messages(task, context))

    def repair_change(
        self,
        task: DevelopmentTask,
        context: CodingContext,
        previous_change: GeneratedChange,
        failure_context: FailureContext,
    ) -> GeneratedChange:
        return self._request_change(build_repair_messages(task, context, previous_change, failure_context))

    def _request_change(self, messages: list[dict[str, str]]) -> GeneratedChange:
        payload = {
            "model": self._settings.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": self._settings.max_tokens},
        }
        endpoint = self._settings.chat_url
        self._egress_policy.require_url(endpoint)
        try:
            response = self._transport.post(
                endpoint,
                {"Content-Type": "application/json", "Accept": "application/json"},
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                self._settings.timeout_seconds,
            )
        except (TimeoutError, socket.timeout) as error:
            raise ModelTimeoutError(
                f"model request timed out after {self._settings.timeout_seconds:g} seconds"
            ) from error
        except URLError as error:
            raise ModelTransportError("unable to reach coding model endpoint") from error
        except OSError as error:
            raise ModelTransportError("coding model transport failed") from error
        if not 200 <= response.status_code < 300:
            raise ModelHTTPError(f"coding model endpoint returned HTTP {response.status_code}")
        try:
            return parse_generated_change(_message_content(response.body))
        except ModelResponseError as error:
            raise LocalInferenceResponseError(str(error)) from error


def _message_content(body: bytes) -> str:
    try:
        envelope = json.loads(body.decode("utf-8"))
        content = envelope["message"]["content"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise LocalInferenceResponseError("model response must contain message.content") from error
    if not isinstance(content, str):
        raise LocalInferenceResponseError("model response message.content must be a string")
    return content
