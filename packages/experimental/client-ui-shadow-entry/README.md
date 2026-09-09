---
description: "Resident Web Shadow entry card: honest status above Settings, backed by the read-only status controller."
kind: "package"
---

# @deepseek-ai/dsh-experimental-client-ui-shadow-entry

English | [中文](README.zh.md)

## Summary

`dsh-experimental-client-ui-shadow-entry` is the resident Web entry for [Shadow](../shadow-router/README.md). It mounts the generated `ctx.remote.shadow` Remote namespace and registers one card into the sidebar's `sidebar.footer.action` seat — the footer stack above Settings — showing the deployment's honest Shadow state: not-enabled while no router is mounted or no controller session is designated, configured while the designated session is not live, and online once it is. The opened panel lists the controller session, the authorized roots, and every durable binding with its workspace, path, and revision. Official releases exclude this package, so it is available only from a source checkout.

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

### Install into a Web profile

Add the [shadow-controller host layer](../shadow-controller/README.md) (the [DevFrame profile layer](../devframe-profile/README.md) carries it) and this package's [Web layer](../shadow-web-profile/README.md). The card reads `ctx.remote.shadow.readStatus()` once on mount and again each time the panel opens; a failed read shows the transport error instead of pretending a state.

### What you get

- The resident trigger (icon plus label in the wide sidebar, icon only in the rail) with the phase dot: gray loading, amber configured, green online.
- The fixed status panel above the trigger with the phase line, honest detail copy for the not-enabled phases, and the session, roots, and bindings facts.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

The browser entry (`src/client/index.ts`) binds the generated Remote contribution and delegates to [`mountShadowEntryUi`](src/client/mount.ts), which mounts the contribution, then — under `ctx.inject(['remote.shadow', 'slots', 'locale'])` — registers the locale dictionaries and one `sidebar.footer.action` entry (id `shadow-entry`, order 30) whose inject face carries the status store and the refresh verb. `ShadowStatusController` wraps `createSnapshotStore` with a superseded-read guard: the last issued read owns the store, failures publish their message beside the last good view. `presentShadowStatus` is a pure fold from snapshot to the card model, and `ShadowCard` renders it — no subscription machinery in the component; the renderer binds the store through the inject `hooks` compartment.

| File | Role |
|---|---|
| [`src/client/index.ts`](src/client/index.ts) | Browser entry binding the generated Remote artifact to the mount lifecycle |
| [`src/client/mount.ts`](src/client/mount.ts) | Remote mount plus card registration and their joint rollback |
| [`src/client/ShadowCard.tsx`](src/client/ShadowCard.tsx) | The resident trigger and status panel |
| [`src/client/shadow-presenter.ts`](src/client/shadow-presenter.ts) | Pure snapshot-to-model fold (phases, rows, locale keys) |
| [`src/client/shadow-store.ts`](src/client/shadow-store.ts) | Status controller over the snapshot store |
| [`src/client/locales.ts`](src/client/locales.ts) | `shadow` locale namespace, English and Chinese dictionaries |
| — | No runtime invariant companion is published; the card is a pure consumer of the controller's read-only snapshot. |

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [Shadow status controller](../shadow-controller/README.md) — the read-only `ctx.remote.shadow` namespace this card reads.
- [Shadow router](../shadow-router/README.md) — the designated-controller domain behind the snapshot.
- [Experimental packages](../README.md) — incubation status and release exclusion.

-----

<a id="model-experience"></a>
## Model Experience

None. The card is browser-only presentation; it adds no model request content.

#### KV Cache effect

None — the entry contributes no prompt, tool, or schema content.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

- **Read-only card** — the entry exposes no Shadow actions; enabling, designation, and stop all stay host-side. Adding verbs requires a deliberate write-face decision on the controller first.
- **No live refresh** — the card reads on mount and on open; it does not subscribe to binding changes, so a long-lived open panel can show a stale revision until the next open.
- **Source-checkout only** — official CLI, Web, npm, and Python release payloads exclude this private package.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
