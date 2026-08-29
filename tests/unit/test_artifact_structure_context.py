from dataclasses import FrozenInstanceError
import json

import pytest

from agentic_platform.domain.models import (
    ArtifactStructureContext,
    CodingContext,
    DependencyContext,
    FrameworkRule,
    ImportSpec,
    RuleStatus,
)
from agentic_platform.retrieval.context import retrieve_artifact_structure
from agentic_platform.models.prompt import build_coding_messages
from agentic_platform.models.gateway import CodingModelError, DeterministicPythonCodingModel
from agentic_platform.tasks.types import DevelopmentTask


def test_coding_context_carries_immutable_generic_artifact_structure() -> None:
    structure = ArtifactStructureContext(
        artifact_family="service",
        base_classes=("BaseArtifact",),
        decorators=("register_artifact",),
        imports=(ImportSpec("app.framework", "BaseArtifact"),),
        dependencies=(DependencyContext("log", "Logger", "app.logging", (), ()),),
    )

    context = CodingContext(structure=structure, examples=())

    assert context.structure is structure
    assert context.structure.artifact_family == "service"
    assert context.structure.base_classes == ("BaseArtifact",)
    assert context.structure.decorators == ("register_artifact",)
    with pytest.raises(FrozenInstanceError):
        context.structure.artifact_family = "other"  # type: ignore[misc]


def test_legacy_coding_context_positional_and_keyword_construction_is_preserved() -> None:
    positional = CodingContext("BaseArtifact", "registered", (), (), ())
    keyword = CodingContext(
        service_base_class="BaseArtifact",
        service_decorator="registered",
        imports=(),
        dependencies=(),
        examples=(),
    )

    for context in (positional, keyword):
        assert context.structure.artifact_family == "service"
        assert context.service_base_class == "BaseArtifact"
        assert context.service_decorator == "registered"
        assert context.imports == ()
        assert context.dependencies == ()


def test_retrieval_builds_structure_from_artifact_family_rules() -> None:
    active = RuleStatus.ACTIVE
    rules = [
        FrameworkRule(
            "service.base_class",
            "BaseArtifact",
            1.0,
            3,
            0,
            (),
            metadata={"import_module": "app.framework", "import_symbol": "BaseArtifact"},
            status=active,
        ),
        FrameworkRule(
            "service.required_decorator",
            "registered",
            1.0,
            3,
            0,
            (),
            metadata={"import_module": "app.framework", "import_symbol": "registered"},
            status=active,
        ),
    ]

    structure = retrieve_artifact_structure(rules, "service")

    assert structure.artifact_family == "service"
    assert structure.base_classes == ("BaseArtifact",)
    assert structure.decorators == ("registered",)
    assert structure.imports == (
        ImportSpec("app.framework", "BaseArtifact"),
        ImportSpec("app.framework", "registered"),
    )


def test_prompt_serializes_generic_artifact_structure_with_legacy_projection() -> None:
    context = CodingContext(
        structure=ArtifactStructureContext(
            artifact_family="service",
            base_classes=("BaseArtifact",),
            decorators=("registered",),
            imports=(),
            dependencies=(),
        ),
        examples=(),
    )

    payload = json.loads(
        build_coding_messages(DevelopmentTask("service", "ExampleArtifact", ()), context)[1]["content"]
    )["coding_context"]

    assert payload["artifact_structure"] == {
        "artifact_family": "service",
        "base_classes": ["BaseArtifact"],
        "decorators": ["registered"],
    }
    assert payload["service_base_class"] == "BaseArtifact"
    assert payload["service_decorator"] == "registered"


def test_prompt_rejects_task_for_different_artifact_family() -> None:
    context = CodingContext(
        structure=ArtifactStructureContext("service", ("BaseArtifact",), ("registered",), (), ()),
        examples=(),
    )

    with pytest.raises(CodingModelError, match="artifact family"):
        build_coding_messages(DevelopmentTask("different", "ExampleArtifact", ()), context)


def test_deterministic_generation_rejects_task_for_different_artifact_family() -> None:
    context = CodingContext(
        structure=ArtifactStructureContext(
            artifact_family="service",
            base_classes=("BaseArtifact",),
            decorators=("registered",),
            imports=(),
            dependencies=(),
        ),
        examples=(),
    )

    with pytest.raises(CodingModelError, match="artifact family"):
        DeterministicPythonCodingModel().generate_change(
            DevelopmentTask("different", "ExampleArtifact", ()),
            context,
        )


def test_incomplete_artifact_structure_fails_closed_for_prompt_and_generation() -> None:
    context = CodingContext(
        structure=ArtifactStructureContext("service", (), (), (), ()),
        examples=(),
    )
    task = DevelopmentTask("service", "ExampleArtifact", ())

    for consumer in (
        lambda: build_coding_messages(task, context),
        lambda: DeterministicPythonCodingModel().generate_change(task, context),
    ):
        with pytest.raises(CodingModelError, match="base classes and decorators"):
            consumer()


def test_deterministic_generation_renders_generic_structure_without_legacy_properties() -> None:
    context = CodingContext(
        structure=ArtifactStructureContext(
            artifact_family="service",
            base_classes=("BaseArtifact",),
            decorators=("registered",),
            imports=(ImportSpec("app.framework", "BaseArtifact"),),
            dependencies=(),
        ),
        examples=(),
    )

    change = DeterministicPythonCodingModel().generate_change(
        DevelopmentTask("service", "ExampleArtifact", ()),
        context,
    )

    assert change.files[0].content == (
        "from app.framework import BaseArtifact\n\n"
        "@registered\n"
        "class ExampleArtifact(BaseArtifact):\n"
        "    def __init__(self) -> None:\n"
        "        pass\n\n"
        "    pass"
    )
