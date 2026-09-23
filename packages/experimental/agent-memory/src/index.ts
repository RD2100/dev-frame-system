/** Persistent agent memory plugin entry. */
export { AgentMemoryError } from './errors.ts'
export type { AgentMemoryErrorCode } from './errors.ts'
export { agentMemoryDomainSpec, episodeSchema, semanticSchema, procedureSchema, traceSchema } from './spec.ts'
export { AgentMemoryService, DEFAULT_CONTEXT_BUDGET_BYTES } from './service.ts'
export type { AgentMemoryConfig } from './service.ts'
export type * from './types.ts'
export { AgentMemoryService as default } from './service.ts'
