# Local Agent Control Plane Stage 2 Acceptance

Date: 2026-06-23
Branch: `codex/go-concurrent-dispatch`
Status: `accepted`

This document is the stage gate for the current Local Agent Control Plane
slice. It is intentionally about acceptance status, evidence, and next-step
automation boundaries, not implementation detail.

## Overall Roadmap

| Stage | Name | Status | Acceptance point |
|---|---|---|---|
| 1 | Direction and public baseline | `passed` | Public repo positioning and governance boundaries are established. |
| 2 | First reviewable control-plane slice | `accepted` | Direction accepted by the human owner; local verification is green. |
| 3 | Parallel `/go` expansion | `verified` | Four-shard `/go` batch executed and release verification is green. |
| 4 | Real Web AI binding validation | `verified_summary_binding` | Chrome/ChatGPT CDP binding imported as a summary-only active session. |
| 5 | Control-plane closed loop | `verified_external_review_gate` | Real Web AI review imported as a summary-only session and projected as a passing acceptance gate. |
| 6 | Stabilization and release preparation | `verified_local_release_preparation` | Public docs, release checks, handoff, and repo hygiene are ready for human review. |
| 7 | Final pre-commit review | `final_precommit_review_pass` | Latest worktree review is complete; stage/commit/PR remains human-owned. |

## Current Stage Verdict

Stage 2 is accepted by the human owner. Stages 3 through 7 have now been
verified locally on this branch. Continue automatically only for low-risk
follow-up slices unless a shard crosses a real high-risk boundary.

The current slice establishes the first reviewable version of the Local Agent
Control Plane path:

- OpenCode is treated as the first built-in local worker backend, not as the
  product identity.
- Web AI conversations can be represented as local read-only session summaries.
- Session and action-queue surfaces are visible through CLI/dashboard exports.
- OpenCode readiness is measured through hermetic probes and schema-backed
  reports.
- Public repo hygiene now treats generated local state as excluded public
  surface.

Reviewer support files:

- `docs/status/local-agent-control-plane-stage-2-precommit-review.md`
- `docs/status/local-agent-control-plane-stage-3-go-batch.md`
- `docs/status/local-agent-control-plane-stage-4-web-ai-binding.md`
- `docs/status/local-agent-control-plane-stage-5-closed-loop.md`
- `docs/status/local-agent-control-plane-stage-6-release-prep.md`
- `docs/status/local-agent-control-plane-stage-7-final-precommit-review.md`

## Verification Evidence

Fresh verification collected on 2026-06-23 after Stage 7:

```powershell
python -m pytest packages\control-plane\tests -q
python -m pytest -q
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

Results:

- `python -m pytest packages\control-plane\tests -q`: `146 passed`.
- `python -m pytest -q`: `160 passed`.
- `powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1`:
  `[OK] Release verification passed.`

The release verification also confirmed:

- public snapshot required paths are present,
- no submodules, local agent state, evidence archives, generated packages, or
  oversized files were found,
- JSON files parse as UTF-8,
- the control-plane wheel smoke passed,
- `git diff --check` passed.

Current local-only artifacts that must stay uncommitted:

- `chatgpt-summary.json`
- `.codegraph/`

## Stage Decision

The owner accepted the direction on 2026-06-23.

Keep future gates lightweight. Stop only for:

- browser profile, cookie, credential, or account-state access,
- external side effects or live provider calls,
- production deployment, release publication, or irreversible actions,
- broad rewrites that blur the Stage 2/Stage 3 review boundary.

## Stage 3 Automation Plan

After Stage 2 acceptance, the next `/go` batch is split into independent shards:

| Shard | Focus | Hard stop |
|---|---|---|
| A | Session detail/page surface | Stop before adding mutating dashboard controls. |
| B | Provider binding adapters | Stop before live browser profile access, credentials, or account state. |
| C | OpenCode readiness and Local Tool Gateway evidence | Stop before running probes in the repo root or committing probe artifacts. |
| D | Public docs and release hygiene | Stop before adding internal delivery logs, private paths, or generated archives. |

Each shard must produce:

- changed file list,
- commands run and result summaries,
- generated artifacts and cleanup status,
- known gaps,
- suggested reviewer focus.

The Stage 3 execution package is
`docs/status/local-agent-control-plane-stage-3-go-batch.md`, and the execution
summary is `docs/status/local-agent-control-plane-stage-3-execution-report.md`.

The orchestrator should merge shard output only after checking:

```powershell
git diff --name-status
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

## Current Continue Rule

Stage 7 final pre-commit review has a local verification verdict on this branch.
Low-risk docs, tests, read-only session surfaces, local probe validation, local
runtime imports, and compact Web AI review prompts can still execute
automatically. Browser profile access, credentials, release publication,
deployment, push, commit creation, and irreversible actions stay behind the stop
list above.
