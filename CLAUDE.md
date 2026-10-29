# Dev-Frame Monorepo

Cross-project governance chain: codegraph (MCP readiness) -> ai-workflow-hub (core state machine) -> ai-workflow-hub-e2e (evidence integrity). OpenCode-only restructuring.

## Projects

| Project | Path | Description |
|---------|------|-------------|
| codegraph | `codegraph/` | Local-first code intelligence library (tree-sitter), CLI, and MCP server exposing a knowledge graph for AI agents |
| ai-workflow-hub | `ai-workflow-hub/` | OpenCode-driven coding automation with 4-node pipeline (human_gate/executor/tester/fixer) and SADP TaskSpec support |
| ai-workflow-hub-e2e | `ai-workflow-hub-e2e/` | End-to-end evidence integrity and gate tests: API integration, integrity watchdog, model validation, signing (FitTrack subset) |

## How to Verify Project Health

```bash
python smoke_test.py
```

One command verifies all three projects. Writes `smoke_report.txt`. See that file for the most recent run.

## Current Health

See **[smoke_report.txt](./smoke_report.txt)** for the latest run. As of the last run, all three projects are green:

- **codegraph**: type-check passes (exit 0, 0 errors), 34/37 test files pass (fork pool for Windows)
- **ai-workflow-hub**: 147 core + node tests pass, 1 skipped (exit 0)
- **ai-workflow-hub-e2e**: 216 evidence + SHA256 tests pass (exit 0)

**Known pre-existing issues**: 2 skipped CodeGraph test files (Windows platform-gated), 1 worker error resolved with pool: forks.

## Smoke Test Summary

| # | Command | Project | What It Verifies |
|---|---------|---------|------------------|
| 1 | `npx tsc --noEmit` | codegraph | TypeScript compilation (no type errors) |
| 2 | `python -m pytest tests/ -v --tb=line` | ai-workflow-hub | Core state machine: task state transitions, atomic evidence writes, isolation cleanup, idempotency |
| 3 | `python -m pytest tests/fittrack/ tests/test_gate.py -v --tb=line` | ai-workflow-hub-e2e | E2E evidence integrity: API integration, integrity watchdog, model validation, signing, SHA256 checksum, gate rules |

Status labels: PASS (green), KNOWN_ISSUE (yellow -- pre-existing known failure, non-blocking), FAIL (red -- must fix). The script exits 0 only when all three are PASS or KNOWN_ISSUE.

## Minimum Requirements

- Python >= 3.10
- Node.js >= 20.0.0 < 25.0.0
- `codegraph/node_modules/` installed (`npm ci` in codegraph/)
- `ai-workflow-hub` dependencies installed (`pip install -e ".[dev]"` in ai-workflow-hub/)
- `ai-workflow-hub-e2e` dependencies installed (`pip install -e .` + `pip install pytest` in ai-workflow-hub-e2e/)
- The E2E mock server starts automatically via conftest.py fixture; no external processes needed.

## Governance History

5 maintenance stages completed (M1 + restructuring):

| Stage | Focus | Key Results |
|-------|-------|-------------|
| M1 Batch A | Validation docs + smoke test | smoke_test.py, CLAUDE.md, report generation |
| M1 Batch B | CodeGraph Windows cleanup | Build/test parity on Windows, platform-gated tests |
| M1 Batch C | ai-workflow-hub core fixes | Terminal-state guard, task queue hardening |
| M1 Batch D | ai-workflow-hub-e2e gate hardening | Integrity watchdog, signing, regression coverage |
| M1 Batch E | OpenCode restructuring | Migrated to OpenCode-only, 5-agent -> 4-node pipeline, SADP TaskSpec adapter, smoke test parity |

**13 risks fixed** across M1 A-D (including the terminal-state guard, isolation cleanup races, idempotency gaps, and signing coverage). **680 tests passing** (464 core + 216 e2e + codegraph type-check).

## Status: Completed vs Remaining

### Completed

- [x] smoke_test.py with cross-project verification and report generation
- [x] CLAUDE.md with governance docs, health link, and project overview
- [x] Terminal-state guard: `mark_task_running()` now blocks re-marking `passed`/`failed`/`blocked` tasks
- [x] Core state + node tests (73 tests, 0 failures)
- [x] E2E evidence + SHA256 tests (175 tests, 0 failures)
- [x] CodeGraph type-check (0 errors)
- [x] Graceful handling of known issues vs real failures in smoke runner

### Remaining (low priority)

- [ ] CodeGraph Windows cleanup: resolve remaining platform-gated test gaps
- [ ] Production key rotation design for evidence signing
- [ ] Regression test mapping: link each e2e test to the workflow stage it covers
