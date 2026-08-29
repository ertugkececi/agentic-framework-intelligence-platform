from __future__ import annotations

from pathlib import Path
import inspect

import agentic_platform.framework_learning.learner as learner_module
from agentic_platform.framework_learning.learner import FrameworkLearner


def test_learner_uses_inventory_filtering_and_ignores_unsupported_files(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "service.py").write_text(
        "from framework import Base, managed\n@managed\nclass ExampleService(Base):\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "app" / "template.js").write_text("this is not JavaScript either }", encoding="utf-8")

    result = FrameworkLearner(minimum_evidence=1).learn(tmp_path)
    rules = result.rules

    assert {(rule.kind, rule.expected_value) for rule in rules} == {
        ("service.base_class", "Base"),
        ("service.required_decorator", "managed"),
    }


def test_learner_has_no_python_ast_extraction_responsibilities() -> None:
    source = inspect.getsource(learner_module)

    assert "import ast" not in source
    assert not hasattr(FrameworkLearner, "_services")
    assert not hasattr(FrameworkLearner, "_dependencies")
    assert not hasattr(FrameworkLearner, "_calls")


def test_learner_sums_subjects_across_modules_and_preserves_rule_order(tmp_path: Path) -> None:
    for name, base, client in (
        ("first", "AlphaBase", "AlphaClient"),
        ("second", "BetaBase", "BetaClient"),
    ):
        (tmp_path / f"{name}.py").write_text(
            f"from framework import {base}, managed, {client}\n"
            "@managed\n"
            f"class {name.title()}Service({base}):\n"
            "    def __init__(self):\n"
            f"        self.client = {client}()\n"
            "    def run(self):\n"
            "        self.client.write('value')\n",
            encoding="utf-8",
        )

    result = FrameworkLearner(minimum_evidence=1).learn(tmp_path)
    rules = result.rules

    assert [(rule.kind, rule.expected_value) for rule in rules] == [
        ("service.base_class", "AlphaBase"),
        ("service.base_class", "BetaBase"),
        ("service.required_decorator", "managed"),
        ("dependency.constructor", "client"),
    ]
    client = rules[-1]
    assert client.support_count == 2
    assert client.conflict_count == 0
    assert client.confidence == 1.0
    assert client.metadata["usage_methods"] == ["write"]
