/**
 * The three-role policy lookup table and the derived tool sets the guard
 * enforces. `reviewer` is deliberately absent: its deny semantics moved into
 * the lead and worker faces, with `send_message` deliberately kept off both —
 * it is the authorized reporting route a worker must retain toward its lead.
 *
 * @module @deepseek-ai/dsh-experimental-agent-hierarchy/policy
 */

import type { AgentRole } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { AgentHierarchyConfig } from './config.ts'

/**
 * Absolute delegation-depth budget of the pluginized hierarchy: controller =
 * 0, lead = 1, worker = 2. A security invariant, not a tunable — the seam's
 * `SubagentDepthError` path stays as the first refusal half and this
 * package's pre-execute guard as the second, independent half.
 */
export const AGENT_HIERARCHY_DELEGATION_DEPTH_BUDGET = 2

/**
 * Every tool name the policy controls: the delegation seam (spawn/fork), the
 * Team spawn/task-control face, and any further creation surface the host
 * declares. A session with no role binding that calls any of these is denied
 * fail closed; everything else an unbound session executes is not this
 * package's boundary.
 * @param config - The resolved host configuration.
 * @returns The controlled tool-name set.
 */
export function controlledToolNames(config: AgentHierarchyConfig): ReadonlySet<string> {
  return new Set([...config.delegationToolNames, ...config.teamToolNames, ...config.otherCreationToolNames])
}

/**
 * The scope-local deny face of one role: the package-owned security face
 * merged with the host's per-role extras. Controllers deny only their extras;
 * leads additionally lose the Team spawn/task-control face (the merged
 * reviewer semantics); workers lose everything that can create an agent.
 * @param role - The bound role of the session.
 * @param config - The resolved host configuration.
 * @returns The monotonic deny set the guard checks first.
 */
export function denyFaceFor(role: AgentRole, config: AgentHierarchyConfig): ReadonlySet<string> {
  const extras = config.roleToolPolicies[role].denyScopedTools ?? []
  switch (role) {
    case 'controller':
      return new Set(extras)
    case 'lead':
      return new Set([...config.teamToolNames, ...extras])
    case 'worker':
      return new Set([...config.delegationToolNames, ...config.teamToolNames, ...config.otherCreationToolNames, ...extras])
  }
}
