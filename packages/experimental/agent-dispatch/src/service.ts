/**
 * The `ctx.agentDispatch` service: the host's daily-dispatch entry over the
 * agent-hierarchy creation engine. The entry validates what the host
 * composition layer owns before any child exists — the requested worktree is
 * really registered and alive, its canonical path and single-writer binding
 * match the registry's authoritative rows (`status` for the live directory
 * and branch, `list` for the path and binding), and the
 * controller→lead→worker chain with its plugin scopes holds over the
 * engine's approved-set contract — and then delegates to the real engine.
 * The engine owns the child's lifecycle; the published
 * {@link CreatedChildAgent} carries no disposer.
 *
 * @module @deepseek-ai/dsh-experimental-agent-dispatch/service
 */

import { Service, type Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type {
  CreateChildAgentOptions,
  CreateChildAgentRequest,
  CreatedChildAgent,
} from '@deepseek-ai/dsh-experimental-agent-hierarchy'
import type {} from '@deepseek-ai/dsh-experimental-session-identity'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import { WorktreeGitOperationError } from '@deepseek-ai/dsh-worktree-registry'
import type { Worktree, WorktreeStatus } from '@deepseek-ai/dsh-worktree-registry'
import { AgentDispatchError } from './errors.ts'
import { evaluateDispatchEntry } from './entry.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    agentDispatch: AgentDispatch
  }
}

/**
 * Engine creation options plus the owner workspace the daily entry needs:
 * the workspace the requested worktree is registered under, which anchors
 * the authoritative `list`-row proof of path and single-writer binding.
 */
export interface DispatchAgentOptions extends CreateChildAgentOptions {
  /** Workspace the requested worktree is registered under. */
  readonly workspaceId: WorkspaceId
}

/**
 * The host daily-dispatch entry. Hard-injects the real creation engine
 * (`ctx.agentHierarchy`), the role authority (`ctx.agentBindings`), and the
 * worktree registry whose rows make the worktree proof real, and fails at
 * activation when any is absent. Denials raised here are
 * {@link AgentDispatchError}s; the engine's own policy denials propagate
 * unchanged.
 */
export class AgentDispatch extends Service {
  static inject = ['agentHierarchy', 'agentBindings', 'worktreeRegistry']

  constructor(ctx: Context) {
    super(ctx, 'agentDispatch')
  }

  /**
   * Validate one dispatch request at the entry and, when it holds, create the
   * child through the real hierarchy engine. A git-broken registered worktree
   * rethrows the registry's classified git failure instead of being reported
   * as unregistered.
   * @param parent - The exact live dispatching agent.
   * @param request - The child creation request; `worktree` is required at
   *   this entry because the dispatched child owns one registered worktree.
   * @param options - Factory setup, route, cancellation, preallocated
   *   identity, and the owner workspace anchoring the registry proof.
   * @returns The published child and its durable binding record.
   */
  async createChildAgent(
    parent: Agent,
    request: CreateChildAgentRequest,
    options: DispatchAgentOptions,
  ): Promise<CreatedChildAgent> {
    const worktree = request.worktree
    if (worktree === undefined) {
      throw new AgentDispatchError(
        'agent-dispatch: a dispatched child requires a registered worktree',
        'DISPATCH_WORKTREE_UNREGISTERED',
      )
    }
    const { workspaceId } = options
    if (workspaceId === undefined) {
      throw new AgentDispatchError(
        `agent-dispatch: worktree "${worktree.worktreeId}" proof requires the owner workspace id`,
        'DISPATCH_WORKTREE_UNREGISTERED',
      )
    }
    const status = await this.observedStatus(worktree.worktreeId)
    if (!status.directoryExists) {
      throw new AgentDispatchError(
        `agent-dispatch: registered worktree "${worktree.worktreeId}" no longer exists on disk`,
        'DISPATCH_WORKTREE_MISMATCH',
      )
    }
    if (worktree.branch !== undefined && status.branch !== undefined && status.branch !== worktree.branch) {
      throw new AgentDispatchError(
        `agent-dispatch: worktree "${worktree.worktreeId}" is on branch "${status.branch}", not the requested "${worktree.branch}"`,
        'DISPATCH_WORKTREE_MISMATCH',
      )
    }
    const row = this.registeredRow(workspaceId, worktree.worktreeId)
    if (row.path !== worktree.worktreePath) {
      throw new AgentDispatchError(
        `agent-dispatch: worktree "${worktree.worktreeId}" is registered at "${row.path}", not the requested "${worktree.worktreePath}"`,
        'DISPATCH_WORKTREE_MISMATCH',
      )
    }
    // Brands differ by design (WorktreeLockHolder vs SessionId); the
    // registry's holder contract is string equality, and an unallocated
    // child identity cannot match any existing binding.
    if (row.lockedBy !== undefined
      && (options.sessionId === undefined || String(row.lockedBy) !== String(options.sessionId))) {
      throw new AgentDispatchError(
        `agent-dispatch: worktree "${worktree.worktreeId}" is bound to writer "${row.lockedBy}"`,
        'DISPATCH_WORKTREE_MISMATCH',
      )
    }
    const creator = this.ctx.agentBindings.find(parent.id)
    if (creator === undefined) {
      throw new AgentDispatchError(
        `agent-dispatch: parent session "${parent.id}" has no role binding`,
        'DISPATCH_PARENT_UNBOUND',
      )
    }
    const approvedScopes = this.ctx.agentHierarchy.config.leadPluginScopes[creator.agentId] ?? []
    const decision = evaluateDispatchEntry(creator, request, approvedScopes)
    if (!decision.allowed) {
      throw new AgentDispatchError(
        decision.reason ?? 'agent-dispatch: dispatch refused',
        'DISPATCH_HIERARCHY_DENIED',
      )
    }
    return await this.ctx.agentHierarchy.createChildAgent(parent, request, {
      ...(options.sessionId === undefined ? {} : { sessionId: options.sessionId }),
      ...(options.agentOptions === undefined ? {} : { agentOptions: options.agentOptions }),
      ...(options.signal === undefined ? {} : { signal: options.signal }),
      ...(options.setup === undefined ? {} : { setup: options.setup }),
    })
  }

  /**
   * Read one registry status observation, classifying an unknown id as an
   * unregistered dispatch. A git-broken registered worktree rethrows the
   * registry's classified failure unchanged.
   */
  private async observedStatus(worktreeId: WorktreeId): Promise<WorktreeStatus> {
    try {
      return await this.ctx.worktreeRegistry.status(worktreeId)
    } catch (error) {
      if (error instanceof WorktreeGitOperationError) throw error
      throw new AgentDispatchError(
        `agent-dispatch: worktree "${worktreeId}" is not a registered worktree`,
        'DISPATCH_WORKTREE_UNREGISTERED',
        { cause: error },
      )
    }
  }

  /**
   * Read the authoritative registry row for one id within its owner
   * workspace — a status observation alone cannot prove the canonical path
   * or the single-writer binding.
   */
  private registeredRow(workspaceId: WorkspaceId, worktreeId: WorktreeId): Worktree {
    let rows: readonly Worktree[]
    try {
      rows = this.ctx.worktreeRegistry.list(workspaceId)
    } catch (error) {
      throw new AgentDispatchError(
        `agent-dispatch: workspace "${workspaceId}" is not a registered workspace`,
        'DISPATCH_WORKTREE_UNREGISTERED',
        { cause: error },
      )
    }
    const row = rows.find(entry => entry.id === worktreeId)
    if (row === undefined) {
      throw new AgentDispatchError(
        `agent-dispatch: worktree "${worktreeId}" is not registered under workspace "${workspaceId}"`,
        'DISPATCH_WORKTREE_UNREGISTERED',
      )
    }
    return row
  }
}
