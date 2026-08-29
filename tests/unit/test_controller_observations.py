from __future__ import annotations

from pathlib import Path

from agentic_platform.framework_learning.inventory import RepositoryScanner
from agentic_platform.framework_learning.python_ast import PythonAstParser, PythonControllerObservationExtractor
from agentic_platform.framework_learning.observations import (
    ObservationBatch,
    StructuralClassObservation,
)
from agentic_platform.domain.models import Evidence, ImportSpec


def test_controller_extractor_translates_base_class_and_decorator(tmp_path: Path) -> None:
    (tmp_path / "controller.py").write_text(
        "from framework import Base as FrameworkBase, managed\n"
        "@managed\n"
        "class OrderController(FrameworkBase):\n"
        "    def __init__(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    source_file = RepositoryScanner().scan(tmp_path).files[0]
    parsed = PythonAstParser().parse(tmp_path, source_file)

    batch = PythonControllerObservationExtractor().extract(parsed)

    assert batch == ObservationBatch(
        1,
        (
            StructuralClassObservation(
                "controller.base_class",
                "FrameworkBase",
                Evidence("controller.py", "OrderController", "FrameworkBase"),
                ImportSpec("framework", "Base", "FrameworkBase"),
            ),
            StructuralClassObservation(
                "controller.required_decorator",
                "managed",
                Evidence("controller.py", "OrderController", "managed"),
                ImportSpec("framework", "managed"),
            ),
        ),
    )


def test_controller_extractor_ignores_services(tmp_path: Path) -> None:
    (tmp_path / "mixed.py").write_text(
        "from framework import Base, managed, GenericClient\n"
        "@managed\n"
        "class OrderService(Base):\n"
        "    def __init__(self):\n"
        "        self.client = GenericClient(__name__)\n"
        "@managed\n"
        "class OrderController(Base):\n"
        "    def __init__(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    source_file = RepositoryScanner().scan(tmp_path).files[0]
    parsed = PythonAstParser().parse(tmp_path, source_file)

    batch = PythonControllerObservationExtractor().extract(parsed)

    assert batch.subject_count == 1
    assert all(
        obs.kind.startswith("controller.")
        for obs in batch.observations
        if isinstance(obs, StructuralClassObservation)
    )


def test_controller_extractor_does_not_infer_dependencies(tmp_path: Path) -> None:
    (tmp_path / "controller.py").write_text(
        "from framework import Base, managed, GenericClient\n"
        "@managed\n"
        "class OrderController(Base):\n"
        "    def __init__(self):\n"
        "        self.client = GenericClient(__name__)\n"
        "    def handle(self):\n"
        "        self.client.write('x')\n",
        encoding="utf-8",
    )
    source_file = RepositoryScanner().scan(tmp_path).files[0]
    parsed = PythonAstParser().parse(tmp_path, source_file)

    batch = PythonControllerObservationExtractor().extract(parsed)

    assert batch.subject_count == 1
    assert all(
        obs.kind in ("controller.base_class", "controller.required_decorator")
        for obs in batch.observations
        if isinstance(obs, StructuralClassObservation)
    )