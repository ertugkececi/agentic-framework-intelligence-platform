from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from agentic_platform.framework_learning.inventory import RepositoryScanner


def test_scanner_records_immutable_python_file_metadata(tmp_path: Path) -> None:
    source = b"value = 1\n"
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "module.py").write_bytes(source)

    inventory = RepositoryScanner().scan(tmp_path)

    assert len(inventory.files) == 1
    item = inventory.files[0]
    assert item.relative_path == "app/module.py"
    assert item.language_id == "python"
    assert item.content_hash == hashlib.sha256(source).hexdigest()
    assert item.size == len(source)
    with pytest.raises(FrozenInstanceError):
        item.size = 0  # type: ignore[misc]


def test_scanner_sorts_sources_and_excludes_tests_hidden_generated_and_runtime_directories(
    tmp_path: Path,
) -> None:
    included = ("z.py", "app/a.py")
    excluded = (
        "tests/test_app.py",
        "app/tests/helper.py",
        ".hidden/secret.py",
        "generated/client.py",
        "runtime/state.py",
        "build/output.py",
        "dist/package.py",
        "__pycache__/cached.py",
        ".venv/library.py",
        "node_modules/tool.py",
        "README.md",
    )
    for relative_path in included + excluded:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("pass\n", encoding="utf-8")

    inventory = RepositoryScanner().scan(tmp_path)

    assert [item.relative_path for item in inventory.files] == ["app/a.py", "z.py"]


def test_scanner_does_not_follow_source_file_symlinks_outside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("secret = True\n", encoding="utf-8")
    (repository / "linked.py").symlink_to(outside)

    inventory = RepositoryScanner().scan(repository)

    assert inventory.files == ()
