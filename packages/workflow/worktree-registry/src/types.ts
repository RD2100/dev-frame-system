/**
 * Public type vocabulary of the worktree registry: the `WorktreeId` brand and
 * the record, request, and status shapes. Types only — the `WorktreeId`
 * factory lives in `index.ts` (this file carries no runtime code).
 * @module @deepseek-ai/dsh-worktree-registry/src/types
 */

import type { Branded } from '@deepseek-ai/dsh-brand'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'

/**
 * Identifies one registered git worktree. A generated uuid, never the path:
 * normalization, casing, and git itself rewrite worktree paths, and a
 * reference anchor must stay stable.
 */
export type WorktreeId = Branded<'WorktreeId'>

/**
 * One `create` request. The service resolves `workspaceId` through
 * `ctx.workspaceRegistry` and runs git from the owner workspace directory;
 * the target directory is created by git.
 */
export interface WorktreeCreateRequest {
  /** Owner workspace; an unknown id rejects before git runs. */
  readonly workspaceId: WorkspaceId
  /** Target checkout directory, in any spelling; resolved to an absolute path. */
  readonly path: string
  /**
   * New branch to create and check out (`git worktree add -b`). Omitted, git
   * derives the branch name from the target directory's basename.
   */
  readonly branch?: string | undefined
}

/** Options of one `remove` request. */
export interface WorktreeRemoveOptions {
  /** Pass `--force` to git, allowing removal of dirty worktrees. */
  readonly force?: boolean | undefined
}

/**
 * One registered worktree: a stable id over a canonical directory path, the
 * owning workspace, and the branch observed at create time. Consumers only
 * see this readonly projection; the durable record stays internal.
 */
export interface Worktree {
  /** Stable record id (generated uuid). */
  readonly id: WorktreeId

  /** The owning workspace record. */
  readonly workspaceId: WorkspaceId

  /**
   * Canonical directory path: the `fs.realpath` observed after
   * `git worktree add` succeeded. Never rewritten afterwards.
   */
  readonly path: string

  /** Branch name observed in the new worktree at create time. */
  readonly branch: string

  /** ISO-8601 creation instant, stamped at create and never rewritten. */
  readonly createdAt: string

  /** ISO-8601 instant of the last durable mutation (create counts as one). */
  readonly updatedAt: string
}

/**
 * One `status` observation. The optional fields describe the live worktree;
 * they are absent when the recorded directory no longer exists, which is a
 * reported observation rather than a failure. A present directory whose git
 * commands fail rejects instead of degrading the status.
 */
export interface WorktreeStatus {
  /** Whether the recorded directory still exists. */
  readonly directoryExists: boolean

  /** Branch name observed in the worktree now; absent when the directory is missing. */
  readonly branch?: string | undefined

  /**
   * Whether `git status --porcelain=v1` printed nothing; absent when the
   * directory is missing.
   */
  readonly clean?: boolean | undefined
}
