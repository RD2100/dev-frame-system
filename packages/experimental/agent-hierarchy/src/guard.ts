/**
 * The monotonic pre-execute guard of the pluginized hierarchy. Registered
 * once on the root tool registry, it resolves the executing agent's role
 * from the binding registry at execution time — never from a stale
 * assignment — and enforces, in order: exact live identity, fail-closed role
 * presence, the role's deny face, the absolute delegation-depth budget, and
 * the lead's approved plugin scopes. Guards cannot allow; the guard only
 * ever narrows.
 *
 * @module @deepseek-ai/dsh-experimental-agent-hierarchy/guard
 */

import type { Agent } from '@deepseek-ai/dsh-agent'
import type { AgentBindingRecord, AgentRole } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { SessionId } from '@deepseek-ai/dsh-session'
import { delegationDepthOf } from '@deepseek-ai/dsh-subagent'
import type { ToolExecution } from '@deepseek-ai/dsh-tools'
import { isAgentRole } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { AgentHierarchyConfig } from './config.ts'
import { AGENT_HIERARCHY_DELEGATION_DEPTH_BUDGET, controlledToolNames, denyFaceFor } from './policy.ts'

/** The live agent registry surface the guard checks exact identity against. */
export interface LiveAgentLookup {
  /** Resolve one live agent by its shared agent/session id. */
  readonly get: (id: SessionId) => Agent | undefined
}

/**
 * The live registries the guard resolves identity and role from. The agent
 * lookup is the exact-identity check surface — the P01 cold-recovery caveat
 * lives here: a restored record is only usable for an agent the registry
 * currently answers to, so a stale identity is denied before its record is
 * ever consulted.
 */
export interface GuardRegistries {
  /** The live agent registry (`ctx.agents`). */
  readonly agents: LiveAgentLookup
  /** The durable binding registry (`ctx.agentBindings`). */
  readonly bindings: { readonly find: (agentId: SessionId) => AgentBindingRecord | undefined }
  /** Optional hook invoked whenever the guard resolves a bound role, so the allow face installs lazily on first enforcement. */
  readonly onRoleResolved?: (agent: Agent, role: AgentRole) => void
}

/**
 * Build the guard callback for one resolved configuration. The deny faces
 * are computed once; roles and scopes are resolved per execution so a
 * binding written or restored after guard registration is honored
 * immediately.
 * @param config - The resolved host configuration.
 * @param registries - The live identity and binding lookups.
 * @returns A monotonic guard: a returned string denies the execution.
 */
export function createHierarchyGuard(
  config: AgentHierarchyConfig,
  registries: GuardRegistries,
): (execution: Readonly<ToolExecution>) => string | undefined {
  const controlled = controlledToolNames(config)
  const faces: Readonly<Record<AgentRole, ReadonlySet<string>>> = {
    controller: denyFaceFor('controller', config),
    lead: denyFaceFor('lead', config),
    worker: denyFaceFor('worker', config),
  }
  return (execution: Readonly<ToolExecution>): string | undefined => {
    const agent = execution.agent
    if (agent === undefined) {
      return `agent-hierarchy: tool "${execution.name}" requires an exact live Agent`
    }
    if (registries.agents.get(agent.id) !== agent) {
      return `agent-hierarchy: stale Agent identity "${agent.id}" cannot execute "${execution.name}"`
    }
    const record = registries.bindings.find(agent.id)
    if (record === undefined) {
      if (!controlled.has(execution.name)) return undefined
      return `agent-hierarchy: session "${agent.id}" has no role binding and cannot execute controlled tool "${execution.name}" (missing role)`
    }
    if (!isAgentRole(record.role)) {
      return `agent-hierarchy: session "${agent.id}" carries role "${String(record.role)}" outside the hierarchy union`
    }
    registries.onRoleResolved?.(agent, record.role)
    if (faces[record.role].has(execution.name)) {
      return `agent-hierarchy: role "${record.role}" cannot execute "${execution.name}"`
    }
    if (config.delegationToolNames.includes(execution.name)) {
      // delegationDepthOf throws on a corrupt runtime depth; inside the tool
      // registry that surfaces as an error result, which is the loud outcome
      // a corrupt caller deserves.
      const parentDepth = delegationDepthOf(agent)
      const childDepth = parentDepth + 1
      if (childDepth > AGENT_HIERARCHY_DELEGATION_DEPTH_BUDGET) {
        return `agent-hierarchy: delegating from depth ${parentDepth} would create a child at depth ${childDepth} beyond the absolute budget ${AGENT_HIERARCHY_DELEGATION_DEPTH_BUDGET}`
      }
      if (record.role === 'lead') {
        if (record.pluginId === undefined) {
          return `agent-hierarchy: lead "${record.agentId}" has no plugin scope binding and cannot delegate`
        }
        const approved = config.leadPluginScopes[record.agentId] ?? []
        if (!approved.includes(record.pluginId)) {
          return `agent-hierarchy: plugin scope "${record.pluginId}" is not in the approved set of lead "${record.agentId}"`
        }
      }
    }
    return undefined
  }
}
