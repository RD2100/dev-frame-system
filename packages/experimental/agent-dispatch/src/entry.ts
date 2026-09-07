/**
 * The daily dispatch discipline: the host composition layer's rule for who
 * may dispatch which child with which plugin scope. The engine's creation
 * evaluator already refuses everything outside controller→lead and
 * lead→worker and the engine rejects scope-less requests before any binding,
 * so this evaluator adds no second policy table: it restates the two-step
 * chain and reads a lead's plugin scope from the engine's approved-set
 * contract (`config.leadPluginScopes[creator.agentId]`, sourced by the
 * service), so a lead approved for several plugins can dispatch inside any
 * of them. The hierarchy service remains the policy authority; this rule
 * only narrows the daily entry.
 *
 * @module @deepseek-ai/dsh-experimental-agent-dispatch/entry
 */

import type { AgentBindingRecord, PluginId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { CreateChildAgentRequest, CreationDecision } from '@deepseek-ai/dsh-experimental-agent-hierarchy'

/**
 * Evaluate one dispatch request against the dispatching parent's durable
 * binding and the engine's approved plugin scopes for that agent id. Fail
 * closed: an unknown parent role or a missing scope denies.
 * @param creator - The durable binding of the dispatching session.
 * @param request - The child creation request as the engine will receive it.
 * @param approvedScopes - The plugin scopes the engine config approves for
 *   `creator.agentId` (`config.leadPluginScopes[creator.agentId]`; an
 *   unlisted lead arrives as an empty set).
 * @returns The verdict with a denial reason when refused.
 */
export function evaluateDispatchEntry(
  creator: AgentBindingRecord,
  request: CreateChildAgentRequest,
  approvedScopes: readonly PluginId[],
): CreationDecision {
  switch (creator.role) {
    case 'worker':
      return {
        allowed: false,
        reason: `agent-dispatch: role "worker" cannot dispatch child agents (requested "${request.role}")`,
      }
    case 'lead': {
      if (request.role !== 'worker') {
        return {
          allowed: false,
          reason: `agent-dispatch: a lead dispatches only workers (requested "${request.role}")`,
        }
      }
      if (request.pluginId === undefined) {
        return {
          allowed: false,
          reason: 'agent-dispatch: a dispatched worker requires an explicit plugin scope',
        }
      }
      if (!approvedScopes.includes(request.pluginId)) {
        return {
          allowed: false,
          reason: `agent-dispatch: requested plugin scope "${request.pluginId}" is not in the approved set of lead "${creator.agentId}" (${approvedScopes.map(scope => `"${scope}"`).join(', ') || 'empty'})`,
        }
      }
      return { allowed: true }
    }
    case 'controller':
      if (request.role !== 'lead') {
        return {
          allowed: false,
          reason: `agent-dispatch: the controller dispatches only leads (requested "${request.role}")`,
        }
      }
      if (request.pluginId === undefined) {
        return {
          allowed: false,
          reason: 'agent-dispatch: a dispatched lead requires an explicit plugin scope',
        }
      }
      return { allowed: true }
  }
}
