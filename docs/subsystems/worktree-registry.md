# Worktree Registry

English | [中文](worktree-registry.zh.md)

The per-workspace git worktree registry — a [capability seam](../../.agents/notes/implemented/feature/2026-09-05-worktree-tools-and-reconcile.md) that keeps durable registrations of git worktrees owned by one workspace. The Service Definition ([`WorktreeRegistry`](../../packages/workflow/worktree-registry), mounted as `ctx.worktreeRegistry`) and the Service Provider (`GitWorktreeRegistry`, git operations over `ctx.subprocess` on the host filesystem) live in one package; the Consumer role is the [`tool-worktree`](../../packages/workflow/tool-worktree) package, which exposes the five `worktree_*` tools to the model and authorizes every call against the calling session's own workspace.

Source: [`packages/workflow/worktree-registry/src/registry.ts`](../../packages/workflow/worktree-registry/src/registry.ts)

## The service

`WorktreeRegistry` declares five operations. `create` resolves the owning workspace through `ctx.workspaceRegistry`, runs `git worktree add` from the workspace directory, and records the observed facts — the canonical path after `fs.realpath` and the branch read back from the new worktree. `list` answers from durable rows in stable `(createdAt, id)` order and never shells out to git. `status` is the observation surface: a missing directory reports `directoryExists: false` without calling git, while a present directory reports its live branch and cleanliness. `remove` runs `git worktree remove` first and deletes the registration only after git succeeded, so a failed removal never hides a real worktree. `reconcile` diffs the rows against `git worktree list` and reports the difference — dangling registrations and unregistered worktrees — dropping stale rows or adopting outside-created worktrees only when the corresponding action is opted in; it never deletes directories or files.

Registrations persist in the `worktree_registry` storage domain (one `worktrees` table keyed by a branded `WorktreeId`); they survive restarts and reappear on the next composition. Directory operations run with the owning workspace path as cwd — a worktree cannot remove itself as its own cwd on Windows. The model reaches these operations only through the `worktree_*` tools of [`tool-worktree`](../../packages/workflow/tool-worktree), whose tool descriptions carry the retry semantics for the four classified git refusal dialects (occupied path, branch conflict, dirty tree, oversized path).

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxworktreeregistry--worktreeregistry-abstract-seam"></a>

### `ctx.worktreeRegistry` — `WorktreeRegistry` (abstract seam)

Abstract worktree registry service. Subclass, implement the abstract methods, and load the subclass as a plugin — it registers as `ctx.worktreeRegistry` (one implementation per context; loading a second throws, which is cordis' standard duplicate-service behavior).

Implementations must honor these semantics:

- Operations resolve the owner workspace through `ctx.workspaceRegistry` and fail loud on an unknown `WorkspaceId`; the anchor is never stored unvalidated.
- Records reflect observed facts: canonical paths after the directory exists, branches read back from the worktree, never caller assumptions.
- `list` answers from durable rows only; the registry, not git metadata, is the authority for what this product registered.
- `status` reports a missing directory as an observation (`directoryExists: false`) without invoking git; git failures on a present directory reject.
- `remove` deletes the durable row only after the provider's worktree removal succeeded, so a failed remove never hides an existing worktree.
- `reconcile` compares the rows with `git worktree list` and only reports by default; its actions are opt-in and never delete directories or files.

```ts cordis-catalog
/**
 * Create a linked worktree for one workspace and register it durably.
 * @param request - Owner workspace, target directory, and optional new
 *   branch name.
 * @returns the registered worktree with observed path and branch.
 */
abstract create(request: WorktreeCreateRequest): Promise<Worktree>

/**
 * The workspace's registered worktrees in the stable (createdAt, id) order.
 * @param workspaceId - Owner workspace; unknown ids reject.
 * @returns a fresh ordered array of registered worktrees.
 */
abstract list(workspaceId: WorkspaceId): readonly Worktree[]

/**
 * Observe one registered worktree's live state.
 * @param id - Registered worktree id; unknown ids reject.
 * @returns the observation; optional fields are absent when the recorded
 *   directory no longer exists.
 */
abstract status(id: WorktreeId): Promise<WorktreeStatus>

/**
 * Remove one worktree through git and delete its registration. The row is
 * deleted only after the removal succeeded.
 * @param id - Registered worktree id; unknown ids reject.
 * @param options - Pass `force` to allow removing dirty worktrees.
 * @returns resolution after the worktree is gone and the row deleted.
 */
abstract remove(id: WorktreeId, options?: WorktreeRemoveOptions): Promise<void>

/**
 * Compare this workspace's rows with `git worktree list` and optionally
 * reconcile the difference. Detection always runs; each action is opt-in:
 * `pruneRows` drops stale rows (never directories or files), and
 * `adoptUnregistered` registers git-tracked worktrees this registry holds
 * no row for under any workspace. The repository's main worktree is never
 * reported as unregistered.
 * @param workspaceId - Owner workspace; unknown ids reject.
 * @param options - The opt-in reconcile actions.
 * @returns the observed differences and the applied changes.
 */
abstract reconcile(workspaceId: WorkspaceId, options?: WorktreeReconcileOptions): Promise<WorktreeReconcileReport>
```

Types: [WorkspaceId](workspace.md)

Source: [`packages/workflow/worktree-registry/src/registry.ts`](../../packages/workflow/worktree-registry/src/registry.ts)
<!-- END GENERATED cordis-surface -->
