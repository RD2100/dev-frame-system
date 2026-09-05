/**
 * The agent binding registry (`ctx.agentBindings`): the Cordis service that
 * owns one durable `session_identity` domain of {@link AgentBindingRecord}
 * rows, creates native Sessions with exact `cwd`/`parentSession`/
 * `delegationDepth` header metadata, binds agents created through other
 * entry points, and restores every binding cold on start.
 *
 * Writes are serialized on one operation chain; every mutation is written
 * through to the domain table and then mirrored into the in-memory query
 * index, so the table stays the only durable authority and the index is
 * rebuildable from it at any time.
 *
 * @module @deepseek-ai/dsh-experimental-session-identity/registry
 */

import { Service, type Context } from '@deepseek-ai/cordis'
import type { KvTable } from '@deepseek-ai/dsh-storage-domain'
import type { Session, SessionId } from '@deepseek-ai/dsh-session'
import { isAgentRole } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { AgentBindingRecord, AgentRole, PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import { SessionIdentityError } from './errors.ts'
import { sessionIdentityDomainSpec } from './spec.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    agentBindings: AgentBindingRegistry
  }
}

/** The registered worktree one agent owns, as the worktree registry recorded it. */
export interface BoundWorktree {
  /** The registry's stable worktree identity. */
  readonly worktreeId: WorktreeId
  /** The canonical path the worktree registry observed. */
  readonly worktreePath: string
  /** The branch checked out in the worktree, when known. */
  readonly branch?: string
}

/** Request to create one native Session and bind it in the same operation. */
export interface CreateBoundSessionRequest {
  /** Absolute working directory written into the Session header; the store validates absoluteness. */
  readonly cwd: string
  /** Hierarchy role fixed at creation. */
  readonly role: AgentRole
  /** Delegating session; must exist in the session store when present. */
  readonly parentSessionId?: SessionId
  /**
   * Explicit delegation depth for the new header. Absent, the depth derives
   * from the parent header (`parent depth + 1`); a top-level creation omits it.
   */
  readonly delegationDepth?: number
  /** Plugin scope the new agent operates in. */
  readonly pluginId?: PluginId
  /** Task the new agent is created for. */
  readonly taskId?: TaskId
  /** Registered worktree the new agent owns. */
  readonly worktree?: BoundWorktree
}

/** Request to bind one agent that an existing entry point (spawn, fork, Team spawn, SDK) already created. */
export interface BindAgentRequest {
  /** Live Agent registry identity; must exist in the session store. */
  readonly agentId: SessionId
  /** Durable Session identity; defaults to {@link BindAgentRequest.agentId} for local agents. */
  readonly sessionId?: SessionId
  /** Hierarchy role fixed at binding. */
  readonly role: AgentRole
  /** Delegating session, when one exists. */
  readonly parentSessionId?: SessionId
  /** Plugin scope the agent operates in. */
  readonly pluginId?: PluginId
  /** Task the agent is bound to. */
  readonly taskId?: TaskId
  /** Registered worktree the agent owns. */
  readonly worktree?: BoundWorktree
}

/** One created Session together with the binding written for it. */
export interface BoundSession {
  /** The live native Session, already entered into the store. */
  readonly session: Session
  /** The durable binding record; `agentId` and `sessionId` equal `session.id`. */
  readonly record: AgentBindingRecord
}

/** Project the optional worktree binding into record fields. */
function worktreeFields(worktree: BoundWorktree | undefined): Pick<AgentBindingRecord, 'worktreeId' | 'worktreePath' | 'branch'> {
  if (worktree === undefined) return {}
  if (worktree.worktreePath.length === 0 || worktree.worktreePath !== worktree.worktreePath.trim()) {
    throw new SessionIdentityError('worktreePath must be a non-empty trimmed path', 'SESSION_IDENTITY_INVALID_REQUEST')
  }
  if (worktree.branch !== undefined && (worktree.branch.length === 0 || worktree.branch !== worktree.branch.trim())) {
    throw new SessionIdentityError('branch must be a non-empty trimmed name', 'SESSION_IDENTITY_INVALID_REQUEST')
  }
  return { worktreeId: worktree.worktreeId, worktreePath: worktree.worktreePath, ...worktree.branch === undefined ? {} : { branch: worktree.branch } }
}

/**
 * Whether two binding records carry the same binding content. `createdAt` is
 * excluded deliberately: it is stamped at the first write and owned by it, so
 * a rebind at a later instant stays idempotent when the identity fields match.
 */
function sameRecord(left: AgentBindingRecord, right: AgentBindingRecord): boolean {
  return left.agentId === right.agentId
    && left.sessionId === right.sessionId
    && left.parentSessionId === right.parentSessionId
    && left.role === right.role
    && left.pluginId === right.pluginId
    && left.taskId === right.taskId
    && left.worktreeId === right.worktreeId
    && left.worktreePath === right.worktreePath
    && left.branch === right.branch
}

/** The agent binding registry: durable hierarchy identity per agent. */
export class AgentBindingRegistry extends Service {
  static inject = ['sessions', 'storageDomain']

  private table?: KvTable<SessionId, AgentBindingRecord>
  private readonly records = new Map<SessionId, AgentBindingRecord>()
  private tail: Promise<unknown> = Promise.resolve()

  constructor(ctx: Context) {
    super(ctx, 'agentBindings')
  }

  protected async [Service.init](): Promise<void> {
    const domain = await this.ctx.storageDomain.open(sessionIdentityDomainSpec)
    this.ctx.effect(() => () => domain.close(), 'session-identity.domainClose')
    this.table = domain.table('bindings')
    // Cold restore: rebuild the whole query index from the durable table.
    // Order (createdAt, agentId) keeps list() stable across restarts. The map
    // holds a detached frozen copy so the durable row stays untouched.
    const entries = [...this.table.entries()]
      .sort(([leftId, left], [rightId, right]) =>
        left.createdAt.localeCompare(right.createdAt) || String(leftId).localeCompare(String(rightId)))
    for (const [id, record] of entries) this.records.set(id, Object.freeze({ ...record }))
  }

  /**
   * Create one native Session with exact cwd and lineage metadata and write
   * its binding record — host Session id, parent session, and worktree — in
   * one durable write. A session whose binding write fails stays live and
   * unbound; the caller owns its disposal.
   * @param request - Creation identity: cwd, role, optional parent/depth/task/plugin/worktree.
   * @returns the live session and the durable binding record.
   */
  async createBoundSession(request: CreateBoundSessionRequest): Promise<BoundSession> {
    return await this.enqueue(async () => {
      if (!isAgentRole(request.role)) {
        throw new SessionIdentityError(`"${String(request.role)}" is not a hierarchy role`, 'SESSION_IDENTITY_INVALID_REQUEST')
      }
      if (typeof request.cwd !== 'string' || request.cwd.length === 0) {
        throw new SessionIdentityError('cwd must be a non-empty absolute path', 'SESSION_IDENTITY_INVALID_REQUEST')
      }
      const parent = this.resolveParent(request.parentSessionId)
      const delegationDepth = this.resolveDepth(request, parent)

      let session: Session
      try {
        session = this.ctx.sessions.create(undefined, {
          meta: {
            cwd: request.cwd,
            ...(parent === undefined ? {} : { parentSession: parent.id }),
            ...(delegationDepth === undefined ? {} : { delegationDepth }),
          },
        })
      } catch (error: unknown) {
        throw new SessionIdentityError(
          'the session store rejected the creation metadata (an existing id or a non-absolute cwd is the usual cause)',
          'SESSION_IDENTITY_INVALID_REQUEST',
          { cause: error },
        )
      }

      const record: AgentBindingRecord = Object.freeze({
        agentId: session.id,
        sessionId: session.id,
        ...(parent === undefined ? {} : { parentSessionId: parent.id }),
        role: request.role,
        ...request.pluginId === undefined ? {} : { pluginId: request.pluginId },
        ...request.taskId === undefined ? {} : { taskId: request.taskId },
        ...worktreeFields(request.worktree),
        createdAt: new Date().toISOString(),
      })
      await this.writeRecord(record)
      return { session, record }
    })
  }

  /**
   * Bind one agent an existing entry point already created. An identical
   * rebind is idempotent; a different binding for the same agent fails loud.
   * @param request - Binding identity: live agent id, role, and optional fields.
   * @returns the durable binding record.
   */
  async bind(request: BindAgentRequest): Promise<AgentBindingRecord> {
    return await this.enqueue(async () => {
      if (!isAgentRole(request.role)) {
        throw new SessionIdentityError(`"${String(request.role)}" is not a hierarchy role`, 'SESSION_IDENTITY_INVALID_REQUEST')
      }
      if (this.ctx.sessions.get(request.agentId) === undefined) {
        throw new SessionIdentityError(`agent "${request.agentId}" does not exist in the session store`, 'SESSION_IDENTITY_AGENT_UNKNOWN')
      }
      const record: AgentBindingRecord = Object.freeze({
        agentId: request.agentId,
        sessionId: request.sessionId ?? request.agentId,
        ...request.parentSessionId === undefined ? {} : { parentSessionId: request.parentSessionId },
        role: request.role,
        ...request.pluginId === undefined ? {} : { pluginId: request.pluginId },
        ...request.taskId === undefined ? {} : { taskId: request.taskId },
        ...worktreeFields(request.worktree),
        createdAt: new Date().toISOString(),
      })
      const existing = this.records.get(request.agentId)
      if (existing !== undefined) {
        if (sameRecord(existing, record)) return existing
        throw new SessionIdentityError(
          `agent "${request.agentId}" is already bound with different content`,
          'SESSION_IDENTITY_ALREADY_BOUND',
        )
      }
      await this.writeRecord(record)
      return record
    })
  }

  /**
   * Read one agent's binding from the restored index.
   * @param agentId - Live Agent registry identity selecting the record.
   * @returns the binding, or `undefined` when the agent has none.
   */
  find(agentId: SessionId): AgentBindingRecord | undefined {
    return this.records.get(agentId)
  }

  /**
   * Read every binding carrying one role.
   * @param role - Hierarchy role to filter by.
   * @returns the matching records in stable (createdAt, agentId) order.
   */
  byRole(role: AgentRole): readonly AgentBindingRecord[] {
    return this.list().filter(record => record.role === role)
  }

  /**
   * Read every binding in stable (createdAt, agentId) order.
   * @returns all restored or written records.
   */
  list(): readonly AgentBindingRecord[] {
    return [...this.records.values()].sort((left, right) =>
      left.createdAt.localeCompare(right.createdAt) || String(left.agentId).localeCompare(String(right.agentId)))
  }

  /** Serialize mutations so concurrent binds cannot interleave validation and writes. */
  private enqueue<T>(operation: () => Promise<T>): Promise<T> {
    const run = this.tail.then(operation, operation)
    this.tail = run.then(() => undefined, () => undefined)
    return run
  }

  /** Resolve the parent session or fail loud on a missing referent. */
  private resolveParent(parentSessionId: SessionId | undefined): Session | undefined {
    if (parentSessionId === undefined) return undefined
    const parent = this.ctx.sessions.get(parentSessionId)
    if (parent === undefined) {
      throw new SessionIdentityError(
        `parent session "${parentSessionId}" does not exist in the session store`,
        'SESSION_IDENTITY_PARENT_UNKNOWN',
      )
    }
    return parent
  }

  /** Resolve the child depth: the explicit value, or parent depth + 1. */
  private resolveDepth(request: CreateBoundSessionRequest, parent: Session | undefined): number | undefined {
    const explicit = request.delegationDepth
    if (explicit === undefined) {
      return parent === undefined ? undefined : (parent.header.delegationDepth ?? 0) + 1
    }
    if (parent === undefined) {
      throw new SessionIdentityError('delegationDepth requires a parentSessionId', 'SESSION_IDENTITY_INVALID_REQUEST')
    }
    if (!Number.isSafeInteger(explicit) || explicit < 0) {
      throw new SessionIdentityError('delegationDepth must be a non-negative safe integer', 'SESSION_IDENTITY_INVALID_REQUEST')
    }
    return explicit
  }

  /** Write one record through to the durable table, then mirror it into the index. */
  private async writeRecord(record: AgentBindingRecord): Promise<void> {
    try {
      await this.requireTable().put(record.agentId, record)
    } catch (error: unknown) {
      throw new SessionIdentityError(
        `binding for agent "${record.agentId}" could not be persisted`,
        'SESSION_IDENTITY_PERSISTENCE',
        { cause: error },
      )
    }
    this.records.set(record.agentId, record)
  }

  /** The opened domain table; absent only before Service.init completed. */
  private requireTable(): KvTable<SessionId, AgentBindingRecord> {
    if (this.table === undefined) {
      throw new SessionIdentityError('the session-identity domain is not open yet', 'SESSION_IDENTITY_PERSISTENCE')
    }
    return this.table
  }
}
