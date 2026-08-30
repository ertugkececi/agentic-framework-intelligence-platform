from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agentic_platform.security.sandbox import StagingSandbox


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "examples" / "sample_customer_repo"


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(("git", *args), cwd=cwd, text=True, capture_output=True, check=True)


def test_clean_git_repository_uses_detached_worktree_and_removes_it(tmp_path: Path) -> None:
    repository = tmp_path / "customer-repo"
    shutil.copytree(SAMPLE, repository)
    _git("init", cwd=repository)
    _git("config", "user.email", "test@example.invalid", cwd=repository)
    _git("config", "user.name", "Test User", cwd=repository)
    _git("add", ".", cwd=repository)
    _git("commit", "-m", "fixture", cwd=repository)

    sandbox = StagingSandbox.create(tmp_path, repository, "run-1")

    assert sandbox.backend == "git_worktree"
    assert sandbox.path.parent == tmp_path / ".development-staging"
    assert (sandbox.path / ".git").is_file()
    assert _git("rev-parse", "HEAD", cwd=sandbox.path).stdout == _git("rev-parse", "HEAD", cwd=repository).stdout

    sandbox.remove()

    assert not sandbox.path.exists()
    assert str(sandbox.path) not in _git("worktree", "list", "--porcelain", cwd=repository).stdout


def test_non_git_repository_uses_disposable_copy_without_runtime_artifacts(tmp_path: Path) -> None:
    repository = tmp_path / "customer-repo"
    shutil.copytree(SAMPLE, repository)
    (repository / "__pycache__").mkdir()
    (repository / "__pycache__" / "ignored.pyc").write_bytes(b"cache")

    sandbox = StagingSandbox.create(tmp_path, repository, "run-2")

    assert sandbox.backend == "copy"
    assert (sandbox.path / "app").is_dir()
    assert not (sandbox.path / "__pycache__").exists()

    sandbox.remove()
    assert not sandbox.path.exists()
    assert not sandbox.path.parent.exists()


def test_staging_sandbox_rejects_a_workspace_inside_the_customer_repository(tmp_path: Path) -> None:
    repository = tmp_path / "customer-repo"
    shutil.copytree(SAMPLE, repository)

    with pytest.raises(PermissionError, match="outside"):
        StagingSandbox.create(repository, repository, "run-3")

    assert not (repository / ".development-staging").exists()
