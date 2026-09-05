/** The stable error type for agent-evidence failures. */

/** Stable, machine-routable failure classifications for the evidence ledger. */
export type AgentEvidenceErrorCode =
  /** A receipt request failed validation: an empty field, a malformed commit name, or a non-integer exit code. */
  | 'AGENT_EVIDENCE_INVALID_RECEIPT'
  /** The storage domain refused a write, or the record on disk failed its schema. */
  | 'AGENT_EVIDENCE_PERSISTENCE'

/**
 * Structured failure from recording or restoring evidence receipts, so host
 * admission and diagnostics can route on the code alone.
 */
export class AgentEvidenceError extends Error {
  /** Stable machine-routable failure classification. */
  readonly code: AgentEvidenceErrorCode

  /**
   * @param message - Human-readable rejection reason.
   * @param code - Stable failure classification.
   * @param options - Original storage failure, when one exists.
   */
  constructor(message: string, code: AgentEvidenceErrorCode, options?: ErrorOptions) {
    super(message, options)
    this.name = 'AgentEvidenceError'
    this.code = code
  }
}
