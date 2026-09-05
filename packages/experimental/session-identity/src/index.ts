/**
 * Package entry for the session-identity service. The default export is the
 * {@link AgentBindingRegistry} Cordis service the Loader mounts; the named
 * exports carry the request shapes, the domain spec, and the stable error
 * type. The service registers as `ctx.agentBindings`.
 * @module @deepseek-ai/dsh-experimental-session-identity
 */

export { SessionIdentityError } from './errors.ts'
export type { SessionIdentityErrorCode } from './errors.ts'
export { agentBindingRecordSchema, sessionIdentityDomainSpec } from './spec.ts'
export { AgentBindingRegistry } from './registry.ts'
export type { BindAgentRequest, BoundSession, BoundWorktree, CreateBoundSessionRequest } from './registry.ts'
export { AgentBindingRegistry as default } from './registry.ts'
