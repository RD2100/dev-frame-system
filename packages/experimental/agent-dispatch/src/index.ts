/**
 * Package entry for the host daily-dispatch adapter. The default export is
 * the {@link AgentDispatch} Cordis service the Loader mounts; the named
 * exports carry the stable error type and the pure dispatch-discipline
 * evaluator. The service registers as `ctx.agentDispatch`.
 * @module @deepseek-ai/dsh-experimental-agent-dispatch
 */

export { AgentDispatchError } from './errors.ts'
export type { AgentDispatchErrorCode } from './errors.ts'
export { evaluateDispatchEntry } from './entry.ts'
export { AgentDispatch } from './service.ts'
export type { DispatchAgentOptions, DispatchedIdentity } from './service.ts'
export { AgentDispatch as default } from './service.ts'
