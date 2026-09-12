---
description: "Remote owner of the Shadow router status snapshot, the panel write faces, and the persistent Shadow conversation host."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-shadow-controller

English | [中文](README.zh.md)

## Summary

`dsh-experimental-shadow-controller` is the Remote owner of the [Shadow router's](../shadow-router/README.md) aggregate status, of the panel write faces host status surfaces drive, and of the human's conversational Shadow. It backs the generated `ctx.remote.shadow` namespace with one honest read, `readStatus()` — whether a shadow router is mounted, which controller session the host composition designated, whether that session is live, the authorized roots, and the open-project rows — three project writes (`openProject(path)`, `sendToController(workspaceId, text)`, `releaseProject(workspaceId)`) that delegate to the router's host bridges, and two conversation faces (`postMessage(text)`, `readConversation(cursor)`) served by the persistent conversation host. Every project write keeps validation, the caller gate (riding the designated Shadow's authority), replay, and the delivery channel in the router; the controller only mints a fresh request id per action. Official releases exclude this package, so it is available only from a source checkout.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Further Exploration](#further-exploration)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

### Read the status from a browser surface

Mount the service beside its [shadow router](../shadow-router/README.md) provider (the [DevFrame profile layer](../devframe-profile/README.md) does this), then call the generated namespace:

```ts
const result = await ctx.remote.shadow.readStatus()
if (!result.ok) return
// result.value: { mounted, shadowSessionId?, shadowLive, authorizedRoots, bindings }
```

`mounted: false` means this deployment composes no shadow router; `shadowSessionId` absent with `mounted: true` means the router exists but the host has not designated a controller. Both are honest not-enabled answers, never a fabricated online state.

### Drive the panel writes

```ts
await ctx.remote.shadow.openProject({ path: 'D:/projects/alpha' }) // ProjectOpenResult
await ctx.remote.shadow.sendToController({ workspaceId, text: 'ship the release' }) // ProjectSendResult
await ctx.remote.shadow.releaseProject({ workspaceId }) // ProjectStopResult, status 'stopped'
```

Failures resolve as `{ ok: false, error: { code, message } }` and carry the router's own rejection verbatim — an unauthorized root, a missing path, a closed project — so a surface shows the service's reason instead of inventing one. With no router mounted, the read stays honest (`mounted: false`) and every write fails loud.

### Talk to the Shadow

Mount the conversation host row (the DevFrame profile layer inserts it), then post into the designated session and read the surface back:

```ts
await ctx.remote.shadow.postMessage({ text: 'Open D:/projects/alpha and fix the failing tests.' })
const page = await ctx.remote.shadow.readConversation({})
// page: { messages: [{ seq, role: 'user' | 'shadow', text, at }], cursor }
```

`postMessage` accepts the message and returns immediately; the session's agent loop claims it, runs the turn — the model may call the four conversational tools — and the reply lands on the persisted surface. `readConversation` folds that surface into bounded, cursor-addressed rows, so a chat surface polls with the returned `cursor`. The conversation survives restarts through session persistence, and the host stays inert (every verb fails loud) while the deployment declares no Shadow session.

### What you get

- The `ctx.shadowController` service with the honest `readStatus()` method, the three write faces, and the two conversation faces.
- The `ctx.shadowAgent` conversation host (`./shadow-agent` entry): create-or-restore of the designated session, the four conversational tools, the persona section, the design tool allowlist enforcement, and the bounded conversation read.
- The generated `@deepseek-ai/dsh-experimental-shadow-controller/remote` Client artifact and the `./types` subpath carrying the status, write, and conversation vocabulary.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

`ShadowController` extends `TypertRemoteService` under the service key `shadowController` and the Remote namespace `shadow`; `ShadowAgent` (same package, `./shadow-agent` entry) is an ordinary Service under `shadowAgent` that injects the agents registry. Every `@Remote` method is decorator-registered; the typert generator emits the host face and the Client contribution under `lib/`. The project writes call `ctx.get('shadowRouter')` and the router's host bridges with a `randomUUID()` request id minted per action. `ShadowAgent.ensure()` resolves the designated session id from the router's snapshot, reuses a live session as found (never owning another row's lifecycle), awaits the complete application, then resumes the persisted session or creates it through `ctx.agents`; the factory setup composes the scoped world — the four conversational tools (`installShadowConversationTools`), the persona section, the design tool allowlist over the session's model face (native presentation pin, inherited tools restricted to explicitly enabled memory access, and the monotonic execution guard), and, on a fresh session, the host default model selection. Only a session this host created or resumed is disposed with it.

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | `ShadowController` service: the read, the three write faces, and the two conversation faces |
| [`src/shadow-agent.ts`](src/shadow-agent.ts) | `ShadowAgent` conversation host: create-or-restore, post, bounded conversation read |
| [`src/shadow-tools.ts`](src/shadow-tools.ts) | The four conversational tools over the router's host bridges |
| [`src/shadow-prompt.ts`](src/shadow-prompt.ts) | The Shadow persona section |
| [`src/types.ts`](src/types.ts) | Client-safe status, write, and conversation vocabulary (types only) |
| [`lib/typert.host.js`](lib/typert.host.js) | Generated host FaceModel with the strict result codecs |
| [`lib/typert.remote-client.js`](lib/typert.remote-client.js) | Generated Client contribution mounting `ctx.remote.shadow` |
| — | No runtime invariant companion is published; the conversation host is covered by a real-composition suite (loop, storage, persistence, router, mock model). |

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [Shadow router](../shadow-router/README.md) — the designated-controller domain, the delivery channel, and the host write bridges this controller exposes.
- [Shadow Web entry](../client-ui-shadow-entry/README.md) — the resident sidebar panel that reads and writes this namespace.
- [Experimental packages](../README.md) — incubation status and release exclusion.

-----

<a id="model-experience"></a>
## Model Experience

### Shadow conversation host

#### What the model sees

The conversation host gives the designated Shadow session a model-visible face: one scoped persona section (`experimental:shadow` — the human's global agent, the human → Shadow → project-controller → worker hierarchy, and the honesty rules) and four tools — `shadow_open_project`, `shadow_message_controller`, `shadow_release_project`, and `shadow_status` — whose schemas carry only task concepts and whose executions run the router's host bridges. No other agent scope sees the section or the tools. The host also enforces the design allowlist over the composed session's model face: the presentation is pinned native, every inherited deployment tool except explicitly enabled user memory (`memory_search`, `memory_read`, `memory_append`) is hidden from the face, and a monotonic guard denies the execution of anything else the scope carries — including the router's same-layer `project_*` whitelist, whose schemas stay visible as a documented residual. The Remote faces themselves stay host-plane and never answer a model.

#### Token effect

Every request in the designated session carries the persona section and the four tool schemas once, on top of the conversation's own history; each conversational tool call appends one result turn.

#### KV Cache effect

The persona section and the four tool schemas enter the designated session's prompt; because the session persists, they occupy that prefix for the conversation's whole life. Other sessions are untouched.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

- **Writes ride the designated Shadow's authority** — the bridges run the same gated flows the model-facing tools run, so a deployment whose designated session is absent or not live rejects every write with an honest message instead of bypassing the gate.
- **The router's `project_*` schemas stay visible on the designated scope** — the conversation host enforces the design allowlist on the session it composes (native presentation pinned, inherited deployment tools hidden except explicitly enabled memory access, and a monotonic guard denying every other execution), but the router's own `markShadow` installs its `project_*` tools into the same scope layer, and the tool registry deliberately exempts a scope's own registrations from restrictions — so the four schemas remain visible while their execution is denied. Closing the visibility residual needs the router-side contract change (one tool face per designated session), not a host-side filter.
- **Do not declare the session in the loop config** — a deployment that creates the designated session through `agent-loop`'s `agents` config leaves the conversation host unable to compose the persona, tools, and allowlist enforcement (the session is used as found); let this host create it.
- **Release is stop semantics** — a released project lands on `stopped` and stays visible with its row; re-opening it is refused by the router (`SHADOW_PROJECT_STOPPED`) because restart follows the host recovery policy.
- **Source-checkout only** — official CLI, Web, npm, and Python release payloads exclude this private package.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
