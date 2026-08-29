from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agentic_platform.framework_learning.inventory import (
    InventoryDiff,
    RepositoryInventory,
    RepositoryRevision,
    RepositoryScanner,
    SourceFile,
)


def _make_file(relative_path: str, content: bytes = b"pass\n") -> SourceFile:
    return SourceFile(
        relative_path=relative_path,
        language_id="python",
        content_hash=hashlib.sha256(content).hexdigest(),
        size=len(content),
    )


class TestRepositoryRevision:
    def test_revision_is_deterministic_for_same_inventory(self) -> None:
        inventory = RepositoryInventory(
            files=(
                _make_file("a.py", b"one"),
                _make_file("b.py", b"two"),
            )
        )
        revision = RepositoryRevision.from_inventory(inventory)
        assert revision == RepositoryRevision.from_inventory(inventory)

    def test_revision_changes_when_file_content_changes(self) -> None:
        original = RepositoryInventory(files=(_make_file("a.py", b"v1"),))
        modified = RepositoryInventory(files=(_make_file("a.py", b"v2"),))
        assert RepositoryRevision.from_inventory(original) != RepositoryRevision.from_inventory(modified)

    def test_revision_changes_when_files_added(self) -> None:
        smaller = RepositoryInventory(files=(_make_file("a.py"),))
        larger = RepositoryInventory(files=(_make_file("a.py"), _make_file("b.py")))
        assert RepositoryRevision.from_inventory(smaller) != RepositoryRevision.from_inventory(larger)

    def test_revision_changes_when_files_removed(self) -> None:
        larger = RepositoryInventory(files=(_make_file("a.py"), _make_file("b.py")))
        smaller = RepositoryInventory(files=(_make_file("a.py"),))
        assert RepositoryRevision.from_inventory(larger) != RepositoryRevision.from_inventory(smaller)

    def test_revision_is_immutable(self) -> None:
        revision = RepositoryRevision.from_inventory(RepositoryInventory(files=(_make_file("a.py"),)))
        with pytest.raises(AttributeError):
            revision.value = "tampered"  # type: ignore[misc]

    def test_empty_repository_has_stable_revision(self) -> None:
        empty = RepositoryInventory(files=())
        assert RepositoryRevision.from_inventory(empty) == RepositoryRevision.from_inventory(empty)


class TestInventoryDiff:
    def test_identical_inventories_produce_empty_diff(self) -> None:
        inventory = RepositoryInventory(files=(_make_file("a.py"), _make_file("b.py")))
        diff = InventoryDiff.compute(inventory, inventory)
        assert diff.added == ()
        assert diff.changed == ()
        assert diff.deleted == ()
        assert diff.is_empty

    def test_added_files_detected(self) -> None:
        old = RepositoryInventory(files=(_make_file("a.py"),))
        new = RepositoryInventory(files=(_make_file("a.py"), _make_file("b.py")))
        diff = InventoryDiff.compute(old, new)
        assert [f.relative_path for f in diff.added] == ["b.py"]
        assert diff.changed == ()
        assert diff.deleted == ()

    def test_deleted_files_detected(self) -> None:
        old = RepositoryInventory(files=(_make_file("a.py"), _make_file("b.py")))
        new = RepositoryInventory(files=(_make_file("a.py"),))
        diff = InventoryDiff.compute(old, new)
        assert diff.added == ()
        assert diff.changed == ()
        assert [f.relative_path for f in diff.deleted] == ["b.py"]

    def test_changed_files_detected_by_hash(self) -> None:
        old = RepositoryInventory(files=(_make_file("a.py", b"v1"),))
        new = RepositoryInventory(files=(_make_file("a.py", b"v2"),))
        diff = InventoryDiff.compute(old, new)
        assert diff.added == ()
        assert [f.relative_path for f in diff.changed] == ["a.py"]
        assert diff.deleted == ()

    def test_unchanged_files_not_in_diff(self) -> None:
        old = RepositoryInventory(files=(_make_file("a.py", b"same"), _make_file("b.py", b"old")))
        new = RepositoryInventory(files=(_make_file("a.py", b"same"), _make_file("c.py", b"new")))
        diff = InventoryDiff.compute(old, new)
        assert [f.relative_path for f in diff.added] == ["c.py"]
        assert diff.changed == ()
        assert [f.relative_path for f in diff.deleted] == ["b.py"]

    def test_complex_diff_with_all_categories(self) -> None:
        old = RepositoryInventory(files=(
            _make_file("keep.py", b"same"),
            _make_file("modify.py", b"old"),
            _make_file("remove.py", b"gone"),
        ))
        new = RepositoryInventory(files=(
            _make_file("keep.py", b"same"),
            _make_file("modify.py", b"new"),
            _make_file("add.py", b"fresh"),
        ))
        diff = InventoryDiff.compute(old, new)
        assert [f.relative_path for f in diff.added] == ["add.py"]
        assert [f.relative_path for f in diff.changed] == ["modify.py"]
        assert [f.relative_path for f in diff.deleted] == ["remove.py"]

    def test_diff_is_immutable(self) -> None:
        diff = InventoryDiff.compute(
            RepositoryInventory(files=(_make_file("a.py"),)),
            RepositoryInventory(files=(_make_file("b.py"),)),
        )
        with pytest.raises(AttributeError):
            diff.added = ()  # type: ignore[misc]

    def test_empty_old_inventory_means_all_added(self) -> None:
        old = RepositoryInventory(files=())
        new = RepositoryInventory(files=(_make_file("a.py"), _make_file("b.py")))
        diff = InventoryDiff.compute(old, new)
        assert [f.relative_path for f in diff.added] == ["a.py", "b.py"]
        assert diff.changed == ()
        assert diff.deleted == ()

    def test_empty_new_inventory_means_all_deleted(self) -> None:
        old = RepositoryInventory(files=(_make_file("a.py"), _make_file("b.py")))
        new = RepositoryInventory(files=())
        diff = InventoryDiff.compute(old, new)
        assert diff.added == ()
        assert diff.changed == ()
        assert [f.relative_path for f in diff.deleted] == ["a.py", "b.py"]


class TestScannerRevisionIntegration:
    def test_scanner_can_compute_revision(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("value = 1\n")
        (tmp_path / "b.py").write_text("value = 2\n")
        scanner = RepositoryScanner()
        inventory = scanner.scan(tmp_path)
        revision = RepositoryRevision.from_inventory(inventory)
        assert revision.value  # non-empty hex digest

    def test_scanner_detects_changed_file_via_revision(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("value = 1\n")
        scanner = RepositoryScanner()
        inv1 = scanner.scan(tmp_path)
        rev1 = RepositoryRevision.from_inventory(inv1)

        (tmp_path / "a.py").write_text("value = 999\n")
        inv2 = scanner.scan(tmp_path)
        rev2 = RepositoryRevision.from_inventory(inv2)

        assert rev1 != rev2
        diff = InventoryDiff.compute(inv1, inv2)
        assert [f.relative_path for f in diff.changed] == ["a.py"]
