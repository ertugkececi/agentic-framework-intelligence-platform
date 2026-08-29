from __future__ import annotations

import ast
from pathlib import Path

from agentic_platform.framework_learning.inventory import RepositoryScanner
from agentic_platform.framework_learning.parser import SourceParseError
from agentic_platform.framework_learning.python_ast import PythonAstParser

import pytest


def test_python_adapter_returns_module_and_typed_import_observations(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text(
        "from package.services import ServiceBase as Base\nclass Example(Base):\n    pass\n",
        encoding="utf-8",
    )
    source_file = RepositoryScanner().scan(tmp_path).files[0]

    parsed = PythonAstParser().parse(tmp_path, source_file)

    assert parsed.source_file is source_file
    assert isinstance(parsed.module, ast.Module)
    assert parsed.imports["Base"].module == "package.services"
    assert parsed.imports["Base"].symbol == "ServiceBase"
    assert parsed.imports["Base"].alias == "Base"


def test_python_syntax_error_is_domain_error_with_relative_path(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    source_file = RepositoryScanner().scan(tmp_path).files[0]

    with pytest.raises(SourceParseError) as raised:
        PythonAstParser().parse(tmp_path, source_file)

    assert raised.value.relative_path == "app/broken.py"
    assert "app/broken.py" in str(raised.value)
