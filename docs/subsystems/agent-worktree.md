# Agent Worktree

English | [中文](agent-worktree.zh.md)

The per-agent worktree seam — a [capability seam](../../.agents/notes/implemented/architecture/2026-09-05-worktree-registry.md) over the [worktree registry](worktree-registry.md) that binds every created worktree to one writer. The Service Definition ([`AgentWorktree`](../../packages/experimental/agent-worktree), mounted as `ctx.agentWorktree`) composes the registry's create/bind/status/remove with the single-writer protocol, and the same package is the Consumer: the model-facing `worktree_create`, `worktree_status`, and `worktree_remove` tools, each authorized against the calling session's own workspace and bound to its durable session id. The package is experimental and private: it ships in no released bundle.

Source: [`packages/experimental/agent-worktree/src/service.ts`](../../packages/experimental/agent-worktree/src/service.ts)

## The service

`AgentWorktree` declares three operations, all over `ctx.worktreeRegistry`. `create` registers the worktree through the registry and binds it to `holder` before answering, so a worktree an agent session creates is that session's single-writer target from its first observation. `status` authorizes by workspace — an id the workspace holds no row for is reported exactly like an unknown one — and projects the binding facts next to the live branch and cleanliness. `remove` refuses while another holder owns the worktree, releases the caller's own binding first, and answers with the canonical path git deleted; the registry's own git refusals (dirty tree without `force`, vanished directory) propagate as classified errors.

The holder is opaque to the registry; this seam mints it from the calling session's durable id, so a recovered agent still matches its binding. The worktree registry keeps the enforcement point — a bound worktree refuses `remove` there whatever the caller asks — and its `reconcile` remains the only way a stale row (binding included) leaves the registry when its directory vanished outside the product.

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxagentworktree--agentworktree-abstract-seam"></a>

### `ctx.agentWorktree` — `AgentWorktree` (abstract seam)

Abstract per-agent worktree service. Subclass, implement the abstract methods, and construct the subclass inside a plugin — it registers as `ctx.agentWorktree` (one implementation per context; loading a second throws, which is cordis' standard duplicate-service behavior).

Implementations must honor these semantics:

- `create` registers the worktree through `ctx.worktreeRegistry` and binds it to `holder` before answering. The registry's git refusals (occupied path, branch conflict, oversized path) propagate as classified errors; a bind failure after a successful create surfaces loud and leaves the worktree registered and unbound.
- `status` authorizes by workspace: an id this workspace holds no row for is reported exactly like an unknown one, and a bound row from the same workspace is observable by any session of that workspace.
- `remove` refuses while the worktree is bound to another holder; the holder's own binding is released first, and an unbound worktree is removable by any authorized session.

```ts cordis-catalog
/**
 * Create a linked worktree for the workspace and bind it to `holder` as
 * its single writer.
 * @param holder - The opaque single-writer marker taking the binding.
 * @param request - Owner workspace, target directory, and optional new
 *   branch name.
 * @returns the registered, bound worktree with observed path and branch.
 */
abstract create(holder: WorktreeLockHolder, request: AgentWorktreeCreateRequest): Promise<AgentWorktreeView>

/**
 * Observe one workspace-authorized worktree's live state and binding.
 * @param workspaceId - The caller's workspace; ids outside it reject.
 * @param id - Registered worktree id.
 * @returns the observation; the live fields are absent when the recorded
 *   directory no longer exists.
 */
abstract status(workspaceId: WorkspaceId, id: WorktreeId): Promise<AgentWorktreeStatus>

/**
 * Remove one workspace-authorized worktree. A worktree bound to another
 * holder refuses; the caller's own binding is released before the removal.
 * @param holder - The opaque single-writer marker of the caller.
 * @param workspaceId - The caller's workspace; ids outside it reject.
 * @param id - Registered worktree id.
 * @param options - Pass `force` to allow removing dirty worktrees.
 * @returns the canonical directory path of the removed worktree.
 */
abstract remove( holder: WorktreeLockHolder, workspaceId: WorkspaceId, id: WorktreeId, options?: { readonly force?: boolean | undefined }, ): Promise<string>
```

Types: [WorkspaceId](workspace.md) · [WorktreeId](worktree-registry.md) · [WorktreeLockHolder](worktree-registry.md)

Source: [`packages/experimental/agent-worktree/src/service.ts`](../../packages/experimental/agent-worktree/src/service.ts)
<!-- END GENERATED cordis-surface -->
