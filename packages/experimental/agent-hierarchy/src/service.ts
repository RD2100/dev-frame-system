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
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { AgentBindingRecord, AgentRole, CreationIntent } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { SessionId } from '@deepseek-ai/dsh-session'
import { isAgentRole } from '@deepseek-ai/dsh-experimental-project-contracts'
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

  /**
   * @param ctx - The mounting context; must carry the injected services.
   * @param config - Raw host configuration; omitted fields take defaults and
   *   invalid values fail loud with `HIERARCHY_INVALID_CONFIG`.
   */
  constructor(ctx: Context, config?: AgentHierarchyConfigInput) {
    super(ctx, 'agentHierarchy')
    this.config = parseAgentHierarchyConfig(config)
  }

  protected async [Service.init](): Promise<void> {
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
    this.ctx.effect(() => () => this.teardown(), 'agent-hierarchy.dispose')
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
