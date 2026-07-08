# Release Readiness

Lifecycle state: Current release-state record

This page records the current public-release gate for `dev-frame-system`.
It is meant for reviewers who need to decide whether the repository is ready
to share, package, or hand off.

For the one-minute current launch decision, start with
[LAUNCH_NOW.md](LAUNCH_NOW.md).

For the current file-level review map, see `docs/status/reviewer-index.md`.
For the client-mainline reconnaissance boundary that now governs write-capable
work, see `docs/status/recon-receipt-local-agent-client-mainline.md`. For the
current T3Code reuse boundary, see
`docs/status/t3code-client-mainline-reuse-assessment.md`.

## Release Gate

Run the full release verification from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

The release gate currently runs:

- `python -m pytest -q`
- `scripts\verify-public-snapshot.ps1 -FailOnTrackedForbidden`
- `scripts\verify-control-plane-wheel.ps1`
- `git diff --check`

The same gate is wired into `.github/workflows/release-verify.yml` for push,
pull request, and manual workflow runs.

The wheel smoke test builds `packages/control-plane`, installs the wheel into a
temporary virtual environment, then runs the installed `devframe` console script
through `devframe --help`, `devframe run --help`, `devframe dashboard --help`,
`devframe visual-state`, `devframe actions`, `devframe dashboard serve`, and
`--paper-project` coverage, and the installed `rdgoal` console script through
`rdgoal`, `rdgoal worker`, and `rdgoal digest`.

As of July 7, 2026, commit `15a9d78d` removed the tracked root review artifacts
from the Git index, and both the ordinary public snapshot gate and the strict
`-FailOnTrackedForbidden` public snapshot gate pass locally. Commit `2725227d`
then landed the review-governance hardening batch, including P3-2 graph
projection and the strict public/release gate fixes. Follow-up status commit
`bd73d6bc` received local GPT-equivalent branch-level review PASS, and the local
full release-gate rerun at that checked state passed end to end:
`1512 passed, 1 skipped`, strict public snapshot PASS, control-plane wheel smoke
PASS, and `git diff --check` PASS with line-ending warnings only.

As of July 8, 2026, the docs/status inventory drift caused by later
runtime-governance Batch B through Batch E audit records has been reconciled in
`status-document-inventory.md`. The Batch F sealed context artifact slice,
Batch G generic go opt-in finalization slice, Batch H ai-workflow-hub
chain-evidence adapter slice, Batch I generic go prepare-evidence slice, and
Batch J automatic superseding FinalVerdict slice then landed as explicit batch
commits after owner approval. A later batch-review pass fixed ai-workflow-hub
adapter fail-closed semantics, go_evidence FinalVerdict supersession
idempotency, CLI finalize/prepare help, and a public-snapshot wording leak. The
local full release-gate rerun then passed end to end again: `1616 passed, 1
skipped`, strict public snapshot PASS, control-plane wheel smoke PASS, and `git
diff --check` PASS.

After owner approval for the PR route, branch `codex/public-mainline-batch-1`
was pushed to PR #4 and GitHub Actions `Release verification` passed. This
proves the current PR verification route, but it does not imply merge approval,
external human review approval, a GitHub Release, or public package release.

## Expected Public Surface

- Root documentation: `README.md`, `README.zh-CN.md`, `AGENTS.md`.
- Runtime docs and status files under `docs/`.
- Stage acceptance status under `docs/status/`.
- Reusable modules under `packages/`.
- Public rules and schemas under `rules/` and `schemas/`.
- Bootstrap assets under `templates/runtime-bootstrap/`.
- Verification scripts under `scripts/`.

Do not include local agent state, browser profiles, evidence packs, generated
archives, `build`, `dist`, or package metadata directories in the public tree.

## Known Behavior

- Source checkout `rdgoal --apply-rdinit` can run the full bootstrap when the
  root bootstrap assets are present.
- Wheel installs do not carry the full repository root bootstrap assets. In
  that mode `rdgoal --apply-rdinit` returns `bootstrap_unavailable`, still
  creates the project contract, and still emits a dispatch packet.
- `rdgoal worker` returns exit code `0` only for `pass`, `passed`, or
  `completed` reports. `blocked`, `failed`, and unknown statuses are non-zero.
- Runtime packets, reports, and snapshots are written outside the public
  repository by default.
- Visual Control Plane default-read-only exports include `/`, `/state.json`,
  `/actions.json`, `/actions.md`, `/actions/open`, and `/go/dispatch`. These
  endpoints are intended for inspection and review, except for the two
  loopback-only confirmed mutation paths: `/actions/execute` for queued go-run
  execution and `/go/dispatch` for project-level `/go` preparation/execution.
- Action Queue resume and filtering use `--action-id` as the focused selector.
- Scripts use `--fail-on-match` as a read-only gate to surface blocked or
  failed actions without mutating state.
- Dashboard binds to non-loopback hosts only when `--allow-remote` is
  explicitly provided.
- `stepfun/step-3.7-flash` is documented for narrow single-file post-TaskSpec
  execution. Its external evidence-dir write limitations are captured in
  `dispatch-model-profiles.md`.
- `devframe web-ai bind-chrome` can bind an already-open ChatGPT tab through a
  loopback Chrome CDP endpoint as a summary-only session. It records debugger
  metadata and the provider URL only; it does not persist raw transcripts,
  cookies, browser profiles, local storage, or message text.
- Imported Web AI review summaries with `native_refs.review_marker` and
  `native_refs.review_verdict` are projected into read-only `acceptance` gates
  in the Visual Control Plane.
- Stage 6 local release preparation is a local worktree verdict only. It does
  not imply that a branch was pushed, a PR was opened, CI passed, or a package
  was published.
- Stage 7 final pre-commit review is also local-only. It does not stage files,
  create a commit, open a PR, push a branch, or publish a release.
- Root `review-bundle-*` paths and `chatgpt-review-reply.txt` are forbidden
  public-surface review artifacts. Commit `15a9d78d` removed the previously
  tracked instances, and the strict snapshot gate now checks that they do not
  return to the Git index.
- Review-governance P3-2 graph projection has local GPT-equivalent review PASS
  and landed in commit `2725227d`; the follow-up status boundary received local
  branch-level review PASS at `bd73d6bc`. The current PR route now has CI PASS,
  but human review, merge, and publication evidence are still required before
  it can support public release readiness.
- Control-plane dashboard tests bypass loopback HTTP proxies during pytest so
  local dashboard server checks do not report proxy-generated 502 responses.

## Reviewer Focus

- Confirm `scripts\verify-release.ps1` is the final gate used before sharing.
- Confirm `scripts\verify-public-snapshot.ps1` catches forbidden generated
  output and private runtime state.
- Confirm the wheel smoke test exercises the installed `devframe` and `rdgoal`
  console scripts, not only `python -m control_plane.*`.
- Confirm rdgoal blocked and failed states cannot be reported as success.
- Confirm public docs do not reference private machine paths.
- Confirm the Visual Control Plane dashboard endpoints `/`, `/state.json`,
  `/actions.json`, `/actions.md`, `/actions/open`, and `/go/dispatch` are
  documented consistently, and that `/actions/execute` plus `/go/dispatch`
  are described as the only confirmed local mutation paths.
- Confirm `--action-id`, `--fail-on-match`, and `--allow-remote` are
  documented and tested as the Action Queue resume/filter mechanism,
  read-only script gate, and dashboard remote-bind safety guard
  respectively.
- Confirm `stepfun/step-3.7-flash` is documented only for narrow post-TaskSpec
  execution and that its evidence-dir write limitations are traceable to
  `dispatch-model-profiles.md`.
- Confirm `devframe web-ai bind-chrome` remains loopback-only and cannot report
  login/auth pages as successful bindings.
- Confirm imported Web AI review gates remain read-only projections and do not
  bypass local verification.
- Confirm Stage 6 local release preparation is not represented as a production
  release, deployment, push, PR, or GitHub CI result.
- Confirm Stage 7 final pre-commit review is based on the current worktree and
  does not imply staging, commit creation, PR creation, push, deployment, or
  package publication.

## Current Verdict

The current non-trivial path proven by this repository is a functional WebGPT MCP
control-plane chain (binding + state/Actions loops + local wheel verification) in
the current local context. That does **not** mean the repository is publish-ready.

For a conservative publish decision, the repository remains release-blocked
until the full public-release workflow is completed from an externally reviewed
state, including merge approval and artifact publication steps, not only a local
release-gate pass or PR CI pass.

The current branch should therefore be treated as local-release-gate-green and
PR-CI-green, but still not public-release-ready.
