/**
 * Package entry for the pluginized-hierarchy contracts. The package owns the
 * cross-plugin type vocabulary only: roles, task states, branded ids,
 * durable records, creation intents, persistence seams, closed-union guards,
 * and the stable error type. It registers no Cordis plugin, holds no live
 * state, and provides no model-facing surface.
 * @module @deepseek-ai/dsh-experimental-project-contracts
 */

export { ProjectContractsError } from './errors.ts'
export type { ProjectContractsErrorCode } from './errors.ts'
export { AGENT_ROLES, TASK_STATES, isAgentRole, isTaskState } from './guards.ts'
export { PluginId, TaskId } from './ids.ts'
export type {
  AgentBindingRecord,
  AgentRole,
  BindingStore,
  CreationIntent,
  TaskRecord,
  TaskState,
  TaskStore,
} from './types.ts'
