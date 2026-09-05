/** The stable error type for session-identity failures. */

/** Stable, machine-routable failure classifications for session identity. */
export type SessionIdentityErrorCode =
  /** A request was malformed: unknown role, incomplete worktree binding, a depth without a parent, or a session creation the store rejected. */
  | 'SESSION_IDENTITY_INVALID_REQUEST'
  /** The requested parent session does not exist in the session store. */
  | 'SESSION_IDENTITY_PARENT_UNKNOWN'
  /** The agent to bind does not exist in the session store. */
  | 'SESSION_IDENTITY_AGENT_UNKNOWN'
  /** The agent already carries a different binding; an identical rebind is idempotent instead. */
  | 'SESSION_IDENTITY_ALREADY_BOUND'
  /** The storage domain refused a write, or the record on disk failed its schema. */
  | 'SESSION_IDENTITY_PERSISTENCE'

/**
 * Structured failure from binding creation, validation, or persistence, so
 * host admission and diagnostics can route on the code alone.
 */
export class SessionIdentityError extends Error {
  /** Stable machine-routable failure classification. */
  readonly code: SessionIdentityErrorCode

  /**
   * @param message - Human-readable rejection reason.
   * @param code - Stable failure classification.
   * @param options - Original storage or session-store failure, when one exists.
   */
  constructor(message: string, code: SessionIdentityErrorCode, options?: ErrorOptions) {
    super(message, options)
    this.name = 'SessionIdentityError'
    this.code = code
  }
}
