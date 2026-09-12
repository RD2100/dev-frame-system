/**
 * Registry-backed Service Provider for the per-agent worktree seam. It holds
 * no durable state of its own: every operation delegates to
 * `ctx.worktreeRegistry`, adding the binding protocol on top — create binds,
 * remove releases the caller's own binding first and refuses while another
 * holder owns the worktree, and status projects the binding facts alongside
 * the live observation.
 * @module @deepseek-ai/dsh-experimental-agent-worktree/provider
 */

import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { WorktreeLockError } from '@deepseek-ai/dsh-worktree-registry'
import type { Worktree, WorktreeId, WorktreeLockHolder, WorktreeRegistry } from '@deepseek-ai/dsh-worktree-registry'
import { AgentWorktree } from './service.ts'
import type { AgentWorktreeCreateRequest, AgentWorktreeStatus, AgentWorktreeView } from './types.ts'

/**
 * The default provider: the worktree registry's create/status/remove with the
 * per-agent single-writer protocol. `static inject` names the registry hard
 * dependency, so a composition without the registry fails at activation —
 * this seam never degrades to a no-op.
 */
export class RegistryAgentWorktree extends AgentWorktree {
  static inject = ['worktreeRegistry']

  private get registry(): WorktreeRegistry {
    return this.ctx.worktreeRegistry
  }

  async create(holder: WorktreeLockHolder, request: AgentWorktreeCreateRequest): Promise<AgentWorktreeView> {
    // The two registry operations serialize on the registry's own mutation
    // chain, and the id is not published until this answers, so the window
    // where another holder could take the binding first is unreachable in
    // practice; a bind failure still surfaces loud with the worktree left
    // registered and unbound.
    const worktree = await this.registry.create(request)
    return toView(await this.registry.bind(worktree.id, holder))
  }

  async status(workspaceId: WorkspaceId, id: WorktreeId): Promise<AgentWorktreeStatus> {
    const known = this.authorizedWorktree(workspaceId, id)
    const observed = await this.registry.status(id)
    return {
      id,
      directoryExists: observed.directoryExists,
      ...observed.branch !== undefined ? { branch: observed.branch } : {},
      ...observed.clean !== undefined ? { clean: observed.clean } : {},
      ...known.lockedBy !== undefined && known.lockedAt !== undefined
        ? { lockedBy: known.lockedBy, lockedAt: known.lockedAt }
        : {},
    }
  }

  async remove(
    holder: WorktreeLockHolder,
    workspaceId: WorkspaceId,
    id: WorktreeId,
    options?: { readonly force?: boolean | undefined },
  ): Promise<string> {
    const known = this.authorizedWorktree(workspaceId, id)
    if (known.lockedBy !== undefined && known.lockedBy !== holder) {
      throw new WorktreeLockError(
        `cannot remove worktree '${id}': it is bound to writer '${known.lockedBy}'; `
        + 'the holding session must remove it or unbind it first',
        'already-locked',
      )
    }
    if (known.lockedBy === holder) {
      await this.registry.unbind(id, holder)
    }
    await this.registry.remove(id, options)
    return known.path
  }

  /**
   * The workspace's row for `id`, rejecting an id from another workspace the
   * same way an unknown one is reported.
   * @param workspaceId - The caller's workspace.
   * @param id - The model-supplied worktree id.
   * @returns the registered, workspace-authorized worktree.
   */
  private authorizedWorktree(workspaceId: WorkspaceId, id: WorktreeId) {
    const known = this.registry.list(workspaceId).find(entry => entry.id === id)
    if (known === undefined) {
      throw new Error(
        `worktree '${id}' is not registered for this workspace; list the workspace's worktrees to get a valid id`,
      )
    }
    return known
  }
}

/** The readonly consumer view of one registry record. */
function toView(worktree: Worktree): AgentWorktreeView {
  return {
    id: worktree.id,
    workspaceId: worktree.workspaceId,
    path: worktree.path,
    branch: worktree.branch,
    createdAt: worktree.createdAt,
    updatedAt: worktree.updatedAt,
    ...worktree.lockedBy !== undefined && worktree.lockedAt !== undefined
      ? { lockedBy: worktree.lockedBy, lockedAt: worktree.lockedAt }
      : {},
  }
}
