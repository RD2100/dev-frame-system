---
description: "Bounded append-only project memory over a user-selected Obsidian Vault: scoped search/read/append tools, exclusive-create notes with session-log receipts, path containment, secret screening, and honest failure reporting."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-project-memory

English | [中文](README.zh.md)

## Summary

`dsh-experimental-project-memory` implements the bounded Obsidian memory of [detailed design part 3](../../../docs/detailDesign-part3.md): the Vault stores only selected facts, preferences, lessons, and unresolved questions, never execution history or authority. The package is a private experimental library built around `ProjectMemoryService`, the three bounded tools (`memory_search`, `memory_read`, `memory_append`), and a receipt seam the host implements over the DSH session log. It is not a general Obsidian synchronization: the service manages only the append-only `<vault>/devframe-memory/` subtree, appends are exclusive-create and idempotent, and memory content is untrusted context that never grants tools, permissions, or authority.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Use this package when the host needs scoped recall and honest append over a user-selected Vault root: the calling session's workspace identity, the consent flags (`writeEnabled`, `userScopeEnabled`), and the receipt store are supplied by the host; the service owns the filesystem behavior.

### Resolve the spec, then run the tools

Defaults are resolved explicitly at the boundary; the service performs no hidden fallbacks.

```ts
import { createMemoryReceiptStore, ProjectMemoryService, resolveMemorySpec } from '@deepseek-ai/dsh-experimental-project-memory'

const spec = resolveMemorySpec({
  vaultRoot: 'D:/Obsidian/MyVault', // user-selected, must already exist
  writeEnabled: true,              // the user enabled appends
  userScopeEnabled: false,         // user memory not allowed for this caller
  workspaceId: workspaceId,        // host-derived native workspace identity
})
const memory = new ProjectMemoryService(spec, receiptStoreOverSessionLog)
const recall = await memory.search({ scope: 'project', query: 'deploy script' })
```

### Implement the receipt seam

`MemoryReceiptStore` fixes only `read` and `write`. The host persists each receipt (relative path plus full-file digest) to the session log before the append returns `created`, so a restart can answer `already_exists`, `memory_changed`, or `memory_missing` without recreating anything. Tests and tools that assemble the seam from an already-restored receipt list use `createMemoryReceiptStore(entries)`.

### Expect explicit failures

Every failure mode from the design surfaces as a stable code on `ProjectMemoryError`: an unconfigured or missing Vault reports `MEMORY_UNAVAILABLE`, disabled writes report `MEMORY_APPEND_DISABLED`, oversized or secret-bearing bodies are rejected with `MEMORY_NOTE_TOO_LARGE` or `MEMORY_CONTENT_REJECTED` (the reason names the rule, never the suspected secret), and unsafe paths report `MEMORY_PATH_REJECTED`. Conflicting or externally changed notes are outcomes (`memory_conflict`, `memory_changed`, `memory_missing`, `incomplete_note`), never silent overwrites.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design decisions behind the feature and points at the code that realizes them; the observable behavior is fully covered in [Use this package](#use-this-package).

### Design decisions

- **Derived identity, committed receipts.** A note id is `sha256(namespace, sourceEventRef)`, so every retry of one append lands on the same file; the receipt (relative path plus full-file digest) is committed before `created` and is the only confirmation a read trusts — editing the note's own metadata cannot replace it.
- **Create-only appends.** Files are created with exclusive-create `wx`, flushed, and never truncated or replaced. A conflicting candidate reports `memory_conflict`; a partial (interrupted) write reports `incomplete_note` and is preserved for explicit repair; permission errors and conflicts are never retried, transient failures follow the bounded retry policy.
- **Containment over trust.** Workspace ids are validated as single safe path segments, note ids are 64-hex digests (traversal probes fail the shape check), every path component is walked for unexpected symlink/reparse points, and resolved targets must stay inside the Vault root realpath.
- **Bounded, deterministic recall.** Limits are UTF-8 byte-counted (8 KiB notes, 16 KiB returns, 10 results, 200 candidates, 2 KiB queries by default), the candidate scan is a sorted deterministic walk, reaching the cap reports `coverageComplete: false` instead of claiming absence, and excerpts truncate only at whole code points.
- **Trust labels are carried, never promoted.** Assertion statuses ride with every hit and read; a `confirmed` user preference requires a host-provided `humanConfirmation` reference; supersession is append-only, namespace-local, and preserves the superseded file.

### Source map

| File | Role |
|---|---|
| [`src/types.ts`](src/types.ts) | Namespaces, note metadata, tool request/result shapes, limits, retry policy, and the receipt seam |
| [`src/ids.ts`](src/ids.ts) | The `NoteId` brand, source-reference validation, and the stable id derivation |
| [`src/notes.ts`](src/notes.ts) | Note serialization, strict parsing, digests, and byte-boundary utilities |
| [`src/vault.ts`](src/vault.ts) | Namespace layout, workspace-segment validation, symlink/reparse rejection, path containment |
| [`src/screen.ts`](src/screen.ts) | Secret-pattern, environment-dump, and unsafe-content screening |
| [`src/config.ts`](src/config.ts) | Explicit spec resolution with the documented defaults |
| [`src/receipt.ts`](src/receipt.ts) | The in-memory receipt store for tests and rehydration |
| [`src/memory.ts`](src/memory.ts) | The service: search, read, and append over the real filesystem |
| [`src/errors.ts`](src/errors.ts) | `ProjectMemoryError` and its stable code union |
| [`src/index.ts`](src/index.ts) | Package entry that re-exports the vocabulary |

### Invariant

No runtime invariant companion is published: the service holds no cross-process observable relationship to assert — its guarantees (exclusive create, receipt-before-`created`, containment) are enforced by the filesystem and receipt seam at operation time and are validated by the behavior tests bound to `AT3-01…09` in `docs/testAndAcceptance.md`.

</details>

-----

<a id="model-experience"></a>
## Model Experience

### Contract vocabulary

#### What the model sees

Nothing yet. The package ships the three tools as a library; wiring them into `ctx.tools`, injecting labeled recall at task start, and recording that injection in session events belong to the host integration ([detailed design part 3, failure behavior and integration](../../../docs/detailDesign-part3.md#failure)).

#### Token effect

Zero direct tokens on every request.

#### KV Cache effect

Independent of live requests: the package never touches a request prefix, so it cannot invalidate provider cache reuse.

## Known Limitations and Deferred Work

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
