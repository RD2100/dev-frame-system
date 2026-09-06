---
description: "Cordis service that routes user intent between independent project roots: a durable controller-binding store, cross-root delivery persistence with distinct received and completed states, and the four model-facing project tools behind a Shadow-only whitelist."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-shadow-router

English | [中文](README.zh.md)

## Summary

`dsh-experimental-shadow-router` mounts `ctx.shadowRouter`, the Shadow-side router of the pluginized agent hierarchy. It keeps one controller binding per workspace in its own `shadow_router` storage domain (JSON documents under the composition's storages root), provisions each project's independent controller root session with exact `cwd` metadata, persists every cross-root delivery twice — the sender's `queued` intent and the target-accepted `received` input — with `completed` as a separate durable state, and installs exactly four project tools (`project_open`, `project_send`, `project_status`, `project_stop`) into the one agent scope the host designates as Shadow. Stopping is per-project: other bindings, their controllers, and their queues are untouched. The package is a private experimental host-side service; it registers no prompt sections and no session events, so the TypeScript and Python SDK projections are untouched.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Mount the service in a composition that already mounts the storage stack, the session store, the workspace registry, and the session-identity binding registry; it hard-injects `ctx.sessions`, `ctx.storageDomain`, `ctx.workspaceRegistry`, and `ctx.agentBindings`, and fails at activation when any is absent.

```yaml
- name: '@deepseek-ai/dsh-storage'
- name: '@deepseek-ai/dsh-storage-json'
  config:
    root: dshHomePath('storages')
- name: '@deepseek-ai/dsh-storage-domain'
  config:
    backend: json
- name: '@deepseek-ai/dsh-session'
- name: '@deepseek-ai/dsh-workspace'
- name: '@deepseek-ai/dsh-experimental-session-identity'
- name: '@deepseek-ai/dsh-experimental-shadow-router'
  config:
    authorizedRoots: [dshHomePath('projects')]
```

### Config

| Field | Default | Meaning |
|---|---|---|
| `authorizedRoots` | `[]` | Absolute directories a project root may live under. Empty means nothing can be opened (fail-closed). |
| `controllerProfile` | `'devframe'` | Profile key pinned on every binding; an existing binding pinned to another profile is rejected. |
| `shadowSessionId` | not set | Session id the composition declares as its Shadow. The service performs the `markShadow` invocation itself when that agent is live (at activation) or created; absent or never-created installs nothing (fail-closed). |
| `maxPendingDeliveries` | `16` | Per-project cap on `queued` deliveries; a full queue rejects new input before acceptance. |
| `maxMessageChars` | `20000` | Upper bound on one delivery's text. |
| `statusPageSize` | `20` | Maximum projects and deliveries per `project_status` page. |

### Designate the Shadow and call the tools

`markShadow(agent)` installs the four tools into that agent's scope and nothing else; every other scope resolves none of them. The host calls the same service methods the tools dispatch to, plus host-only seams the model never reaches: `setActiveGoal` authorizes one open run per project, `completeDelivery` settles a received delivery, `confirmProjectStopped` finishes a stop, and `recoverDeliveries` converges interrupted rows on restart.

```ts
const shadow = ctx.agentLoop.create(SessionId('session-shadow'), { provider: 'mock', model: 'mock' })
ctx.shadowRouter.markShadow(shadow)

const open = await ctx.shadowRouter.openProject(shadow, { path: projectRoot, requestId: 'open-1' })
await ctx.shadowRouter.setActiveGoal(open.workspaceId, goalId, acceptanceHash)
const receipt = await ctx.shadowRouter.sendToProject(shadow, {
  workspaceId: open.workspaceId, bindingRevision: open.bindingRevision,
  goalId, acceptanceHash, requestId: 'send-1', mode: 'work', text: '…',
})
```

Compositions can also declare the designation in the row's config: with `shadowSessionId` set, the service performs the `markShadow` invocation itself — immediately when that agent is already live at activation, otherwise when it is created — while session creation stays host-owned. An id that never becomes live installs nothing, and an unconfigured mount keeps the fail-closed `SHADOW_CALLER_FORBIDDEN` behavior.

```yaml
- name: '@deepseek-ai/dsh-experimental-shadow-router'
  config:
    authorizedRoots: [dshHomePath('projects')]
    shadowSessionId: session-shadow
```

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design decisions behind the feature and points at the code that realizes them; the observable behavior is fully covered in [Use this package](#use-this-package).

### Design decisions

- **One provisioning state machine per project.** `reserving → provisioning → ready` persists each step before acting on it, so a crash at any point leaves a row a later open or host reconcile converges around: the reserved session id is never minted twice, a creation failure rolls the row to a visible `failed` state, and a cwd mismatch parks as `needs_attention` instead of a second writer.
- **Two-write delivery, three durable states.** `sendToProject` persists the sender intent as `queued` first, then marks the target-accepted input `received`; `completed` is a controller-side fact the host settles separately, so a receipt never claims work ran. `queued → received` and `received → completed` are the only forward transitions; cancelled queued rows stay visible with a reason.
- **Request replay journal.** Every open/send/stop stores its normalized input hash and result keyed by the caller's `requestId`, so a retry after an interrupted response replays the stored result instead of duplicating work, and the same id with different input fails loud (`SHADOW_REQUEST_CONFLICT`).
- **Registry facts, not mailbox semantics.** Routing reuses workspace-registry canonical-path facts (`fs.realpath` canon, alias-collapsing, segment-aware overlap checks); agent-team mailbox member validation is deliberately not reused, because a Shadow target is authorized by the binding store, not by team membership.
- **Per-project stop isolation.** Stopping cancels only that binding's `queued` deliveries (kept visible with `project-stopped` reasons), parks the binding in `stopping`, and leaves every other binding, controller session, and queue untouched; accepted deliveries survive a later stop.

### Source map

| File | Role |
|---|---|
| [`src/service.ts`](src/service.ts) | The `ctx.shadowRouter` service: binding lifecycle, delivery persistence, replay, status, host seams |
| [`src/tools.ts`](src/tools.ts) | The four project tools and their Shadow-scope installation |
| [`src/spec.ts`](src/spec.ts) | The `shadow_router` domain spec: bindings, deliveries, and requests tables |
| [`src/ids.ts`](src/ids.ts) | Branded request, message, and acceptance-hash ids |
| [`src/errors.ts`](src/errors.ts) | `ShadowRouterError` and its stable code union |
| [`src/index.ts`](src/index.ts) | Package entry and default export |

### Invariant

No runtime invariant companion is published: the in-memory index is a write-through projection of one domain table and is rebuilt from it at start, and the JSON backend refuses a second live handle on the same unit, so no independent observation exists that could diverge.

</details>

-----

<a id="model-experience"></a>
## Model Experience

### Shadow project tools

#### What the model sees

The designated Shadow scope gains exactly four tools. `project_open` resolves one authorized existing directory to a workspace and controller root; `project_send` delivers one bounded `work`/`note` message and returns a `received` receipt that never claims completion; `project_status` reads one project or a bounded page, including per-delivery state and blocking reasons; `project_stop` stops exactly one project and reports stopping until the host confirms. Failures return structured `SHADOW_*` codes (stale revision, unknown workspace, unauthorized caller, oversized text, queue full), never raw storage errors.

#### Token effect

Four tool schemas persist in the Shadow scope's tool list on every request; each tool call adds one result turn bounded by the delivery and status page limits.

#### KV Cache effect

The tool schemas are declared once and stay byte-stable, so the request prefix before the first project call reuses provider cache; per-call results append after it and do not invalidate the shared prefix.

## Known Limitations and Deferred Work

These limits define when the router is a poor fit or needs special operational care. They are current package constraints, not a task backlog.

- **No UI state set** — the client-facing project state projection (queue cards, stop confirmations) is a separate concern and is not part of this package.
- **Delivery presentation is host-side** — the router persists and receipts deliveries; forwarding received input into the controller's session log is the host composition's job, so a bare mount receives nothing model-visible.
- **Empty `authorizedRoots` opens nothing** — the fail-closed default is deliberate; a composition must name the roots it serves.
- **One live process per storage root** — the JSON backend refuses a second live handle on the same unit, so a second router process over one root fails loud instead of racing it.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
