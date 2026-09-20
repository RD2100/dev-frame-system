# Agent Note: Hierarchical dispatch mode for the expert-team plugin

Status: implemented

English | [中文](2026-09-15-expert-team-m3.zh.md)

## Problem

In pipeline mode, the runtime creates a persona-scoped session per phase through the same scoped-create seam and drives one turn via `followup()` + `await agent.whenIdle()`. The controller / lead / worker distinction lives only in the data-pack YAML — the runtime treats all three identically. M3's software-development team needs the controller → lead → worker relationship visible at runtime: lead phases should act as dispatch parents, worker phases should be dispatch children, so the hierarchy guard can apply tool policies by role and the host-side binding registry can track the parent-child chain.

## Decision

For every phase session in hierarchical mode, the runtime calls `ctx.agentBindings.bind` after creation and before briefing delivery. Each binding carries three facts: role (`controller` / `lead` / `worker`), `parentSessionId` (the dispatch parent; present only for workers), and `pluginId` (`expert-team`). Binding is best-effort: it is skipped silently in environments that do not mount `agentBindings` (most tests); real deployments always mount it.

The session header is seeded with `parentSession` and `delegationDepth` (parent depth + 1) so the hierarchy guard reads the correct depth through `delegationDepthOf` at execution time without exceeding the absolute budget. Worker phases resolve their parent on the orchestrator side via BFS along the `depends_on` graph to the nearest completed lead or controller; when none is found the binding is skipped silently.

M3 reuses scoped-create as the derivation seam instead of `agentHierarchy.createChildAgent`'s dispatch seam: expert-team phases have no registered worktree, and the dispatch seam requires worktree binding (path match + cwd alignment + independence from parent). Scoped-create plus post-creation `bind` is lighter and shares the same derivation line as pipeline mode.

## Alternatives considered

**Full dispatch through `agentDispatch.createChildAgent`.** Rejected: the dispatch seam requires a registered worktree, and expert-team's artifacts are files inside the run directory, not worktrees; introducing worktree management buys no corresponding benefit.

**Bind role inside the setup window.** Rejected: `bindPreparedSession` runs inside setup, but scoped-create's setup window executes before the session is persisted to the session store; post-creation `bindAgent` achieves the same result with cleaner timing.

**Install hierarchy-guard tool restrictions on expert-team agents.** Rejected: the guard's `leadPluginScopes` lookup is keyed by exact creator agentId, and expert-team session ids are derived at runtime (containing runId); the guard's deny face does not conflict with the expert allowlist (the allowlist is more restrictive), so binding establishes the role relationship without producing tool-side effects.

## Consequences

Gained: the parent-child relationship is visible to the host — `ctx.agentBindings.list()` can filter expert-team bindings by role / `parentSessionId`; the controller → lead → worker chain is durably recorded through session header plus binding row; worker phase dispatch parents are derived automatically from the `depends_on` graph, with no extra data-pack field to maintain. Tool policy is unchanged: the expert allowlist remains the primary restriction, and the hierarchy guard's deny face does not affect the tool set the expert allowlist permits. Cost: binding adds `parentSession` / `delegationDepth` to the session header, but those fields are inert for expert-team phase semantics; legacy deployments that do not mount `agentBindings` skip binding silently — hierarchy-side visibility is lost but phase execution is unaffected.

## Testing

Runtime unit tests cover the best-effort binding path (no agentBindings mounted, binding skipped without error); worker phase `resolveParentAgent` BFS to the nearest lead or controller parent; and correct `parentSession` + `delegationDepth` in the session header after binding. Orchestration tests add two hierarchical paths: one boots a test-only Loader composition with the fixture hierarchical pack, proving controller → worker two-phase execution, artifact durability, and run-state mirroring; the other mounts Storage + StorageDomain + AgentBindingRegistry and verifies the binding rows — controller has no parent, worker's `parentSessionId` points to the controller's agentId, and `pluginId` is `expert-team`. REAL-composition spec drives the four tools (`expert_team_list`, `expert_team_run`, `expert_team_status`, `expert_team_approve`) through a mock model adapter under the REAL harness, carrying model-visible coverage during the snapshot-tier gap.
