/** The stable error type shared by every consumer of the contracts vocabulary. */

/** Stable, machine-routable failure classifications for the contracts vocabulary. */
export type ProjectContractsErrorCode =
  /** An id factory received an empty, whitespace-only, or padded string. */
  | 'CONTRACTS_INVALID_ID'
  /** A record failed its structural validation at a durable boundary. */
  | 'CONTRACTS_INVALID_RECORD'
  /** A write would replace a record whose stored content disagrees with the replacement's key or immutable fields. */
  | 'CONTRACTS_CONFLICT'
  /** The persistence backend behind a store seam is unusable. */
  | 'CONTRACTS_STORE_UNAVAILABLE'

/**
 * Structured failure thrown by the contract factories and by every store
 * implementation built on the {@link ProjectContractsErrorCode} vocabulary,
 * so host admission and diagnostics can route on the code alone.
 */
export class ProjectContractsError extends Error {
  /** Stable machine-routable failure classification. */
  readonly code: ProjectContractsErrorCode

  /**
   * @param message - Human-readable rejection reason.
   * @param code - Stable failure classification.
   * @param options - Original backend failure, when one exists.
   */
  constructor(message: string, code: ProjectContractsErrorCode, options?: ErrorOptions) {
    super(message, options)
    this.name = 'ProjectContractsError'
    this.code = code
  }
}
