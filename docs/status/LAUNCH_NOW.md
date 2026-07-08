# Launch Now

Date: 2026-07-08

## Live Snapshot

- timestamp_utc: `2026-07-08T12:50:23+00:00`
- head: `5cea92a56f63270831c3213dfc93f1de8c409139`
- dirty_summary_version: `fd1244ac1f00`
- counts: `total=28, tracked=21, untracked=7, modified=21, added=0, deleted=0, renamed=0, copied=0, unmerged=0`
- snapshot_cmd: `release-closure status snapshot from repository root`
- snapshot_id: `2026-07-08T12:50:23+00:00:5cea92a56f63:fd1244ac1f00`

Verdict: **NO-GO for public release**; **LOCAL-GATE-GREEN for the current worktree**.

This is the current launch-control entrypoint. It replaces reading every
runtime-governance batch note first, but it does not delete or supersede their
evidence.

## Current Decision

Runtime-governance closure has locally advanced through Batch J and the
follow-up batch-review fixes. The latest recorded full local release gate passed
with `1616 passed, 1 skipped`, local strict public snapshot PASS, local
control-plane wheel smoke PASS, and local `git diff --check` PASS.

That evidence is local only. It does not prove a clean worktree, clean publish
branch, pushed branch, pull request, external review, GitHub CI, or package
publication. Public release remains blocked until those owner-controlled steps
are completed from a reviewed state.

The paper-domain adapter is explicitly deferred from this closure wave. Current
paper support has read-model and visual-state coverage, but `/rdpaper` remains a
later Phase 6 domain-adapter slice rather than a Batch F-J release blocker.

## Prepared, Not Executed

- `current-dirty-tree-batch-map-20260708.md`: the batch map exists and has now
  been reviewed against the live dirty tree. Commit staging, PR, push, CI, and
  publication remain owner-gated.
- Owner-gate dry-run: the explicit staging list matches the live dirty set
  exactly, `expected=28 actual=28 missing=0 extra=0`, snapshot
  `fd1244ac1f00`. It is still not executable without `approve-batch-commits`.

## Done Locally

| Area | Status | Evidence |
| --- | --- | --- |
| Runtime-governance Batch F sealed context artifacts | done locally | [runtime-governance-batch-f-sealed-context-artifacts.md](runtime-governance-batch-f-sealed-context-artifacts.md) |
| Runtime-governance Batch G generic go opt-in finalization | done locally | [runtime-governance-batch-g-generic-go-opt-in-finalization.md](runtime-governance-batch-g-generic-go-opt-in-finalization.md) |
| Runtime-governance Batch H ai-workflow-hub chain evidence adapter | done locally | [runtime-governance-batch-h-ai-workflow-hub-chain-evidence-canonicalization.md](runtime-governance-batch-h-ai-workflow-hub-chain-evidence-canonicalization.md) |
| Runtime-governance Batch I generic go prepare evidence | done locally | [runtime-governance-batch-i-generic-go-prepare-evidence.md](runtime-governance-batch-i-generic-go-prepare-evidence.md) |
| Runtime-governance Batch J automatic superseding FinalVerdict | done locally | [runtime-governance-batch-j-automatic-superseding-final-verdict.md](runtime-governance-batch-j-automatic-superseding-final-verdict.md) |
| Full local release gate | done locally | [release-readiness.md](release-readiness.md) |
| Reviewer handoff surface | done locally | [reviewer-index.md](reviewer-index.md) |
| Dirty worktree batch map and final local review | done locally | [current-dirty-tree-batch-map-20260708.md](current-dirty-tree-batch-map-20260708.md) |

## Deferred From This Release

| Area | Bucket | Reason | Evidence |
| --- | --- | --- | --- |
| Paper-domain adapter and `/rdpaper` command closure | superseded/deferred | Current repo support covers paper read-model and visual-state projection, but full domain-adapter authority is a later Phase 6 slice. | [runtime-governance-and-evidence-closure-transformation-plan.md](runtime-governance-and-evidence-closure-transformation-plan.md), [runtime-governance-batch-e-paper-trust-fail-closed.md](runtime-governance-batch-e-paper-trust-fail-closed.md), [runtime-governance-batch-j-automatic-superseding-final-verdict.md](runtime-governance-batch-j-automatic-superseding-final-verdict.md) |

## Remaining Blockers

| ID | Bucket | Blocker | Owner | Next action | Pass condition |
| --- | --- | --- | --- | --- | --- |
| B1 | owner_required | Dirty worktree batches are reviewed, but staging/commit route has not been authorized. | Owner | Choose whether to allow staged batch commits or keep the tree as a review bundle. | Clean worktree or intentionally staged batches with gate evidence. |
| B2 | owner_required | Public release path has not been authorized. | Owner | Choose whether to allow branch creation, PR, push, external review, and package publication. | Owner-approved release route exists. |
| B3 | owner_required | External PR review, GitHub CI, and publication evidence are absent. | Owner, then Agent | After approval, create the PR/review bundle and collect external evidence. | External review or CI PASS plus package-release evidence if publishing. |

## Owner Decision Packet

No action in this section is authorized by this document. It is a prepared
decision menu for the owner.

| Decision | Meaning | Agent action after approval |
| --- | --- | --- |
| `approve-batch-commits` | Convert the reviewed dirty tree into staged batch commits only. | Stage only the files listed in [current-dirty-tree-batch-map-20260708.md](current-dirty-tree-batch-map-20260708.md), commit by batch, and rerun `scripts\verify-release.ps1`. |
| `review-bundle-only` | Keep all changes unstaged for human or external review. | Leave the worktree dirty and use this file plus the batch map as the review surface. |
| `approve-pr-route` | Allow branch/PR preparation after batch commits. This does not authorize publication by itself. | Create or use an approved branch, prepare a PR/review bundle, and collect external CI/review evidence. |

Public package or release publication remains a separate owner decision after
PR, CI, and external review evidence exists.

Default if no decision is given: keep the repository in reviewed-but-unstaged
state.

## Next 3 Actions

1. Owner: decide whether this dirty tree should be staged as review batches or
   left as an unstaged review bundle.
2. Agent after approval: stage/commit only the approved batch files and rerun
   the full release gate.
3. Owner: approve the PR, push, external-review, or package-publication route.

## Evidence Map

| Question | Start Here |
| --- | --- |
| Can this be publicly released now? | This file, then [release-readiness.md](release-readiness.md). |
| How should the current dirty worktree be reviewed? | [current-dirty-tree-batch-map-20260708.md](current-dirty-tree-batch-map-20260708.md). |
| What changed in the current closure wave? | [reviewer-index.md](reviewer-index.md), then Batch F-J evidence records. |
| Why are there many status files? | [status-document-inventory.md](status-document-inventory.md). |
| What is the broader transformation plan? | [runtime-governance-and-evidence-closure-transformation-plan.md](runtime-governance-and-evidence-closure-transformation-plan.md). |
