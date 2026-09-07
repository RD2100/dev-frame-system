# Worktree Registry

English | [中文](worktree-registry.zh.md)

The per-workspace git worktree registry — a [capability seam](../../.agents/notes/implemented/architecture/2026-09-05-worktree-registry.md) that keeps durable registrations of git worktrees owned by one workspace. The Service Definition ([`WorktreeRegistry`](../../packages/workflow/worktree-registry), mounted as `ctx.worktreeRegistry`) and the Service Provider (`GitWorktreeRegistry`, git operations over `ctx.subprocess` on the host filesystem) live in one package. Two packages play the Consumer role: [`tool-worktree`](../../packages/workflow/tool-worktree) exposes the five `worktree_*` tools to workspace sessions and authorizes every call against the calling session's own workspace; the experimental [`agent-worktree`](agent-worktree.md) seam binds each created worktree to a single writer and serves agent sessions.

Source: [`packages/workflow/worktree-registry/src/registry.ts`](../../packages/workflow/worktree-registry/src/registry.ts)

## The service

`WorktreeRegistry` declares eight operations. `create` resolves the owning workspace through `ctx.workspaceRegistry`, runs `git worktree add` from the workspace directory, and records the observed facts — the canonical path after `fs.realpath` and the branch read back from the new worktree — after refusing a path the workspace or another registered worktree already occupies and an explicit branch another worktree of the same workspace already holds. `bind`/`unbind` maintain one single-writer binding per worktree: the holder value is opaque, re-binding by the current holder is idempotent, and every other bind, an unbind by a non-holder, or an unbind of an unbound worktree refuses with a `WorktreeLockError`. `list` answers from durable rows in stable `(createdAt, id)` order and never shells out to git. `status` is the observation surface: a missing directory reports `directoryExists: false` without calling git, while a present directory reports its live branch and cleanliness. `remove` refuses while the worktree is bound — `force` never overrides the binding — then runs `git worktree remove` and deletes the registration only after git succeeded, so a failed removal never hides a real worktree. `reconcile` diffs the rows against `git worktree list` and reports the difference — dangling registrations and unregistered worktrees — dropping stale rows or adopting outside-created worktrees only when the corresponding action is opted in; it never deletes directories or files, and `pruneRows` drops a stale row together with its binding, because a binding guards a live checkout, not a vanished directory.

Registrations persist in the `worktree_registry` storage domain (version 2; one `worktrees` table keyed by a branded `WorktreeId`, carrying the optional `lockedBy`/`lockedAt` binding fields written and read together); they survive restarts and reappear on the next composition. Directory operations run with the owning workspace path as cwd — a worktree cannot remove itself as its own cwd on Windows. The model reaches these operations only through the `worktree_*` tools of [`tool-worktree`](../../packages/workflow/tool-worktree) and the per-agent seam of [`agent-worktree`](agent-worktree.md), whose tool descriptions carry the retry semantics for the four classified git refusal dialects (occupied path, branch conflict, dirty tree, oversized path).

## Commit request and result

`WorktreeCommitId` is a branded full Git object ID. `WorktreeCommitRequest` identifies the registered checkout with `id`, the authorized writer with `holder`, and the optimistic precondition with `expectedHead`; `paths` lists literal relative files and `message` supplies the commit message. `WorktreeCommitResult` returns the new `head` and whole-checkout `clean` state.

The host-only `commit` operation requires consumer authorization and writer quiescence. It preserves unrelated changes, refuses existing staging, and requires the registered branch and expected HEAD. Cancellation or failure may leave staging or a commit; inspect before retrying. The [package contract](../../packages/workflow/worktree-registry/README.md) owns hooks, filters, and path restrictions.

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
- `bind`/`unbind` maintain one single-writer binding per worktree. The holder value is opaque; equality is the entire contract. Re-binding by the current holder is an idempotent success; any other bind, an unbind by a non-holder, or an unbind of an unbound worktree refuses with a `WorktreeLockError`.
- `remove` refuses while the worktree is bound, whatever options say — the lock is a product-level exclusivity promise, not a dirty-tree guard.
- `remove` deletes the durable row only after the provider's worktree removal succeeded, so a failed remove never hides an existing worktree.
- `reconcile` compares the rows with `git worktree list` and only reports by default; its actions are opt-in and never delete directories or files.

```ts cordis-catalog
/**
 * Create a linked worktree for one workspace and register it durably. The
 * path must not collide with the owner workspace directory or any registered
 * worktree, and an explicitly requested branch must not already be
 * registered to another worktree of the same workspace (git itself refuses
 * a branch that exists in the repository, whatever workspace registered it).
 * @param request - Owner workspace, target directory, and optional new
 *   branch name.
 * @returns the registered worktree with observed path and branch.
 */
abstract create(request: WorktreeCreateRequest): Promise<Worktree>

/**
 * Bind one worktree to a single writer. The holder is opaque to the
 * registry; binding succeeds when the worktree is unbound or already bound
 * to the same holder, and refuses with `WorktreeLockError`
 * (`already-locked`) otherwise.
 * @param id - Registered worktree id; unknown ids reject.
 * @param holder - The single-writer marker taking or holding the binding.
 * @returns the updated worktree with the binding stamped.
 */
abstract bind(id: WorktreeId, holder: WorktreeLockHolder): Promise<Worktree>

/**
 * Release a worktree's single-writer binding. Refuses with
 * `WorktreeLockError` (`not-locked`) when the worktree is unbound and
 * (`holder-mismatch`) when `holder` is not the current holder.
 * @param id - Registered worktree id; unknown ids reject.
 * @param holder - The single-writer marker releasing the binding.
 * @returns the updated worktree with the binding cleared.
 */
abstract unbind(id: WorktreeId, holder: WorktreeLockHolder): Promise<Worktree>

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
 * Commit selected paths through the host provider while retaining the writer lock.
 * The consumer must authorize the calling writer and stop its other mutations first.
 * Existing staged changes, a changed branch, and a stale HEAD reject before staging.
 * A rejection after staging may leave an index or commit; inspect before retrying.
 * No rollback, reset, history rewrite, or sandbox permission change is performed.
 * @param request - Trusted writer, registered target, expected HEAD and literal paths.
 * @param signal - Cancellation of queued or executing Git operations.
 * @returns The verified new commit and the remaining worktree cleanliness.
 */
abstract commit(request: WorktreeCommitRequest, signal?: AbortSignal): Promise<WorktreeCommitResult>

/**
 * Remove one worktree through git and delete its registration. A bound
 * worktree refuses with `WorktreeLockError` (`already-locked`) until its
 * holder unbinds — `force` never overrides the lock. The row is deleted
 * only after the removal succeeded.
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
