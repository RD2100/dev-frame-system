/**
 * Package entry for the host daily-dispatch adapter and the formal host
 * bootstrap. The Loader mount face is the function-plugin namespace
 * (`name`/`inject`/`Config`/`apply`), which mounts the {@link AgentDispatch}
 * service, the {@link AgentProjectRun} bootstrap service, and the
 * model-facing `agent_dispatch` tool; the namespace is the ONLY entry the
 * Loader unwraps, so no default export exists here. The named exports carry
 * the services for direct consumers (tests and compositions that mount the
 * service classes), the stable error types, and the pure dispatch-discipline
 * evaluator.
 * @module @deepseek-ai/dsh-experimental-agent-dispatch
 */

export { AgentDispatchError } from './errors.ts'
export type { AgentDispatchErrorCode } from './errors.ts'
export { evaluateDispatchEntry } from './entry.ts'
export { foldBriefingAck } from './ack.ts'
export type { BriefingAckFold, DispatchAckState, DispatchTaskAck } from './ack.ts'
export { AgentDispatch } from './service.ts'
export type { DispatchAgentOptions, DispatchedIdentity, RecoverDispatchAgentOptions } from './service.ts'
export { AgentProjectRun, ProjectRunError } from './run.ts'
export type {
  CandidateHostReceipt,
  CandidateScenario,
  CandidateScenarioTask,
  ProjectRunConfig,
  ProjectRunErrorCode,
  TaskChecksApproval,
} from './run.ts'
export { settlementNotice, watchChildSettlement } from './child-settlement.ts'
export type { DispatchSettledMessageSource, SettlementFlush } from './child-settlement.ts'
export { name, inject, Config, apply, TOOL_NAMES } from './consumer.ts'
