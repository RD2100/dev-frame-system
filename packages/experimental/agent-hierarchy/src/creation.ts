/**
 * The programmatic creation face: validate a {@link CreationIntent} against
 * the creator's durable binding. Tool executions reach the same policy
 * through the guard, which derives an equivalent intent from the execution —
 * this module is the seam every non-tool creation entry (host services, SDK
 * bridges, later controller waves) must call before a child exists.
 *
 * @module @deepseek-ai/dsh-experimental-agent-hierarchy/creation
 */

import type { AgentBindingRecord, CreationIntent } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { AgentHierarchyConfig } from './config.ts'

/** One creation-face verdict; `reason` explains a denial for the caller's own surface. */
export interface CreationDecision {
  /** Whether the creation may proceed. */
  readonly allowed: boolean
  /** Human-readable rejection reason; absent when allowed. */
  readonly reason?: string | undefined
}

/**
 * Evaluate one creation intent against the creator's role and approved
 * plugin scopes. Workers may create nothing; a lead may only create workers
 * inside a scope the host config approved for its agent id (unlisted leads
 * are approved for nothing — fail closed); a controller may create only leads.
 * @param config - The resolved host configuration.
 * @param creator - The durable binding of the creating session.
 * @param intent - The recorded creation attempt: parent, requested role, requested scope.
 * @returns The verdict with a denial reason when refused.
 */
export function evaluateCreationIntent(
  config: AgentHierarchyConfig,
  creator: AgentBindingRecord,
  intent: CreationIntent,
): CreationDecision {
  switch (creator.role) {
    case 'worker':
      return {
        allowed: false,
        reason: `agent-hierarchy: role "worker" cannot create agents (requested "${intent.requestedRole}")`,
      }
    case 'lead': {
      if (intent.requestedRole !== 'worker') {
        return {
          allowed: false,
          reason: `agent-hierarchy: a lead may only create workers, requested "${intent.requestedRole}"`,
        }
      }
      if (intent.pluginScope === undefined) {
        return {
          allowed: false,
          reason: `agent-hierarchy: the creation intent of lead "${creator.agentId}" carries no pluginScope`,
        }
      }
      const approved = config.leadPluginScopes[creator.agentId] ?? []
      if (!approved.includes(intent.pluginScope)) {
        return {
          allowed: false,
          reason: `agent-hierarchy: plugin scope "${intent.pluginScope}" is not in the approved set of lead "${creator.agentId}"`,
        }
      }
      return { allowed: true }
    }
    case 'controller':
      return intent.requestedRole === 'lead'
        ? { allowed: true }
        : { allowed: false, reason: `agent-hierarchy: a controller may only create leads, requested "${intent.requestedRole}"` }
  }
}
