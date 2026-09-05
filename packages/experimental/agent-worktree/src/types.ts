/**
 * Public type vocabulary of the per-agent worktree seam: the request and view
 * shapes the service hands across the boundary. Types only — the Service
 * Definition lives in `service.ts` (this file carries no runtime code).
 * @module @deepseek-ai/dsh-experimental-agent-worktree/types
 */

import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type { WorktreeId, WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'

/**
 * One `create` request from an agent session: the session's own workspace
 * (resolved by the consumer, never model-supplied) and the target checkout
 * directory. The created worktree is bound to the requesting holder.
 */
export interface AgentWorktreeCreateRequest {
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

/**
 * One worktree created (or held) by an agent session: the registry's readonly
 * record projection plus the binding facts. `lockedBy` is the opaque
 * single-writer marker — for this seam, the owning session's durable id.
 */
export interface AgentWorktreeView {
  /** Stable registry record id (generated uuid). */
  readonly id: WorktreeId

  /** The owning workspace record. */
  readonly workspaceId: WorkspaceId

  /** Canonical directory path observed after `git worktree add` succeeded. */
  readonly path: string

  /** Branch observed in the new worktree at create time. */
  readonly branch: string

  /** ISO-8601 creation instant, stamped at create and never rewritten. */
  readonly createdAt: string

  /** ISO-8601 instant of the last durable mutation (create counts as one). */
  readonly updatedAt: string

  /** The single-writer marker the worktree is bound to; absent when unbound. */
  readonly lockedBy?: WorktreeLockHolder

  /** ISO-8601 instant the binding was acquired; absent when unbound. */
  readonly lockedAt?: string
}

/**
 * One `status` observation for an agent session: the live worktree facts plus
 * the binding stated from the caller's perspective. The optional live fields
 * are absent when the recorded directory no longer exists — an observation,
 * not a failure.
 */
export interface AgentWorktreeStatus {
  /** The observed worktree's registry id. */
  readonly id: WorktreeId

  /** Whether the recorded directory still exists. */
  readonly directoryExists: boolean

  /** Branch observed in the worktree now; absent when the directory is missing. */
  readonly branch?: string | undefined

  /** Whether the tree is clean; absent when the directory is missing. */
  readonly clean?: boolean | undefined

  /** The single-writer marker holding the binding; absent when unbound. */
  readonly lockedBy?: WorktreeLockHolder

  /** ISO-8601 instant the binding was acquired; absent when unbound. */
  readonly lockedAt?: string
}
