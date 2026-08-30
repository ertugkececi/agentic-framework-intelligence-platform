"""Disposable staging sandboxes for development runs."""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


_RUN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_GIT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class StagingSandbox:
    """A service-owned disposable copy or detached Git worktree."""

    workspace: Path
    repository: Path
    path: Path
    backend: str

    @classmethod
    def create(cls, workspace: Path, repository: Path, run_name: str) -> "StagingSandbox":
        workspace_root = workspace.resolve()
        repository_root = repository.resolve()
        if not repository_root.is_dir():
            raise ValueError("sandbox repository must be a directory")
        if not isinstance(run_name, str) or _RUN_NAME.fullmatch(run_name) is None:
            raise ValueError("invalid sandbox run name")
        staging_parent = workspace_root / ".development-staging"
        if repository_root == staging_parent or repository_root in staging_parent.parents:
            raise PermissionError("staging sandbox must be outside the customer repository")
        if staging_parent.is_symlink():
            raise PermissionError("staging parent must not be a symlink")
        staging_parent.mkdir(parents=True, exist_ok=True)
        if staging_parent.resolve() != staging_parent:
            raise PermissionError("staging parent escapes workspace")
        stage = staging_parent / run_name
        if stage.exists() or stage.is_symlink():
            raise FileExistsError(stage)

        if cls._is_clean_git_root(repository_root):
            completed = cls._git(
                repository_root, "worktree", "add", "--detach", str(stage), "HEAD"
            )
            if completed.returncode != 0:
                shutil.rmtree(stage, ignore_errors=True)
                cls._remove_empty_parent(staging_parent)
                raise RuntimeError("unable to create detached Git worktree")
            return cls(workspace_root, repository_root, stage, "git_worktree")

        try:
            shutil.copytree(
                repository_root,
                stage,
                ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"),
            )
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            cls._remove_empty_parent(staging_parent)
            raise
        return cls(workspace_root, repository_root, stage, "copy")

    @classmethod
    def attach(cls, workspace: Path, repository: Path, stage: Path) -> "StagingSandbox":
        workspace_root = workspace.resolve()
        repository_root = repository.resolve()
        stage_root = stage.resolve()
        if stage_root.parent != workspace_root / ".development-staging" or not stage_root.is_dir():
            raise PermissionError("invalid staging sandbox")
        backend = "git_worktree" if (stage_root / ".git").is_file() else "copy"
        return cls(workspace_root, repository_root, stage_root, backend)

    def remove(self) -> None:
        if self.backend == "git_worktree":
            self._git(self.repository, "worktree", "remove", "--force", str(self.path))
            if self.path.exists():
                shutil.rmtree(self.path, ignore_errors=True)
            self._git(self.repository, "worktree", "prune")
        elif self.backend == "copy":
            shutil.rmtree(self.path, ignore_errors=True)
        else:
            raise ValueError("unknown staging sandbox backend")
        self._remove_empty_parent(self.path.parent)

    @classmethod
    def _is_clean_git_root(cls, repository: Path) -> bool:
        top = cls._git(repository, "rev-parse", "--show-toplevel")
        if top.returncode != 0:
            return False
        try:
            is_root = Path(top.stdout.strip()).resolve() == repository
        except (OSError, ValueError):
            return False
        if not is_root:
            return False
        status = cls._git(repository, "status", "--porcelain", "--untracked-files=all")
        return status.returncode == 0 and not status.stdout.strip()

    @staticmethod
    def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ("git", "-C", str(repository), *arguments),
                text=True,
                capture_output=True,
                check=False,
                timeout=_GIT_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return subprocess.CompletedProcess(("git", *arguments), 1, "", str(error))

    @staticmethod
    def _remove_empty_parent(parent: Path) -> None:
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
