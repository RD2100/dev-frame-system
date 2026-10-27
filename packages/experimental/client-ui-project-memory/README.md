---
description: "Library capability-center tab: browse, search, and preview the read-only Obsidian Vault, copy absolute paths, and reference files in conversation."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-client-ui-project-memory

English | [中文](README.zh.md)

## Summary

`dsh-experimental-client-ui-project-memory` adds a Library tab to the capability center for the read-only Obsidian Vault served by [project-memory](../project-memory/README.md). It mounts the generated `ctx.remote.library` namespace and shows the vault availability status and file count, lists accessible files, searches names and content, and previews each file with its absolute path. The preview can copy that path or append a `@vault:<absolutePath>` reference to the current conversation draft. A deployment without a configured Vault shows that the library is unavailable and hides browsing controls. The vault is strictly read-only: the page never appends, edits, or writes files. The package is published as an optional client plugin and joins the center through its public keyed slot.

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

### Install into a DSH Web profile

The [DevFrame profile layer](../devframe-profile/README.md) mounts the Host memory service and this browser entry. For a manual composition, mount `@deepseek-ai/dsh-experimental-project-memory` on the Host and this package on the Web side; the package root is inert in headless compositions and the Web loader selects its `/client` export through the `dsh.client` manifest. The client package optionally consumes the capability-center slot contract and remains usable without the center provider.

### What you get

- A Library tab in the capability center for the configured Vault.
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

The browser entry (`src/client/index.ts`) imports the generated Library Remote contribution from `@deepseek-ai/dsh-experimental-project-memory/remote` and delegates to [`mountLibraryUi`](src/client/mount.ts). The mount registers the English and Chinese `library` dictionaries and contributes the keyed `library` page through `capabilities.center.tab`; a type-only import loads that slot declaration without importing the inventory feature at runtime. It builds the face over `ctx.remote.library` (view/list/read/search) plus a `LibraryReferenceController` for conversation actions. The page reads its snapshot on mount and refreshes it on request. Search results stay separate from the file listing, and request generations discard stale replies after newer work or unmount. The preview pane is presentational (`LibraryPane`), split from the stateful `LibraryCard` so the client spec can exercise each branch. The reference controller reads the current session from `sessions.list`, resolves its conversation scope, and appends to the existing draft through `conversation.input`; it never creates or switches sessions, and it reports a localized hint when no current session can receive the reference.

| File | Role |
|---|---|
| [`src/client/index.ts`](src/client/index.ts) | Browser entry and generated Remote binding |
| [`src/client/mount.ts`](src/client/mount.ts) | Remote mount, locale registration, and capability-center tab lifecycle |
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
- [DevFrame profile](../devframe-profile/README.md) — an optional source composition for the broader stack.
- [Experimental packages](../README.md) — incubation status and package boundaries.

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
- **Optional provider** — the Library page appears when both this package and the capability-center shell are mounted; its Host Remote still reports an honest unavailable state when no Vault is configured.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
