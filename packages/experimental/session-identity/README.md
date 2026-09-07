---
description: "Cordis service that persists agent binding records, restores them cold, and creates native Sessions with exact cwd and lineage metadata."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-session-identity

English | [中文](README.zh.md)

## Summary

`dsh-experimental-session-identity` mounts `ctx.agentBindings`, the durable binding registry of the pluginized agent hierarchy. It keeps one `AgentBindingRecord` per agent in its own `session_identity` storage domain (JSON documents under the composition's storages root), creates native Sessions with exact `cwd`, `parentSession`, and `delegationDepth` header metadata and writes host Session id, parent, and worktree into the binding in one durable write, binds agents that other entry points (spawn, fork, Team spawn, SDK) already created, and restores every binding cold on start. Queries answer from the in-process index; the domain table stays the only durable authority. The package is a private experimental host-side service: it registers no tools, no prompt sections, and no session events, so the TypeScript and Python SDK projections are untouched.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Mount the service in a composition that already mounts the session store and the storage stack; it hard-injects `ctx.sessions` and `ctx.storageDomain` and fails at activation when either is absent.

```yaml
- name: '@deepseek-ai/dsh-storage'
- name: '@deepseek-ai/dsh-storage-json'
  config:
    root: dshHomePath('storages')
- name: '@deepseek-ai/dsh-storage-domain'
  config:
    backend: json
- name: '@deepseek-ai/dsh-session'
- name: '@deepseek-ai/dsh-experimental-session-identity'
```

### Create a bound session

`createBoundSession` creates a standalone Session, not a live Agent. The parent must exist; the child depth derives from the parent header (`parent depth + 1`) unless the caller passes `delegationDepth` explicitly.

```ts
const { session, record } = await ctx.agentBindings.createBoundSession({
  cwd: workspacePath,
  role: 'lead',
  parentSessionId: controllerSession.id,
  pluginId: PluginId('agent-reliability'),
  worktree: { worktreeId, worktreePath, branch },
})
```

### Bind, query, and restore

`bind` registers an agent created through another entry point; an identical rebind is idempotent and a different one fails loud. `find`, `byRole`, and `list` answer from the index restored at start, so a cold process sees every binding without replaying sessions.

Inside Agent factory setup, use `bindPreparedSession(agentCtx.agent.session, request)` to persist the binding before publication. The factory owns Session creation and teardown; a standalone live Session cannot be adopted by a second factory call. Identity and lineage derive from the prepared Session. If later setup or publication fails, the binding remains reserved for explicit recovery instead of silently creating a replacement.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design decisions behind the feature and points at the code that realizes them; the observable behavior is fully covered in [Use this package](#use-this-package).

### Design decisions

- **One durable write per binding.** Creation validates role, parent referent, depth, and the worktree binding first, then creates the session and writes the complete record once — host Session id, parent, and worktree together — instead of staging partial facts.
- **Write-through index.** Every mutation awaits the domain table write and then mirrors the record into the query index; start rebuilds the index from the table in (createdAt, agentId) order, so restart and recovery need no replay.
- **No session events.** Binding records are host-side hierarchy metadata that never reaches a model request; their durability lives in this package's own storage domain, so `SessionEventMap` gains no member and neither SDK projection changes.
- **Idempotent rebind.** `bind` compares every identity field but `createdAt` — the timestamp is owned by the first write — and rejects a conflicting binding with a stable `SESSION_IDENTITY_ALREADY_BOUND` code.

### Source map

| File | Role |
|---|---|
| [`src/registry.ts`](src/registry.ts) | The `ctx.agentBindings` service: creation entry, bind, queries, cold restore |
| [`src/spec.ts`](src/spec.ts) | The `session_identity` domain spec and the zod record schema bound to the shared contract type |
| [`src/errors.ts`](src/errors.ts) | `SessionIdentityError` and its stable code union |
| [`src/index.ts`](src/index.ts) | Package entry and default export |

### Invariant

No runtime invariant companion is published: the query index is a write-through projection of one domain table and is rebuilt from it at start, and the JSON backend refuses a second live handle on the same unit, so no independent observation exists that could diverge.

</details>

-----

<a id="model-experience"></a>
## Model Experience

### Binding registry

#### What the model sees

Nothing. The package registers no tools, no prompt sections, and no session events — no `AgentBindingRecord` value ever reaches a model request — so no request field carries its data.

#### Token effect

Zero direct tokens on every request.

#### KV Cache effect

Independent of live requests: the package never touches a request prefix, so it cannot invalidate provider cache reuse.

## Known Limitations and Deferred Work

These limits define when the registry is a poor fit or needs special operational care. They are current package constraints, not a task backlog.

- **`bind` requires a live local session** — the agent id must resolve in the session store, so agents served by remote providers cannot be bound yet; a remote-binding shape is deferred until a consumer exists.
- **No unbind** — binding records are durable facts with no removal operation; an agent that leaves the hierarchy keeps its record, and a lifecycle removal is deferred until a consumer needs it.
- **A failed binding write leaves a live unbound session** — the session is created before the record is written, so a storage failure on the write path surfaces as a loud `SESSION_IDENTITY_PERSISTENCE` error and the caller owns the session's disposal.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
