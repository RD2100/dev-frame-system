/**
 * Package entry for the agent-hierarchy policy. The default export is the
 * {@link AgentHierarchy} Cordis service the Loader mounts; the named exports
 * carry the resolved configuration, the role policy table, the creation
 * evaluator, and the stable error type. The service registers as
 * `ctx.agentHierarchy`.
 * @module @deepseek-ai/dsh-experimental-agent-hierarchy
 */

export { AgentHierarchyError } from './errors.ts'
export type { AgentHierarchyErrorCode } from './errors.ts'
export { agentHierarchyConfigSchema, parseAgentHierarchyConfig } from './config.ts'
export type { AgentHierarchyConfig, AgentHierarchyConfigInput } from './config.ts'
export { AGENT_HIERARCHY_DELEGATION_DEPTH_BUDGET, controlledToolNames, denyFaceFor } from './policy.ts'
export { evaluateCreationIntent } from './creation.ts'
export type { CreationDecision } from './creation.ts'
export { createHierarchyGuard } from './guard.ts'
export type { GuardRegistries, LiveAgentLookup } from './guard.ts'
export { AgentHierarchy } from './service.ts'
export { AgentHierarchy as default } from './service.ts'
