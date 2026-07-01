# Continue - Global Coordinator Conversation Mainline

Last updated: 2026-07-01 (Asia/Tokyo)
Branch: `codex/public-mainline-batch-1`
PR: `#4`

## Current State

The public repo side of the Global Coordinator conversation mainline has moved
from product docs into real contracts, thread projection behavior, and a
shell-friendly coordinator entry surface.

Current pushed branch head already has these landed:

- `docs: define total control conversation mainline`
- `feat: model global coordinator conversations in t3 shell`
- `feat: return coordinator conversation contract on cluster runs`
- `feat: expose coordinator conversation types to t3 bridge`
- `feat: add project binding endpoint for coordinator goals`
- `feat: expose coordinator project helpers in t3 bridge`
- `feat: expose coordinator conversation model endpoint`
- `feat: always expose global coordinator thread`
- `feat: project goal conversations into t3 shell`
- `feat: add thread list metadata for coordinator flows`
- `feat: add display sort helper for coordinator threads`

At the time of writing:

- local worktree is **not clean**
- current uncommitted code slice adds a one-call coordinator shell entry
  contract and its tests
- these two handoff files are also untracked until the user chooses whether to
  include them in the formal handoff point
- PR `#4` is open; merge and release remain human-owned
- latest local release verification on the current uncommitted worktree passed:
  `816 passed, 1 skipped`, plus public snapshot, wheel smoke, and diff
  whitespace checks

## What Is Already True

### Product / Decision Layer

Read first:

- `docs/status/recon-receipt-global-coordinator-conversation-mainline.md`
- `docs/status/phase-1-global-coordinator-conversation-plan.md`
- `docs/status/cluster-coordinator-design-and-roadmap.md`

These lock the mainline decision:

- Global Coordinator must be a first-class conversation, not a dashboard card
- one goal equals one project coordinator conversation
- reuse shell/UI patterns from RD-Code/T3Code
- reuse orchestration core via LangGraph in later slices
- keep DevFrame as the governance, evidence, review, gate, and state-projection
  owner

### Contract / Backend Layer

Already implemented in the public repo:

- `threadKind`, `coordinatorScope`, `projectBinding`
- top-level `conversationModel`
- `global_coordinator` thread always exists
- cluster runs can project into `goal_conversation` threads
- `threadListPriority` and `threadListSummary`
- `/api/t3/projects`
- `/api/t3/conversation-model`
- cluster-run responses include project/conversation binding semantics

Current uncommitted slice adds:

- `/api/t3/coordinator-entry`
- `build_t3_coordinator_entry(...)`
- client manifest entry `t3-coordinator-entry`
- launch-plan endpoint `endpoints.coordinatorEntry`
- generated bridge type `DevFrameCoordinatorShellEntry`
- generated bridge helper `fetchDevFrameCoordinatorShellEntry()`
- schema `schemas/t3_coordinator_entry.schema.json`
- shell-readiness fixtures under
  `packages/control-plane/tests/fixtures/t3_coordinator_entry/`

### Bridge / TS Helper Layer

Generated bridge source now exposes helpers for:

- reading control-plane config
- reading conversation model
- reading project options
- reading cluster targets
- starting coordinator goals
- sorting threads for display
- fetching a directly consumable coordinator shell entry

The new coordinator entry shape contains:

- `conversationModel`
- `projects`
- `globalCoordinatorThread`
- `goalConversations`
- `projectOptions`
- `selectedProject`
- `projectCoordinatorThread`
- `shellThreads`
- `sortedShell`
- `canStartCoordinatorGoal`
- `emptyStateReason`
- `disabledReason`

Follow-up review tightened this slice further:

- client smoke now checks `/api/t3/coordinator-entry` against
  `/api/t3/projects`, `/api/t3/conversation-model`, and `/t3-shell.json`
- the coordinator entry has an independent JSON schema
- generated TS local builder now has a default conversation-model fallback for
  older or non-standard envelopes
- fixture-backed tests cover empty projects, global-only entry, project goals,
  no project goals, can-start false, malformed partial responses, and selected
  project vs goal-conversation project-id mismatch
- project coordinator thread selection is exact-match only; it no longer falls
  back to another project's goal conversation

## Automatic vs Human-Owned Work

The agent can continue automatically on:

- public repo contracts and read-only projection helpers
- tests for `t3_adapter`, `t3_bridge_bundle`, manifest, launcher, dashboard, and
  cluster-control endpoints
- generated bridge source and README text
- local release verification with `scripts\verify-release.ps1`
- review/audit of current diffs and handoff docs
- small shell-consumption seams that do not require external RD-Code source

The user must own or explicitly authorize:

- final product judgment that the RD-Code shell now feels like a real
  total-control conversation
- access/scope for an external RD-Code/T3 checkout
- PR merge, release, deployment, or online publication
- committing/pushing if the desired boundary is a formal handoff point
- any product naming decision broader than the existing Phase 1 law:
  "Global Coordinator is a conversation, not a dashboard card"

## Most Important Remaining Gap

The public repo contracts are now mature enough for shell integration. The
repo-side readiness slice is complete and locally verified.

The next meaningful progress is no longer to invent more backend fields. The
next meaningful progress is to wire a real RD-Code/T3 checkout, when available
and in scope, to consume `/api/t3/coordinator-entry` and
`fetchDevFrameCoordinatorShellEntry()`.

Do **not** jump to LangGraph migration yet. Phase 1 is still shell-first.

## Next Action

Move to actual RD-Code/T3 shell consumption when the external checkout is
available and in scope. Keep that first shell slice read-only: render/navigate
the global coordinator and project goal conversations from the coordinator
entry contract.

Concretely:

1. inspect the current diff and confirm the coordinator-entry shape is still the
   right shell-facing contract
2. keep the slice public-repo-safe
3. run the focused tests and full release gate again if any file changes
4. commit/push only after human approval if that is the chosen handoff point

## Do Not

- do **not** reopen the product decision about dashboard-first total control
- do **not** start a broad LangGraph migration in this slice
- do **not** vendor or copy external T3 source into this public repo
- do **not** replace OpenCode/ACP execution paths
- do **not** weaken release verification just to move faster

## Verification Commands

Use these as the minimum bar after the next edit:

```powershell
python -m pytest packages/control-plane/tests/test_t3_adapter.py -q
python -m pytest packages/control-plane/tests/test_t3_bridge_bundle.py -q
python -m pytest packages/control-plane/tests/test_client_manifest.py packages/control-plane/tests/test_client_launcher.py packages/control-plane/tests/test_cluster_control.py -q
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

Latest observed verification for the current uncommitted slice:

```powershell
python -m pytest packages/control-plane/tests/test_client_launcher.py packages/control-plane/tests/test_cluster_control.py packages/control-plane/tests/test_t3_adapter.py packages/control-plane/tests/test_t3_bridge_bundle.py -q
# 196 passed

powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
# 816 passed, 1 skipped; release verification passed
```

## Human-Only Tasks

The user still owns:

- final product judgment that the shell now really feels like a Global
  Coordinator conversation
- deciding whether to commit/push the current uncommitted slice and handoff docs
- PR merge
- release / onlining

Until that point, the agent can keep safely automating repo-side contracts,
tests, integration seams, and review evidence.
