"""Deterministic inventory of supported repository source files."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path


_LANGUAGE_BY_SUFFIX = {".py": "python"}

_EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        "__pycache__",
        "build",
        "dist",
        "generated",
        "htmlcov",
        "node_modules",
        "runtime",
        "target",
        "test",
        "tests",
        "venv",
    }
)


@dataclass(frozen=True)
class SourceFile:
    """Content identity and location for one supported source file."""

    relative_path: str
    language_id: str
    content_hash: str
    size: int


@dataclass(frozen=True)
class RepositoryInventory:
    """Immutable, path-sorted collection of repository source files."""

    files: tuple[SourceFile, ...]


@dataclass(frozen=True)
class RepositoryRevision:
    """Stable identity for a repository inventory snapshot.

    The revision is a SHA-256 digest over the ordered file identities,
    so any addition, removal, or content change produces a new revision.
    """

    value: str

    @classmethod
    def from_inventory(cls, inventory: RepositoryInventory) -> RepositoryRevision:
        hasher = hashlib.sha256()
        for source_file in inventory.files:
            hasher.update(b"\x00")
            hasher.update(source_file.relative_path.encode("utf-8"))
            hasher.update(b"\x00")
            hasher.update(source_file.content_hash.encode("utf-8"))
            hasher.update(b"\x00")
            hasher.update(str(source_file.size).encode("utf-8"))
        return cls(value=hasher.hexdigest())


@dataclass(frozen=True)
class InventoryDiff:
    """Immutable difference between two repository inventories."""

    added: tuple[SourceFile, ...]
    changed: tuple[SourceFile, ...]
    deleted: tuple[SourceFile, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.changed or self.deleted)

    @classmethod
    def compute(
        cls,
        old: RepositoryInventory,
        new: RepositoryInventory,
    ) -> InventoryDiff:
        old_by_path = {f.relative_path: f for f in old.files}
        new_by_path = {f.relative_path: f for f in new.files}

        added_paths = sorted(set(new_by_path) - set(old_by_path))
        deleted_paths = sorted(set(old_by_path) - set(new_by_path))
        changed_paths = sorted(
            path
            for path in set(old_by_path) & set(new_by_path)
            if old_by_path[path].content_hash != new_by_path[path].content_hash
            or old_by_path[path].size != new_by_path[path].size
        )

        return cls(
            added=tuple(new_by_path[p] for p in added_paths),
            changed=tuple(new_by_path[p] for p in changed_paths),
            deleted=tuple(old_by_path[p] for p in deleted_paths),
        )


class RepositoryScanner:
    """Build source inventories without framework-specific assumptions."""

    def scan(self, repository: Path) -> RepositoryInventory:
        files = []
        for directory, directory_names, file_names in os.walk(repository, followlinks=False):
            directory_names[:] = sorted(
                name
                for name in directory_names
                if not name.startswith(".") and name not in _EXCLUDED_DIRECTORY_NAMES
            )
            parent = Path(directory)
            for file_name in sorted(file_names):
                path = parent / file_name
                language_id = _LANGUAGE_BY_SUFFIX.get(path.suffix)
                if language_id is None or path.is_symlink():
                    continue
                content = path.read_bytes()
                files.append(
                    SourceFile(
                        relative_path=path.relative_to(repository).as_posix(),
                        language_id=language_id,
                        content_hash=hashlib.sha256(content).hexdigest(),
                        size=len(content),
                    )
                )
        return RepositoryInventory(tuple(sorted(files, key=lambda item: item.relative_path)))
