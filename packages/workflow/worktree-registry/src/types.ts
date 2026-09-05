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
 * The opaque single-writer marker a worktree is bound to. The registry never
 * interprets the value — callers mint it from whatever identity owns the
 * write target (typically an agent session id) — and equality is the entire
 * contract: the same value may re-bind or unbind, any other value is refused.
 */
export type WorktreeLockHolder = Branded<'WorktreeLockHolder'>

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

  /**
   * The single writer the worktree is bound to, present exactly together with
   * {@link lockedAt}. A bound worktree refuses removal until its holder
   * unbinds.
   */
  readonly lockedBy?: WorktreeLockHolder

  /** ISO-8601 instant the current binding was acquired; absent when unlocked. */
  readonly lockedAt?: string
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

/** Why one registry row no longer reflects git or disk reality. */
export type WorktreeDanglingReason =
  /** The recorded directory is gone from disk; git may still list it as prunable. */
  | 'directory-missing'
  /** The directory exists but `git worktree list` no longer tracks that path. */
  | 'git-unknown'

/** One registry row whose worktree is stale. */
export interface WorktreeDanglingRegistration {
  /** The stale registration's id. */
  readonly id: WorktreeId

  /** The recorded canonical path. */
  readonly path: string

  /** Why the row is stale. */
  readonly reason: WorktreeDanglingReason
}

/** One git-tracked linked worktree that no registry row holds. */
export interface WorktreeUnregisteredWorktree {
  /** The path git reports (forward slashes); adopt canonicalizes it. */
  readonly path: string

  /** Branch git reports; absent when the worktree is on a detached HEAD. */
  readonly branch?: string | undefined
}

/**
 * Options of one `reconcile` request. Both actions default to off: a bare
 * call only observes. `pruneRows` never deletes directories or files — it
 * drops stale registry rows only.
 */
export interface WorktreeReconcileOptions {
  /**
   * Drop the dangling registry rows. Dropping a `directory-missing` row also
   * runs `git worktree prune` once, so git stops listing the dead admin entry.
   */
  readonly pruneRows?: boolean

  /** Register each unregistered worktree under the reconciled workspace. */
  readonly adoptUnregistered?: boolean
}

/**
 * One `reconcile` result: the differences observed at the start, and what the
 * actions actually changed. Empty `dangling`/`unregistered` arrays mean the
 * registry and git agree. Detection is point-in-time; applying actions to a
 * moving tree can race, in which case a later reconcile reports the remainder.
 */
export interface WorktreeReconcileReport {
  /** Stale rows detected for this workspace, before any action ran. */
  readonly dangling: readonly WorktreeDanglingRegistration[]

  /** Unregistered git worktrees detected, before any action ran. */
  readonly unregistered: readonly WorktreeUnregisteredWorktree[]

  /** Rows the `pruneRows` action dropped. */
  readonly removedRows: readonly WorktreeId[]

  /** Canonical paths the `adoptUnregistered` action registered. */
  readonly adoptedPaths: readonly string[]
}
