"""Aggregate language-neutral source observations into framework rules."""
from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict, Iterable

from agentic_platform.domain.models import Evidence, FrameworkRule, ImportSpec, RuleStatus
from agentic_platform.framework_learning.observations import (
    ConstructorDependencyObservation,
    ObservationBatch,
    StructuralClassObservation,
)


_SUPPORTED_ARGUMENT_SHAPES = {
    "string_literal",
    "integer_literal",
    "float_literal",
    "boolean_literal",
    "none_literal",
    "empty_mapping",
    "empty_sequence",
}


class FrameworkRuleAggregator:
    """Infer framework rules from normalized observations."""

    def __init__(self, minimum_evidence: int = 3, active_threshold: float = 0.8) -> None:
        self.minimum_evidence = minimum_evidence
        self.active_threshold = active_threshold

    def aggregate(self, batch: ObservationBatch) -> list[FrameworkRule]:
        grouped: DefaultDict[str, DefaultDict[object, list[object]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for observation in batch.observations:
            if isinstance(observation, StructuralClassObservation):
                imported = observation.imported
                key = (
                    observation.expected_value,
                    imported.module if imported else "",
                    imported.symbol if imported else observation.expected_value,
                    imported.alias if imported else None,
                )
                grouped[observation.kind][key].append(observation)
            else:
                grouped["dependency.constructor"][observation.attribute].append(observation)

        rules = []
        for kind, values in grouped.items():
            for key, entries in values.items():
                if kind == "dependency.constructor":
                    rules.append(self._dependency_rule(str(key), entries, batch.subject_count))
                else:
                    rules.append(self._structure_rule(kind, key, entries, batch.subject_count))
        return rules

    def _dependency_rule(
        self, attribute: str, entries: list[object], subject_count: int
    ) -> FrameworkRule:
        observations = [item for item in entries if isinstance(item, ConstructorDependencyObservation)]
        evidence = tuple(item.evidence for item in observations)
        concrete_types = sorted({item.concrete_type for item in observations})
        import_modules = sorted({item.imported.module for item in observations if item.imported})
        constructor_argument_shapes = sorted({item.constructor_arguments for item in observations})
        invocations = sorted(
            {
                (invocation.method_name, invocation.argument_shapes)
                for item in observations
                for invocation in item.invocations
            }
        )
        invocation_evidence = [
            self._invocation_requirement(invocation, observations, subject_count)
            for invocation in invocations
        ]
        metadata = {
            "concrete_types": concrete_types,
            "import_modules": import_modules,
            "constructor_arguments": constructor_argument_shapes[0]
            if len(constructor_argument_shapes) == 1
            else (),
            "usage_methods": sorted({method_name for method_name, _ in invocations}),
            "required_invocations": [item for item in invocation_evidence if item["active"]],
            "invocation_evidence": invocation_evidence,
            "concrete_imports": {
                item.concrete_type: self._import_metadata(item.imported)
                for item in observations
                if item.imported is not None
            },
            "type_pattern": self._suffix(concrete_types),
        }
        return self._rule(
            "dependency.constructor", attribute, evidence, metadata, subject_count
        )

    def _invocation_requirement(
        self,
        invocation: tuple[str, tuple[str, ...]],
        entries: list[ConstructorDependencyObservation],
        subject_count: int,
    ) -> dict[str, object]:
        method_name, argument_shapes = invocation
        evidence = [
            item.evidence
            for item in entries
            if invocation
            in {(call.method_name, call.argument_shapes) for call in item.invocations}
        ]
        support_count = len(evidence)
        confidence = support_count / subject_count if subject_count else 0.0
        active = (
            support_count >= self.minimum_evidence
            and confidence >= self.active_threshold
        )
        return {
            "method_name": method_name,
            "argument_shapes": list(argument_shapes),
            "supported": all(shape in _SUPPORTED_ARGUMENT_SHAPES for shape in argument_shapes),
            "support_count": support_count,
            "conflict_count": subject_count - support_count,
            "confidence": confidence,
            "evidence": [item.__dict__ for item in evidence],
            "active": active,
        }

    def _structure_rule(
        self, kind: str, key: object, entries: list[object], subject_count: int
    ) -> FrameworkRule:
        expected_value, import_module, import_symbol, import_alias = key  # type: ignore[misc]
        evidence = tuple(
            item.evidence for item in entries if isinstance(item, StructuralClassObservation)
        )
        metadata = (
            {
                "import_module": import_module,
                "import_symbol": import_symbol,
                "import_alias": import_alias,
            }
            if import_module
            else {}
        )
        return self._rule(kind, expected_value, evidence, metadata, subject_count)

    def _rule(
        self,
        kind: str,
        expected_value: str,
        evidence: tuple[Evidence, ...],
        metadata: dict[str, object],
        subject_count: int,
    ) -> FrameworkRule:
        support_count = len(evidence)
        confidence = support_count / subject_count if subject_count else 0.0
        status = (
            RuleStatus.ACTIVE
            if support_count >= self.minimum_evidence and confidence >= self.active_threshold
            else RuleStatus.CANDIDATE
        )
        return FrameworkRule(
            kind=kind,
            expected_value=expected_value,
            confidence=confidence,
            support_count=support_count,
            conflict_count=subject_count - support_count,
            evidence=evidence,
            metadata=metadata,
            status=status,
        )

    @staticmethod
    def _import_metadata(imported: ImportSpec) -> dict[str, str | None]:
        return {"module": imported.module, "symbol": imported.symbol, "alias": imported.alias}

    @staticmethod
    def _suffix(types: Iterable[str]) -> str | None:
        values = list(types)
        if len(values) < 2:
            return None
        suffix = values[0]
        for value in values[1:]:
            while suffix and not value.endswith(suffix):
                suffix = suffix[1:]
        return f"*{suffix}" if len(suffix) >= 4 and suffix[0].isupper() else None
