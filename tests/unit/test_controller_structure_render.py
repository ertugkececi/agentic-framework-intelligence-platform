from __future__ import annotations

from agentic_platform.domain.models import ArtifactStructureContext, CodingContext, ImportSpec
from agentic_platform.models.gateway import DeterministicPythonCodingModel
from agentic_platform.tasks.types import DevelopmentTask


def test_generic_structure_render_handles_service() -> None:
    context = CodingContext(
        structure=ArtifactStructureContext(
            artifact_family="service",
            base_classes=("BaseService",),
            decorators=("business_service",),
            imports=(
                ImportSpec("app.framework", "BaseService"),
                ImportSpec("app.framework", "business_service"),
            ),
            dependencies=(),
        ),
        examples=(),
    )

    change = DeterministicPythonCodingModel().generate_change(
        DevelopmentTask("service", "GeneratedService", ()),
        context,
    )

    assert change.files[0].content == (
        "from app.framework import BaseService, business_service\n\n"
        "@business_service\n"
        "class GeneratedService(BaseService):\n"
        "    def __init__(self) -> None:\n"
        "        pass\n\n"
        "    pass"
    )


def test_generic_structure_render_handles_controller() -> None:
    context = CodingContext(
        structure=ArtifactStructureContext(
            artifact_family="controller",
            base_classes=("BaseController",),
            decorators=("controller_decorator",),
            imports=(
                ImportSpec("app.framework", "BaseController"),
                ImportSpec("app.framework", "controller_decorator"),
            ),
            dependencies=(),
        ),
        examples=(),
    )

    change = DeterministicPythonCodingModel().generate_change(
        DevelopmentTask("controller", "GeneratedController", ()),
        context,
    )

    assert change.files[0].content == (
        "from app.framework import BaseController, controller_decorator\n\n"
        "@controller_decorator\n"
        "class GeneratedController(BaseController):\n"
        "    def __init__(self) -> None:\n"
        "        pass\n\n"
        "    pass"
    )


def test_generic_structure_render_handles_controller_with_method() -> None:
    from agentic_platform.tasks.types import OperationSpec, ParameterSpec

    context = CodingContext(
        structure=ArtifactStructureContext(
            artifact_family="controller",
            base_classes=("BaseController",),
            decorators=("controller_decorator",),
            imports=(
                ImportSpec("app.framework", "BaseController"),
                ImportSpec("app.framework", "controller_decorator"),
            ),
            dependencies=(),
        ),
        examples=(),
    )

    change = DeterministicPythonCodingModel().generate_change(
        DevelopmentTask("controller", "OrderController", (
            OperationSpec("handle", (ParameterSpec("order_id"),)),
        )),
        context,
    )

    assert "def handle(self, order_id):" in change.files[0].content
    assert "return None" in change.files[0].content