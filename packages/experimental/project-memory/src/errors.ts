/** The stable error type for project-memory failures. */

/**
 * Stable, machine-routable failure classifications for the bounded Obsidian
 * memory service, matching the failure table of
 * `docs/detailDesign-part3.md` (memory_unavailable, append disabled, invalid
 * or secret-bearing content, write failure) plus the path/id boundaries it
 * requires.
 */
export type ProjectMemoryErrorCode =
  /** The Vault root is not configured, missing, or not an accessible directory. */
  | 'MEMORY_UNAVAILABLE'
  /** The requested namespace is not allowed for this service instance (user memory not enabled). */
  | 'MEMORY_SCOPE_FORBIDDEN'
  /** Append was requested while the user has not enabled writes; memory stays read-only. */
  | 'MEMORY_APPEND_DISABLED'
  /** A request field failed its structural check (empty query, out-of-range limit, missing human confirmation). */
  | 'MEMORY_INVALID_REQUEST'
  /** A note field failed its structural check: empty body, empty source reference, or self-supersession. */
  | 'MEMORY_INVALID_NOTE'
  /** The note body exceeds the configured per-note byte limit. */
  | 'MEMORY_NOTE_TOO_LARGE'
  /** The search query exceeds the configured query byte limit. */
  | 'MEMORY_QUERY_TOO_LARGE'
  /** Content screening rejected the body; the reason names the rule and never echoes the suspected secret. */
  | 'MEMORY_CONTENT_REJECTED'
  /** A note id is not a host-issued id (malformed shape, traversal probe). */
  | 'MEMORY_INVALID_NOTE_ID'
  /** A workspace id is not a safe single path segment (traversal, reserved Windows name). */
  | 'MEMORY_INVALID_WORKSPACE_ID'
  /** A Vault path holds an unexpected symlink/reparse component or resolves outside the Vault root. */
  | 'MEMORY_PATH_REJECTED'
  /** Exclusive create or write failed on the real filesystem after the bounded retry policy, or the provider cannot create exclusively. */
  | 'MEMORY_WRITE_FAILED'
  /** The receipt store seam failed before `created` could be returned; the file stays unconfirmed. */
  | 'MEMORY_RECEIPT_FAILED'

/**
 * Structured failure thrown by the project-memory service, so host admission
 * and diagnostics can route on the code alone.
 */
export class ProjectMemoryError extends Error {
  /** Stable machine-routable failure classification. */
  readonly code: ProjectMemoryErrorCode

  /**
   * @param message - Human-readable rejection reason; carries no note content.
   * @param code - Stable failure classification.
   * @param options - Original filesystem or seam failure, when one exists.
   */
  constructor(message: string, code: ProjectMemoryErrorCode, options?: ErrorOptions) {
    super(message, options)
    this.name = 'ProjectMemoryError'
    this.code = code
  }
}
