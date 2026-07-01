# Next Agent Prompt - Global Coordinator Conversation Mainline

Copy/paste prompt:

```text
You are taking over work in the dev-frame-system repository on branch codex/public-mainline-batch-1.

Read these files first:
- docs/status/continue-global-coordinator-conversation-mainline.md
- docs/status/recon-receipt-global-coordinator-conversation-mainline.md
- docs/status/phase-1-global-coordinator-conversation-plan.md
- docs/status/cluster-coordinator-design-and-roadmap.md

Current truth:
- PR #4 is the active branch PR.
- The worktree may be dirty; inspect git status before acting.
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
  - read-only shell mapping fields selectedProject, projectOptions,
    projectCoordinatorThread, shellThreads, emptyStateReason, disabledReason
  - client smoke cross-checks the coordinator entry against /api/t3/projects,
    /api/t3/conversation-model, and /t3-shell.json
- Latest local release gate observed for this slice:
  powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
  -> 816 passed, 1 skipped; release verification passed
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
- small shell-consumption seams that do not require external RD-Code source

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
- if an external RD-Code/T3 checkout is explicitly in scope, wire the shell to
  consume /api/t3/coordinator-entry and fetchDevFrameCoordinatorShellEntry()
- keep that first real shell slice read-only; do not start LangGraph migration
  or agent execution yet

Keep changes narrow.
Run focused tests first, then run:
`powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1`

When reporting progress, explain:
1. what changed
2. what user-facing or integration risk was reduced
3. what remains before the human needs to step in
```
