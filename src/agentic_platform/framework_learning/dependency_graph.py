"""Dependency graph and impact analysis for incremental learning.

Tracks cross-file dependencies (imports, base classes, symbols) to identify
which files are transitively affected when a file changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from agentic_platform.framework_learning.inventory import InventoryDiff
from agentic_platform.framework_learning.observations import ObservationStore


@dataclass(frozen=True)
class DependencyEdge:
    """A directed dependency between two source files."""

    source: str  # file that depends on target
    target: str  # file that is depended upon
    symbol: str  # the symbol that creates the dependency


@dataclass(frozen=True)
class DependencyGraph:
    """Immutable dependency graph between source files."""

    edges: tuple[DependencyEdge, ...]

    def dependents_of(self, path: str) -> tuple[str, ...]:
        """Return all files that depend on the given file."""
        return tuple(sorted({e.source for e in self.edges if e.target == path}))

    def dependencies_of(self, path: str) -> tuple[str, ...]:
        """Return all files that the given file depends on."""
        return tuple(sorted({e.target for e in self.edges if e.source == path}))


@dataclass(frozen=True)
class ImpactAnalysis:
    """Result of analyzing the impact of an inventory change."""

    directly_changed: tuple[str, ...]
    transitively_affected: tuple[str, ...]
    observations_to_recompute: tuple[str, ...]

    @classmethod
    def compute(
        cls,
        diff: InventoryDiff,
        graph: DependencyGraph,
        *,
        observation_store: ObservationStore | None = None,
    ) -> ImpactAnalysis:
        """Compute the impact of an inventory change.

        Identifies directly changed files (added, changed, deleted) and
        transitively affected files (those that depend on changed files).
        """
        changed_paths: set[str] = set()
        for f in diff.added:
            changed_paths.add(f.relative_path)
        for f in diff.changed:
            changed_paths.add(f.relative_path)
        for f in diff.deleted:
            changed_paths.add(f.relative_path)

        # Transitively affected = dependents of changed files (recursively)
        affected: set[str] = set()
        to_process = list(changed_paths)
        visited: set[str] = set()
        while to_process:
            current = to_process.pop()
            if current in visited:
                continue
            visited.add(current)
            for dependent in graph.dependents_of(current):
                if dependent not in changed_paths:
                    affected.add(dependent)
                if dependent not in visited:
                    to_process.append(dependent)

        # If we have an observation store, mark observations for affected files
        # for re-computation
        observations_to_recompute: set[str] = set(changed_paths)
        if observation_store is not None:
            for path in affected:
                if observation_store.observations_for(path):
                    observations_to_recompute.add(path)

        return cls(
            directly_changed=tuple(sorted(changed_paths)),
            transitively_affected=tuple(sorted(affected)),
            observations_to_recompute=tuple(sorted(observations_to_recompute)),
        )
