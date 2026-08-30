"""Native Anthropic Messages implementation of the coding-model port."""
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
from agentic_platform.models.settings import AnthropicSettings
from agentic_platform.security.secret_resolution import EgressPolicy, SecretResolver, resolve_secret
from agentic_platform.tasks.types import DevelopmentTask, GeneratedChange


class AnthropicResponseError(CodingModelError):
    """The Messages response did not satisfy the structured contract."""


class AnthropicCodingModel(CodingModel):
    """Generate typed changes through the native Anthropic Messages API."""

    def __init__(
        self,
        settings: AnthropicSettings,
        transport: HttpTransport | None = None,
        *,
        secret_resolver: SecretResolver | None = None,
        egress_policy: EgressPolicy | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport or UrllibHttpTransport()
        self._secret_resolver = secret_resolver
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
        system = "\n\n".join(item["content"] for item in messages if item["role"] == "system")
        conversational = [item for item in messages if item["role"] != "system"]
        payload = {
            "model": self._settings.model,
            "max_tokens": self._settings.max_tokens,
            "temperature": 0,
            "system": system,
            "messages": conversational,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "anthropic-version": self._settings.api_version,
        }
        endpoint = self._settings.messages_url
        self._egress_policy.require_url(endpoint)
        api_key = self._settings.api_key
        if self._settings.api_key_reference is not None:
            api_key = resolve_secret(self._settings.api_key_reference, self._secret_resolver)
        if api_key:
            headers["x-api-key"] = api_key
        try:
            response = self._transport.post(
                endpoint,
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
        try:
            return parse_generated_change(_message_text(response.body))
        except ModelResponseError as error:
            raise AnthropicResponseError(str(error)) from error


def _message_text(body: bytes) -> str:
    try:
        envelope = json.loads(body.decode("utf-8"))
        blocks = envelope["content"]
        text = next(block["text"] for block in blocks if block.get("type") == "text")
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, StopIteration, TypeError) as error:
        raise AnthropicResponseError("model response must contain a text content block") from error
    if not isinstance(text, str):
        raise AnthropicResponseError("model response text content must be a string")
    return text
