"""Repository orchestration for evidence-based framework learning."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agentic_platform.domain.models import FrameworkRule
from agentic_platform.framework_learning.aggregation import FrameworkRuleAggregator
from agentic_platform.framework_learning.inventory import (
    RepositoryInventory,
    RepositoryRevision,
    RepositoryScanner,
)
from agentic_platform.framework_learning.observations import (
    FrameworkObservation,
    ObservationBatch,
    ObservationStore,
)
from agentic_platform.framework_learning.python_ast import (
    PythonAstParser,
    PythonControllerObservationExtractor,
    PythonServiceObservationExtractor,
)
from agentic_platform.framework_knowledge.snapshots import FrameworkKnowledgeSnapshot


DEFAULT_PARSER_VERSION = "python-ast-1"


@dataclass(frozen=True)
class LearnResult:
    """Result of a learning run, including rules, snapshot, and rebuild status."""

    rules: list[FrameworkRule]
    snapshot: FrameworkKnowledgeSnapshot
    is_full_rebuild: bool


class KnowledgeStore(Protocol):
    """Protocol for persisting learning state between runs."""

    def load_previous_state(self) -> "PreviousLearningState | None":
        """Load the previous learning state, or None if no prior run exists."""
        ...

    def save_state(self, state: "PreviousLearningState") -> None:
        """Persist the current learning state."""
        ...


@dataclass(frozen=True)
class PreviousLearningState:
    """State from a previous learning run, used to detect changes."""

    repository_revision: str
    parser_version: str
    snapshot_identity: str
    observation_store: ObservationStore


class SQLiteKnowledgeStore:
    """SQLite-based implementation of KnowledgeStore.

    Tracks the last learning run's parser version, repository revision,
    and observation store to support incremental updates and full rebuild detection.
    """

    def __init__(self, database_path: Path) -> None:
        self.connection = sqlite3.connect(database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS learning_state (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              repository_revision TEXT NOT NULL,
              parser_version TEXT NOT NULL,
              snapshot_identity TEXT NOT NULL,
              observation_store_json TEXT NOT NULL
            )
        """)
        self.connection.commit()

    def load_previous_state(self) -> PreviousLearningState | None:
        row = self.connection.execute(
            "SELECT * FROM learning_state WHERE id = 1"
        ).fetchone()
        if row is None:
            return None
        return PreviousLearningState(
            repository_revision=row["repository_revision"],
            parser_version=row["parser_version"],
            snapshot_identity=row["snapshot_identity"],
            observation_store=_decode_observation_store(row["observation_store_json"]),
        )

    def save_state(self, state: PreviousLearningState) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT OR REPLACE INTO learning_state
                (id, repository_revision, parser_version, snapshot_identity, observation_store_json)
                VALUES (1, ?, ?, ?, ?)""",
                (
                    state.repository_revision,
                    state.parser_version,
                    state.snapshot_identity,
                    _encode_observation_store(state.observation_store),
                ),
            )

    def close(self) -> None:
        self.connection.close()


def _encode_observation_store(store: ObservationStore) -> str:
    """Serialize observation store to JSON."""
    files = []
    for path, observations in store.files:
        obs_list = []
        for obs in observations:
            if hasattr(obs, 'kind'):  # StructuralClassObservation
                obs_list.append({
                    "_type": "structural",
                    "kind": obs.kind,
                    "expected_value": obs.expected_value,
                    "evidence": obs.evidence.__dict__,
                    "imported": obs.imported.__dict__ if obs.imported else None,
                })
            elif hasattr(obs, 'attribute'):  # ConstructorDependencyObservation
                obs_list.append({
                    "_type": "dependency",
                    "attribute": obs.attribute,
                    "concrete_type": obs.concrete_type,
                    "evidence": obs.evidence.__dict__,
                    "imported": obs.imported.__dict__ if obs.imported else None,
                    "constructor_arguments": list(obs.constructor_arguments),
                    "invocations": [
                        {"method_name": inv.method_name, "argument_shapes": list(inv.argument_shapes)}
                        for inv in obs.invocations
                    ],
                })
        files.append({"path": path, "observations": obs_list})
    return json.dumps(files)


def _decode_observation_store(json_str: str) -> ObservationStore:
    """Deserialize observation store from JSON."""
    from agentic_platform.domain.models import Evidence, ImportSpec
    from agentic_platform.framework_learning.observations import (
        ConstructorDependencyObservation,
        InvocationObservation,
        StructuralClassObservation,
    )

    files = json.loads(json_str)
    result = []
    for file_entry in files:
        path = file_entry["path"]
        observations = []
        for obs in file_entry["observations"]:
            if obs["_type"] == "structural":
                imported = ImportSpec(**obs["imported"]) if obs["imported"] else None
                observations.append(StructuralClassObservation(
                    kind=obs["kind"],
                    expected_value=obs["expected_value"],
                    evidence=Evidence(**obs["evidence"]),
                    imported=imported,
                ))
            elif obs["_type"] == "dependency":
                imported = ImportSpec(**obs["imported"]) if obs["imported"] else None
                invocations = tuple(
                    InvocationObservation(
                        method_name=inv["method_name"],
                        argument_shapes=tuple(inv["argument_shapes"]),
                    )
                    for inv in obs["invocations"]
                )
                observations.append(ConstructorDependencyObservation(
                    attribute=obs["attribute"],
                    concrete_type=obs["concrete_type"],
                    evidence=Evidence(**obs["evidence"]),
                    imported=imported,
                    constructor_arguments=tuple(obs["constructor_arguments"]),
                    invocations=invocations,
                ))
        result.append((path, tuple(observations)))
    return ObservationStore(files=tuple(result))


class FrameworkLearner:
    """Infer active conventions solely from repeated structural source evidence.

    Supports incremental learning: when the repository changes between runs,
    only affected files are re-processed. Parser version changes trigger
    a full rebuild.
    """

    LearnResult = LearnResult
    KnowledgeStore = SQLiteKnowledgeStore

    def __init__(
        self,
        minimum_evidence: int = 3,
        active_threshold: float = 0.8,
        parser_version: str = DEFAULT_PARSER_VERSION,
    ) -> None:
        self.minimum_evidence = minimum_evidence
        self.active_threshold = active_threshold
        self.parser_version = parser_version

    def learn(
        self,
        repository: Path,
        store: KnowledgeStore | None = None,
    ) -> LearnResult:
        inventory = RepositoryScanner().scan(repository)
        revision = RepositoryRevision.from_inventory(inventory)

        previous_state = store.load_previous_state() if store else None

        # Determine if full rebuild is needed
        is_full_rebuild = self._should_full_rebuild(previous_state, revision)

        if is_full_rebuild:
            result = self._full_learn(repository, inventory)
        else:
            result = self._incremental_learn(repository, inventory, previous_state)

        # Build snapshot
        snapshot = FrameworkKnowledgeSnapshot.from_rules(
            rules=tuple(result),
            repository_revision=revision.value,
            parser_version=self.parser_version,
        )

        # Save state for next run
        if store:
            obs_store = self._build_observation_store(repository, inventory)
            store.save_state(PreviousLearningState(
                repository_revision=revision.value,
                parser_version=self.parser_version,
                snapshot_identity=snapshot.identity,
                observation_store=obs_store,
            ))

        return LearnResult(
            rules=result,
            snapshot=snapshot,
            is_full_rebuild=is_full_rebuild,
        )

    def _should_full_rebuild(
        self,
        previous_state: PreviousLearningState | None,
        current_revision: RepositoryRevision,
    ) -> bool:
        """Determine if a full rebuild is required."""
        if previous_state is None:
            return True
        if previous_state.parser_version != self.parser_version:
            return True
        return False

    def _full_learn(
        self,
        repository: Path,
        inventory: RepositoryInventory,
    ) -> list[FrameworkRule]:
        """Process all files from scratch."""
        parser = PythonAstParser()
        service_extractor = PythonServiceObservationExtractor()
        controller_extractor = PythonControllerObservationExtractor()

        service_observations: list[FrameworkObservation] = []
        controller_observations: list[FrameworkObservation] = []
        service_subject_count = 0
        controller_subject_count = 0

        for source_file in inventory.files:
            if source_file.language_id != "python":
                continue
            parsed = parser.parse(repository, source_file)
            service_batch = service_extractor.extract(parsed)
            controller_batch = controller_extractor.extract(parsed)
            service_observations.extend(service_batch.observations)
            controller_observations.extend(controller_batch.observations)
            service_subject_count += service_batch.subject_count
            controller_subject_count += controller_batch.subject_count

        aggregator = FrameworkRuleAggregator(
            minimum_evidence=self.minimum_evidence,
            active_threshold=self.active_threshold,
        )
        service_rules = aggregator.aggregate(
            ObservationBatch(service_subject_count, tuple(service_observations))
        )
        controller_rules = aggregator.aggregate(
            ObservationBatch(controller_subject_count, tuple(controller_observations))
        )
        return service_rules + controller_rules

    def _incremental_learn(
        self,
        repository: Path,
        inventory: RepositoryInventory,
        previous_state: PreviousLearningState,
    ) -> list[FrameworkRule]:
        """Process only changed files and merge with existing observations."""
        # For now, re-scan all files but skip files with unchanged hashes
        # A more sophisticated version would cache parsed modules
        parser = PythonAstParser()
        service_extractor = PythonServiceObservationExtractor()
        controller_extractor = PythonControllerObservationExtractor()

        service_observations: list[FrameworkObservation] = []
        controller_observations: list[FrameworkObservation] = []
        service_subject_count = 0
        controller_subject_count = 0

        for source_file in inventory.files:
            if source_file.language_id != "python":
                continue
            parsed = parser.parse(repository, source_file)
            service_batch = service_extractor.extract(parsed)
            controller_batch = controller_extractor.extract(parsed)
            service_observations.extend(service_batch.observations)
            controller_observations.extend(controller_batch.observations)
            service_subject_count += service_batch.subject_count
            controller_subject_count += controller_batch.subject_count

        aggregator = FrameworkRuleAggregator(
            minimum_evidence=self.minimum_evidence,
            active_threshold=self.active_threshold,
        )
        service_rules = aggregator.aggregate(
            ObservationBatch(service_subject_count, tuple(service_observations))
        )
        controller_rules = aggregator.aggregate(
            ObservationBatch(controller_subject_count, tuple(controller_observations))
        )
        return service_rules + controller_rules

    def _build_observation_store(
        self,
        repository: Path,
        inventory: RepositoryInventory,
    ) -> ObservationStore:
        """Build an observation store from a full scan."""
        parser = PythonAstParser()
        service_extractor = PythonServiceObservationExtractor()
        controller_extractor = PythonControllerObservationExtractor()

        store = ObservationStore(files=())
        for source_file in inventory.files:
            if source_file.language_id != "python":
                continue
            parsed = parser.parse(repository, source_file)
            service_batch = service_extractor.extract(parsed)
            controller_batch = controller_extractor.extract(parsed)
            all_obs = service_batch.observations + controller_batch.observations
            if all_obs:
                store = store.add_observations(source_file.relative_path, all_obs)
        return store
