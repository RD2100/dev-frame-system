/** The stable error type of the agent-hierarchy package. */

/** Stable machine-routable failure classifications for the hierarchy policy. */
export type AgentHierarchyErrorCode =
  /** The host configuration failed its zod validation at load. */
  | 'HIERARCHY_INVALID_CONFIG'
  /** The native tools service was absent when the policy tried to install. */
  | 'HIERARCHY_TOOLS_UNAVAILABLE'
  /** The agent binding registry was absent when the policy tried to read roles. */
  | 'HIERARCHY_BINDINGS_UNAVAILABLE'
  /** A restored binding record carried a role outside the closed union. */
  | 'HIERARCHY_ROLE_UNKNOWN'

/**
 * Structured failure thrown when the hierarchy policy fails at load —
 * configuration validation, a missing required service, or an unreadable
 * role. Guard denials are plain reason strings, never this error.
 */
export class AgentHierarchyError extends Error {
  /** Stable machine-routable failure classification. */
  readonly code: AgentHierarchyErrorCode

  /**
   * @param message - Human-readable failure detail.
   * @param code - Stable hierarchy-policy failure classification.
   * @param options - Original backend failure, when one exists.
   */
  constructor(message: string, code: AgentHierarchyErrorCode, options?: ErrorOptions) {
    super(message, options)
    this.name = 'AgentHierarchyError'
    this.code = code
  }
}
