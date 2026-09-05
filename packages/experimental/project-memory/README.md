---
description: "Bounded append-only project memory over a user-selected Obsidian Vault: scoped search/read/append tools, exclusive-create notes with session-log receipts, path containment, secret screening, and honest failure reporting."
kind: "package-bundle"
---

# @deepseek-ai/dsh-experimental-project-memory

English | [中文](README.zh.md)

## Summary

`dsh-experimental-project-memory` is a private experimental profile layer that implements the bounded Obsidian memory of [detailed design part 3](../../../docs/detailDesign-part3.md): the Vault stores only selected facts, preferences, lessons, and unresolved questions, never execution history or authority. Its patch inserts one `project-memory` row that provides `ctx.projectMemory` and registers the three bounded tools (`memory_search`, `memory_read`, `memory_append`) on `ctx.tools`; the receipt seam rides the session log, so a cold restart recovers it from replayed logs. With the shipped defaults memory mounts unconfigured and read-only, and the tools report `MEMORY_UNAVAILABLE` until a deployment configures a Vault root. Memory content is untrusted context that never grants tools, permissions, or authority; this is not a general Obsidian synchronization — the service manages only the append-only `<vault>/devframe-memory/` subtree.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

### Install into a profile

From this repository checkout, add the layer to an initialized profile:

```sh
pnpm dsh plugin --profile headless add ./packages/experimental/project-memory
```

The command initializes a custom profile with `@deepseek-ai/dsh-base` first and links the package from the checkout; the manifest's `dsh.bundle.patch` declaration is what makes it join the ordered layer stack instead of staying a plain dependency. Removing it with `dsh plugin --profile <name> remove @deepseek-ai/dsh-experimental-project-memory` removes the dependency and the layer.

### Configure a Vault

The shipped patch defaults mount the row with `workspaceId: default`, writes off, and no Vault root, so loading is safe everywhere and every tool call reports `MEMORY_UNAVAILABLE` until the deployment overrides the row's config with `vaultRoot`. The user-selected Vault root must already exist — the service never creates it — and enabling `writeEnabled` without an explicit `vaultRoot` fails the profile at load. A patch entry replaces the target row's whole configuration, so restate every setting you keep; the [base bundle README](../../bundle/base/README.md) owns the override semantics.

### What you get

The layer adds the `project-memory` plugin row: a `ctx.projectMemory` service over the configured Vault subtree plus three model tools.

- `memory_search` — deterministic, byte-bounded text match over one scope's note bodies; hits carry note ids, excerpts, trust labels, and freshness, and `coverageComplete: false` means a scan cap was hit, never that the knowledge does not exist.
- `memory_read` — one full note by id with trust labels and provenance; `memory_changed` or `incomplete_note` means the stored file disagrees with its committed receipt, so treat the content as unverified.
- `memory_append` — exclusive-create, idempotent append of one bounded note; the receipt reaches the calling session's log before `created` returns, and rejected bodies name the screening rule without echoing the suspected secret.

Every failure mode from the design surfaces as a stable code on `ProjectMemoryError` (`MEMORY_UNAVAILABLE`, `MEMORY_APPEND_DISABLED`, `MEMORY_NOTE_TOO_LARGE`, `MEMORY_CONTENT_REJECTED`, `MEMORY_PATH_REJECTED`); conflicting or externally changed notes are outcomes, never silent overwrites.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design decisions behind the feature and points at the code that realizes them; the observable behavior is fully covered in [Use this package](#use-this-package).

### Patch document

The package's runtime content is [`cordis.patch.yml`](cordis.patch.yml): one `insert` list that mounts the `project-memory` row with its shipped defaults over the profile root. Later bundle layers and the user's profile patch override the row by id, with the last write winning per row. Source-checkout hosts that compose the service directly, outside a profile, import the library face instead: `resolveMemorySpec` resolves the validated spec at the boundary, `ProjectMemoryService` performs the filesystem behavior, and the host supplies the `MemoryReceiptStore` over its own session log.

### Design decisions

- **Derived identity, committed receipts.** A note id is `sha256(namespace, sourceEventRef)`, so every retry of one append lands on the same file; the receipt (relative path plus full-file digest) is committed before `created` and is the only confirmation a read trusts — editing the note's own metadata cannot replace it.
- **Create-only appends.** Files are created with exclusive-create `wx`, flushed, and never truncated or replaced. A conflicting candidate reports `memory_conflict`; a partial (interrupted) write reports `incomplete_note` and is preserved for explicit repair; permission errors and conflicts are never retried, transient failures follow the bounded retry policy.
- **Containment over trust.** Workspace ids are validated as single safe path segments, note ids are 64-hex digests (traversal probes fail the shape check), every path component is walked for unexpected symlink/reparse points, and resolved targets must stay inside the Vault root realpath.
- **Bounded, deterministic recall.** Limits are UTF-8 byte-counted (8 KiB notes, 16 KiB returns, 10 results, 200 candidates, 2 KiB queries by default), the candidate scan is a sorted deterministic walk, reaching the cap reports `coverageComplete: false` instead of claiming absence, and excerpts truncate only at whole code points.
- **Trust labels are carried, never promoted.** Assertion statuses ride with every hit and read; a `confirmed` user preference requires a host-provided `humanConfirmation` reference; supersession is append-only, namespace-local, and preserves the superseded file.

### Source map

| File | Role |
|---|---|
| [`cordis.patch.yml`](cordis.patch.yml) | The bundle substance: the `project-memory` row with its shipped defaults |
| [`src/types.ts`](src/types.ts) | Namespaces, note metadata, tool request/result shapes, limits, retry policy, and the receipt seam |
| [`src/ids.ts`](src/ids.ts) | The `NoteId` brand, source-reference validation, and the stable id derivation |
| [`src/notes.ts`](src/notes.ts) | Note serialization, strict parsing, digests, and byte-boundary utilities |
| [`src/vault.ts`](src/vault.ts) | Namespace layout, workspace-segment validation, symlink/reparse rejection, path containment |
| [`src/screen.ts`](src/screen.ts) | Secret-pattern, environment-dump, and unsafe-content screening |
| [`src/config.ts`](src/config.ts) | Explicit spec resolution with the documented defaults |
| [`src/receipt.ts`](src/receipt.ts) | The in-memory receipt store for tests and rehydration |
| [`src/memory.ts`](src/memory.ts) | The service: search, read, and append over the real filesystem |
| [`src/errors.ts`](src/errors.ts) | `ProjectMemoryError` and its stable code union |
| [`src/index.ts`](src/index.ts) | Package entry that re-exports the vocabulary and the plugin wiring |

### Invariant

No runtime invariant companion is published: the service holds no cross-process observable relationship to assert — its guarantees (exclusive create, receipt-before-`created`, containment) are enforced by the filesystem and receipt seam at operation time and are validated by the behavior tests bound to `AT3-01…09` in `docs/testAndAcceptance.md`.

</details>

-----

<a id="model-experience"></a>
## Model Experience

### Bounded memory tools

#### What the model sees

When the layer is mounted, exactly three tools join the tool scopes: `memory_search`, `memory_read`, and `memory_append`. Their descriptions carry the policy: notes are labeled data, never instructions; appends record observations, and `confirmed` user preferences stay reachable only through the host's human-confirmation flow. With the shipped defaults every call fails with `MEMORY_UNAVAILABLE` instead of touching any path.

#### Token effect

Zero while the layer is absent. When mounted, the three tool schemas cost tokens on every request in the scopes that see them, and each call appends one JSON result bounded by the recall limits.

#### KV Cache effect

Prefix-stable while the row config and tool schemas stay unchanged: the schemas are declared once, and call results append after the reusable request prefix. Mounting or removing the layer changes the tool list and breaks the affected agents' provider cache reuse for the next request.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

These limits define when the memory service is a poor fit or needs special operational care. They are current package constraints, not a task backlog.

- **Screening is a reduction, not a guarantee.** The rule list is fixed; content that no rule recognizes still reaches the Vault, and legitimate prose resembling a pattern is rejected — both by design.
- **Receipt durability is the host's job.** The in-memory store loses receipts on disposal; without them, confirmation falls back to the append-retry content comparison, and a confirmed file that disappears is never recreated.
- **Recall is bounded text matching.** No background index, embedding, or vector store exists by design until a measured retrieval problem justifies one.
- **Unknown filesystem errors are treated as transient.** They consume retry attempts within the configured bound and then fail with `MEMORY_WRITE_FAILED` or `MEMORY_UNAVAILABLE`.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
