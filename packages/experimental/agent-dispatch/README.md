---
description: "Host dispatch entry over the agent-hierarchy engine (ctx.agentDispatch): hierarchy-authorized lead creation with authoritative worktree-row validation, the single-writer lock, and the agent_dispatch consumption tool."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-agent-dispatch

English | [中文](README.zh.md)

## Summary

`dsh-experimental-agent-dispatch` is the host-side dispatch entry over the [agent-hierarchy engine](../agent-hierarchy/README.md). The service definition exposes `ctx.agentDispatch.createChildAgent(parent, request, options)` for composition-layer callers; the engine owns child-agent identity and lifecycle, and this adapter never implements creation itself. Before the engine call the adapter validates the request against the authoritative registry rows: registered worktree id, existing directory, path/branch match, and the workspace's lock occupant (`status` reports `directoryExists/branch/clean`; path and `lockedBy` come from `worktreeRegistry.list`). It reuses the engine's approved-scope contract (`config.leadPluginScopes[creator.agentId]`) — the adapter does not re-copy role policy, and engine rejections propagate unchanged. Assembly happens inside the entry: preset `composeFrom(parent.ctx)`, the `worktreeRegistry.bind` single-writer lock held by the child session id, then the engine's `bindPreparedSession`; an optional `prompt` is delivered through `child.agent.followup` only after the engine publishes. Caller-provided `setup` runs after the assembly slice and must not be used to supply the assembly itself. The same package is the Consumer, exposing the `agent_dispatch` tool. The package is experimental and private: it ships in no released bundle, and its contracts can change.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Use this package when a composition layer must turn the hierarchy's role rules into dispatched children — the controller turning tasks over to leads, a lead staffing workers inside its approved scopes. Skip it when the caller wants raw engine creation without registry validation or when the deployment has not preallocated lead identities; the engine's own `createChildAgent` remains the authority this entry delegates to.

### When to use it

Dispatch requires four decisions per call, all validated before the engine runs: the child's `role` (lead from the controller, worker from a lead), the `taskId` it owns (one task, at most one dispatched child), the `pluginId` scope it works under, and the `worktreeId` it will hold. A retried task passes `retry: true` — or the previously returned child id — and reuses the existing child without re-delivering its briefing. A dispatched child's worktree lock is bound to the child for its whole life; recover an interrupted creation through the engine's `recoverChildAgent` semantics (typed `SessionPersistenceNotFoundError` restores the original id; corruption and cancellation do not fall back), and the adapter adds only durable identity lookup — identity reuse never re-dispatches a prompt. A settled child continues through `followup: true` with a prompt: the instructions are delivered to that child's inbox as its next ordinary turn, while a fresh dispatch never queues a followup. When a dispatched child finishes a real turn, the service delivers a typed `dispatch-settled` notice to the parent as the parent's next ordinary turn, so the parent wakes on real completions without polling.

<a id="understand-the-implementation"></a>
## Understand the implementation

The Service mounts on the plugin fiber, so the seam lives and dies with the plugin (HMR-safe by construction). `AgentDispatchError` codes: `DISPATCH_WORKTREE_UNREGISTERED`, `DISPATCH_WORKTREE_MISMATCH`, `DISPATCH_PARENT_UNBOUND`, `DISPATCH_HIERARCHY_DENIED`. Engine rejections (role, scope, depth, dedupe) propagate as their own typed errors. `DispatchAgentOptions` is the adapter options face: the four engine `CreateChildAgentOptions` fields passed through key-explicit, plus the required `workspaceId` used for authoritative-row validation, the optional `prompt`, and the optional `followupPrompt` that delivers one continuation turn to an existing child. The per-task gate serializes identity check, engine create/recover, and first delivery into one atomic span, so concurrent same-task requests produce exactly one child and one briefing. The settlement watch mounts on fresh, reused, and cold-recovered children alike, deduplicating on the parent's durable ledger plus a claim scoped to the exact live child.

No runtime invariant companion is published: every guarantee the adapter makes (worktree registration, path/branch match, lock exclusivity, scope approval) is derived from the same authoritative registry rows and engine evaluation it calls, and the rejections are observable at the `AgentDispatchError` surface those calls return, so no independent observation exists that could diverge.

<a id="model-experience"></a>
## Model Experience

### System prompt

#### What the model sees

Every parent request in this plugin's registration scope receives the fixed guidance below.

##### Agent dispatch guidance

```markdown
The agent dispatch tool is the daily delegation entry over the agent hierarchy. The controller dispatches a lead per task onto its own registered worktree; the lead dispatches workers inside the plugin scopes approved for it in the deployment's leadPluginScopes. Every dispatch binds the worktree's single-writer lock to the new child for its whole life. A retried task reuses the existing child (retry: true) — never re-brief a running child.
```

#### Token effect

Small fixed guidance cost per request while the plugin is active.

#### KV Cache effect

Prefix-stable while the plugin scope and guidance text are unchanged. Activation or disposal may invalidate reuse from this prompt section.

### Tool schema

#### What the model sees

The `agent_dispatch` entry in the generated [tool catalog](../../../docs/tool-catalog.md#deepseek-aidsh-experimental-agent-dispatch) owns the schema; the consumption face adds no fields beyond it.

#### Token effect

Small fixed cost per dispatch round: one tool call plus its result naming the created child or the refusal cause.

#### KV Cache effect

Append-only per dispatch round; nothing in this package rewrites earlier request tokens.

## Known Limitations and Deferred Work

- Evidence state: the real-Loader composition suite proves tool registration and the controller/lead/worker visibility faces; the real model round proved the service face and one real dispatch round (worker artifact). The shipped opt-in overlay is wired — its candidate-profile verification (explicit `--patch`, isolated home) is the remaining acceptance step.
- Recovery of an interrupted creation reuses the engine's `recoverChildAgent` semantics; the adapter adds only durable identity lookup and never re-dispatches a prompt on identity reuse.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

Open directions: the worker-side repair-round return path once the orchestration domain owns it; wired lead-assignment consumption already landed in the devframe package. Dispatched-child settlement acknowledgment has landed: the settlement wake and the followup contract are covered by the [settlement notice note](../../../.agents/notes/implemented/architecture/2026-09-08-dispatch-settlement-wake.md).

</details>
