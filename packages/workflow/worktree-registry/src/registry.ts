/**
 * Service Definition for the per-workspace git worktree capability seam
 * (`ctx.worktreeRegistry`). Providers execute git through their own execution
 * world and own the durable rows; this class declares only the interface, the
 * shared semantics every provider must honor, and the Context key.
 * @module @deepseek-ai/dsh-worktree-registry/src/registry
 */

import { Context, Service } from '@deepseek-ai/cordis'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type {
  Worktree,
  WorktreeCreateRequest,
  WorktreeId,
  WorktreeReconcileOptions,
  WorktreeReconcileReport,
  WorktreeRemoveOptions,
  WorktreeStatus,
} from './types.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    worktreeRegistry: WorktreeRegistry
  }
}

/**
 * Abstract worktree registry service. Subclass, implement the abstract
 * methods, and load the subclass as a plugin — it registers as
 * `ctx.worktreeRegistry` (one implementation per context; loading a second
 * throws, which is cordis' standard duplicate-service behavior).
 *
 * Implementations must honor these semantics:
 * - Operations resolve the owner workspace through `ctx.workspaceRegistry`
 *   and fail loud on an unknown `WorkspaceId`; the anchor is never stored
 *   unvalidated.
 * - Records reflect observed facts: canonical paths after the directory
 *   exists, branches read back from the worktree, never caller assumptions.
 * - `list` answers from durable rows only; the registry, not git metadata,
 *   is the authority for what this product registered.
 * - `status` reports a missing directory as an observation (`directoryExists:
 *   false`) without invoking git; git failures on a present directory reject.
 * - `remove` deletes the durable row only after the provider's worktree
 *   removal succeeded, so a failed remove never hides an existing worktree.
 * - `reconcile` compares the rows with `git worktree list` and only reports by
 *   default; its actions are opt-in and never delete directories or files.
 */
export abstract class WorktreeRegistry extends Service {
  constructor(ctx: Context) {
    super(ctx, 'worktreeRegistry')
  }

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
  abstract reconcile(
    workspaceId: WorkspaceId,
    options?: WorktreeReconcileOptions,
  ): Promise<WorktreeReconcileReport>
}
