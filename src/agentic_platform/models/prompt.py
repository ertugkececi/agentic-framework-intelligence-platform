"""Prompt construction for the coding-model gateway."""
from __future__ import annotations

import json

from agentic_platform.domain.models import CodingContext
from agentic_platform.models.gateway import FailureContext, validate_artifact_structure
from agentic_platform.tasks.types import DevelopmentTask, GeneratedChange

_SYSTEM_PROMPT = """You generate repository changes from a bounded coding context.
Return only a JSON object with this exact shape:
{"summary":"short description","files":[{"path":"relative/path","content":"complete file content"}]}.
Do not include Markdown fences, commentary, or fields outside that schema.
Do not assume dependencies or conventions not present in the supplied context."""


def build_coding_messages(task: DevelopmentTask, context: CodingContext) -> list[dict[str, str]]:
    """Build provider-independent Chat Completions messages from typed inputs."""
    validate_artifact_structure(task, context.structure)
    request_context = {
        "task": {
            "artifact_type": task.artifact_type,
            "artifact_name": task.artifact_name,
            "operations": [
                {"name": operation.name, "parameters": [parameter.name for parameter in operation.parameters]}
                for operation in task.operations
            ],
        },
        "coding_context": {
            "artifact_structure": {
                "artifact_family": context.structure.artifact_family,
                "base_classes": list(context.structure.base_classes),
                "decorators": list(context.structure.decorators),
            },
            # Compatibility projection for current service prompt consumers.
            "service_base_class": context.structure.base_classes[0],
            "service_decorator": context.structure.decorators[0],
            "imports": [
                {"module": item.module, "symbol": item.symbol, "alias": item.alias}
                for item in context.structure.imports
            ],
            "dependencies": [
                {
                    "attribute": item.attribute,
                    "class_name": item.class_name,
                    "import_module": item.import_module,
                    "methods": list(item.methods),
                    "constructor_arguments": list(item.constructor_arguments),
                    "type_pattern": item.type_pattern,
                    "required": item.required,
                    "required_invocations": [
                        {
                            "method_name": invocation.method_name,
                            "argument_shapes": list(invocation.argument_shapes),
                            "supported": invocation.supported,
                        }
                        for invocation in item.required_invocations
                    ],
                }
                for item in context.structure.dependencies
            ],
            "examples": [
                {
                    "source_path": item.source_path,
                    "symbol": item.symbol,
                    "snippet": item.snippet,
                    "score": item.score,
                    "reasons": list(item.reasons),
                }
                for item in context.examples
            ],
            "unresolved_dependencies": [
                {
                    "source_path": item.source_path,
                    "attribute": item.attribute,
                    "class_name": item.class_name,
                    "import_module": item.import_module,
                    "methods": list(item.methods),
                    "constructor_arguments": list(item.constructor_arguments),
                    "score": item.score,
                    "reasons": list(item.reasons),
                }
                for item in context.unresolved_dependencies
            ],
        },
    }
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(request_context, ensure_ascii=False, separators=(",", ":"))},
    ]


def build_repair_messages(
    task: DevelopmentTask,
    context: CodingContext,
    previous_change: GeneratedChange,
    failure_context: FailureContext,
) -> list[dict[str, str]]:
    """Build a bounded repair request without relying on provider-specific tools."""
    request_context = json.loads(build_coding_messages(task, context)[1]["content"])
    request_context["repair_request"] = {
        "previous_change": {
            "summary": previous_change.summary,
            "files": [{"path": item.path, "content": item.content} for item in previous_change.files],
        },
        "failure": {
            "stage": failure_context.stage,
            "attempt": failure_context.attempt,
            "command": list(failure_context.command),
            "output": failure_context.output,
        },
    }
    return [
        {"role": "system", "content": f"{_SYSTEM_PROMPT}\nRevise the previous change to address the supplied failure evidence."},
        {"role": "user", "content": json.dumps(request_context, ensure_ascii=False, separators=(",", ":"))},
    ]
