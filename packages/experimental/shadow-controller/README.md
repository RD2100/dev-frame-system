---
description: "Remote owner of the Shadow router status snapshot and the panel write faces for host status surfaces."
kind: "package"
---

# @deepseek-ai/dsh-experimental-shadow-controller

English | [中文](README.zh.md)

## Summary

`dsh-experimental-shadow-controller` is the Remote owner of the [Shadow router's](../shadow-router/README.md) aggregate status and of the panel write faces host status surfaces drive. It backs the generated `ctx.remote.shadow` namespace with one honest read, `readStatus()` — whether a shadow router is mounted, which controller session the host composition designated, whether that session is live, the authorized roots, and the open-project rows — and three writes: `openProject(path)`, `sendToController(workspaceId, text)`, and `releaseProject(workspaceId)`. Every write delegates to a shadow-router host bridge, so validation, the caller gate (riding the designated Shadow's authority), replay, and the delivery channel stay the router's own; the controller only mints a fresh request id per action. The service never wakes a model. Official releases exclude this package, so it is available only from a source checkout.

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

### What you get

- The `ctx.shadowController` service with the honest `readStatus()` method and the three write faces.
- The generated `@deepseek-ai/dsh-experimental-shadow-controller/remote` Client artifact and the `./types` subpath carrying `ShadowStatusView` and the write vocabulary.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

`ShadowController` extends `TypertRemoteService` under the service key `shadowController` and the Remote namespace `shadow`. Every method is `@Remote`-decorated; the typert generator emits the host face and the Client contribution under `lib/`. The implementation calls `ctx.get('shadowRouter')` — optional-service read, no declared injection. `readStatus()` projects the router's snapshot verbatim beside the `mounted` fact; the writes call `openProjectForHost`, `sendToProjectForHost`, and `releaseProjectForHost` with a `randomUUID()` request id minted per action, because each panel action is one fresh intent.

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | `ShadowController` service: the read and the three `@Remote` write faces |
| [`src/types.ts`](src/types.ts) | Client-safe `ShadowStatusView` and write vocabulary (types only) |
| [`lib/typert.host.js`](lib/typert.host.js) | Generated host FaceModel with the strict result codecs |
| [`lib/typert.remote-client.js`](lib/typert.remote-client.js) | Generated Client contribution mounting `ctx.remote.shadow` |
| — | No runtime invariant companion is published; every method is a projection of or a delegation to router state already covered by the router's own suites. |

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

None. The service is host-plane and never invoked by a model; it adds no prompt, tool, or schema content.

#### KV Cache effect

None — the controller contributes no model-visible content.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

- **Writes ride the designated Shadow's authority** — the bridges run the same gated flows the model-facing tools run, so a deployment whose designated session is absent or not live rejects every write with an honest message instead of bypassing the gate.
- **Release is stop semantics** — a released project lands on `stopped` and stays visible with its row; re-opening it is refused by the router (`SHADOW_PROJECT_STOPPED`) because restart follows the host recovery policy.
- **Source-checkout only** — official CLI, Web, npm, and Python release payloads exclude this private package.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
