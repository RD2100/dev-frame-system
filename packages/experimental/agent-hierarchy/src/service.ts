/**
 * The `ctx.agentHierarchy` service: installs the monotonic creation guard on
 * the root tool registry, applies each bound agent's inherited tool
 * restriction, rebuilds both from the durable binding registry on cold
 * recovery, and lifts everything it owns on agent disposal or context
 * teardown. The guard — not the installed restrictions — is the security
 * authority: it resolves roles live per execution, so a binding written or
 * restored after this service activated is honored immediately, and the
 * allow face installs lazily on first enforcement.
 *
 * @module @deepseek-ai/dsh-experimental-agent-hierarchy/service
 */

import { Service, type Context } from '@deepseek-ai/cordis'
import { randomUUID } from 'node:crypto'
import type { Agent, CreateAgentOptions } from '@deepseek-ai/dsh-agent'
import type { AgentBindingRecord, AgentRole, CreationIntent } from '@deepseek-ai/dsh-experimental-project-contracts'
import { SessionId } from '@deepseek-ai/dsh-session'
import { SessionPersistenceNotFoundError } from '@deepseek-ai/dsh-session-persistence'
import { isAgentRole } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { CreateBoundSessionRequest } from '@deepseek-ai/dsh-experimental-session-identity'
import { delegationDepthOf } from '@deepseek-ai/dsh-subagent'
import { AGENT_HIERARCHY_DELEGATION_DEPTH_BUDGET } from './policy.ts'
// Type-only: pull the session-identity Context augmentation (`ctx.agentBindings`)
// into this program; the registry is a hard injection point, never a value import.
import type {} from '@deepseek-ai/dsh-experimental-session-identity'
import { parseAgentHierarchyConfig, type AgentHierarchyConfig, type AgentHierarchyConfigInput } from './config.ts'
import { AgentHierarchyError } from './errors.ts'
import { createHierarchyGuard, type GuardRegistries } from './guard.ts'
import { evaluateCreationIntent, type CreationDecision } from './creation.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    agentHierarchy: AgentHierarchy
  }
}

/** One installed per-agent restriction: the exact agent it was applied to and its disposer. */
interface InstalledRestriction {
  readonly agent: Agent
  readonly release: () => void
}

/** Child identity and worktree requested by a trusted host creation consumer. */
export type CreateChildAgentRequest = Omit<CreateBoundSessionRequest, 'parentSessionId' | 'delegationDepth'>

/** Factory setup, route, cancellation, and optional preallocated identity. */
export type CreateChildAgentOptions = Pick<CreateAgentOptions, 'setup' | 'agentOptions' | 'signal'>
  & Partial<Pick<CreateAgentOptions, 'sessionId'>>

/** Published child and its durable hierarchy identity; the hierarchy service owns its lifecycle. */
export interface CreatedChildAgent {
  /** Published Agent; prompts may be delivered after creation resolves. */
  readonly agent: Agent
  /** Binding persisted before publication. */
  readonly record: AgentBindingRecord
}

/**
 * The pluginized-hierarchy role and creation policy service. Hard-injects
 * `ctx.agentBindings` (the role authority), `ctx.tools` (the guard and
 * restriction surface), and `ctx.agents` (the exact-identity check the P01
 * cold-recovery caveat requires) and fails at activation when any is absent.
 */
export class AgentHierarchy extends Service {
  static inject = ['agentBindings', 'tools', 'agents']

  /** The resolved host configuration; validated once at construction. */
  readonly config: AgentHierarchyConfig

  private readonly disposers: Array<() => void> = []
  private readonly installedRestrictions = new Map<SessionId, InstalledRestriction>()
  private disposed = false
  private preparationTail: Promise<void> = Promise.resolve()

  /**
   * @param ctx - The mounting context; must carry the injected services.
   * @param config - Raw host configuration; omitted fields take defaults and
   *   invalid values fail loud with `HIERARCHY_INVALID_CONFIG`.
   */
  constructor(ctx: Context, config?: AgentHierarchyConfigInput) {
    super(ctx, 'agentHierarchy')
    this.config = parseAgentHierarchyConfig(config)
  }

  protected [Service.init](): void {
    const registries: GuardRegistries = {
      agents: this.ctx.agents,
      bindings: this.ctx.agentBindings,
      onRoleResolved: (agent, role) => { this.installRestriction(agent, role) },
    }
    this.disposers.push(this.ctx.tools.guard(createHierarchyGuard(this.config, registries)))
    this.disposers.push(this.ctx.on('agent/created', ({ agent }) => {
      const record = this.ctx.agentBindings.find(agent.id)
      if (record === undefined || !isAgentRole(record.role)) return
      this.installRestriction(agent, record.role)
    }))
    this.disposers.push(this.ctx.on('agent/disposed', ({ agent }) => {
      const installed = this.installedRestrictions.get(agent.id)
      if (installed === undefined || installed.agent !== agent) return
      this.installedRestrictions.delete(agent.id)
      installed.release()
    }))
    this.ctx.effect(() => () => { this.teardown() }, 'agent-hierarchy.dispose')
    // Cold recovery: the binding registry has already restored its records;
    // reinstall the inherited restriction for every agent that is live right
    // now. Agents created later are covered by the `agent/created` listener.
    this.reinstallForActiveSessions()
  }

  /**
   * Resolve the hierarchy role of one exact live agent.
   * @param agent - Candidate agent identity.
   * @returns The bound role, or `undefined` when the identity is stale or unbound.
   */
  roleOf(agent: Agent): AgentRole | undefined {
    if (this.ctx.agents.get(agent.id) !== agent) return undefined
    const record = this.ctx.agentBindings.find(agent.id)
    return record !== undefined && isAgentRole(record.role) ? record.role : undefined
  }

  /**
   * Evaluate a programmatic creation intent against the creator's binding
   * and this host's approved plugin scopes. Tool executions reach the same
   * policy through the installed guard; every non-tool creation entry must
   * call this before the child exists.
   * @param creator - The durable binding of the creating session.
   * @param intent - The recorded creation attempt.
   * @returns The verdict with a denial reason when refused.
   */
  evaluateCreation(creator: AgentBindingRecord, intent: CreationIntent): CreationDecision {
    return evaluateCreationIntent(this.config, creator, intent)
  }

  /**
   * Create a child through the Agent factory with its role persisted in setup.
   * The caller supplies a registered, independently owned worktree. This
   * operation does not allocate a worktree or send a prompt.
   * Persistence failures retain the session-identity registry's recovery semantics.
   * Matching parent/task retries reuse the stored binding; changed requests and
   * occupied worktrees reject. A persisted child whose Session is unavailable
   * requires recovery rather than replacement.
   * @param parent - Exact live delegating Agent with a durable role binding.
   * @param request - Child role plus required task, explicit plugin scope, and registered worktree.
   * @param options - Factory composition, model options, and cancellation signal.
   * @returns The published Agent and its durable binding.
   */
  async createChildAgent(
    parent: Agent,
    request: CreateChildAgentRequest,
    options: CreateChildAgentOptions = {},
  ): Promise<CreatedChildAgent> {
    const prepared = this.preparationTail.then(() => this.createChildAgentSerial(parent, request, options))
    this.preparationTail = prepared.then(() => undefined, () => undefined)
    return prepared
  }

  /**
   * Recover one reserved child without replacing its identity or replaying a task.
   * Existing durable history is resumed; only a missing durable log permits
   * fresh publication under the same reserved identity.
   * @param parent - Exact live parent recorded by the reservation.
   * @param request - Original role, plugin, task, cwd and worktree binding.
   * @param options - Reserved Session identity and explicit host setup and route.
   * @returns The recovered child and its unchanged durable binding.
   */
  async recoverChildAgent(
    parent: Agent,
    request: CreateChildAgentRequest,
    options: CreateChildAgentOptions & { sessionId: SessionId },
  ): Promise<CreatedChildAgent> {
    const prepared = this.preparationTail.then(() => this.createChildAgentSerial(parent, request, options, true))
    this.preparationTail = prepared.then(() => undefined, () => undefined)
    return prepared
  }

  /** Serialize ownership lookup and durable creation so duplicate callers cannot reserve two children. */
  private async createChildAgentSerial(
    parent: Agent,
    request: CreateChildAgentRequest,
    options: CreateChildAgentOptions,
    recover = false,
  ): Promise<CreatedChildAgent> {
    if (this.disposed || this.ctx.agents.get(parent.id) !== parent) {
      throw new Error('agent-hierarchy: child preparation requires an exact live parent')
    }
    const creator = this.ctx.agentBindings.find(parent.id)
    if (creator === undefined) throw new Error('agent-hierarchy: parent has no role binding')
    const decision = this.evaluateCreation(creator, {
      parentSessionId: parent.id,
      requestedRole: request.role,
      ...(request.pluginId === undefined ? {} : { pluginScope: request.pluginId }),
    })
    if (!decision.allowed) throw new Error(decision.reason)
    const depth = delegationDepthOf(parent) + 1
    if (depth > AGENT_HIERARCHY_DELEGATION_DEPTH_BUDGET) {
      throw new Error('agent-hierarchy: child exceeds the delegation depth budget')
    }
    if (request.taskId === undefined || request.worktree === undefined) {
      throw new Error('agent-hierarchy: child requires a task and registered worktree')
    }
    if (request.pluginId === undefined) {
      throw new Error('agent-hierarchy: child requires an explicit plugin scope')
    }
    const { taskId, worktree } = request
    if (request.cwd !== request.worktree.worktreePath) {
      throw new Error('agent-hierarchy: child cwd must match its registered worktree path')
    }
    if (request.worktree.worktreeId === creator.worktreeId || request.cwd === parent.session.header.cwd) {
      throw new Error('agent-hierarchy: child requires a worktree independent of its parent')
    }
    const records = this.ctx.agentBindings.list()
    const existing = records.find(record => record.parentSessionId === parent.id && record.taskId === request.taskId)
    if (existing !== undefined) {
      if (existing.role !== request.role || existing.pluginId !== request.pluginId
        || (options.sessionId !== undefined && existing.agentId !== options.sessionId)
        || existing.worktreeId !== request.worktree.worktreeId || existing.worktreePath !== request.cwd
        || existing.branch !== request.worktree.branch) {
        throw new Error('agent-hierarchy: task already has a different child binding')
      }
      const agent = this.ctx.agents.get(existing.sessionId)
      if (agent !== undefined) return { agent, record: existing }
      if (!recover) throw new Error('agent-hierarchy: reserved child requires session recovery')
    } else if (recover) {
      throw new Error('agent-hierarchy: recovery requires an existing child reservation')
    }
    if (existing === undefined
      && records.some(record => record.worktreeId === worktree.worktreeId || record.worktreePath === request.cwd)) {
      throw new Error('agent-hierarchy: worktree already belongs to another session')
    }
    let record: AgentBindingRecord | undefined
    let setupStarted = false
    const factoryOptions = {
      sessionId: options.sessionId ?? SessionId(`session-${randomUUID()}`),
      ...options,
      meta: {
        cwd: request.cwd,
        ...(parent.session.header.agentPreset === undefined ? {} : { agentPreset: parent.session.header.agentPreset }),
        parentSession: parent.id,
        delegationDepth: depth,
      },
      setup: async (childCtx) => {
        setupStarted = true
        const child = childCtx.agent
        if (child === undefined) throw new Error('agent-hierarchy: factory setup has no Agent')
        if (child.session.header.cwd !== request.cwd || child.session.header.parentSession !== parent.id
          || child.session.header.delegationDepth !== depth) {
          throw new Error('agent-hierarchy: recovered Session header conflicts with its reservation')
        }
        const commit = await options.setup?.(childCtx)
        record = await this.ctx.agentBindings.bindPreparedSession(child.session, {
          role: request.role,
          ...(request.pluginId === undefined ? {} : { pluginId: request.pluginId }),
          taskId,
          worktree,
        })
        return { commit: () => {
          if (this.disposed || this.ctx.agents.get(parent.id) !== parent) {
            throw new Error(`agent-hierarchy: parent ended during creation; recover child ${child.id}`)
          }
          commit?.commit()
        } }
      },
    } satisfies CreateAgentOptions
    const publish = async () => {
      if (existing === undefined) return await this.ctx.agents.create(factoryOptions)
      try {
        return await this.ctx.agents.resume({
          resumeSessionId: existing.sessionId,
          ...(options.agentOptions === undefined ? {} : { agentOptions: options.agentOptions }),
          ...(options.signal === undefined ? {} : { signal: options.signal }),
          setup: factoryOptions.setup,
        })
      } catch (error) {
        if (setupStarted || !(error instanceof SessionPersistenceNotFoundError)
          || error.sessionId !== existing.sessionId) throw error
      }
      return await this.ctx.agents.create({ ...factoryOptions, sessionId: existing.sessionId })
    }
    const handle = await publish()
    if (record === undefined) throw new Error('agent-hierarchy: factory published without completing binding setup')
    return { agent: handle.agent, record }
  }

  /** Reinstall the inherited restriction for every restored binding whose agent is currently live. */
  private reinstallForActiveSessions(): void {
    for (const record of this.ctx.agentBindings.list()) {
      if (!isAgentRole(record.role)) {
        throw new AgentHierarchyError(
          `restored binding for agent "${record.agentId}" carries role "${String(record.role)}" outside the hierarchy union`,
          'HIERARCHY_ROLE_UNKNOWN',
        )
      }
      const agent = this.ctx.agents.get(record.agentId)
      if (agent !== undefined) this.installRestriction(agent, record.role)
    }
  }

  /**
   * Apply one agent's inherited allow restriction. Idempotent per agent;
   * skips a stale identity silently (the guard still enforces every denial).
   * A configured tool name that matches no global tool throws here — at
   * service init that fails load loud; inside `agent/created` the agent
   * registry contains the listener failure and logs it.
   */
  private installRestriction(agent: Agent, role: AgentRole): void {
    if (this.disposed || this.installedRestrictions.has(agent.id)) return
    if (this.ctx.agents.get(agent.id) !== agent) return
    const policy = this.config.roleToolPolicies[role]
    const release = agent.ctx.tools.restrict({ allow: [...policy.inheritedTools] })
    this.installedRestrictions.set(agent.id, { agent, release })
  }

  /** Release the guard, both lifecycle listeners, and every installed restriction. Idempotent. */
  private teardown(): void {
    this.disposed = true
    for (const release of this.disposers.splice(0)) release()
    for (const installed of this.installedRestrictions.values()) installed.release()
    this.installedRestrictions.clear()
  }
}
