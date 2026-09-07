/**
 * Package entry for the host daily-dispatch adapter. The default export is
 * the {@link AgentDispatch} Cordis service; the package root is also the
 * Loader plugin face (`name`/`inject`/`apply`) that mounts the service and
 * the model-facing `agent_dispatch` tool. The named exports carry the
 * stable error type and the pure dispatch-discipline evaluator.
 * @module @deepseek-ai/dsh-experimental-agent-dispatch
 */

export { AgentDispatchError } from './errors.ts'
export type { AgentDispatchErrorCode } from './errors.ts'
export { evaluateDispatchEntry } from './entry.ts'
export { AgentDispatch } from './service.ts'
export type { DispatchAgentOptions, DispatchedIdentity, RecoverDispatchAgentOptions } from './service.ts'
export { AgentDispatch as default } from './service.ts'
export { name, inject, apply, TOOL_NAMES } from './consumer.ts'
