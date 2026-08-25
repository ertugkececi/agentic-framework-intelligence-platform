---
name: development-loop
description: Run maker-checker-fixer gates before substantial changes.
version: 0.1.0
author: Ertuğ Keleşeci (ertugkececi), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [development, maker, checker, review, quality]
    related_skills: []
---

# Maker → Checker → Fixer Development Loop

Use this protocol for every substantial repository change. The parent session is the orchestrator; it does not act as the sole implementer and approver. This protocol does not replace user authorization for external effects.

## When to Use

- New features, behavior changes, refactors, bug fixes, security changes, or workflow changes.
- Do not use for a read-only explanation or a trivial documentation typo with no behavioral effect.

## Acceptance Contract

Before implementation, state: baseline commit, acceptance criteria, architecture invariants, known constraints, required tests, and source-leak tokens. A criterion is only **PASS**, **FAIL**, or **NOT PROVEN**; NOT PROVEN blocks commit.

## Procedure

1. **Maker** — dispatch an isolated `delegate_task` child with the original request, baseline, acceptance contract, and constraints. It changes code/tests and runs focused tests. It must not commit or push. Require this format:

   ```text
   MAKER RESULT
   Files Changed:
   Tests Added:
   Tests Run:
   Known Limitations:
   Ready For Checker: YES
   ```

2. **Fresh Checker** — dispatch a new isolated child. Give it the original request, acceptance contract, invariants, baseline/diff, and current worktree; do not treat Maker narrative as evidence. The Checker reads source, tests, fixtures, and execution results adversarially. It must return:

   ```text
   CHECKER RESULT: PASS | FAIL
   Acceptance Matrix:
   - <criterion>: PASS | FAIL | NOT PROVEN
   Critical Findings:
   - ...
   Adversarial Tests:
   - positive / negative / counterexample / mutation
   Regression Risk:
   - ...
   Commit Allowed: YES | NO
   ```

3. **Fixer** — on FAIL or NOT PROVEN, dispatch a focused child with only actionable checker findings. It must not commit or push.

4. **Fresh Checker again** — never reuse a checker context after a fix. Repeat Maker/Fixer → fresh Checker at most three rounds. At round three failure: stop, do not commit/push, report blockers.

5. **Deterministic gates after PASS** — the parent runs `PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q`, `git diff --check`, configured linters if present, and product-source leak scans. Every named token must have zero hits in `src/`.

6. **Approval marker and publish** — write `.hermes/runtime/checker-approval.json` with `status: PASS`, `reviewed_head` equal to `git rev-parse HEAD`, test/gate booleans, and UTC timestamp. The local pre-push hook rejects a missing/stale marker. Parent alone commits, then updates the marker for that commit, pushes, and verifies remote SHA.

## Checker Focus

Attack semantic inversions with truth tables: test both condition true and false, plus counterexamples and mutation. Confirm wiring through production graph, not only unit helpers. Check durable framework rules are not confused with transient task candidates; development does not learn implicitly; model returns only `GeneratedChange`; writes use validation then capability checks; repair invokes `repair_change`, not initial generation.

## Pitfalls

- A green test suite is not evidence if test and implementation encode the same wrong expectation.
- A Maker summary is not checker evidence.
- Do not commit when any acceptance row is NOT PROVEN.
- The marker is intentionally ignored and HEAD-bound; any new commit invalidates it.

## Verification

- Checker output says PASS and `Commit Allowed: YES`.
- Full tests, diff check, and leak scans pass.
- `.hermes/runtime/checker-approval.json` matches the final local HEAD.
- `git ls-remote --heads origin main` matches local HEAD after push.
