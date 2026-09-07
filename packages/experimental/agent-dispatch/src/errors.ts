/** The stable error type of the agent-dispatch package. */

/** Stable machine-routable failure classifications for the dispatch entry. */
export type AgentDispatchErrorCode =
  /** The request carries no worktree or owner workspace, or the requested worktree has no registry row. */
  | 'DISPATCH_WORKTREE_UNREGISTERED'
  /** The registry row disagrees with the request or with disk: missing directory, path/branch mismatch, or a foreign single-writer binding. */
  | 'DISPATCH_WORKTREE_MISMATCH'
  /** The parent task already has a dispatched child; retry by passing the returned agent id back as `sessionId`. */
  | 'DISPATCH_IDENTITY_EXISTS'
  /** The parent session carries no durable role binding. */
  | 'DISPATCH_PARENT_UNBOUND'
  /** The daily dispatch discipline refused this parent/request pair. */
  | 'DISPATCH_HIERARCHY_DENIED'

/**
 * Structured failure thrown when the dispatch entry refuses a creation before
 * the hierarchy engine is reached. The engine's own denials (role policy,
 * scope approval, depth budget, dedupe conflicts) surface as the hierarchy
 * service's errors, never this one.
 */
export class AgentDispatchError extends Error {
  /** Stable machine-routable failure classification. */
  readonly code: AgentDispatchErrorCode

  /**
   * @param message - Human-readable failure detail.
   * @param code - Stable dispatch-entry failure classification.
   * @param options - Original backend failure, when one exists.
   */
  constructor(message: string, code: AgentDispatchErrorCode, options?: ErrorOptions) {
    super(message, options)
    this.name = 'AgentDispatchError'
    this.code = code
  }
}
