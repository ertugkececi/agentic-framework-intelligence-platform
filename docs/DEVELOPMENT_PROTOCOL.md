# Development Protocol

Substantial changes in this repository use the project-local `development-loop` skill.

```text
Acceptance contract → Maker → fresh Checker
  ├─ FAIL / NOT PROVEN → Fixer → fresh Checker (maximum 3 rounds)
  └─ PASS → deterministic gates → commit → approval marker → push
```

## Commit and push gates

A commit/push is allowed only after a fresh checker matrix contains no `FAIL` or `NOT PROVEN`, all deterministic gates pass, and the parent orchestrator has written the local approval marker.

Required gates:

```bash
PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q
git diff --check
```

Additionally scan `src/agentic_platform` for task fixture and customer-framework symbol leakage appropriate to the task.

## Local pre-push guard

This repository configures `core.hooksPath=.githooks`. The committed pre-push hook requires this ignored marker:

```text
.hermes/runtime/checker-approval.json
```

The marker must contain `status: PASS` and a `reviewed_head` equal to the current `HEAD`. A source-changing commit makes the prior marker stale. The hook is defense-in-depth; the primary enforcement remains the fresh Checker and deterministic gates described in the skill.
