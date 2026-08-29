"""Language-neutral observations produced by source-specific extractors."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from agentic_platform.domain.models import Evidence, ImportSpec
from agentic_platform.framework_learning.inventory import InventoryDiff


@dataclass(frozen=True)
class InvocationObservation:
    """One method invocation made through a constructed dependency."""

    method_name: str
    argument_shapes: tuple[str, ...]


@dataclass(frozen=True)
class StructuralClassObservation:
    """One structural convention observed on a framework class."""

    kind: str
    expected_value: str
    evidence: Evidence
    imported: ImportSpec | None = None


@dataclass(frozen=True)
class ConstructorDependencyObservation:
    """Constructor and use evidence for one class dependency attribute."""

    attribute: str
    concrete_type: str
    evidence: Evidence
    imported: ImportSpec | None
    constructor_arguments: tuple[str, ...]
    invocations: tuple[InvocationObservation, ...]


FrameworkObservation: TypeAlias = StructuralClassObservation | ConstructorDependencyObservation


@dataclass(frozen=True)
class ObservationBatch:
    """Observations plus the population used to calculate confidence."""

    subject_count: int
    observations: tuple[FrameworkObservation, ...]


@dataclass(frozen=True)
class ObservationStore:
    """Immutable, file-keyed store of observations supporting incremental updates.

    Each entry maps a source file path to the observations extracted from it.
    Updates produce new stores; the original is never mutated.
    """

    files: tuple[tuple[str, tuple[FrameworkObservation, ...]], ...]

    @property
    def is_empty(self) -> bool:
        return not self.files

    def observations_for(self, path: str) -> tuple[FrameworkObservation, ...]:
        for file_path, observations in self.files:
            if file_path == path:
                return observations
        return ()

    def all_observations(self) -> tuple[FrameworkObservation, ...]:
        result: list[FrameworkObservation] = []
        for _, observations in self.files:
            result.extend(observations)
        return tuple(result)

    @property
    def subject_count(self) -> int:
        return sum(len(obs) for _, obs in self.files)

    def replace_observations(
        self, path: str, observations: tuple[FrameworkObservation, ...]
    ) -> ObservationStore:
        new_files = tuple(
            (file_path, observations) if file_path == path else (file_path, obs)
            for file_path, obs in self.files
        )
        return ObservationStore(files=new_files)

    def remove_observations(self, path: str) -> ObservationStore:
        new_files = tuple(
            (file_path, obs) for file_path, obs in self.files if file_path != path
        )
        return ObservationStore(files=new_files)

    def add_observations(
        self, path: str, observations: tuple[FrameworkObservation, ...]
    ) -> ObservationStore:
        """Add observations for a new file, maintaining path-sorted order."""
        new_entry = (path, observations)
        entries = list(self.files)
        # Find insertion point to maintain sorted order
        inserted = False
        for i, (file_path, _) in enumerate(entries):
            if path < file_path:
                entries.insert(i, new_entry)
                inserted = True
                break
        if not inserted:
            entries.append(new_entry)
        return ObservationStore(files=tuple(entries))

    def apply_diff(
        self,
        diff: InventoryDiff,
        new_observations: dict[str, tuple[FrameworkObservation, ...]],
    ) -> ObservationStore:
        """Apply an inventory diff, replacing observations for changed files,
        removing observations for deleted files, and adding observations for
        new files."""
        store = self
        # Remove observations for deleted files
        for source_file in diff.deleted:
            store = store.remove_observations(source_file.relative_path)
        # Replace observations for changed files
        for source_file in diff.changed:
            path = source_file.relative_path
            if path in new_observations:
                store = store.replace_observations(path, new_observations[path])
            else:
                store = store.remove_observations(path)
        # Add observations for new files
        for source_file in diff.added:
            path = source_file.relative_path
            if path in new_observations:
                store = store.add_observations(path, new_observations[path])
        return store
