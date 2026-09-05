# Agent Note: DevFrame three-tier spawn policy as per-tier delegation overrides

Status: implemented

English | [中文](2026-09-05-devframe-hierarchy-spawn-policy.zh.md)

## Problem

DevFrame's product rule "controller builds leads, a lead builds workers, a worker builds nothing" existed only as mechanism: the subagent seam already supported per-spawn `toolFilter` and absolute `maxDepth` caps, but nothing fixed which overrides each tier's spawn carries. A spawned executor therefore kept a working delegation tool by default, and the three-tier structure stayed an orchestration convention instead of a tested capability.

## Decision

`devframeSpawnOverrides(tier)` in [`packages/experimental/devframe/src/hierarchy/index.ts`](../../../../packages/experimental/devframe/src/hierarchy/index.ts) fixes the per-tier policy as detached delegation-request overrides: every DevFrame spawn pins `maxDepth` to the tree budget `2` (controller 0, lead 1, worker 2), and a worker spawn additionally denies the delegation tool through `toolFilter.deny` (default name `subagent`, overridable for renamed deployments). Enforcement stays in the seam at the executor: the tools registry refuses a denied tool at execution with `UNKNOWN_TOOL` (not prompt absence alone), `SubagentDepthError` refuses a spawn above the budget before any child is published, and the continuable descriptor persists the `toolFilter` so cold resume reapplies it. Tests anchor the executor-level refusal, the depth-budget refusal, the parent-child `sendMessage` direction authorization, and the cold-resumed role in `packages/subagent`.

## Alternatives considered

- **Extend the subagent seam's spawn request with a role concept.** Rejected: both enforcement mechanisms already exist in the seam, so a role field would duplicate policy the caller can express with existing fields and widen the seam's contract without new enforcement.
- **Rely on depth alone through deployment tool configuration.** Rejected as the sole path: the delegation tool's default `maxDepth` is `3`, so depth-only enforcement requires every deployment to remember a config change; the deny filter makes the refusal intrinsic to the spawned child regardless of tool config.

## Consequences

- DevFrame parents must spread the overrides on every spawn; a spawn that omits them keeps the seam defaults, so the policy is a library contract, not something the seam imposes.
- A worker keeps `send_message` and the control tools: the deny list names only the delegation tool, so reporting to its lead over the authorized parent-child routes still works.
- Cold resume preserves the role because the descriptor carries the filter; a resumed worker is still executor-denied the spawn tool and still pinned at its persisted depth floor.
