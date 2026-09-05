---
description: "Per-agent worktree capability seam over the worktree registry (ctx.agentWorktree): single-writer bindings plus the worktree_create/worktree_status/worktree_remove tools for agent sessions."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-agent-worktree

English | [中文](README.zh.md)

## Summary

`dsh-experimental-agent-worktree` is the per-agent layer over the [worktree registry](../../workflow/worktree-registry/README.md): it gives an agent session second checkouts of its workspace repository that only it may write to and remove. The Service Definition (`AgentWorktree`, mounted as `ctx.agentWorktree`) composes the registry's create/bind/status/remove with a single-writer protocol; the same package is the Consumer, exposing the `worktree_create`, `worktree_status`, and `worktree_remove` tools. Every call authorizes against the calling session's own workspace and binds to its durable session id, so a created worktree is that session's exclusive write target until the session unbinds or removes it. The package is experimental and private: it ships in no released bundle, and its contracts can change.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Use this package when agent sessions in the pluginized hierarchy need isolated checkouts with an exclusivity promise — a task's changes separated from the workspace, a parallel agent with its own tree. Skip it when sessions never create worktrees or when plain workspace-shared checkouts suffice; the workspace-facing [`tool-worktree`](../../workflow/tool-worktree/README.md) tools cover the shared case.

### When to use it

The plugin declares hard injections on `ctx.tools`, `ctx.workspaceRegistry`, `ctx.worktreeRegistry`, and `ctx.systemPrompt`, so it mounts only where the worktree registry is already mounted. The registry missing is not a degraded mode: the plugin fiber stays pending, contributes no tools, and activates the moment the registry arrives. A composition must not mount this package alongside `tool-worktree` — the three shared tool names would double-register and the second load fails loud.

### Setting up

A minimal composition for agent sessions:

```yaml
- name: '@deepseek-ai/dsh-storage'
- name: '@deepseek-ai/dsh-storage-domain'
  config:
    backend: json
- name: '@deepseek-ai/dsh-subprocess-local'
- name: '@deepseek-ai/dsh-workspace'
- name: '@deepseek-ai/dsh-worktree-registry'
- name: '@deepseek-ai/dsh-experimental-agent-worktree'
```

The package takes no Config: every choice — holder identity, target directory, branch — comes from the calling session or the model call.

### Creating, observing, and removing a bound worktree

`worktree_create` mints the checkout and binds it before answering; `worktree_status` reports the live facts plus who holds the binding; `worktree_remove` refuses for other holders and releases the caller's own binding on the way to git:

```text
worktree_create { path: 'wt-task-7', branch: 'agent/task-7' }
// → { id, path, branch } — bound to this session as its single writer
worktree_status { id }
// → { id, directoryExists, branch, clean, locked, lockedByThisSession }
worktree_remove { id }
// → { id, path } — another session's binding refuses; the holder's is released
```

The same operations are reachable programmatically through `ctx.agentWorktree` — a host tool policy can bind a worktree to a session it created without any model call.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design decisions behind the seam and points at the code that realizes them; the observable behavior is fully covered in [Use this package](#use-this-package).

### Design decisions

- **The registry keeps the enforcement point.** `AgentWorktree` adds policy, not a second enforcement surface: the registry's `remove` refuses any bound worktree whatever the caller asks, and this seam only decides when to unbind first. A host that bypasses `ctx.agentWorktree` hits the same wall.
- **The holder is the session's durable id.** `WorktreeLockHolder` stays opaque to the registry; this seam mints it from the calling session's durable id, so a recovered agent still matches its binding while a fresh agent identity in the same session would not be possible.
- **Authorization mirrors the session header.** The workspace comes from the immutable session `cwd`, never from the model; an id the workspace holds no row for is reported exactly like an unknown one.
- **Failures propagate as classified errors.** git refusals arrive as the registry's `WorktreeGitOperationError` kinds (occupied path, branch conflict, dirty tree, oversized path); binding refusals arrive as the registry's `WorktreeLockError`.

### Source map

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | The function plugin: service mount, the three tools, usage guidance |
| [`src/service.ts`](src/service.ts) | The abstract Service Definition and the `ctx.agentWorktree` key |
| [`src/provider.ts`](src/provider.ts) | Registry-backed provider: create+bind, workspace-authorized status, unbind-then-remove |
| [`src/authorization.ts`](src/authorization.ts) | Caller resolution: session cwd → workspace, session id → holder |
| [`src/types.ts`](src/types.ts) | Request, view, and status shapes — types only |

### Invariant

No runtime invariant companion is published: the seam holds no live state of its own — every guarantee it makes (binding exclusivity, workspace authorization) is enforced and observable at the worktree registry, which owns the durable rows and the removal path, so there is no independent observation that could diverge.

</details>

-----

<a id="model-experience"></a>
## Model Experience

### System prompt

#### What the model sees

Every parent request in this plugin's registration scope receives the fixed guidance below.

##### Agent worktree guidance

```markdown
The agent worktree tools manage second checkouts (git worktrees) of the calling session's own workspace. worktree_create binds the new worktree to this session as its single writer: other sessions can observe it but cannot remove it, and it survives restarts — always worktree_remove a worktree this session created before finishing, or unbind it explicitly if another session must take it over. Get ids from the creating session or the host before worktree_status or worktree_remove.
```

#### Token effect

Small fixed guidance cost per request while the plugin is active.

#### KV Cache effect

Prefix-stable while the plugin scope and guidance text are unchanged. Activation or disposal may invalidate reuse from this prompt section.

### Tool schema

#### What the model sees

The generated [`worktree_*` schemas](../../../docs/tool-catalog.md#deepseek-aidsh-experimental-agent-worktree) expose three tools. `worktree_create` takes a required `path` string and an optional `branch` string; `worktree_status` takes a required worktree `id`; `worktree_remove` takes the required `id` plus an optional `force` boolean. Registry-side details — durable rows, subprocess calls, refusal classification — are absent from the call schemas.

#### Token effect

Small fixed schema cost on each request where the tools are visible.

#### KV Cache effect

Prefix-stable while the definitions and visibility are unchanged.

### Tool results

#### What the model sees

Create returns `{ id, path, branch }` with render text naming the binding; status returns `{ id, directoryExists, branch?, clean?, locked, lockedByThisSession }`, the live fields absent when the directory is gone; remove returns `{ id, path }`. Errors return isError results whose text states the cause and the concrete fix — including the holder that owns a refused removal.

#### Token effect

Single-item results for all three tools.

#### KV Cache effect

Each result appends after the reusable request prefix; no prefix invalidation comes from this package.

## Known Limitations and Deferred Work

These limits define what the seam does not yet support. They are current constraints, not a task backlog.

- **One workspace per call** — the authorization anchors every operation to the calling session's workspace; a session cannot manage another workspace's worktrees even when that workspace is registered.
- **No list tool** — ids reach the model from the creating session's context or the host; a workspace-wide listing tool is deferred until a consumer needs it.
- **No unbind tool** — a session releases its binding only by removing the worktree; an explicit hand-over tool is deferred until the hierarchy needs it.
- **Stale bindings block others** — a session that abandons its worktree without removing it wedges removal for every other session until the binding's holder acts or the row is dropped through the registry's reconcile.
- **Presentation stays generic** — every card is the `generic` card; dedicated worktree card renderers are deferred.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

Open directions: an explicit unbind/hand-over tool pair for the hierarchy's worktree hand-off; a workspace-scoped list tool once a consumer needs it; wiring the holder to P01's `AgentBindingRecord.worktreeId` when session-identity lands.

</details>
