# Target Architecture Delivery Roadmap

The accepted production target is documented in:

- [Interactive architecture diagram](target-architecture.html)
- [SVG architecture diagram](target-architecture.svg)
- [PNG architecture diagram](target-architecture.png)
- [Detailed architecture](../ARCHITECTURE.md)

Development proceeds as a sequence of executable milestones. A milestone is done
only when its focused tests and the complete regression suite pass.

## Milestone 1 — Generic learning foundation — COMPLETE

Delivered:

- Immutable repository source inventory
- Relative POSIX source identities
- SHA-256 content hashes and byte sizes
- Deterministic source ordering and scan exclusions
- Symlink boundary protection
- Typed language parser port
- Python AST parser adapter
- Path-bearing parse errors
- Existing `FrameworkLearner` integration without public API breakage

Verification:

```text
82 passed
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: PASS
security pattern scan: PASS
```

Known boundary: inventory is rebuilt on every learning run; changed/deleted-file
processing belongs to Milestone 3.

## Milestone 2 — Expanded Python framework intelligence — COMPLETE

Outcome: move beyond the narrow `*Service` vertical slice while retaining generic,
evidence-based rule discovery.

### Milestone 2A — Typed observation boundary — COMPLETE

Delivered:

- Immutable language-neutral observation records
- Python AST-to-observation extraction boundary
- Dedicated observation-to-rule aggregation boundary
- `FrameworkLearner` reduced to repository orchestration
- Python AST responsibilities isolated in the Python adapter
- Multi-module subject counting and deterministic rule ordering
- Backward-compatible evidence, metadata, confidence and status semantics

Verification:

```text
focused architecture/parser/observation tests: 8 passed
complete suite: 87 passed
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: PASS
security pattern scan: PASS
```

### Milestone 2B — Generic artifact-family context — COMPLETE

Delivered:

- Immutable `ArtifactStructureContext`
- Generic artifact family, base-class, decorator, import and dependency context
- Backward-compatible positional and keyword `CodingContext` construction
- Legacy service properties retained as compatibility projections
- Family-scoped structural rule retrieval
- Generic prompt payload with temporary service compatibility fields
- Deterministic generator driven by generic structure
- Shared fail-closed validation for family mismatch and incomplete structure

Verification:

```text
focused artifact-structure tests: 8 passed
complete suite: 95 passed
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: PASS
security pattern scan: PASS
```

### Milestone 2C — First additional Python artifact family — COMPLETE

Delivered:
- Task parser: `Create <Name>Controller [with method name(parameters)]` grammar with `artifact_type='controller'`
- `PythonControllerObservationExtractor` — `controller.base_class` and `controller.required_decorator` rule kinds
- `retrieve_controller_context()` — controller counterpart of the service path
- Generic task-aware orchestration (`_retrieve` and `_empty_task_requires_invocation` family-aware)
- Generic compliance validator covering both families; `validate_service` retained as backward-compatible wrapper
- Deterministic generator with generic structure render for both families
- Two synthetic Controller framework styles (BaseController/controller_decorator + Base/managed)
- Runtime symbol-mutation proof: `FrameworkComponent → DomainUnit` re-learn path

Verification:
```text
complete suite: 115 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

## Milestone 3 — Incremental learning and snapshots — COMPLETE

Delivered:

- `RepositoryRevision` — content-addressed inventory identity
- `InventoryDiff` — added/changed/deleted file detection from inventory hashes
- `ObservationStore` — file-keyed immutable observation store with replace/add/remove
- `InventoryDiff.apply_diff()` — replace-not-append observation updates
- `DependencyGraph` + `ImpactAnalysis` — cross-file dependency tracking and transitive impact
- `FrameworkKnowledgeSnapshot` — immutable, content-addressed knowledge snapshots
- `SnapshotMetadata` — revision, parser version, rule count, timestamp
- `FrameworkLearner.parser_version` — parser-version-triggered full rebuilds
- `LearnResult` — structured learning result with `is_full_rebuild` flag
- `SQLiteKnowledgeStore` — persists learning state between runs
- `ObservationStore` JSON serialization for persistence

Verification:

```text
focused revision/diff tests: 17 passed
focused incremental observation tests: 9 passed
focused snapshot tests: 10 passed
focused parser-version rebuild tests: 6 passed
focused dependency impact analysis tests: 10 passed
complete suite: 167 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

## Milestone 4 — Versioned structured knowledge

### Milestone 4A — Tenant and version scope boundary — COMPLETE

Delivered:

- Immutable `KnowledgeScope` for Customer → Framework → Framework Version → Project → optional Module
- Scope-bearing framework rules with backward-compatible unscoped construction
- Scope-isolated SQLite replacement and active-rule retrieval
- In-place SQLite schema migration for existing local knowledge databases
- Scope-aware snapshot identities that cannot collide across tenants
- Fail-closed unscoped retrieval that cannot expose scoped rules

Verification:

```text
RED: KnowledgeScope import failed; scope-insensitive snapshot identity and implicit scoped-write assertions failed
focused scope/snapshot tests: 15 passed
complete suite: 172 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 4B — PostgreSQL + JSONB production adapter — COMPLETE

Delivered:

- Shared typed `RuleKnowledgeStore` port for local and production adapters
- PostgreSQL 16 schema with JSONB rule values, evidence and metadata
- Lazy psycopg connection factory with mapping-row configuration
- Atomic scope replacement and deterministic active-rule retrieval
- Mandatory complete production scope for fail-closed tenant isolation
- Scope-specific repository revision metadata with null-safe module uniqueness
- SQLite retained as the infrastructure-free local adapter

Verification:

```text
RED: PostgresKnowledgeStore module import failed
focused PostgreSQL adapter tests: 4 passed
focused structured-knowledge tests: 19 passed
complete suite: 176 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 4C — Rule provenance and review history — COMPLETE

Delivered:

- Typed support/conflict evidence polarity with invalid-value rejection
- Complete rule-origin vocabulary including imported knowledge
- Immutable approve/reject/edit review records with validated actor and edit replacement
- Append-only, tenant/version-scoped review history in SQLite and PostgreSQL adapters
- PostgreSQL JSONB replacement payloads and deterministic chronological retrieval
- Review persistence port shared by local and production stores

Verification:

```text
RED: EvidencePolarity import failed during focused test collection
focused provenance/review and structured-store tests: 13 passed
complete suite: 180 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 4D — Rule lifecycle — COMPLETE

Delivered:

- Complete candidate/active/rejected/superseded/deprecated status vocabulary
- Typed rule status and origin normalization at the domain boundary
- Explicit irreversible lifecycle transition policy with terminal-state protection
- Atomic, scope-isolated transitions in SQLite and PostgreSQL adapters
- PostgreSQL row locking for concurrent lifecycle decisions
- Fail-closed missing, ambiguous and unscoped rule transitions
- Shared lifecycle transition operation on the structured knowledge store port

Verification:

```text
RED: lifecycle vocabulary and transition store operation tests failed
focused lifecycle/structured-store tests: 17 passed
complete suite: 184 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

## Milestone 5 — Semantic code and documentation retrieval

### Milestone 5A — Scoped source/document chunk model — COMPLETE

Delivered:

- Immutable source and document chunk contract
- SHA-256 content hashes and deterministic content-addressed chunk identities
- Mandatory Customer → Framework → Framework Version → Project → optional Module scope
- Provider-neutral filter metadata for tenant/version-safe vector retrieval
- Repository revision, relative POSIX path, line span, language and symbol provenance
- Fail-closed source metadata, path and line-boundary validation
- Cross-tenant and cross-location identity isolation

Verification:

```text
RED: semantic chunk module import failed during focused test collection
focused semantic chunk tests: 9 passed
complete suite: 193 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 5B — Qdrant production adapter — COMPLETE

Delivered:

- Provider-neutral typed semantic-vector store port
- Dependency-free Qdrant REST transport with validated endpoint, timeout and optional API key
- Deterministic UUID mapping for content-addressed chunk identities
- Dimension and finite-value validation before vector writes
- Complete source/document payloads with mandatory tenant/version/project/module metadata
- Scope- and path-filtered source deletion with null-safe module handling
- Fail-closed collection names, source paths and transport failures

Verification:

```text
RED: QdrantSemanticStore module import failed during focused test collection
focused Qdrant adapter tests: 3 passed
complete suite: 196 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 5C — Metadata-filtered semantic retrieval — COMPLETE

Delivered:

- Provider-neutral typed semantic match and search contract
- Qdrant similarity search with mandatory Customer → Framework → Framework Version → Project → optional Module filters
- Optional source/document kind filtering
- Query dimension, finite-value and positive-limit validation before transport
- Null-safe module isolation
- Typed semantic chunk reconstruction with content-addressed identity validation
- Fail-closed malformed, tampered and cross-scope response handling

Verification:

```text
RED: SemanticMatch import failed during focused test collection
focused Qdrant retrieval and adapter tests: 6 passed
complete suite: 199 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 5D — Representative example mining — COMPLETE

Delivered:

- Provider-neutral semantic-match to `CodeExample` mining boundary
- Mandatory tenant/version/project/module scope validation before context admission
- Source-only and symbol-bearing representative example enforcement
- Deterministic similarity ordering and source-symbol deduplication
- Bounded result size with bounded duplicate-candidate overfetch
- Semantic score and selection-reason provenance
- Fail-closed malformed, non-finite and cross-scope candidate handling

Verification:

```text
RED: representative example mining module import failed during focused test collection
focused example-mining and semantic retrieval tests: 18 passed
complete suite: 202 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 5E — Bounded coding-context assembly — COMPLETE

Delivered:

- Provider-neutral production assembly boundary for structured and semantic stores
- Scope-filtered artifact and dependency rule retrieval
- Rule-authoritative structure and dependency constraints
- Semantically ranked, bounded representative examples
- Preservation of task-aware unresolved dependency candidates
- Fail-closed cross-scope structured-rule validation before semantic retrieval
- Service and controller artifact-family routing with unsupported-family rejection

Verification:

```text
RED: coding-context assembly module import failed during focused test collection
focused assembly/retrieval/regression tests: 18 passed, 1 warning
complete suite: 204 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

## Milestone 6 — Production LangGraph development engine

- Explicit planning and review nodes
- Bounded repair loops
- Persistent checkpoints
- Human approval interrupts
- Reproducible run identity and artifact records

## Milestone 7 — Security and isolation

- Immutable capability grants across every adapter
- Sandboxed worktrees/containers
- Tenant boundaries and RBAC
- Secret references, egress policy and redaction
- Resource and time quotas

## Milestone 8 — Model gateway, observability and deployment

- Provider-neutral production model adapters
- Local/air-gapped inference
- Task-based model routing
- OpenTelemetry traces, metrics and audit replay
- Kubernetes deployment with PostgreSQL and Qdrant

## Global completion gates

Every milestone must preserve:

- No customer-specific framework symbols in product source
- Deterministic parsing, validation and repository operations
- Bounded model context and retry behavior
- Existing security/path/staging constraints
- A passing complete test suite
