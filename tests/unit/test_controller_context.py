from __future__ import annotations

import pytest

from agentic_platform.domain.models import (
    ArtifactStructureContext,
    CodingContext,
    FrameworkRule,
    ImportSpec,
    RuleStatus,
)
from agentic_platform.retrieval.context import retrieve_artifact_structure, retrieve_controller_context
from agentic_platform.framework_knowledge.sqlite_store import SQLiteKnowledgeStore
from agentic_platform.tasks.types import DevelopmentTask
from pathlib import Path
import tempfile


def test_retrieve_controller_context_builds_structure_from_rules() -> None:
    active = RuleStatus.ACTIVE
    rules = [
        FrameworkRule(
            "controller.base_class",
            "BaseController",
            1.0,
            3,
            0,
            (),
            metadata={"import_module": "app.framework", "import_symbol": "BaseController"},
            status=active,
        ),
        FrameworkRule(
            "controller.required_decorator",
            "controller_decorator",
            1.0,
            3,
            0,
            (),
            metadata={"import_module": "app.framework", "import_symbol": "controller_decorator"},
            status=active,
        ),
    ]

    structure = retrieve_artifact_structure(rules, "controller")

    assert structure.artifact_family == "controller"
    assert structure.base_classes == ("BaseController",)
    assert structure.decorators == ("controller_decorator",)
    assert structure.imports == (
        ImportSpec("app.framework", "BaseController"),
        ImportSpec("app.framework", "controller_decorator"),
    )


def test_retrieve_controller_context_assembles_coding_context() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repository = tmp_path / "repo"
        repository.mkdir()
        (repository / "app").mkdir()
        (repository / "app" / "controllers.py").write_text(
            "from framework import Base, managed\n"
            "@managed\n"
            "class OrderController(Base):\n"
            "    def __init__(self):\n"
            "        pass\n",
            encoding="utf-8",
        )

        rules = [
            FrameworkRule(
                "controller.base_class",
                "Base",
                1.0,
                3,
                0,
                (),
                metadata={"import_module": "framework", "import_symbol": "Base"},
                status=RuleStatus.ACTIVE,
            ),
            FrameworkRule(
                "controller.required_decorator",
                "managed",
                1.0,
                3,
                0,
                (),
                metadata={"import_module": "framework", "import_symbol": "managed"},
                status=RuleStatus.ACTIVE,
            ),
        ]

        store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite")
        store.replace_rules(rules, "dummy_fp")
        task = DevelopmentTask("controller", "PaymentController", ())
        resolved_rules, context = retrieve_controller_context(store, repository, task)
        store.close()

        assert context.structure.artifact_family == "controller"
        assert context.structure.base_classes == ("Base",)
        assert context.structure.decorators == ("managed",)
        assert context.structure.dependencies == ()
        assert len(resolved_rules) == 2


def test_retrieve_controller_context_requires_active_rules() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repository = tmp_path / "repo"
        repository.mkdir()
        (repository / "app").mkdir()
        (repository / "app" / "controllers.py").write_text(
            "from framework import Base, managed\n"
            "@managed\n"
            "class OrderController(Base):\n"
            "    def __init__(self):\n"
            "        pass\n",
            encoding="utf-8",
        )

        store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite")
        store.replace_rules([], "dummy_fp")
        task = DevelopmentTask("controller", "PaymentController", ())

        with pytest.raises(ValueError, match="Missing active rule"):
            retrieve_controller_context(store, repository, task)

        store.close()