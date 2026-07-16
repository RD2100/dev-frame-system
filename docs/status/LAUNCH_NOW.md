# Launch Now

Date: 2026-07-17

Verdict: **CONDITIONAL-GO** for continued public development on `main`.
Release, deployment, and production changes are outside this verdict.

## Current Decision

The accepted public mainline is usable for continued development. The current
work is change-tree consolidation: preserve local candidates, remove proven
noise, and deliver retained capabilities as small reviewed pull requests.
Local dirty state and imported source are not release evidence.

## Already Good Enough

| Area | Status | Evidence |
|---|---|---|
| Public mainline | PRs #15 through #20 merged | [Current Handoff](HANDOFF.md) |
| Session inspection | Read-only list, JSON detail, and HTML detail are on `main` | `packages/control-plane/control_plane/dashboard.py` and its tests |
| Public distribution gate | Passing on the accepted mainline slices | `scripts/verify-public-snapshot.ps1` and GitHub Release verification |
| Current continuation entrypoint | One authoritative handoff | [Current Handoff](HANDOFF.md) |

## Remaining Blockers

| ID | Blocker | Why non-blocking for this verdict | Owner | Next action | Pass condition |
|---|---|---|---|---|---|
| CT-1 | The primary worktree still contains retained local candidates | Non-blocking: it blocks tree closure, not continued work from accepted `main` | Coordinator | Classify, back up, consolidate, test, and review each bounded slice | No unowned status entries remain |
| CT-2 | Local runtime state needs exclusion from public change lists | Non-blocking: it is preserved outside accepted commits and does not alter `main` | Coordinator | Merge the narrow `.aiworkflow/` ignore slice after CI | Ignore probe and public snapshot pass on `main` |
| CT-3 | Release or deployment has not been requested for this closure wave | Out-of-scope: release and production require a separate verdict | Owner | Make a separate release decision when desired | Explicit authorization plus release evidence and postcheck |

## Accepted Deferred Items

| Item | Why non-blocking | Follow-up trigger |
|---|---|---|
| Historical Tutti shell and Windows-preview research | Useful input, but not current implementation authority | A new shell/product slice passes Recon against current `main` |
| Historical RD-Code realignment plans | They contain prior exploration, not a current product commitment | A current capability gap requires re-evaluation |
| PyPI and downstream publication | Separate from repository cleanup | Owner explicitly requests a publication route |

## Next 3 Actions

1. Merge the local-state ignore PR after its required check succeeds.
2. Consolidate backed-up handoff and shell-plan material into current authority,
   then remove the redundant working copies.
3. Review the remaining product candidates by subsystem and deliver only
   independently verified slices.

## Source Of Truth

- Current continuation and accepted merges: [HANDOFF.md](HANDOFF.md)
- Detailed review map: [reviewer-index.md](reviewer-index.md)
- Release boundary: [release-readiness.md](release-readiness.md)
- Status document classification: [status-document-inventory.md](status-document-inventory.md)
