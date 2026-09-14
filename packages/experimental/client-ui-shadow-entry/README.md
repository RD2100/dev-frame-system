---
description: "Resident Web Shadow entry: the trigger opens the Shadow's one permanent conversation through the standard surface, and a Manage button opens the honest read-only status dropdown."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-client-ui-shadow-entry

English | [中文](README.zh.md)

## Summary

`dsh-experimental-client-ui-shadow-entry` is the resident Web entry for [Shadow](../shadow-router/README.md) — the human's global, cross-project surface. It mounts the generated `ctx.remote.shadow` Remote namespace and registers one card into the sidebar's `sidebar.footer.action` seat — the footer stack above Settings. The trigger opens the Shadow's one permanent conversation: the deployment's designated session, rendered by the same standard conversation surface the main chat uses, the same conversation on every click and never a newly created one; the card itself renders no conversation. The entry also classifies that designated session as internal, so the session list renders no row for it while the entry is mounted. A Manage button beside the trigger opens a read-only dropdown: the honest Shadow phase — not-enabled while no router is mounted or no controller session is designated, configured while the designated session is not live, and online once it is — the designated session id, the authorized roots, and the controller preset. Opening the dropdown re-reads the status, and a failed read shows the transport error instead of pretending a state. Official releases exclude this package, so it is available only from a source checkout.

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

Add the [shadow-controller host layer](../shadow-controller/README.md) (the [DevFrame profile layer](../devframe-profile/README.md) carries it) and this package's [Web layer](../shadow-web-profile/README.md). The trigger opens the deployment's designated session through the standard conversation surface; the card reads `ctx.remote.shadow.readStatus()` once on mount and again each time the manage menu opens, a failed read shows the transport error instead of pretending a state, and every successful read classifies the designated id as an internal session so the session list never grows a row for it.

### What you get

- The resident trigger (icon plus label in the wide sidebar, icon only in the rail). Clicking it opens the Shadow's designated session — one permanent conversation, the same one every time, rendered by the standard conversation surface the main chat uses — and the session list carries no row for it. While that conversation is the current session the trigger renders its active fill (`aria-pressed`), so an already-there click is explained instead of feeling dead.
- The Manage button beside the trigger (wide sidebar) opening a read-only dropdown portaled beside the sidebar: the honest phase with its detail copy for the not-enabled phases, the designated session id, the authorized roots (or the explicit empty copy), and the controller preset. A detail line beside the trigger carries the same honest copy in the wide sidebar without opening anything.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

The browser entry (`src/client/index.ts`) binds the generated Remote contribution and delegates to [`mountShadowEntryUi`](src/client/mount.ts), which mounts the contribution, then — under `ctx.inject(['remote.shadow', 'slots', 'locale', 'sessions'])` — registers the locale dictionaries and one `sidebar.footer.action` entry (id `shadow-entry`, order 30) whose inject face carries the status store and two verbs: `onRefresh`, a pass-through status read, and `onOpenConversation`, which reads `shadow/readStatus`, refreshes the session list when the designated id is not yet listed, and opens that id through the `sessions` client contract — never `create()`: the host creates the designated session at boot through the agent path, which records no `cwd`, and the `session/create` RPC refuses to adopt such a session for the workspace (`session/conflict`). Every successful status read also registers the designated id through `sessions.markInternal()`, which the session browser honours by rendering no row for that session: the classification is client-local, follows a redeployed designation, and is withdrawn on unmount. `ShadowStatusController` wraps `createSnapshotStore` with a superseded-read guard: the last issued read owns the store, and failures publish their message beside the last good state. `presentShadowStatus` is a pure fold from snapshot to the card model, and `ShadowCard` renders it — no subscription machinery in the component; the renderer binds the store through the inject `hooks` compartment. The manage dropdown portals to `document.body` and fixed-positions beside the sidebar, because the sidebar column clips overflow and no in-place surface can reach the page area.

| File | Role |
|---|---|
| [`src/client/index.ts`](src/client/index.ts) | Browser entry binding the generated Remote artifact to the mount lifecycle |
| [`src/client/mount.ts`](src/client/mount.ts) | Remote mount, card registration, designated-session classification, and their joint rollback |
| [`src/client/ShadowCard.tsx`](src/client/ShadowCard.tsx) | The resident trigger that opens the designated conversation and the Manage button with its read-only dropdown |
| [`src/client/shadow-presenter.ts`](src/client/shadow-presenter.ts) | Pure snapshot-to-model fold |
| [`src/client/shadow-store.ts`](src/client/shadow-store.ts) | Status controller over the snapshot store |
| [`src/client/locales.ts`](src/client/locales.ts) | `shadow` locale namespace, English and Chinese dictionaries |
| — | No runtime invariant companion is published; the card is a pure consumer of the controller's snapshot and a pass-through to its read faces. |

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

### Shadow entry card

#### What the model sees

Nothing reaches a model request. The card is browser-only presentation: it registers no tools, no prompt sections, and no session events, and its reads and writes run through the generated `ctx.remote.shadow` Remote namespace, which stays host-plane and never enters a prompt.

#### Token effect

Zero direct tokens on every request.

#### KV Cache effect

Independent of live requests: the entry contributes no prompt, tool, or schema content, so it cannot invalidate provider cache reuse.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

- **Refresh is explicit** — the card reads status on mount and each time the manage menu opens; it does not subscribe to changes, so a long-lived page can show a stale phase until the next open or menu click.
- **Hiding the designated row depends on this entry** — the classification is client-local and lives exactly as long as the mounted entry, so a web client without this package, or any non-web client, still lists the designated session as an ordinary row.
- **A failed open is silent** — the trigger opens the designated session in the background, so a status read that fails or names no session leaves the button visibly inert and the rejection reaches only the console; user-visible error reporting remains open.
- **Source-checkout only** — official CLI, Web, npm, and Python release payloads exclude this private package.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
