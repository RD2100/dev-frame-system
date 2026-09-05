/**
 * Parsing for `git worktree list --porcelain -z` output and the path
 * comparison the reconcile pass needs. git prints worktree paths with forward
 * slashes while the registry stores canonical Windows paths, so every
 * comparison goes through {@link sameGitPath}.
 * @module @deepseek-ai/dsh-worktree-registry/src/porcelain
 */

/** One worktree entry from `git worktree list`. */
export interface GitWorktreeEntry {
  /** The path git reports, in git's own spelling (forward slashes). */
  readonly path: string

  /** The checked-out branch without its `refs/heads/` prefix; absent when the worktree is on a detached HEAD. */
  readonly branch?: string
}

const BRANCH_PREFIX = 'branch refs/heads/'

/**
 * Parse the NUL-separated porcelain output. With `-z`, fields inside a record
 * are separated by one NUL and records by two; an output truncated mid-record
 * therefore yields a malformed trailing record instead of a silent half-entry,
 * and callers are expected to reject truncated output before parsing.
 * @param output - The collected stdout of `git worktree list --porcelain -z`.
 * @returns the parsed entries in git's reported order.
 */
export function parseWorktreeList(output: string): GitWorktreeEntry[] {
  const entries: GitWorktreeEntry[] = []
  for (const record of output.split('\0\0')) {
    const fields = record.split('\0').filter(field => field.trim().length > 0)
    const first = fields[0]
    if (first === undefined || !first.startsWith('worktree ')) continue
    const entry: {
      path: string
      branch?: string
    } = { path: first.slice('worktree '.length) }
    for (const field of fields.slice(1)) {
      if (field.startsWith(BRANCH_PREFIX)) {
        entry.branch = field.slice(BRANCH_PREFIX.length)
      }
    }
    entries.push(entry)
  }
  return entries
}

/**
 * Compare a git-reported worktree path with a registry-recorded path. git
 * prints forward slashes; Windows paths are case-insensitive and may reach the
 * registry through either casing, so separators are normalized and comparison
 * folds case on Windows only.
 * @param gitPath - A path as git reported it.
 * @param recordedPath - A path as the registry recorded it.
 * @returns whether both spellings name the same worktree directory.
 */
export function sameGitPath(gitPath: string, recordedPath: string): boolean {
  const left = gitPath.replace(/\\/g, '/')
  const right = recordedPath.replace(/\\/g, '/')
  /* v8 ignore next -- native Windows coverage exercises this platform dispatch; POSIX lanes compare case-sensitively */
  return process.platform === 'win32' ? left.toLowerCase() === right.toLowerCase() : left === right
}
