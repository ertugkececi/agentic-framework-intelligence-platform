from __future__ import annotations

from pathlib import Path

import pytest

from agentic_platform.domain.models import (
    DependencyContext,
    FrameworkRule,
    ImportSpec,
    RuleStatus,
)
from agentic_platform.framework_learning.dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    ImpactAnalysis,
)
from agentic_platform.framework_learning.inventory import (
    InventoryDiff,
    RepositoryInventory,
    RepositoryScanner,
    SourceFile,
)
from agentic_platform.framework_learning.observations import (
    ObservationStore,
    StructuralClassObservation,
)
from agentic_platform.domain.models import Evidence


def _file(path: str, content: bytes = b"pass\n") -> SourceFile:
    import hashlib
    return SourceFile(
        relative_path=path,
        language_id="python",
        content_hash=hashlib.sha256(content).hexdigest(),
        size=len(content),
    )


class TestDependencyEdge:
    def test_edge_is_immutable(self) -> None:
        edge = DependencyEdge(source="a.py", target="b.py", symbol="Base")
        with pytest.raises(AttributeError):
            edge.source = "x.py"  # type: ignore[misc]


class TestDependencyGraph:
    def test_empty_graph_has_no_edges(self) -> None:
        graph = DependencyGraph(edges=())
        assert graph.edges == ()
        assert graph.dependents_of("a.py") == ()
        assert graph.dependencies_of("a.py") == ()

    def test_graph_tracks_dependents(self) -> None:
        graph = DependencyGraph(edges=(
            DependencyEdge(source="b.py", target="a.py", symbol="Base"),
            DependencyEdge(source="c.py", target="a.py", symbol="Helper"),
        ))
        assert graph.dependents_of("a.py") == ("b.py", "c.py")
        assert graph.dependents_of("b.py") == ()

    def test_graph_tracks_dependencies(self) -> None:
        graph = DependencyGraph(edges=(
            DependencyEdge(source="b.py", target="a.py", symbol="Base"),
            DependencyEdge(source="c.py", target="a.py", symbol="Helper"),
        ))
        assert graph.dependencies_of("b.py") == ("a.py",)
        assert graph.dependencies_of("a.py") == ()

    def test_graph_is_immutable(self) -> None:
        graph = DependencyGraph(edges=(
            DependencyEdge(source="b.py", target="a.py", symbol="Base"),
        ))
        with pytest.raises(AttributeError):
            graph.edges = ()  # type: ignore[misc]


class TestImpactAnalysis:
    def test_impact_analysis_identifies_directly_affected(self) -> None:
        graph = DependencyGraph(edges=(
            DependencyEdge(source="svc.py", target="base.py", symbol="Base"),
            DependencyEdge(source="ctrl.py", target="base.py", symbol="Base"),
        ))
        diff = InventoryDiff.compute(
            RepositoryInventory(files=(_file("base.py", b"old"), _file("svc.py"), _file("ctrl.py"))),
            RepositoryInventory(files=(_file("base.py", b"new"), _file("svc.py"), _file("ctrl.py"))),
        )
        analysis = ImpactAnalysis.compute(diff, graph)
        assert "base.py" in analysis.directly_changed
        assert "svc.py" in analysis.transitively_affected
        assert "ctrl.py" in analysis.transitively_affected

    def test_impact_analysis_handles_added_files(self) -> None:
        graph = DependencyGraph(edges=())
        diff = InventoryDiff.compute(
            RepositoryInventory(files=(_file("a.py"),)),
            RepositoryInventory(files=(_file("a.py"), _file("b.py"))),
        )
        analysis = ImpactAnalysis.compute(diff, graph)
        assert "b.py" in analysis.directly_changed
        assert analysis.transitively_affected == ()

    def test_impact_analysis_handles_deleted_files(self) -> None:
        graph = DependencyGraph(edges=(
            DependencyEdge(source="svc.py", target="base.py", symbol="Base"),
        ))
        diff = InventoryDiff.compute(
            RepositoryInventory(files=(_file("base.py"), _file("svc.py"))),
            RepositoryInventory(files=(_file("svc.py"),)),
        )
        analysis = ImpactAnalysis.compute(diff, graph)
        assert "base.py" in analysis.directly_changed
        # Deleting base.py affects svc.py which depends on it
        assert "svc.py" in analysis.transitively_affected

    def test_impact_analysis_transitive_chain(self) -> None:
        graph = DependencyGraph(edges=(
            DependencyEdge(source="mid.py", target="base.py", symbol="Base"),
            DependencyEdge(source="top.py", target="mid.py", symbol="Mid"),
        ))
        diff = InventoryDiff.compute(
            RepositoryInventory(files=(_file("base.py", b"old"), _file("mid.py"), _file("top.py"))),
            RepositoryInventory(files=(_file("base.py", b"new"), _file("mid.py"), _file("top.py"))),
        )
        analysis = ImpactAnalysis.compute(diff, graph)
        assert "base.py" in analysis.directly_changed
        assert "mid.py" in analysis.transitively_affected
        assert "top.py" in analysis.transitively_affected  # transitive through mid.py

    def test_impact_analysis_preserves_observation_store(self) -> None:
        graph = DependencyGraph(edges=(
            DependencyEdge(source="svc.py", target="base.py", symbol="Base"),
        ))
        diff = InventoryDiff.compute(
            RepositoryInventory(files=(_file("base.py", b"old"), _file("svc.py"))),
            RepositoryInventory(files=(_file("base.py", b"new"), _file("svc.py"))),
        )
        store = ObservationStore(files=(
            ("base.py", (StructuralClassObservation(
                "service.base_class", "Base",
                Evidence("base.py", "Base", "Base"), None,
            ),)),
            ("svc.py", (StructuralClassObservation(
                "service.base_class", "Base",
                Evidence("svc.py", "Svc", "Base"), None,
            ),)),
        ))
        analysis = ImpactAnalysis.compute(diff, graph, observation_store=store)
        # Observations for affected files should be flagged for re-evaluation
        assert "svc.py" in analysis.observations_to_recompute
        assert "base.py" in analysis.observations_to_recompute
