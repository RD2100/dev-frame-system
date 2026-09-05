/** Closed-union guards and frozen member tuples for the contracts vocabulary. */

import type { AgentRole, TaskState } from './types.ts'

/** Every {@link AgentRole} member, frozen so the tuple cannot drift at runtime. */
export const AGENT_ROLES: readonly AgentRole[] = Object.freeze(['controller', 'lead', 'worker'])

/** Every {@link TaskState} member, frozen so the tuple cannot drift at runtime. */
export const TASK_STATES: readonly TaskState[] = Object.freeze([
  'planned',
  'assigned',
  'developing',
  'reviewing',
  'submitted',
  'integrated',
  'completed',
  'blocked',
  'failed',
])

/**
 * Whether an unknown value is one of the three hierarchy roles.
 * @param value - Untrusted value from a durable boundary or configuration.
 * @returns whether the value is an {@link AgentRole}.
 */
export function isAgentRole(value: unknown): value is AgentRole {
  return typeof value === 'string' && (AGENT_ROLES as readonly string[]).includes(value)
}

/**
 * Whether an unknown value is one of the nine task states.
 * @param value - Untrusted value from a durable boundary or configuration.
 * @returns whether the value is a {@link TaskState}.
 */
export function isTaskState(value: unknown): value is TaskState {
  return typeof value === 'string' && (TASK_STATES as readonly string[]).includes(value)
}
