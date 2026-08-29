from __future__ import annotations

from pathlib import Path

import pytest

from agentic_platform.domain.models import Evidence, ImportSpec
from agentic_platform.framework_learning.inventory import (
    InventoryDiff,
    RepositoryInventory,
    RepositoryRevision,
    RepositoryScanner,
    SourceFile,
)
from agentic_platform.framework_learning.observations import (
    ConstructorDependencyObservation,
    InvocationObservation,
    ObservationBatch,
    ObservationStore,
    StructuralClassObservation,
)


def _file(path: str, content: bytes = b"pass\n") -> SourceFile:
    import hashlib
    return SourceFile(
        relative_path=path,
        language_id="python",
        content_hash=hashlib.sha256(content).hexdigest(),
        size=len(content),
    )


class TestObservationStore:
    def test_empty_store_has_no_files(self) -> None:
        store = ObservationStore(files=())
        assert store.files == ()
        assert store.is_empty

    def test_store_maps_observations_by_path(self) -> None:
        obs_a = StructuralClassObservation(
            "service.base_class", "Base",
            Evidence("a.py", "Svc", "Base"), None,
        )
        obs_b = StructuralClassObservation(
            "service.base_class", "Base",
            Evidence("b.py", "Svc", "Base"), None,
        )
        store = ObservationStore(files=(
            ("a.py", (obs_a,)),
            ("b.py", (obs_b,)),
        ))
        assert store.observations_for("a.py") == (obs_a,)
        assert store.observations_for("b.py") == (obs_b,)
        assert store.observations_for("missing.py") == ()

    def test_store_is_immutable(self) -> None:
        store = ObservationStore(files=(
            ("a.py", (StructuralClassObservation(
                "service.base_class", "Base",
                Evidence("a.py", "Svc", "Base"), None,
            ),)),
        ))
        with pytest.raises(AttributeError):
            store.files = ()  # type: ignore[misc]

    def test_store_all_observations_flattens_in_order(self) -> None:
        obs_a = StructuralClassObservation(
            "service.base_class", "Base",
            Evidence("a.py", "Svc", "Base"), None,
        )
        obs_b = StructuralClassObservation(
            "service.required_decorator", "managed",
            Evidence("b.py", "Svc", "managed"), None,
        )
        store = ObservationStore(files=(
            ("a.py", (obs_a,)),
            ("b.py", (obs_b,)),
        ))
        assert store.all_observations() == (obs_a, obs_b)

    def test_store_subject_count_sums_correctly(self) -> None:
        obs = StructuralClassObservation(
            "service.base_class", "Base",
            Evidence("a.py", "Svc", "Base"), None,
        )
        store = ObservationStore(files=(
            ("a.py", (obs,)),
            ("b.py", (obs,)),
            ("c.py", (obs,)),
        ))
        assert store.subject_count == 3


class TestObservationStoreReplace:
    def test_replace_observations_for_changed_file(self) -> None:
        old_obs = StructuralClassObservation(
            "service.base_class", "OldBase",
            Evidence("a.py", "Svc", "OldBase"), None,
        )
        new_obs = StructuralClassObservation(
            "service.base_class", "NewBase",
            Evidence("a.py", "Svc", "NewBase"), None,
        )
        store = ObservationStore(files=(
            ("a.py", (old_obs,)),
            ("b.py", (old_obs,)),
        ))

        updated = store.replace_observations("a.py", (new_obs,))

        assert updated.observations_for("a.py") == (new_obs,)
        assert updated.observations_for("b.py") == (old_obs,)  # unchanged
        # Original store is unchanged
        assert store.observations_for("a.py") == (old_obs,)

    def test_remove_observations_for_deleted_file(self) -> None:
        obs = StructuralClassObservation(
            "service.base_class", "Base",
            Evidence("a.py", "Svc", "Base"), None,
        )
        store = ObservationStore(files=(
            ("a.py", (obs,)),
            ("b.py", (obs,)),
        ))

        updated = store.remove_observations("a.py")

        assert updated.observations_for("a.py") == ()
        assert updated.observations_for("b.py") == (obs,)
        assert "a.py" not in [f for f, _ in updated.files]

    def test_add_observations_for_new_file(self) -> None:
        obs = StructuralClassObservation(
            "service.base_class", "Base",
            Evidence("a.py", "Svc", "Base"), None,
        )
        store = ObservationStore(files=())

        added = store.add_observations("new.py", (obs,))

        assert added.observations_for("new.py") == (obs,)
        assert ("new.py", (obs,)) in added.files

    def test_apply_diff_replaces_changed_adds_new_removes_deleted(self) -> None:
        old_obs = StructuralClassObservation(
            "service.base_class", "OldBase",
            Evidence("a.py", "Svc", "OldBase"), None,
        )
        new_obs = StructuralClassObservation(
            "service.base_class", "NewBase",
            Evidence("a.py", "Svc", "NewBase"), None,
        )
        added_obs = StructuralClassObservation(
            "service.base_class", "AddedBase",
            Evidence("c.py", "Svc", "AddedBase"), None,
        )

        store = ObservationStore(files=(
            ("a.py", (old_obs,)),
            ("b.py", (old_obs,)),  # will be deleted
        ))

        new_inventory = RepositoryInventory(files=(
            _file("a.py", b"new content"),
            _file("c.py", b"added"),
        ))
        diff = InventoryDiff.compute(
            RepositoryInventory(files=(_file("a.py", b"old content"), _file("b.py", b"deleted"))),
            new_inventory,
        )

        # Simulate: for changed/deleted files we remove, for added/changed we add new
        updated = store.apply_diff(
            diff=diff,
            new_observations={
                "a.py": (new_obs,),
                "c.py": (added_obs,),
            },
        )

        assert updated.observations_for("a.py") == (new_obs,)
        assert updated.observations_for("c.py") == (added_obs,)
        assert updated.observations_for("b.py") == ()  # deleted
