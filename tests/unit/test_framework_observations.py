from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from agentic_platform.domain.models import Evidence, ImportSpec, RuleStatus
from agentic_platform.framework_learning.inventory import RepositoryScanner
from agentic_platform.framework_learning.observations import (
    ConstructorDependencyObservation,
    InvocationObservation,
    ObservationBatch,
    StructuralClassObservation,
)


def test_observation_records_are_typed_and_immutable() -> None:
    evidence = Evidence("app/service.py", "GenericService", "Base")
    imported = ImportSpec("framework", "Base")
    structure = StructuralClassObservation("service.base_class", "Base", evidence, imported)
    invocation = InvocationObservation("write", ("string_literal",))
    dependency = ConstructorDependencyObservation(
        "client",
        "GenericClient",
        Evidence("app/service.py", "GenericService", "client"),
        ImportSpec("framework", "GenericClient"),
        ("__name__",),
        (invocation,),
    )
    batch = ObservationBatch(1, (structure, dependency))

    assert batch.observations == (structure, dependency)
    assert dependency.invocations == (invocation,)
    with pytest.raises(FrozenInstanceError):
        dependency.attribute = "changed"  # type: ignore[misc]


def test_python_extractor_translates_parsed_module_to_domain_observations(tmp_path) -> None:
    from agentic_platform.framework_learning.python_ast import PythonAstParser, PythonServiceObservationExtractor

    (tmp_path / "service.py").write_text(
        "from framework import Base as FrameworkBase, managed, GenericClient\n"
        "@managed\n"
        "class GenericService(FrameworkBase):\n"
        "    def __init__(self):\n"
        "        self.client = GenericClient(__name__)\n"
        "    def run(self):\n"
        "        self.client.write('value')\n",
        encoding="utf-8",
    )
    source_file = RepositoryScanner().scan(tmp_path).files[0]
    parsed = PythonAstParser().parse(tmp_path, source_file)

    batch = PythonServiceObservationExtractor().extract(parsed)

    assert batch == ObservationBatch(
        1,
        (
            StructuralClassObservation(
                "service.base_class",
                "FrameworkBase",
                Evidence("service.py", "GenericService", "FrameworkBase"),
                ImportSpec("framework", "Base", "FrameworkBase"),
            ),
            StructuralClassObservation(
                "service.required_decorator",
                "managed",
                Evidence("service.py", "GenericService", "managed"),
                ImportSpec("framework", "managed"),
            ),
            ConstructorDependencyObservation(
                "client",
                "GenericClient",
                Evidence("service.py", "GenericService", "client"),
                ImportSpec("framework", "GenericClient"),
                ("__name__",),
                (InvocationObservation("write", ("string_literal",)),),
            ),
        ),
    )


def test_aggregator_preserves_rule_evidence_metadata_status_and_ordering() -> None:
    from agentic_platform.framework_learning.aggregation import FrameworkRuleAggregator

    base_import = ImportSpec("framework", "Base")
    observations = (
        StructuralClassObservation(
            "service.base_class", "Base", Evidence("a.py", "FirstService", "Base"), base_import
        ),
        ConstructorDependencyObservation(
            "client",
            "GenericClient",
            Evidence("a.py", "FirstService", "client"),
            ImportSpec("clients", "GenericClient"),
            (),
            (
                InvocationObservation("read", ()),
                InvocationObservation("write", ("string_literal",)),
            ),
        ),
        StructuralClassObservation(
            "service.base_class", "Base", Evidence("b.py", "SecondService", "Base"), base_import
        ),
        ConstructorDependencyObservation(
            "client",
            "AlternateClient",
            Evidence("b.py", "SecondService", "client"),
            ImportSpec("clients", "AlternateClient"),
            (),
            (InvocationObservation("write", ("string_literal",)),),
        ),
        StructuralClassObservation(
            "service.base_class", "Base", Evidence("c.py", "ThirdService", "Base"), base_import
        ),
    )

    rules = FrameworkRuleAggregator(minimum_evidence=2, active_threshold=0.6).aggregate(
        ObservationBatch(3, observations)
    )

    assert [(rule.kind, rule.expected_value) for rule in rules] == [
        ("service.base_class", "Base"),
        ("dependency.constructor", "client"),
    ]
    structure, dependency = rules
    assert structure.support_count == 3
    assert structure.conflict_count == 0
    assert structure.confidence == 1.0
    assert structure.status is RuleStatus.ACTIVE
    assert structure.metadata == {
        "import_module": "framework",
        "import_symbol": "Base",
        "import_alias": None,
    }
    assert dependency.support_count == 2
    assert dependency.conflict_count == 1
    assert dependency.confidence == pytest.approx(2 / 3)
    assert dependency.status is RuleStatus.ACTIVE
    assert dependency.metadata == {
        "concrete_types": ["AlternateClient", "GenericClient"],
        "import_modules": ["clients"],
        "constructor_arguments": (),
        "usage_methods": ["read", "write"],
        "required_invocations": [
            {
                "method_name": "write",
                "argument_shapes": ["string_literal"],
                "supported": True,
                "support_count": 2,
                "conflict_count": 1,
                "confidence": pytest.approx(2 / 3),
                "evidence": [
                    Evidence("a.py", "FirstService", "client").__dict__,
                    Evidence("b.py", "SecondService", "client").__dict__,
                ],
                "active": True,
            }
        ],
        "invocation_evidence": [
            {
                "method_name": "read",
                "argument_shapes": [],
                "supported": True,
                "support_count": 1,
                "conflict_count": 2,
                "confidence": pytest.approx(1 / 3),
                "evidence": [Evidence("a.py", "FirstService", "client").__dict__],
                "active": False,
            },
            {
                "method_name": "write",
                "argument_shapes": ["string_literal"],
                "supported": True,
                "support_count": 2,
                "conflict_count": 1,
                "confidence": pytest.approx(2 / 3),
                "evidence": [
                    Evidence("a.py", "FirstService", "client").__dict__,
                    Evidence("b.py", "SecondService", "client").__dict__,
                ],
                "active": True,
            },
        ],
        "concrete_imports": {
            "GenericClient": {"module": "clients", "symbol": "GenericClient", "alias": None},
            "AlternateClient": {"module": "clients", "symbol": "AlternateClient", "alias": None},
        },
        "type_pattern": "*Client",
    }
