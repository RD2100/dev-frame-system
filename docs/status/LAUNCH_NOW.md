# Launch Now

Date: 2026-07-08

## Initial Owner-Gate Snapshot

- timestamp_utc: `2026-07-08T12:50:23+00:00`
- head: `5cea92a56f63270831c3213dfc93f1de8c409139`
- dirty_summary_version: `fd1244ac1f00`
- counts: `total=28, tracked=21, untracked=7, modified=21, added=0, deleted=0, renamed=0, copied=0, unmerged=0`
- snapshot_cmd: `release-closure status snapshot from repository root`
- snapshot_id: `2026-07-08T12:50:23+00:00:5cea92a56f63:fd1244ac1f00`

This snapshot records the dirty-tree state that was reviewed before owner
approval. The current external branch state is PR #4; use the PR head and
GitHub `Release verification` check as the authority for post-approval CI
status.

Verdict: **GITHUB RELEASED as `v0.1.0`**; **PYPI NOT PUBLISHED**;
**PHASE 6 PAPER ADAPTER DEFERRED**.

This is the current launch-control entrypoint. It replaces reading every
runtime-governance batch note first, but it does not delete or supersede their
evidence.

## Current Decision

Runtime-governance closure has advanced through Batch J and the follow-up
batch-review fixes. The reviewed dirty tree was converted into explicit batch
commits after owner approval, the branch was pushed to PR #4, the PR was merged
to `main`, and the GitHub `Release verification` check passed on `main`.
Release `v0.1.0` was then published as a GitHub Release with the
`devframe_control_plane-0.1.0-py3-none-any.whl` asset.

That evidence proves the local gate, PR route, merge route, main CI route, and
GitHub Release publication for `v0.1.0`. It does not prove PyPI publication,
downstream adoption, or Phase 6 paper-domain adapter closure.

The paper-domain adapter is explicitly deferred from this closure wave. Current
paper support has read-model and visual-state coverage, but `/rdpaper` remains a
later Phase 6 domain-adapter slice rather than a Batch F-J release blocker.

## Executed After Owner Approval

- `current-dirty-tree-batch-map-20260708.md`: the batch map exists and has now
  been reviewed against the live dirty tree and used for explicit batch
  commits.
- PR route: owner approval was given after the local batch commits. The current
  branch was pushed to PR #4, and GitHub `Release verification` passed for that
  route.
- Publication: GitHub Release `v0.1.0` was executed with the control-plane
  wheel asset. PyPI publication was not executed because this repository does
  not define a PyPI publish workflow or credential path.

## Done Locally

| Area | Status | Evidence |
| --- | --- | --- |
| Runtime-governance Batch F sealed context artifacts | done locally | [runtime-governance-batch-f-sealed-context-artifacts.md](runtime-governance-batch-f-sealed-context-artifacts.md) |
| Runtime-governance Batch G generic go opt-in finalization | done locally | [runtime-governance-batch-g-generic-go-opt-in-finalization.md](runtime-governance-batch-g-generic-go-opt-in-finalization.md) |
| Runtime-governance Batch H ai-workflow-hub chain evidence adapter | done locally | [runtime-governance-batch-h-ai-workflow-hub-chain-evidence-canonicalization.md](runtime-governance-batch-h-ai-workflow-hub-chain-evidence-canonicalization.md) |
| Runtime-governance Batch I generic go prepare evidence | done locally | [runtime-governance-batch-i-generic-go-prepare-evidence.md](runtime-governance-batch-i-generic-go-prepare-evidence.md) |
| Runtime-governance Batch J automatic superseding FinalVerdict | done locally | [runtime-governance-batch-j-automatic-superseding-final-verdict.md](runtime-governance-batch-j-automatic-superseding-final-verdict.md) |
| Full local release gate | done locally | [release-readiness.md](release-readiness.md) |
| PR branch and GitHub Release verification | done for PR route | PR #4 on `RD2100/dev-frame-system` |
| Main merge and main Release verification | done for release route | merge commit `d555e3203fdf68feacd9c4f186595f8f178d51a2`, run `28949249871` |
| GitHub Release `v0.1.0` | published | `https://github.com/RD2100/dev-frame-system/releases/tag/v0.1.0` |
| Reviewer handoff surface | done locally | [reviewer-index.md](reviewer-index.md) |
| Dirty worktree batch map and final local review | done locally | [current-dirty-tree-batch-map-20260708.md](current-dirty-tree-batch-map-20260708.md) |

## Deferred From This Release

| Area | Bucket | Reason | Evidence |
| --- | --- | --- | --- |
| Paper-domain adapter and `/rdpaper` command closure | superseded/deferred | Current repo support covers paper read-model and visual-state projection, but full domain-adapter authority is a later Phase 6 slice. | [runtime-governance-and-evidence-closure-transformation-plan.md](runtime-governance-and-evidence-closure-transformation-plan.md), [runtime-governance-batch-e-paper-trust-fail-closed.md](runtime-governance-batch-e-paper-trust-fail-closed.md), [runtime-governance-batch-j-automatic-superseding-final-verdict.md](runtime-governance-batch-j-automatic-superseding-final-verdict.md) |

## Remaining Blockers

| ID | Bucket | Blocker | Owner | Next action | Pass condition |
| --- | --- | --- | --- | --- | --- |
| B1 | done | Dirty worktree batches have been converted into explicit batch commits. | Owner, Agent | None. | Clean current branch plus local gate evidence. |
| B2 | done for PR route | Branch push, PR route, and GitHub Release verification have been completed for PR #4. | Owner, Agent | Keep PR #4 as the review surface. | PR branch exists and CI is green. |
| B3 | done for GitHub Release | PR merge, release tagging, GitHub Release, and release-asset publication were authorized and completed. | Owner, Agent | None for GitHub Release `v0.1.0`. | Release URL and main CI evidence exist. |
| B4 | owner_required | PyPI publication and downstream announcement are not executed by this repository's release workflow. | Owner | Decide whether a separate PyPI or downstream distribution process should exist. | Separate publish workflow, credentials, and evidence. |

## Owner Decision Packet

No action in this section is authorized by this document. It is a prepared
decision menu for the owner.

| Decision | Meaning | Agent action after approval |
| --- | --- | --- |
| `approve-batch-commits` | Convert the reviewed dirty tree into staged batch commits only. | Completed. |
| `review-bundle-only` | Keep all changes unstaged for human or external review. | Leave the worktree dirty and use this file plus the batch map as the review surface. |
| `approve-pr-route` | Allow branch/PR preparation after batch commits. This does not authorize publication by itself. | Completed for PR #4 and GitHub `Release verification`. |

GitHub Release publication is complete for `v0.1.0`. PyPI publication remains a
separate future decision because no PyPI publish workflow is defined here.

Default next action if no new decision is given: keep `v0.1.0` as the current
GitHub Release and do not create a PyPI release.

## Next 3 Actions

1. Owner: decide whether PyPI publication is needed for this project.
2. Owner: decide whether Phase 6 paper-domain adapter work should begin.
3. Agent after approval: create the matching implementation or publication
   evidence and update this status entrypoint again.

## Evidence Map

| Question | Start Here |
| --- | --- |
| Can this be publicly released now? | This file, then [release-readiness.md](release-readiness.md). |
| How should the current dirty worktree be reviewed? | [current-dirty-tree-batch-map-20260708.md](current-dirty-tree-batch-map-20260708.md). |
| What changed in the current closure wave? | [reviewer-index.md](reviewer-index.md), then Batch F-J evidence records. |
| Why are there many status files? | [status-document-inventory.md](status-document-inventory.md). |
| What is the broader transformation plan? | [runtime-governance-and-evidence-closure-transformation-plan.md](runtime-governance-and-evidence-closure-transformation-plan.md). |
