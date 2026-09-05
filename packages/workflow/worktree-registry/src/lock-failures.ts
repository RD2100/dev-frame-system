/**
 * Failure type for registry-level lock refusals. A lock refusal is a product
 * decision, not a git observation — git never saw the request — so it carries
 * its own closed refusal-kind union instead of flowing through the git stderr
 * classifier.
 * @module @deepseek-ai/dsh-worktree-registry/src/lock-failures
 */

/** Why the registry refused a bind, unbind, or remove over a worktree lock. */
export type WorktreeLockRefusalKind =
  /** The worktree is bound, and the caller is not its holder. */
  | 'already-locked'
  /** An unbind was requested for a worktree that is not bound. */
  | 'not-locked'
  /** An unbind was requested by a holder other than the worktree's holder. */
  | 'holder-mismatch'

/**
 * A lock refusal the registry recognized, carrying its kind. The message names
 * the holder facts and the way out (unbind for the holder, or reconcile's
 * `pruneRows` when the row itself is stale).
 */
export class WorktreeLockError extends Error {
  /** The refusal kind. */
  readonly kind: WorktreeLockRefusalKind

  /**
   * @param message - The full refusal message: the worktree, the holder
   *   facts, and what unblocks the caller.
   * @param kind - The refusal kind.
   */
  constructor(message: string, kind: WorktreeLockRefusalKind) {
    super(message)
    this.name = 'WorktreeLockError'
    this.kind = kind
  }
}
