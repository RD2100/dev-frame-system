# Continue - Global Coordinator Conversation Mainline

Last updated: 2026-07-02 (Asia/Tokyo)
Branch: `codex/public-mainline-batch-1`
PR: `#4`

## 2026-07-02 External T3/RD-Code Update

The earlier assumption that an external T3/RD-Code checkout was unavailable is
wrong. The checkout exists at:

```text
<repo-root>\.devframe-runtime\external\t3code
```

It is an independent checkout and must stay outside the public repo commit
surface.

Current external-checkout truth:

- `apps/web` now consumes the coordinator-entry path through the real shell and
  thread state layers.
- Sidebar exposes `Coordinator` as a top-level entry.
- `global_coordinator` and `goal_conversation` rows are visually distinguished.
- selected project and project goal binding are shown read-only in the sidebar.
- direct global/goal routes render a DevFrame read-only banner.
- DevFrame coordinator/goal conversations render a static read-only composer
  panel instead of send, approval, or agent-execution controls.
- `&address agents` / cluster-dispatch composer affordances are explicitly
  disabled for this Phase 1 read-only slice with
  `ENABLE_DEVFRAME_CLUSTER_COMPOSER = false`.
- Phase 2 hardening has started: when that flag is false,
  `detectComposerTrigger()` no longer produces `cluster` triggers for `&...`,
  the inline cluster confirm card is also flag-gated, and the confirm handler
  returns before `startClusterRun(...)`.
- Phase 2 also tightened selected-project binding: fetched coordinator-entry
  payloads no longer trust a `projectCoordinatorThread` from the wrong project;
  the UI normalization keeps it only when it exactly matches the selected
  project id and `goal_conversation`.
- Phase 2 now formats coordinator `emptyStateReason` / `disabledReason` into
  user-facing sidebar copy instead of exposing internal enum strings such as
  `no_threads` or `missing_required_project`.
- Phase 1 readiness hardening slimmed `/api/t3/coordinator-entry`: it now keeps
  thread summaries for navigation and strips full `threadDetails` / heavy
  `devframe` action/evidence payloads from the one-call entry. A live isolated
  server on port `8792` measured the entry at about `328 KB` instead of about
  `7.25 MB`.
- DevFrame approval response is a no-op in the T3 bridge path; it does not POST
  an approval/write endpoint.

Latest focused external-checkout verification observed:

```powershell
pnpm --filter @t3tools/web test -- composer-logic.test.ts
# 37 passed

pnpm --filter @t3tools/web test -- ChatView.logic.test.ts
# 22 passed

pnpm --filter @t3tools/web test -- devframeShellBridge.test.ts
# 5 passed

pnpm --filter @t3tools/web test -- "chatThreadRoute"
# 6 passed

pnpm --filter @t3tools/web test -- Sidebar.logic.test.ts
# 57 passed

pnpm --filter @t3tools/web typecheck
# passed

pnpm --filter @t3tools/web test -- composer-logic.test.ts ChatView.logic.test.ts devframeShellBridge.test.ts chatThreadRoute Sidebar.logic.test.ts
# 5 files passed, 130 tests passed

python -m pytest packages/control-plane/tests/test_t3_adapter.py -q
# 70 passed

python -m pytest packages/control-plane/tests/test_cluster_control.py -q
# 36 passed

powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
# 821 passed, 1 skipped; release verification passed
```

Browser smoke evidence was written under `.devframe-runtime/logs/`, including:

- `phase1-t3web-readonly-after-logic-extract.png`
- `phase1-t3web-cluster-write-guard.png`
- `phase1-t3web-cluster-flag-guard.png`
- `phase1-t3web-global-direct-slim-wait-smoke.png`

Latest direct-route smoke against the slim coordinator-entry path observed:

- `Coordinator` enabled
- selected project shown as `Dev Frame System - <repo-root>`
- selected goal shown as `Goal: coordinator / chatgpt / chatgpt-web-mcp-real-call`
- read-only composer shown
- send button count `0`
- cluster confirm count `0`
- approval action text absent
- `No active thread` absent
- internal enum strings absent

Important caveat: the external checkout has substantial pre-existing dirty
changes, including rebrand/i18n/desktop/customization work. Do not revert them,
and do not claim all dirty files as part of the coordinator-entry slice.

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
  `821 passed, 1 skipped`, plus public snapshot, wheel smoke, and diff
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
- external shell consumer guide:
  `docs/examples/t3-coordinator-entry-consumer.md`

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
- drift-guard tests now assert the endpoint remains GET/read-only, manifest
  `mutates=false`, schema required fields are closed, malformed priorities do
  not break sorting, and global coordinator sorting stays first

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

The public repo contracts are mature enough for shell integration, and the
external T3/RD-Code checkout now has a first read-only shell consumption slice.

The next meaningful progress is not to invent more backend fields. It is to
review, harden, and product-check the external checkout slice until it is ready
for human product acceptance.

Do **not** jump to LangGraph migration yet. Phase 1 is still shell-first.

## Next Action

Continue in the external T3/RD-Code checkout only if that checkout is in scope.
Keep the work read-only: render/navigate the global coordinator and project goal
conversations from the coordinator entry contract, and keep write/approval/agent
execution affordances disabled.

Concretely:

1. inspect both repo statuses before acting:
   `<repo-root>` and
   `<repo-root>\.devframe-runtime\external\t3code`
2. preserve unrelated dirty work in the external checkout
3. keep the T3 slice read-only; do not enable `ENABLE_DEVFRAME_CLUSTER_COMPOSER`
   in Phase 1
4. run focused external checkout tests and browser smoke after UI changes
5. commit/push only after human approval if that is the chosen handoff point

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
# 821 passed, 1 skipped; release verification passed
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
