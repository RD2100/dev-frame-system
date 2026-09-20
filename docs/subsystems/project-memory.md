# Bounded project memory

English | [中文](project-memory.zh.md)

The project-memory subsystem implements the bounded Obsidian memory: a user-selected Vault stores only selected facts, preferences, lessons, and unresolved questions — never execution history or authority — and the service manages only the append-only `<vault>/devframe-memory/` subtree. Its bundle layer provides `ctx.projectMemory` and registers three model tools (`memory_search`, `memory_read`, `memory_append`); the receipt seam rides the session log, so a cold restart recovers it from replayed logs. With the shipped defaults the row mounts unconfigured and read-only, and every tool call reports `MEMORY_UNAVAILABLE` until a deployment configures a Vault root. Memory content is untrusted context that never grants tools, permissions, or authority. The [package README](../../packages/experimental/project-memory/README.md) owns the install path, the layer configuration, and the model experience.

## Service surface

`ctx.projectMemory` is the Vault service. Its core operations:

- `search` — deterministic, byte-bounded text match over one scope's note bodies; hits carry note ids, excerpts, trust labels, and freshness, and `coverageComplete: false` means a scan cap was hit, never that the knowledge does not exist.
- `read` — one full note by id with trust labels and provenance; `memory_changed` or `incomplete_note` means the stored file disagrees with its committed receipt, so treat the content as unverified.
- `append` — exclusive-create, idempotent append of one bounded note; the receipt reaches the calling session's log before `created` returns, and rejected bodies name the screening rule without echoing the suspected secret.

## Contracts

Every failure mode surfaces as a stable code on `ProjectMemoryError` (`MEMORY_UNAVAILABLE`, `MEMORY_APPEND_DISABLED`, `MEMORY_NOTE_TOO_LARGE`, `MEMORY_CONTENT_REJECTED`, `MEMORY_PATH_REJECTED`, and the request, query, workspace, note, receipt, scope, and write-family codes); conflicting or externally changed notes are outcomes, never silent overwrites. Limits are UTF-8 byte-counted (8 KiB notes, 16 KiB returns, 10 results, 200 candidates, 2 KiB queries by default), the candidate scan is a sorted deterministic walk, and excerpts truncate only at whole code points. A note id is `sha256(namespace, sourceEventRef)`, so every retry of one append lands on the same file; files are created with exclusive-create `wx`, flushed, and never truncated or replaced. Containment over trust: workspace ids are single safe path segments, note ids are 64-hex digests, every path component is walked for unexpected symlink/reparse points, and resolved targets must stay inside the Vault root realpath. Trust labels ride with every hit and read and are never promoted — a `confirmed` user preference requires a host-provided human-confirmation reference.

## Boundaries

The three tools join the [tools](tools.md) registry through the bundle layer, and the [base bundle](../../packages/bundle/base/README.md) owns the row-override semantics that turn the shipped defaults into a configured Vault. The receipt seam rides the [session](session.md) log instead of a storage domain: the Vault is a user-selected filesystem root, not a JSON domain table, and the in-memory receipt store is the host's to make durable. Screening is a reduction, not a guarantee, and recall is bounded text matching — no background index or embedding exists by design.

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxmemorylibrarygateway--memorylibrarygateway"></a>

### `ctx.memoryLibraryGateway` — `MemoryLibraryGateway`

Host service backing the generated `ctx.remote.library` namespace.

```ts cordis-catalog
/**
 * Read the current library status and file listing in one call.
 * @returns availability metadata plus the accessible files; an unconfigured
 *   vault yields an `UNAVAILABLE` status and an empty listing.
 */
@Remote('view') async view(): Promise<MemoryLibrarySnapshot>

/**
 * Inspect vault availability without touching any file.
 * @returns the same status object the model tool reports.
 */
@Remote('status') status(): Promise<LibraryStatus>

/**
 * List the accessible library files with an optional depth cap.
 * @param request - Listing options.
 * @returns the sorted file metadata rows.
 * @throws {@link ProjectMemoryError} with `MEMORY_UNAVAILABLE` when no vault
 *   is configured or the vault is inaccessible.
 */
@Remote('list') async list(request: MemoryLibraryListRequest): Promise<readonly LibraryFile[]>

/**
 * Read one library file for preview, with its real absolute on-disk path.
 * @param request - Relative path inside the vault (forward slashes).
 * @returns the file content and the absolute copy/reference target.
 * @throws {@link ProjectMemoryError} with the same codes as
 *   {@link readLibraryFile}; the absolute path is computed only after the
 *   path has passed the full containment and symlink validation.
 */
@Remote('read') async read(request: MemoryLibraryReadRequest): Promise<MemoryLibraryReadResult>

/**
 * Search the library by name and text content from the UI.
 * @param request - Non-empty query and an optional result cap.
 * @returns the bounded search hits.
 * @throws {@link ProjectMemoryError} with the same codes as
 *   {@link searchLibrary}.
 */
@Remote('search') async search(request: MemoryLibrarySearchRequest): Promise<readonly LibrarySearchResult[]>
```

Source: [`packages/experimental/project-memory/src/gateway.ts`](../../packages/experimental/project-memory/src/gateway.ts)

<a id="ctxprojectmemory--projectmemoryservice"></a>

### `ctx.projectMemory` — `ProjectMemoryService`

The project memory service. One instance is bound to one calling session's workspace identity and allowed scopes; construct it with a spec resolved by `resolveMemorySpec` and a host-owned receipt store.

```ts cordis-catalog
/**
 * Search one allowed namespace: deterministic filename order, bounded
 * candidate scan, bounded text matching, and explicit partial-coverage
 * reporting. Scope checks run before any note content is read; notes that
 * disagree with their receipt, are incomplete, or are superseded inside
 * the same namespace are excluded from automatic recall.
 * @param request - Scope, query text, and optional result cap.
 * @returns the bounded hits with coverage and truncation facts.
 */
async search(request: MemorySearchRequest): Promise<MemorySearchResult>

/**
 * Read one note by host-issued id within one allowed namespace. Unknown
 * ids, missing files, changed files, and incomplete files are each
 * reported honestly; nothing is chased across namespaces.
 * @param request - Scope and the host-issued note id.
 * @returns the honest read outcome for the note.
 */
async read(request: MemoryReadRequest): Promise<MemoryReadResult>

/**
 * Append one note: validate, screen, derive the stable id, check the
 * committed receipt, then create the file exclusively and commit the
 * receipt before returning `created`. The candidate body is never
 * regenerated; conflicting or externally changed files are never modified.
 * @param request - Scope, stable source reference, kind, candidate body,
 *   assertion status, optional snapshot, and optional superseded note.
 * @returns the append outcome with the note id and expected path.
 */
async append(request: MemoryAppendRequest): Promise<MemoryAppendResult>
```

Source: [`packages/experimental/project-memory/src/memory.ts`](../../packages/experimental/project-memory/src/memory.ts)
<!-- END GENERATED cordis-surface -->
