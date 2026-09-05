/**
 * Service Definition for the per-agent worktree capability seam
 * (`ctx.agentWorktree`). It composes the per-workspace worktree registry with
 * the single-writer binding protocol: a session creates a worktree already
 * bound to itself, observes it, and removes it — another session's binding is
 * an immovable refusal, and only the registry's own reconcile can drop a row
 * whose directory vanished. Providers implement the three operations; this
 * class declares the interface and the Context key.
 * @module @deepseek-ai/dsh-experimental-agent-worktree/service
 */

import { Context, Service } from '@deepseek-ai/cordis'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type { WorktreeId, WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import type { AgentWorktreeCreateRequest, AgentWorktreeStatus, AgentWorktreeView } from './types.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    agentWorktree: AgentWorktree
  }
}

/**
 * Abstract per-agent worktree service. Subclass, implement the abstract
 * methods, and construct the subclass inside a plugin — it registers as
 * `ctx.agentWorktree` (one implementation per context; loading a second
 * throws, which is cordis' standard duplicate-service behavior).
 *
 * Implementations must honor these semantics:
 * - `create` registers the worktree through `ctx.worktreeRegistry` and binds
 *   it to `holder` before answering. The registry's git refusals (occupied
 *   path, branch conflict, oversized path) propagate as classified errors;
 *   a bind failure after a successful create surfaces loud and leaves the
 *   worktree registered and unbound.
 * - `status` authorizes by workspace: an id this workspace holds no row for
 *   is reported exactly like an unknown one, and a bound row from the same
 *   workspace is observable by any session of that workspace.
 * - `remove` refuses while the worktree is bound to another holder; the
 *   holder's own binding is released first, and an unbound worktree is
 *   removable by any authorized session.
 */
export abstract class AgentWorktree extends Service {
  constructor(ctx: Context) {
    super(ctx, 'agentWorktree')
  }

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
  abstract remove(
    holder: WorktreeLockHolder,
    workspaceId: WorkspaceId,
    id: WorktreeId,
    options?: { readonly force?: boolean | undefined },
  ): Promise<string>
}
