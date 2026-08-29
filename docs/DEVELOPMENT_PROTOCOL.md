# Development Protocol

Development is organized as a sequence of working milestones toward the accepted
[target production architecture](target-architecture.html).

```text
Target architecture
  → smallest useful milestone
  → implementation + focused tests
  → full deterministic gates
  → working artifact
  → next milestone
```

## Priorities

1. Prefer steady delivery toward the target architecture over process ceremony.
2. Keep every completed milestone executable and backward compatible unless a
   breaking change is explicitly accepted.
3. Use deterministic code for scanning, parsing, persistence, builds, tests,
   policy checks, and repository operations. Use models only where reasoning is
   genuinely needed.
4. Never hard-code customer framework symbols into product source.
5. Do not silently weaken capability, tenant, path, secret, or staging boundaries.

## Milestone acceptance contract

Before a substantial milestone, record its outcome, boundaries, constraints, and
verification commands. A milestone is complete only when concrete tool output
proves the acceptance criteria.

Minimum gates:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
git diff --check
python -m compileall -q src
```

Use the platform-appropriate virtual-environment interpreter on Windows. Run any
focused tests added for the milestone before the full suite. Scan
`src/agentic_platform` for customer-specific fixture symbol leakage when learning,
retrieval, generation, or validation code changes.

## Review policy

Independent maker/checker/fixer agents are optional tools for risky, ambiguous,
security-sensitive, or large parallel changes; they are not a mandatory ritual
for every milestone. Tests and deterministic gates remain mandatory. A failed or
unproven gate blocks claiming completion.

## Long-running development

Use a persistent goal per milestone rather than one unbounded goal for the whole
product. A goal should name:

- the working outcome,
- the command or artifact that proves completion,
- behavior that must not regress,
- directories in scope,
- conditions requiring human input.

Provider fallback and reset-aware cooldowns may keep work moving through model
limits. If all providers are unavailable, preserve repository state and resume the
same milestone after the cooldown; never replace missing execution with fabricated
results.

## Commit and push

Commit only after the milestone gates pass. Push only when explicitly requested or
when the active persistent goal includes publishing as an approved outcome. Always
verify the remote SHA after a push.

The local pre-push hook may use `.hermes/runtime/checker-approval.json` as a
legacy defense-in-depth marker. It does not replace the deterministic gates above.
