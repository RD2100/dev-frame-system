/** Host-owned role restrictions for one DevFrame project composition. */

import type { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { SessionId } from '@deepseek-ai/dsh-session'

/** Roles admitted by the single-project DevFrame profile. */
export type DevFrameRole = 'controller' | 'worker' | 'reviewer'

/** A restriction over inherited global tools plus optional local denials. */
export interface RoleToolPolicy {
  /** Global tools retained in the exact Agent scope. */
  readonly inheritedTools: readonly string[]
  /** Additional scope-local tool names denied by the profile guard. */
  readonly denyScopedTools?: readonly string[]
}

/** Complete role policy selected by the host for one project profile. */
export interface RolePolicyConfig {
  readonly controller: RoleToolPolicy
  readonly worker: RoleToolPolicy
  readonly reviewer: RoleToolPolicy
}

/** Scope-local Team tools a reviewer cannot execute. */
export const REVIEWER_DENIED_SCOPED_TOOLS: readonly string[] = Object.freeze([
  'spawn_teammate',
  'send_message',
  'followup_task',
  'interrupt_agent',
  'team_task_create',
  'team_task_update',
])

/** Minimal execution identity consumed by the host guard. */
interface RoleToolExecution {
  readonly agent?: Agent
  readonly name: string
}

/** Native tool restriction operations used without coupling this slice to the tool package. */
interface RoleToolRuntime {
  restrict(filter: { readonly allow?: readonly string[]; readonly deny?: readonly string[] }): () => void
  guard(check: (execution: Readonly<RoleToolExecution>) => string | undefined): () => void
}

/** Minimal live-agent lookup required for exact identity checks. */
interface RoleAgentRegistry {
  get(id: SessionId): Agent | undefined
}

interface RoleAssignment {
  readonly agent: Agent
  readonly role: DevFrameRole
  readonly deniedScopedTools: ReadonlySet<string>
  readonly releaseRestriction: () => void
}

/** Structured failure for a conflicting or unavailable role assignment. */
export class RolePolicyError extends Error {
  /** Stable machine-readable failure classification. */
  readonly code: 'ROLE_ALREADY_ASSIGNED' | 'ROLE_IDENTITY_CONFLICT' | 'ROLE_TOOLS_UNAVAILABLE'

  /**
   * @param message - Human-readable failure detail.
   * @param code - Stable role-policy failure classification.
   */
  constructor(message: string, code: RolePolicyError['code']) {
    super(message)
    this.name = 'RolePolicyError'
    this.code = code
  }
}

/**
 * Host-owned role policy that combines inherited restrictions with a monotonic
 * guard over scope-local Team tools.
 */
export class RolePolicy {
  private readonly assignments = new Map<SessionId, RoleAssignment>()
  private readonly releaseGuard: () => void
  private readonly releaseDisposedListener: () => void
  private disposed = false

  /**
   * @param context - Root context that owns the global tool guard.
   * @param config - Host-selected inherited tools and additional local denials.
   */
  constructor(private readonly context: Context, private readonly config: RolePolicyConfig) {
    const tools = this.toolRuntime(context)
    this.releaseGuard = tools.guard(execution => this.guardReason(execution))
    this.releaseDisposedListener = context.on('agent/disposed', ({ agent }) => {
      this.releaseAssignment(agent)
    })
  }

  /**
   * Assign one immutable role to an exact live Agent and apply its inherited filter.
   * @param agent - Exact live Agent that will carry the role.
   * @param role - Host-selected DevFrame role.
   * @returns Nothing; the assignment remains until Agent disposal or policy disposal.
   */
  assign(agent: Agent, role: DevFrameRole): void {
    if (this.disposed) throw new RolePolicyError('role policy is disposed', 'ROLE_TOOLS_UNAVAILABLE')
    const agents = this.context.get('agents') as RoleAgentRegistry | undefined
    if (agents?.get(agent.id) !== agent) {
      throw new RolePolicyError(`Agent "${agent.id}" is not the exact live registry identity`, 'ROLE_IDENTITY_CONFLICT')
    }
    const current = this.assignments.get(agent.id)
    if (current !== undefined) {
      if (current.agent === agent && current.role === role) {
        throw new RolePolicyError(`Agent "${agent.id}" already has role "${role}"`, 'ROLE_ALREADY_ASSIGNED')
      }
      throw new RolePolicyError(`Agent "${agent.id}" has a different live role assignment`, 'ROLE_IDENTITY_CONFLICT')
    }
    const roleConfig = this.config[role]
    const tools = this.toolRuntime(agent.ctx)
    const releaseRestriction = tools.restrict({ allow: roleConfig.inheritedTools })
    this.assignments.set(agent.id, {
      agent,
      role,
      deniedScopedTools: new Set([
        ...role === 'reviewer' ? REVIEWER_DENIED_SCOPED_TOOLS : [],
        ...roleConfig.denyScopedTools ?? [],
      ]),
      releaseRestriction,
    })
  }

  /**
   * Resolve the role for one exact live Agent.
   * @param agent - Candidate Agent identity.
   * @returns The assigned role, or undefined when no exact assignment exists.
   */
  roleOf(agent: Agent): DevFrameRole | undefined {
    const assignment = this.assignments.get(agent.id)
    return assignment?.agent === agent ? assignment.role : undefined
  }

  /**
   * Resolve the role for one Session identity, without requiring the live Agent
   * object. This is the SessionId-keyed read face for seams that only carry the
   * identity (for example review-event authorization); exact live-identity
   * checks keep using {@link RolePolicy.roleOf}.
   * @param sessionId - Session identity to resolve.
   * @returns The assigned role, or undefined when the Session holds no assignment.
   */
  roleOfSession(sessionId: SessionId): DevFrameRole | undefined {
    return this.assignments.get(sessionId)?.role
  }

  /**
   * Remove one exact assignment and lift its inherited restriction.
   * @param agent - Agent being disposed by the host lifecycle.
   */
  private releaseAssignment(agent: Agent): void {
    const assignment = this.assignments.get(agent.id)
    if (assignment?.agent !== agent) return
    this.assignments.delete(agent.id)
    assignment.releaseRestriction()
  }

  /**
   * Dispose the guard, lifecycle listener, and all agent-scoped restrictions.
   * Callers own this capability and should release it after owned work drains.
   */
  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.releaseDisposedListener()
    for (const assignment of this.assignments.values()) assignment.releaseRestriction()
    this.assignments.clear()
    this.releaseGuard()
  }

  /** Resolve the role runtime and fail explicitly when tools are not mounted. */
  private toolRuntime(context: Context): RoleToolRuntime {
    const tools = context.get('tools') as RoleToolRuntime | undefined
    if (tools === undefined) {
      throw new RolePolicyError('role policy requires the native tools service', 'ROLE_TOOLS_UNAVAILABLE')
    }
    return tools
  }

  /** Return a monotonic denial reason for an execution, or undefined to allow it. */
  private guardReason(execution: Readonly<RoleToolExecution>): string | undefined {
    const agent = execution.agent
    if (agent === undefined) return 'DevFrame role policy requires an exact live Agent'
    const assignment = this.assignments.get(agent.id)
    if (assignment === undefined) return `DevFrame role policy has no role for Agent "${agent.id}"`
    if (assignment.agent !== agent) return `DevFrame role policy rejected stale Agent identity "${agent.id}"`
    if (assignment.deniedScopedTools.has(execution.name)) {
      return `DevFrame role "${assignment.role}" cannot execute "${execution.name}"`
    }
    return undefined
  }
}

/**
 * Install one host-owned policy and return its disposal capability.
 * @param context - Root context containing the native tools service.
 * @param config - Explicit role capabilities selected by the host profile.
 * @returns The live role policy; call {@link RolePolicy.dispose} after owned work drains.
 */
export function installRolePolicy(context: Context, config: RolePolicyConfig): RolePolicy {
  const policy = new RolePolicy(context, config)
  context.effect(() => () => { policy.dispose() }, 'devframe.rolePolicy()')
  return policy
}
