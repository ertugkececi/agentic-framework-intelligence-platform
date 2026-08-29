# Milestone 2 — Expanded Python Intelligence Acceptance Contract

Milestone 2 expands framework learning beyond the original service-only vertical
slice. Expansion must remain evidence-driven and must not embed symbols from any
sample or customer framework in product source.

## Delivery strategy

Milestone 2 is delivered through vertical slices. A new artifact family is not
considered supported merely because the learner emits a rule. Each slice must
connect the complete development path:

```text
typed task
→ source inventory and parsing
→ typed framework observations
→ rule aggregation and persistence
→ scoped context retrieval
→ structured change generation
→ deterministic compliance validation
→ build and test gates
```

## Milestone 2A — Typed observation boundary

Purpose: separate language-specific Python AST extraction from language-neutral
rule aggregation.

Acceptance criteria:

- Observation records are immutable and typed.
- Observation records contain no `ast` nodes.
- Python extraction maps `ParsedPythonModule` instances to observations.
- Rule aggregation consumes observations rather than nested untyped tuples.
- Existing rule kinds, metadata, evidence, confidence and status remain compatible.
- `FrameworkLearner.learn(repository)` remains backward compatible.
- Invalid Python and repository boundary behavior remain unchanged.

## Milestone 2B — Generic artifact-family context

Purpose: remove service-specific assumptions from the internal context boundary
before adding a second artifact family.

Acceptance criteria:

- A typed artifact-family context represents structure, imports and dependencies.
- Existing service context is expressible without losing information.
- Existing service generation and validation behavior remains unchanged.
- Missing and ambiguous required rules fail closed.
- No artifact-family name is inferred from customer-specific vocabulary.

## Milestone 2C — First additional Python artifact family

The first additional family will be selected from generic structural evidence,
not product-source symbol lists. Its delivery must include:

- Deterministic task parsing
- Repeated-source observation and confidence thresholds
- Version-compatible rule persistence
- Family-scoped context retrieval
- Structured generated changes
- AST compliance validation
- Focused end-to-end tests with at least two distinct synthetic framework styles
- Mutation proof showing that framework symbols come from repository evidence

## Remaining Milestone 2 slices

After the first additional family proves the reusable path, apply the same
vertical approach to:

- Repository/query conventions
- DTO/model/entity mapping conventions
- Exception conventions
- Validation conventions
- Transaction boundaries
- Test naming, fixture and assertion conventions

## Global gates

Every slice must pass:

```text
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src
git diff --check
```

Additional mandatory checks:

- No customer/sample framework symbol leaks in `src/agentic_platform`.
- No weakening of capability, repository-root, staging or publish boundaries.
- No implicit learning during development execution.
- No arbitrary shell command surface.
- Generated changes remain structured and are validated before publication.
