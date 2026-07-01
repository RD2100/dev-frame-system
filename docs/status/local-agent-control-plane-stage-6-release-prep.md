# Local Agent Control Plane Stage 6 Release Preparation

Date: 2026-06-23
Branch: `codex/go-concurrent-dispatch`
Status: `verified_local_release_preparation`

This report records the Stage 6 stabilization pass for the Local Agent Control
Plane route. It is a local release-preparation verdict, not a production
release, push, merge, deployment, or GitHub CI claim.

## What Was Stabilized

Stage 6 closes the public-review loop around the previous stages:

- Stage 1 established the public repo direction and governance boundary.
- Stage 2 was accepted by the human owner.
- Stage 3 verified the parallel `/go` expansion.
- Stage 4 verified real Chrome/ChatGPT binding as a summary-only session.
- Stage 5 verified that a real external-brain review can project a read-only
  acceptance gate.
- Stage 6 verifies that the current worktree can be reviewed through the public
  status docs, release readiness page, reviewer index, and release script.

The release preparation remains intentionally local. It does not publish a
package, create a PR, push a branch, deploy anything, or move browser/profile
state into the repository.

## Public Surface Checks

Manual and scripted checks confirmed:

- the real ChatGPT conversation URL is not present in public docs or package
  files;
- local runtime summaries stay outside the repository and under the OS temp
  directory;
- `.codegraph/` and `chatgpt-summary.json` remain ignored local artifacts;
- generated package directories such as `build`, `dist`, and `*.egg-info` are
  absent after release verification;
- the only private-path scan hit is the public wheel-smoke script's temporary
  directory prefix, which is expected test logic.

## Verification

Stage 6 uses the same release gate that reviewers should run:

```powershell
python -m pytest packages\control-plane\tests -q
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

Current local result:

- `python -m pytest packages\control-plane\tests -q`: `146 passed`.
- `python -m pytest -q`: `160 passed`.
- `powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1`:
  `[OK] Release verification passed.`

The release script includes:

- `python -m pytest -q`
- `scripts\verify-public-snapshot.ps1`
- `scripts\verify-control-plane-wheel.ps1`
- `git diff --check`

## Reviewer Index

Primary reviewer entry points:

- `docs/status/local-agent-control-plane-stage-2-acceptance.md`
- `docs/status/local-agent-control-plane-stage-3-go-batch.md`
- `docs/status/local-agent-control-plane-stage-3-execution-report.md`
- `docs/status/local-agent-control-plane-stage-4-web-ai-binding.md`
- `docs/status/local-agent-control-plane-stage-5-closed-loop.md`
- `docs/status/local-agent-control-plane-stage-6-release-prep.md`
- `docs/status/local-agent-control-plane-stage-7-final-precommit-review.md`
- `docs/status/release-readiness.md`
- `docs/status/reviewer-index.md`

Critical review focus:

- imported Web AI sessions remain summary-only;
- imported Web AI review gates remain read-only projections;
- positive external-brain verdicts never replace local verification;
- local runtime files, browser profiles, cookies, transcripts, and generated
  archives stay outside the public repo;
- release readiness is claimed only after the local release gate passes on the
  current worktree.

## Current Verdict

Stage 6 is verified as local release preparation. The latest pre-commit review
is recorded in
`docs/status/local-agent-control-plane-stage-7-final-precommit-review.md`. The
next human-owned choices are whether to stage/commit, create a PR, or continue
with another implementation slice.
