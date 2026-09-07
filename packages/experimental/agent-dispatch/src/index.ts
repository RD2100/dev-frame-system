/**
 * Package entry for the host daily-dispatch adapter. The Loader mount face
 * is the function-plugin namespace (`name`/`inject`/`apply`), which mounts
 * the {@link AgentDispatch} service and the model-facing `agent_dispatch`
 * tool; the namespace is the ONLY entry the Loader unwraps, so no default
 * export exists here. The named exports carry the service for direct
 * consumers (tests and compositions that mount the service class), the
 * stable error type, and the pure dispatch-discipline evaluator.
 * @module @deepseek-ai/dsh-experimental-agent-dispatch
 */

export { AgentDispatchError } from './errors.ts'
export type { AgentDispatchErrorCode } from './errors.ts'
export { evaluateDispatchEntry } from './entry.ts'
export { AgentDispatch } from './service.ts'
export type { DispatchAgentOptions, DispatchedIdentity, RecoverDispatchAgentOptions } from './service.ts'
export { name, inject, apply, TOOL_NAMES } from './consumer.ts'
