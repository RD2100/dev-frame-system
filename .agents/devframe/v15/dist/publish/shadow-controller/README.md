---
description: "Read-only Remote owner of the Shadow router status snapshot for host status surfaces."
kind: "package"
---

# @deepseek-ai/dsh-experimental-shadow-controller

English | [中文](README.zh.md)

## Summary

`dsh-experimental-shadow-controller` is the read-only Remote owner of the [Shadow router's](../shadow-router/README.md) aggregate status. It backs the generated `ctx.remote.shadow` namespace with one method, `readStatus()`, that answers the deployment's real facts: whether a shadow router is mounted, which controller session the host composition designated, whether that session is live, the authorized roots, and the durable binding rows. The read never mutates router state and never wakes a model. Official releases exclude this package, so it is available only from a source checkout.

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

### What you get

- The `ctx.shadowController` service with the read-only `readStatus()` method.
- The generated `@deepseek-ai/dsh-experimental-shadow-controller/remote` Client artifact and the `./types` subpath carrying `ShadowStatusView`.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

`ShadowController` extends `TypertRemoteService` under the service key `shadowController` and the Remote namespace `shadow`. `readStatus()` is `@Remote`-decorated; the typert generator emits the host face and the Client contribution under `lib/`. The implementation calls `ctx.get('shadowRouter')` — optional-service read, no declared injection — and projects the router's `readStatus()` verbatim beside the `mounted` fact.

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | `ShadowController` service and the single `@Remote readStatus()` method |
| [`src/types.ts`](src/types.ts) | Client-safe `ShadowStatusView` vocabulary (types only) |
| [`lib/typert.host.js`](lib/typert.host.js) | Generated host FaceModel with the strict result codec |
| [`lib/typert.remote-client.js`](lib/typert.remote-client.js) | Generated Client contribution mounting `ctx.remote.shadow` |
| — | No runtime invariant companion is published; the read is a pure projection of router state already covered by the router's own suites. |

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [Shadow router](../shadow-router/README.md) — the designated-controller domain and binding index this controller projects.
- [Shadow Web entry](../client-ui-shadow-entry/README.md) — the resident sidebar card that reads this namespace.
- [Experimental packages](../README.md) — incubation status and release exclusion.

-----

<a id="model-experience"></a>
## Model Experience

None. The service is read-only, host-plane, and never invoked by a model; it adds no prompt, tool, or schema content.

#### KV Cache effect

None — the controller contributes no model-visible content.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

- **Read-only by construction** — the controller exposes no write face; mutations stay with the shadow router's own host-side APIs. Future status actions (for example requesting a stop from the Web) need a deliberate write-face decision first.
- **Source-checkout only** — official CLI, Web, npm, and Python release payloads exclude this private package.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
