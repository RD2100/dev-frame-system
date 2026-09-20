---
description: "Library page Web entry: browse, search, and preview the read-only Obsidian Vault, copy absolute paths, and reference files in conversation."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-client-ui-project-memory

English | [中文](README.zh.md)

## Summary

`dsh-experimental-client-ui-project-memory` is the resident Web entry for the read-only Obsidian Vault served by [project-memory](../project-memory/README.md). It mounts the generated `ctx.remote.library` namespace and registers a sidebar trigger in the `sidebar.footer.action` seat (order 25, between the Expert center and the shadow entry). The trigger opens a Library page that shows the vault availability status and file count, lists the accessible files, searches the library by file name and content, and opens a preview pane with the real absolute on-disk path, a copy-path action, and a "reference in conversation" action that appends a `@vault:<absolutePath>` marker to the current conversation draft. A deployment without a configured Vault stays an honest empty state: the page reports that the library is unavailable and exposes no dead controls. The vault is strictly read-only — the page never appends, edits, or writes files. Official releases exclude this package, so it is available only from a source checkout.

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

### Install into the DevFrame Web profile

The [DevFrame profile layer](../devframe-profile/README.md) already mounts the Host memory service and this browser entry. For a manual composition, mount `@deepseek-ai/dsh-experimental-project-memory` on the Host and this package on the Web side; the package root is inert in headless compositions and the Web loader selects its `/client` export through the `dsh.client` manifest.

### What you get

- A resident sidebar trigger that opens the Library page for the configured Vault.
- The vault availability state and accessible file count from one snapshot read, with an explicit refresh action.
- The file listing under the vault root, with per-file preview reads that return the file content and its real absolute on-disk path.
- A search box that queries file names and content, with bounded excerpts per hit.
- A preview pane that copies the absolute path to the clipboard and references the file in the current conversation as `@vault:<absolutePath>`.
- An honest empty state when the deployment has no Vault directory — no dead controls, no fabricated inventory.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

The browser entry (`src/client/index.ts`) imports the generated Library Remote contribution from `@deepseek-ai/dsh-experimental-project-memory/remote` and delegates to [`mountLibraryUi`](src/client/mount.ts). The mount registers the English and Chinese `library` dictionaries, injects the sidebar entry (id `project-library`, order 25), and builds the card face over `ctx.remote.library` (view/list/read/search) plus a `LibraryReferenceController` for the conversation action. The card reads the snapshot once on mount; refresh re-reads it. Search reads are separate from the file listing, so browsing and searching never mix result sets. The preview pane is presentational (`LibraryPane`), split from the stateful `LibraryCard` so the client spec can exercise every branch directly. The reference controller reads the current session from `sessions.list`, resolves its conversation scope, and appends to the existing draft through `conversation.input` — it never creates or switches sessions, and without a current session scope the action reports a localized hint instead of a dead control.

| File | Role |
|---|---|
| [`src/client/index.ts`](src/client/index.ts) | Browser entry and generated Remote binding |
| [`src/client/mount.ts`](src/client/mount.ts) | Remote mount, locale registration, and sidebar contribution lifecycle |
| [`src/client/LibraryCard.tsx`](src/client/LibraryCard.tsx) | Stateful card plus the presentational `LibraryPane` |
| [`src/client/reference.ts`](src/client/reference.ts) | Draft-append conversation reference (never creates sessions) |
| [`src/client/locales.ts`](src/client/locales.ts) | `library` locale namespace and English/Chinese dictionaries |
| [`src/index.ts`](src/index.ts) | Inert Host-side package entry for profile compositions |
| — | No runtime invariant companion is published; the card is a pure consumer of the Host Remote snapshot. |

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [Project-memory core](../project-memory/README.md) — the bounded Obsidian memory service and the Host Remote owner.
- [DevFrame profile](../devframe-profile/README.md) — the source-checkout Web composition that mounts the Host and browser rows together.
- [Experimental packages](../README.md) — incubation status and release exclusion.

-----

<a id="model-experience"></a>
## Model Experience

### Library page

#### What the model sees

The page itself is browser-only and registers no tools or prompt sections. The reference action stages ordinary user-visible draft text (`@vault:<absolutePath>`) in the current conversation; if the user submits that draft, the normal Conversation path sends it. The in-session model tools over the vault remain the model-visible surface for reading the referenced file.

#### Token effect

Opening, browsing, searching, or referencing adds no automatic request. A submitted staged reference contributes its visible text like any other user prompt.

#### KV Cache effect

The entry contributes no tool or schema content. Any cache effect comes from the user-submitted prompt text and follows normal Conversation behavior.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

- **Read-only Vault** — the page browses, previews, searches, copies paths, and references files; it never appends, edits, or writes library content, by design.
- **No recent-access or Vault-selection UI** — the page operates on the deployment-configured vault only; choosing or switching vaults stays out of scope.
- **Draft append, not auto-submit** — the reference lands in the composer and is sent only when the user submits it. Without a current session scope, the action reports a hint and makes no changes.
- **No live subscription** — the snapshot is read on mount and refresh; file changes outside the page appear on the next read.
- **Source-checkout only** — official CLI, Web, npm, and Python release payloads exclude this private package.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
