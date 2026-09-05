/**
 * Package entry for the agent reliability service. The default export is the
 * {@link AgentReliability} Cordis service the Loader mounts; the named
 * exports carry the plan/outcome shapes, the stop contract re-export, and
 * the stable error type. The service registers as `ctx.agentReliability`.
 * @module @deepseek-ai/dsh-experimental-agent-reliability
 */

export { AgentReliabilityError } from './errors.ts'
export type { AgentReliabilityErrorCode } from './errors.ts'
export type { StopIssue, StopObservation, StopProcess, StopProjectOptions, StopResult } from '@deepseek-ai/dsh-experimental-devframe/reliability'
export { AgentReliability } from './service.ts'
export type {
  FlushBarrierResult,
  ReconciliationProbe,
  ReconciledOutcome,
  ReliabilityAdmission,
  UncertainCallPlan,
} from './service.ts'
export { AgentReliability as default } from './service.ts'
