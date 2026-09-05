# Agent Note: Model-facing worktree tools bound to the calling session's workspace

Status: implemented

English | [中文](2026-09-05-worktree-tools-and-reconcile.zh.md)

## Problem

The worktree registry seam shipped as a host-side service: `ctx.worktreeRegistry` with create/list/status/remove, durable rows, and a provider that runs git. Nothing exposed it to the model, so the capability the seam was built for — an agent managing its workspace's second checkouts — stayed unreachable, and two host-side gaps made a naive exposure unsafe:

- A tool that accepted a workspace id from the model would let one session's agent create, inspect, or delete another workspace's worktrees by guessing ids; durable worktree ids are stable, guessable-in-principle references.
- Rows and git drift apart in normal use: a user deletes a worktree directory outside the product, or creates one with plain git. The registry's `remove` refused on vanished directories with no recovery path, and outside-created worktrees were invisible to `list`.

## Decision

Package `packages/workflow/tool-worktree` (`@deepseek-ai/dsh-tool-worktree`) is the seam's Consumer: five model-facing tools — `worktree_create`, `worktree_list`, `worktree_status`, `worktree_remove`, `worktree_prune` — registered on `ctx.tools`, with a fixed routing guidance section in the system prompt. The package is configless; every deployment-varying value stays in the registry's Config. It rides the [registry seam](../architecture/2026-09-05-worktree-registry.md), whose operations and durable rows it consumes without re-implementing.

### Authorization: the session cwd is the anchor

Every execute body resolves the caller from `exec.agent`'s session header cwd — never from a model-supplied id. The cwd is canonicalized with `fs.realpath` and matched against `ctx.workspaceRegistry`'s registered paths (case-folded on Windows); a call without a calling agent, a header without a cwd, or an unregistered directory rejects with the reason stated. Tool ids resolve through the caller's workspace only: an id registered under a different workspace is reported with the same message as an unknown id, so error differences leak nothing about other workspaces' registrations. Relative `worktree_create` targets resolve against the authorized workspace directory explicitly, so the registry always receives an absolute path regardless of the host process cwd.

### Reconcile as the drift recovery path

The seam gained `reconcile`, and `worktree_prune` exposes it: report-only by default, with `pruneDangling: true` dropping stale registrations and `adoptUnregistered: true` registering outside-created worktrees. The registry owns the semantics and the `git worktree prune` call; the tool owns the flag mapping and a report rendering that names dangling registrations, unregistered worktrees, and applied action counts. `worktree_status`'s missing-directory observation and `worktree_remove`'s vanished-directory refusal both point at `worktree_prune` as the recovery.

### Failure dialects as model-usable retry semantics

The registry classifies the four git refusal dialects a model can actually cause — occupied path, branch conflict, dirty tree, oversized path — into typed errors whose text states the concrete fix. The tools add no classification of their own; `worktree_create`'s description names the refusal kinds so the model can retry with a corrected argument without host help.

### Presentation and logging

Pending calls render `generic` cards titled from the call's arguments; results keep plain generic cards with per-item render text where it aids recovery. Results ride the ordinary tool call/result session events — no new `SessionEventMap` member is owed. Composition mounts the consumer in the base bundle's agent plane; the web-app bundle keeps it disabled beside its enabled registry.

## Alternatives considered

- **Workspace id as a tool parameter** (the model passes which workspace to manage): rejected — the anchor for "which worktrees may this call touch" is the directory the session actually runs in; a model-supplied id would let any session manage any workspace and made the authorization a politeness check instead of a boundary.
- **Per-tool config fields** (tool names, guidance toggle, id validation strictness): rejected — the consumer has no deployment-varying choice of its own; the registry's Config owns timeouts and output bounds, and the guidance text is part of the tool contract like any tool description.
- **Reconcile flags inside `worktree_remove`** (a `--prune` variant that drops vanished rows): rejected — remove's contract is "delete one worktree through git"; silently turning it into a registry cleanup conflates one worktree's lifecycle with the workspace's whole registration set, and the report-only default of reconcile would have no surface.
- **Dedicated card renderers** for status and prune: deferred — the generic card with per-item text carries the recovery information; the Web card pipeline can derive richer worktree cards later from the same raw events.
- **A session event per reconcile adoption**: rejected — adoption becomes durable registry state observable through later tool calls; the log already carries the tool exchange that performed it.

## Consequences

The seam is complete: the model creates, observes, removes, and reconciles worktrees of the session's own workspace, and cannot reach another workspace's registrations even by guessing stable ids. The drift that previously wedged `remove` forever now has an explicit, model-invoked recovery. What it cost:

- **The cwd anchor is strict.** A session whose header cwd moved or was never attached to a registered workspace cannot use the tools at all, even a workspace-scoped read.
- **Adoption is unconditional.** `adoptUnregistered` trusts `git worktree list`; a linked checkout of an unrelated repository can be adopted under the reconciling workspace with no confirmation step.
- **The guidance section costs tokens.** Every request in the plugin's registration scope carries the fixed routing guidance; the text states the authorization scope and the prune recovery to keep model retries cheap.

## Verification

- `pnpm exec vitest run packages/workflow/tool-worktree` covers the authorization rejections (no agent, no cwd, unregistered directory, foreign id indistinguishable from unknown), relative/absolute target resolution, empty-argument rejection before the registry runs, remove with and without `force`, prune flag mapping, and the render texts (`packages/workflow/tool-worktree/tests/tool-worktree.spec.ts`).
- The registry-side reconcile and failure-classification coverage lives in `packages/workflow/worktree-registry/tests/` and is reported by the [seam Agent Note](../architecture/2026-09-05-worktree-registry.md).
- `pnpm run gen-tool-catalog` keeps the generated `worktree_*` schemas fresh; the catalog entry mounts a stand-in registry because the schema does not depend on the provider.
