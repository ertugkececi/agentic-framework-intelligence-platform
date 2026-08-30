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

### Milestone 6A — Explicit planning and review nodes — COMPLETE

Delivered:

- Immutable, provider-neutral change plan and review contracts
- Explicit LangGraph planning node between bounded retrieval and implementation
- Rule-kind and normalized target-path provenance in the minimum change plan
- Explicit review node after deterministic build, test and compliance gates
- Fail-closed planner/reviewer adapter failures and rejected reviews
- Review rejection proof that the customer repository remains byte-identical
- Backward-compatible deterministic planner and reviewer defaults

Verification:

```text
RED: development planning/review module import failed during focused test collection
focused planning/review tests: 4 passed, 1 warning
complete suite: 208 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 6B — Bounded review repair loop — COMPLETE

Delivered:

- Review rejections routed through the shared bounded repair loop
- Typed review failure context supplied to the coding model
- Shared retry budget across build, test, compliance and review failures
- Redacted and size-bounded review feedback history
- Retry-budget-derived LangGraph recursion limit that permits clean bounded exhaustion
- Reviewer adapter failures remain fail-closed and do not enter repair

Verification:

```text
RED: rejected review terminated without repair feedback
focused planning/review and orchestration tests: 11 passed, 1 warning
complete suite: 209 passed, 1 warning
```

### Milestone 6C — Persistent development checkpoints — COMPLETE

Delivered:

- Disk-backed LangGraph SQLite checkpoints for every authorized development run
- Caller-supplied or generated run IDs mapped to isolated checkpoint thread IDs
- Workspace-local checkpoint database with deterministic location
- Graph compilation against the production-compatible checkpointer port
- Capability grants and factory-issued staging authorizations kept out of persisted graph state
- Backward-compatible returned authorization evidence for lifecycle security assertions

Verification:

```text
RED: DevelopmentService rejected the run_id checkpoint contract
focused persistent-checkpoint test: 1 passed, 1 warning
complete suite: 210 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 6D — Human approval interrupts — COMPLETE

Delivered:

- Typed, bounded human approval request and decision contracts
- Policy-driven LangGraph interrupt before model generation
- Durable `needs_human_review` state keyed by development run ID
- Explicit approved/rejected resume operation with actor and reason provenance
- Fresh capability and staging authorization checks on every resume
- Cross-process resume from SQLite checkpoints without persisting runtime authority
- Fail-closed rejection before generation and publish
- Disposable staging preservation while pending and cleanup after terminal decisions

Verification:

```text
RED: HumanApprovalDecision import failed during focused test collection
focused human-approval/planning/checkpoint tests: 8 passed, 1 warning
complete suite: 212 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 6E — Reproducible run identity and artifact records — COMPLETE

Delivered:

- Immutable, content-addressed development run records
- Input identity pinned to run ID, repository revision, task hash, model identity and retry policy
- Deterministic selected-rule identities for knowledge replay provenance
- Generated artifact path, SHA-256 content hash and byte-size records
- SQLite audit adapter with payload identity verification on read
- Fail-closed run-ID reuse for different inputs
- Repository-revision validation before human-approval resume
- Terminal and interrupted run record persistence alongside LangGraph checkpoints

Verification:

```text
RED: development run record module import failed during focused test collection
focused run-record/checkpoint/approval/planning tests: 10 passed, 1 warning
complete suite: 214 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

## Milestone 7 — Security and isolation — COMPLETE

### Milestone 7A — Immutable capability grant foundation — COMPLETE

Delivered:

- Defensive capability snapshots that cannot inherit later caller mutations
- Runtime rejection of untyped capability values
- Canonical repository-root binding at grant construction
- Shared immutable grant semantics across orchestration and repository/build/test adapters

Verification:

```text
RED: mutable capability input expanded an existing grant; string capabilities were accepted
focused capability and safe-execution tests: 26 passed, 1 warning
complete suite: 216 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 7B — PostgreSQL production adapter capability enforcement — COMPLETE

Delivered:

- Mandatory typed capability grants for PostgreSQL adapter construction
- Database-write authorization before schema initialization or DSN connection
- Independent database-read and database-write enforcement per adapter operation
- Combined read/write authorization for atomic rule lifecycle transitions
- Fail-closed denial before transactions, cursors, dependency loading or network access

Verification:

```text
RED: PostgreSQL adapter rejected the grant contract; unauthorized DSN creation attempted network access
focused PostgreSQL capability/review/lifecycle tests: 15 passed
complete suite: 219 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 7C — Qdrant production adapter capability enforcement — COMPLETE

Delivered:

- Mandatory typed capability grants for Qdrant adapter construction
- Vector-database write authorization before collection initialization
- Independent database-read authorization for semantic search
- Database-write authorization for vector upsert and scoped source deletion
- URL factory denial before transport construction for invalid or insufficient grants
- Fail-closed denial before validation, transport calls or network access

Verification:

```text
RED: Qdrant adapter rejected the grant contract; unauthorized initialization and operations reached the transport boundary
focused Qdrant capability/store/retrieval tests: 9 passed
complete suite: 222 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 7D — Detached Git worktree staging — COMPLETE

Delivered:

- Service-owned staging sandbox lifecycle abstraction
- Clean Git repositories executed in detached disposable worktrees pinned to `HEAD`
- Non-Git and dirty-repository compatibility through the existing disposable-copy backend
- Canonical workspace and repository boundary checks before staging creation
- Symlink and nested-workspace rejection before repository copying
- Worktree registration pruning and staging-directory cleanup after terminal runs
- Development-service integration proving build execution occurs in the detached worktree

Verification:

```text
RED: staging sandbox module import failed during focused test collection
focused sandbox and safe-execution tests: 28 passed, 1 warning
complete suite: 226 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 7E — Container-backed command execution — COMPLETE

Delivered:

- Immutable Docker/Podman execution configuration with digest-pinned OCI images
- Fixed build and test commands with explicit entrypoint replacement
- Network-disabled, read-only-root containers with all Linux capabilities dropped
- No-new-privileges, CPU, memory, PID, timeout and output bounds
- Exact disposable staging bind mount with service-issued authorization enforcement
- Capability and repository checks before runtime discovery or process execution
- Development-service integration with host/container runner conflict rejection
- Fail-closed invalid runtime, image, mount and configuration handling

Verification:

```text
RED: container execution module import failed; DevelopmentService rejected the container runner contract
focused container/sandbox/safe-execution tests: 41 passed, 1 warning
complete suite: 239 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 7F — Tenant-bound RBAC grants — COMPLETE

Delivered:

- Immutable authenticated principals bound to exactly one tenant
- Typed viewer, developer, knowledge-admin and platform-admin roles
- Fail-closed role-to-capability authorization at grant construction
- Mandatory principal identity on every capability grant
- Tenant-scope checks before PostgreSQL transactions and Qdrant transport access
- Cross-tenant structured and semantic write/read denial
- Explicit local operator identity retained for infrastructure-free adapters

Verification:

```text
RED: Principal and Role imports failed; production adapters accepted cross-tenant scopes
focused tenant/RBAC and production-adapter tests: 30 passed
complete suite: 245 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 7G — Secret-reference and redaction foundation — COMPLETE

Delivered:

- Immutable identifier-only secret references for external providers
- Strict provider, path, key and optional version validation
- Shared redactor for explicitly resolved values and common credential structures
- Deterministic longest-value-first masking without retaining mutable caller input
- Centralized development failure, review and validation redaction
- Backward-compatible orchestration behavior with focused regression coverage

Verification:

```text
RED: secret-reference/redaction module import failed during focused test collection
focused secret/redaction and safe-execution tests: 28 passed, 1 warning
complete suite: 248 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 7H — Secret resolution and egress enforcement — COMPLETE

Delivered:

- Provider-neutral secret resolver port accepting identifier-only references
- Fail-closed resolved-value validation and sanitized provider failures
- Exact-origin HTTP(S) egress policy with canonical origin validation
- Egress authorization before secret resolution or transport access
- OpenAI-compatible model integration resolving credentials only at the transport boundary
- Secret values excluded from model prompt bodies
- Backward-compatible direct-key support with mixed credential configuration rejection
- Composition-root injection for secret resolvers and egress policies

Verification:

```text
RED: secret resolution and egress policy module import failed during focused test collection
focused secret-resolution/redaction/model tests: 21 passed
complete suite: 254 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 7I — Resource and time quotas — COMPLETE

Delivered:

- Immutable per-run wall-clock, model-call, command-execution and generated-byte limits
- Checkpoint-safe cumulative resource usage across generation and bounded repair attempts
- Wall-clock enforcement before model, staging, command, compliance, review and publish boundaries
- Model-call exhaustion before provider construction or repair invocation
- Command quota enforcement before build/test runner invocation
- Generated-byte rejection before staging apply, checkpoint payload retention or customer publication
- Fail-closed quota termination with disposable staging cleanup and byte-identical customer repositories

Verification:

```text
RED: development quota module import failed during focused test collection
focused quota/approval/orchestration tests: 17 passed, 1 warning
complete suite: 263 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

## Milestone 8 — Model gateway, observability and deployment

### Milestone 8A — Native Anthropic production model adapter — COMPLETE

Delivered:

- Native Anthropic Messages API adapter behind the existing provider-neutral coding-model port
- Typed provider settings with bounded output tokens, timeout and API-version validation
- Translation of provider-neutral system/user prompts into the native Messages contract
- Structured response translation into the shared generated-change domain contract
- Secret-reference resolution only after exact-origin egress authorization
- Composition-root routing between OpenAI-compatible and native Anthropic adapters
- Dependency-free standard-library transport reuse with sanitized failure boundaries

Verification:

```text
RED: Anthropic adapter module import failed during focused test collection
focused Anthropic/OpenAI/secret-egress tests: 22 passed
complete suite: 267 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 8B — Native local/air-gapped inference adapter — COMPLETE

Delivered:

- Native non-streaming local chat API adapter behind the provider-neutral coding-model port
- Credential-free settings for on-premise and air-gapped inference endpoints
- Deterministic JSON-mode generation with bounded output tokens and timeout
- Shared provider-neutral generation and bounded repair prompts
- Typed response translation into the shared generated-change contract
- Exact-origin egress enforcement before local inference transport access
- Composition-root routing alongside OpenAI-compatible and native Anthropic adapters

Verification:

```text
RED: local inference adapter module import failed during focused test collection
focused local/OpenAI/Anthropic/egress tests: 24 passed
complete suite: 269 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

### Milestone 8C — Task-based model routing — COMPLETE

Delivered:

- Provider-neutral coding-model router keyed by immutable task artifact family
- Explicit multi-family route declarations for shared specialist models
- Deterministic generation and repair routing through the same task classification
- Optional explicit default model for general-purpose tasks
- Fail-closed unmatched-task behavior when no default is configured
- Startup rejection for empty, malformed and overlapping route declarations

Verification:

```text
RED: task model routing module import failed during focused test collection
focused task-routing/model-adapter tests: 27 passed
complete suite: 272 passed, 1 warning
python -m compileall -q src: PASS
git diff --check: PASS
customer-symbol leak scan: 0 match
security pattern scan: 0 match
```

Remaining:

- OpenTelemetry traces, metrics and audit replay
- Kubernetes deployment with PostgreSQL and Qdrant

## Global completion gates

Every milestone must preserve:

- No customer-specific framework symbols in product source
- Deterministic parsing, validation and repository operations
- Bounded model context and retry behavior
- Existing security/path/staging constraints
- A passing complete test suite
