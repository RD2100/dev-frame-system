---
name: tdd
description: Red-green-refactor TDD discipline. Use when user says "@tdd", "test-driven development", "write tests first", "red green refactor", or when a task requires TDD workflow. NOT for casual refactoring without test contracts.
---

# tdd - Test-Driven Development Discipline

Role: methodology skill, not runtime executor. `@tdd` enforces red-green-refactor discipline for every change that has an observable contract.

## State Machine

```
human_gate
  -> red (failing test)
  -> green (minimal implementation)
  -> refactor (clean up under green)
  -> reviewer
  -> finalizer
```

Every TDD cycle MUST complete all states. Skipping `red` or `reviewer` is a hard stop.

## Evidence Contract

Each `@tdd` run must produce a run evidence directory containing:

| File | Producer | Purpose |
|------|----------|---------|
| `test-<name>.py` | executor/fixer | Failing test before implementation |
| `implementation.py` | executor/fixer | Minimal code to pass the test |
| `test-output.md` | tester | Command output and exit codes |
| `chain-evidence.json` | orchestrator/harness | Role/session/model chain |
| `review.md` | reviewer only | Human-readable review |
| `review.yaml` | reviewer only | Machine-readable review verdict |
| `final-report.md` | finalizer only | Deterministic summary |

`executor` and `fixer` must not write `review.md` or `review.yaml`.
`finalizer` must not substitute for reviewer judgment.

## Reviewer Rules

The reviewer must:

- Run tests in a separate session/model identity from the executor/fixer.
- Read `test-<name>.py`, `implementation.py`, `test-output.md`, and `chain-evidence.json`.
- Treat executor logs/reports as claims, not facts.
- Produce both `review.md` and `review.yaml`.
- Block if any P0/P1 finding is unresolved.

Minimum `review.yaml`:

```yaml
reviewer_role: reviewer
reviewer_id: "<session-or-agent-id>"
executor_id: "<executor-session-or-agent-id>"
verdict: pass | blocked | fail | escalate
reviewed_inputs:
  - test-<name>.py
  - implementation.py
  - test-output.md
  - chain-evidence.json
findings:
  - id: finding-001
    severity: P0 | P1 | P2 | P3
    status: open | resolved | false_positive
    title: "short finding"
```

## Workflow

1. Gate 0: check `AGENTS.md`, rules, mode/profile, and TaskSpec `allow_write`.
2. Red: write a failing test that captures the next observable behavior.
3. Green: write the minimal implementation to pass the test.
4. Refactor: clean code under green; do not change behavior.
5. Tester: run commands; write `test-output.md`.
6. Reviewer: dispatch a separate reviewer session; write `review.md` and `review.yaml`.
7. Finalizer: run deterministic artifact validation.
8. Verdict: `passed` only if guard, reviewer, and evidence validation all pass.

## P0 Hard Stops

| # | Rule |
|---|------|
| 1 | No implementation before a failing test |
| 2 | No destructive git without human approval |
| 3 | No secrets in code, logs, or reports |
| 4 | No command injection or path traversal |
| 5 | No fake green |
| 6 | No pass without independent `review.yaml` |
| 7 | No pass with unresolved P0/P1 findings |

Full protocol: `docs/agent-runtime/sub-agent-dispatch-protocol.md`
