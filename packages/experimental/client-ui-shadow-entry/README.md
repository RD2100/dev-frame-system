---
description: "Resident Web Shadow entry: honest status above Settings and the actionable multi-project panel for the human's global Shadow."
kind: "package"
---

# @deepseek-ai/dsh-experimental-client-ui-shadow-entry

English | [中文](README.zh.md)

## Summary

`dsh-experimental-client-ui-shadow-entry` is the resident Web entry for [Shadow](../shadow-router/README.md) — the human's global, cross-project surface. It mounts the generated `ctx.remote.shadow` Remote namespace and registers one card into the sidebar's `sidebar.footer.action` seat — the footer stack above Settings — showing the deployment's honest Shadow state: not-enabled while no router is mounted or no controller session is designated, configured while the designated session is not live, and online once it is. The opened panel is actionable, not a status plaque: it lists every authorized root, opens a project from a path, lists every open project with its workspace, path, revision, and state, delivers a message to a project's controller, releases (stops) a project, and refreshes on demand. Every action's success or the service's rejection is shown verbatim. Official releases exclude this package, so it is available only from a source checkout.

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
- The fixed panel above the trigger with the phase line, honest detail copy for the not-enabled phases, the session and authorized-roots facts, and the multi-project list: one row per open project with send and release actions, the open-project form, and an explicit refresh button.
- Honest write feedback: a busy line while an action is in flight (all actions lock), a success line per action kind, and the service's failure message verbatim. Server rejections — an unauthorized root, a missing path, a closed project — are never masked.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

The browser entry (`src/client/index.ts`) binds the generated Remote contribution and delegates to [`mountShadowEntryUi`](src/client/mount.ts), which mounts the contribution, then — under `ctx.inject(['remote.shadow', 'slots', 'locale'])` — registers the locale dictionaries and one `sidebar.footer.action` entry (id `shadow-entry`, order 30) whose inject face carries the status store, the refresh verb, and the three write verbs (`onOpenProject`, `onSendToController`, `onReleaseProject`), each a pass-through to the generated namespace. `ShadowStatusController` wraps `createSnapshotStore` with a superseded-read guard: the last issued read owns the store, failures publish their message beside the last good view. `presentShadowStatus` is a pure fold from snapshot to the card model, `presentWriteOutcome` folds the component-local write outcome into its tone and locale key, and `ShadowCard` renders both — no subscription machinery in the component; the renderer binds the store through the inject `hooks` compartment.

| File | Role |
|---|---|
| [`src/client/index.ts`](src/client/index.ts) | Browser entry binding the generated Remote artifact to the mount lifecycle |
| [`src/client/mount.ts`](src/client/mount.ts) | Remote mount plus card registration and their joint rollback |
| [`src/client/ShadowCard.tsx`](src/client/ShadowCard.tsx) | The resident trigger and the actionable panel |
| [`src/client/shadow-presenter.ts`](src/client/shadow-presenter.ts) | Pure snapshot-to-model and write-outcome folds |
| [`src/client/shadow-store.ts`](src/client/shadow-store.ts) | Status controller over the snapshot store |
| [`src/client/locales.ts`](src/client/locales.ts) | `shadow` locale namespace, English and Chinese dictionaries |
| — | No runtime invariant companion is published; the card is a pure consumer of the controller's snapshot and a pass-through to its write faces. |

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [Shadow status controller](../shadow-controller/README.md) — the `ctx.remote.shadow` namespace this panel reads and writes.
- [Shadow router](../shadow-router/README.md) — the designated-controller domain and host write bridges behind the panel.
- [Experimental packages](../README.md) — incubation status and release exclusion.

-----

<a id="model-experience"></a>
## Model Experience

None. The card is browser-only presentation; it adds no model request content.

#### KV Cache effect

None — the entry contributes no prompt, tool, or schema content.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

- **Refresh is explicit** — the card reads on mount, on open, and after each successful write; it does not subscribe to binding changes, so a long-lived open panel can show a stale revision until the next refresh.
- **Released projects stay visible** — a released row lands on `stopped` and remains listed, matching the router's stop semantics; there is no durable-delete action.
- **Source-checkout only** — official CLI, Web, npm, and Python release payloads exclude this private package.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
