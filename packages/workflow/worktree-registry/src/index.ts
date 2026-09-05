/**
 * Package entry for the per-workspace git worktree registry. The named
 * `WorktreeRegistry` is the Service Definition; the default export is the
 * local git Service Provider the Loader mounts (composition rows address
 * `@deepseek-ai/dsh-worktree-registry`).
 * @module @deepseek-ai/dsh-worktree-registry
 */

import { GitWorktreeRegistry } from './git-provider.ts'
import type { WorktreeId as WorktreeIdBrand, WorktreeLockHolder as WorktreeLockHolderBrand } from './types.ts'

export { WorktreeRegistry } from './registry.ts'
export { worktreeDomainSpec, worktreeRecord } from './spec.ts'
export type { WorktreeRecord } from './spec.ts'
export { GitWorktreeRegistry, assertServiceableGitConfig } from './git-provider.ts'
export type { GitWorktreeRegistryConfig } from './git-provider.ts'
export { WorktreeGitOperationError, WORKTREE_GIT_FAILURE_REMEDIATION } from './git-failures.ts'
export type { WorktreeGitFailureKind } from './git-failures.ts'
export { WorktreeLockError } from './lock-failures.ts'
export type { WorktreeLockRefusalKind } from './lock-failures.ts'
export { parseWorktreeList, sameGitPath } from './porcelain.ts'
export type { GitWorktreeEntry } from './porcelain.ts'
export type {
  Worktree,
  WorktreeCreateRequest,
  WorktreeDanglingReason,
  WorktreeDanglingRegistration,
  WorktreeReconcileOptions,
  WorktreeReconcileReport,
  WorktreeRemoveOptions,
  WorktreeStatus,
  WorktreeUnregisteredWorktree,
} from './types.ts'

/** Identifies one registered git worktree (see `src/types.ts` for the brand rationale). */
export type WorktreeId = WorktreeIdBrand

/**
 * Brand a string as a {@link WorktreeId}.
 * @param id - Raw worktree id string.
 * @returns the same string, branded at compile time.
 */
export function WorktreeId(id: string): WorktreeId {
  return id as WorktreeId
}

/** The opaque single-writer marker a worktree can be bound to (see `src/types.ts`). */
export type WorktreeLockHolder = WorktreeLockHolderBrand

/**
 * Brand a string as a {@link WorktreeLockHolder}.
 * @param holder - Raw holder string (typically the owning agent's session id).
 * @returns the same string, branded at compile time.
 */
export function WorktreeLockHolder(holder: string): WorktreeLockHolder {
  return holder as WorktreeLockHolder
}

export default GitWorktreeRegistry
