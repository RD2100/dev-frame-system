/**
 * Failure classification for git operations the provider runs. git's stderr
 * is the evidence; the classifier maps the observed refusal messages to a
 * closed set of failure kinds, each with a remediation the caller (model or
 * host) can act on. Unclassified git failures stay generic errors with the
 * stderr attached.
 * @module @deepseek-ai/dsh-worktree-registry/src/git-failures
 */

/** The classified git refusal kinds the provider can produce. */
export type WorktreeGitFailureKind =
  /** The target directory already exists and is not empty. */
  | 'path-exists'
  /** The requested new branch already exists. */
  | 'branch-conflict'
  /** The worktree holds modified or untracked files and `--force` was not given. */
  | 'dirty-tree'
  /** The path exceeds the platform's path-length limit for this git configuration. */
  | 'path-length'

/** The remediation each failure kind suggests, phrased for the caller. */
export const WORKTREE_GIT_FAILURE_REMEDIATION: Readonly<
  Record<WorktreeGitFailureKind, string>
> = Object.freeze({
  'path-exists':
    'The target directory already exists and is not empty; '
    + 'choose a different target directory, or reuse or clear the existing one first.',
  'branch-conflict':
    'A branch with this name already exists; '
    + 'choose a different branch name, or reuse the existing branch without -b.',
  'dirty-tree':
    'The worktree holds modified or untracked files; '
    + 'repeat the removal with force: true to discard them, or clean the worktree first.',
  'path-length':
    'The target path exceeds the path-length limit of this git configuration; '
    + 'choose a shorter target path, or enable long paths for the repository (git config core.longpaths true). '
    + 'git may have left empty leading directories behind, which the registry never records.',
})

/** Patterns from real git refusals, most specific first: the branch-conflict
 * message also contains "already exists", so it must be tested before the
 * bare path refusal. */
const PATTERNS: ReadonlyArray<{ kind: WorktreeGitFailureKind; pattern: RegExp }> = Object.freeze([
  { kind: 'branch-conflict', pattern: /a branch named .+ already exists/i },
  { kind: 'path-exists', pattern: /already exists/ },
  { kind: 'dirty-tree', pattern: /contains modified or untracked files/i },
  { kind: 'path-length', pattern: /filename too long|enametoolong|\$GIT_DIR'? too big/i },
])

/** A git refusal the classifier recognized, carrying its kind and remediation. */
export class WorktreeGitOperationError extends Error {
  /** The classified refusal kind. */
  readonly kind: WorktreeGitFailureKind

  /**
   * @param message - The full failure message: the git invocation facts, git's
   *   stderr, and the remediation for the kind.
   * @param kind - The classified refusal kind.
   */
  constructor(message: string, kind: WorktreeGitFailureKind) {
    super(message)
    this.name = 'WorktreeGitOperationError'
    this.kind = kind
  }
}

/**
 * Classify one git refusal against its stderr.
 * @param stderr - The collected git stderr for the failed invocation.
 * @returns the refusal kind, or `undefined` when the stderr matches no known
 *   refusal pattern.
 */
export function classifyGitFailure(stderr: string): WorktreeGitFailureKind | undefined {
  for (const { kind, pattern } of PATTERNS) {
    if (pattern.test(stderr)) return kind
  }
  return undefined
}
