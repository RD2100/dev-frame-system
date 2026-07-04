# Next Agent Prompt - Global Coordinator Conversation Mainline

Copy/paste prompt:

```text
You are taking over work in the dev-frame-system repository on branch codex/public-mainline-batch-1.

Read these files first:
- docs/status/continue-global-coordinator-conversation-mainline.md
- docs/status/recon-receipt-global-coordinator-conversation-mainline.md
- docs/status/phase-1-global-coordinator-conversation-plan.md
- docs/status/cluster-coordinator-design-and-roadmap.md
- Read the concrete read-only consumer example: docs/examples/t3-coordinator-entry-consumer.md

Current truth:
- PR #4 is the active branch PR.
- The worktree may be dirty; inspect git status before acting.
- External T3/RD-Code source exists and is already in scope for this mainline:
  `D:\dev-frame-system\.devframe-runtime\external\t3code`
- That external checkout is independent and dirty. Do not vendor it into
  `D:\dev-frame-system`, do not commit it in the public repo, and do not revert
  unrelated dirty files there.
- Current slice adds a one-call coordinator shell entry and shell-readiness
  contract pack:
  - GET /api/t3/coordinator-entry
  - build_t3_coordinator_entry(...)
  - manifest endpoint t3-coordinator-entry
  - launch-plan endpoint endpoints.coordinatorEntry
  - generated bridge type DevFrameCoordinatorShellEntry
  - generated bridge helper fetchDevFrameCoordinatorShellEntry()
  - schema schemas/t3_coordinator_entry.schema.json
  - fixtures under packages/control-plane/tests/fixtures/t3_coordinator_entry/
  - external read-only consumer guide:
    docs/examples/t3-coordinator-entry-consumer.md
  - read-only shell mapping fields selectedProject, projectOptions,
    projectCoordinatorThread, shellThreads, emptyStateReason, disabledReason
  - drift guards for schema closure, read-only endpoint methods, global sorting
    priority, malformed priority handling, and exact project/thread matching
  - client smoke cross-checks the coordinator entry against /api/t3/projects,
    /api/t3/conversation-model, and /t3-shell.json
- Latest local release gate observed for this slice:
  powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
  -> 821 passed, 1 skipped; release verification passed
- The first real external T3/RD-Code read-only UI slice has also been
  implemented locally in the external checkout:
  - `apps/web/src/devframe/devframeShellBridge.ts`
  - `apps/web/src/state/shell.ts`
  - `apps/web/src/state/threads.ts`
  - `apps/web/src/components/Sidebar.tsx`
  - `apps/web/src/components/ChatView.tsx`
  - `apps/web/src/components/ChatView.logic.ts`
  - `apps/web/src/components/ChatView.logic.test.ts`
  - `apps/web/src/components/chat/ChatComposer.tsx`
  - `apps/web/src/composer-logic.ts`
  - `apps/web/src/composer-logic.test.ts`
  - route loading helpers under `apps/web/src/routes/`
- External T3 UI behavior now observed:
  - real apps/web consumes `/api/t3/coordinator-entry`
  - Sidebar has a top-level `Coordinator` entry
  - global/goal threads are visually tagged
  - selected project and project coordinator goal binding are shown read-only
  - global/goal thread detail routes show a DevFrame read-only banner
  - global/goal thread detail routes render a static read-only composer panel
    with no send, approval, or cluster-dispatch controls
  - `ENABLE_DEVFRAME_CLUSTER_COMPOSER = false` keeps `&address agents` /
    cluster dispatch disabled for Phase 1
  - Phase 2 hardening has started: `detectComposerTrigger()` no longer emits
    `cluster` triggers while that flag is false, the inline cluster confirm card
    is flag-gated, and `confirmClusterRun` returns before `startClusterRun(...)`
    when the flag is false
  - fetched coordinator-entry normalization now rejects a
    `projectCoordinatorThread` unless it exactly matches the selected project id
    and is a `goal_conversation`
  - Sidebar formats coordinator `emptyStateReason` / `disabledReason` into
    user-facing copy instead of exposing internal enum strings such as
    `no_threads` or `missing_required_project`
  - `/api/t3/coordinator-entry` was slimmed for Phase 1 readiness: it keeps
    thread summaries for navigation but strips full `threadDetails` and heavy
    `devframe` action/evidence payloads from the one-call entry
- External checkout focused verification observed:
  - `pnpm --filter @t3tools/web test -- composer-logic.test.ts` -> 37 passed
  - `pnpm --filter @t3tools/web test -- ChatView.logic.test.ts` -> 22 passed
  - `pnpm --filter @t3tools/web test -- devframeShellBridge.test.ts` -> 5 passed
  - `pnpm --filter @t3tools/web test -- "chatThreadRoute"` -> 6 passed
  - `pnpm --filter @t3tools/web test -- Sidebar.logic.test.ts` -> 57 passed
  - `pnpm --filter @t3tools/web test -- composer-logic.test.ts ChatView.logic.test.ts devframeShellBridge.test.ts chatThreadRoute Sidebar.logic.test.ts` -> 5 files passed, 130 tests passed
  - `pnpm --filter @t3tools/web typecheck` -> passed
  - `python -m pytest packages/control-plane/tests/test_t3_adapter.py -q` -> 70 passed
  - `python -m pytest packages/control-plane/tests/test_cluster_control.py -q` -> 36 passed
  - `git diff --check` in the external checkout -> passed with only existing
    CRLF warnings
- Isolated live server measurement on port `8792`:
  - `/t3-shell.json` remained the full-detail read model, about `4.87 MB`
  - `/api/t3/coordinator-entry` was about `328 KB`, down from about `7.25 MB`
- Browser smoke screenshots exist under
  `D:\dev-frame-system\.devframe-runtime\logs`, including:
  - `phase1-t3web-readonly-after-logic-extract.png`
  - `phase1-t3web-cluster-write-guard.png`
  - `phase1-t3web-cluster-flag-guard.png`
  - `phase1-t3web-global-direct-slim-wait-smoke.png`
- Latest direct-route smoke against the slim entry showed Coordinator enabled,
  selected project/goal visible, read-only composer visible, no send button, no
  cluster confirm, no approval action, no `No active thread`, and no internal
  enum leak.
- The repo already supports:
  - global_coordinator thread projection
  - goal_conversation thread projection from cluster runs
  - project binding semantics
  - /api/t3/projects
  - /api/t3/conversation-model
  - /api/t3/coordinator-entry
  - bridge helpers for project options, conversation model, cluster targets,
    coordinator goal start, display sorting, and coordinator shell entry fetch

Automatic work you may continue:
- repo-side read-only contracts and projection helpers
- generated T3 bridge source / README updates
- focused tests and release verification
- code review, risk review, and handoff cleanup
- focused external T3/RD-Code shell hardening if the local checkout is in scope

Human-owned work:
- final product judgment that the actual RD-Code shell feels like a first-class
  Global Coordinator conversation
- access/scope for an external RD-Code/T3 checkout
- merge, release, deployment, or publication
- deciding whether to push, merge, or release the current slice

Your mission:
- keep pushing Phase 1 total-control conversationization until only human
  product acceptance / merge / release remain
- do NOT reopen dashboard-first designs
- do NOT start LangGraph migration yet
- do NOT vendor external T3 source into this public repo
- do NOT replace OpenCode/ACP execution paths

Preferred next slice:
- review and harden the external T3/RD-Code read-only UI slice
- keep it read-only; do not start LangGraph migration or agent execution yet
- do not enable `ENABLE_DEVFRAME_CLUSTER_COMPOSER` in Phase 1
- preserve unrelated dirty external-checkout changes

Keep changes narrow.
Run focused tests first. In the public repo, use the release gate when public
repo files change:
`powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1`

In the external T3/RD-Code checkout, use focused web checks such as:
`pnpm --filter @t3tools/web test -- ChatView.logic.test.ts`
`pnpm --filter @t3tools/web test -- composer-logic.test.ts`
`pnpm --filter @t3tools/web typecheck`

When reporting progress, explain:
1. what changed
2. what user-facing or integration risk was reduced
3. what remains before the human needs to step in
```
