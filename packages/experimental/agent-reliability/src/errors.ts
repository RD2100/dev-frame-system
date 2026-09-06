/** The stable error type for agent-reliability admission failures. */

/** Stable, machine-routable failure classifications for the reliability service. */
export type AgentReliabilityErrorCode =
  /** A dispatch pre-step ran while admission was closed or before any identity was opened. */
  | 'AGENT_RELIABILITY_ADMISSION_CLOSED'
  /** A dispatch pre-step ran after the admitted generation's cutoff instant; the window is dead. */
  | 'AGENT_RELIABILITY_ADMISSION_DEADLINE_CLOSED'
  /** openAdmission received a cutoff that is not a finite epoch millisecond instant. */
  | 'AGENT_RELIABILITY_ADMISSION_DEADLINE_INVALID'
  /** A dispatch pre-step ran for a work identity other than the admitted one. */
  | 'AGENT_RELIABILITY_IDENTITY_MISMATCH'

/**
 * Structured failure from the admission pre-step, so dispatchers can route on
 * the code alone. Reconciliation and flush barriers report outcomes as data
 * instead of throwing.
 */
export class AgentReliabilityError extends Error {
  /** Stable machine-routable failure classification. */
  readonly code: AgentReliabilityErrorCode

  /**
   * @param message - Human-readable rejection reason.
   * @param code - Stable failure classification.
   */
  constructor(message: string, code: AgentReliabilityErrorCode) {
    super(message)
    this.name = 'AgentReliabilityError'
    this.code = code
  }
}
