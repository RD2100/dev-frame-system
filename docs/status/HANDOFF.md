# DevFrame Current Handoff

Lifecycle state: Current public handoff

This is the single starting point for a maintainer resuming public
`dev-frame-system` work. It summarizes release-ready work without turning
local runtime state, private evidence, or an unreviewed worktree into public
history.

## Current Mainline

The default branch is `main`. Its recent accepted milestones are PRs #15, #16,
#17, and #18, merged as `0939b6e`, `c501308`, `e77baff`, and `3a5dfca`
respectively. PR #18 adds the read-only HTML session-detail route while
preserving the JSON detail route.

## Start Here

1. Read [Release Readiness](release-readiness.md) for the release boundary.
2. Read [Reviewer Index](reviewer-index.md) for code and verification entry
   points.
3. Read [Status Document Inventory](status-document-inventory.md) to locate a
   scoped plan or recon receipt.
4. Verify remote PR head, base, checks, and review state before merging any
   candidate.

## Change-Tree Closure Rule

Only accepted, single-topic changes may be staged or committed. Preserve
unknown, user-owned, local-runtime, generated, and external-worktree content
as a hash-bound exception until its owner and publishability are proven. Do
not use reset, clean, stash, broad staging, or broad deletion to make a tree
look tidy.

Historical handoff files remain evidence and context, not competing current
instructions: `continue-global-coordinator-conversation-mainline.md`,
`next-agent-global-coordinator-prompt.md`, and
`devframe-code-opencode-handoff.md`.

## Known Gates

- Merge only CI-green, reviewed, exact-head PRs into `main` with a normal
  merge; release and deployment remain separate decisions.
- Treat external runtime/provider availability and any local dirty worktree as
  operational state, not evidence that a public change is acceptable.
- Run `scripts/verify-public-snapshot.ps1` for every public candidate.
