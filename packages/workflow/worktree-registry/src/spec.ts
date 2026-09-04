/**
 * The worktree registry domain declaration: record schema and the
 * `defineDomain` spec the provider opens. The zod schema validates the shipped
 * format at the durability boundary. A worktree record never joins the
 * workspace domain — see the package README and the proposed Agent Note.
 * @module @deepseek-ai/dsh-worktree-registry/src/spec
 */

import { z } from 'zod'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { defineDomain, domainTable } from '@deepseek-ai/dsh-storage-domain'
import type { WorktreeId } from './types.ts'

/** Workspace id schema at the durable boundary; the anchor is opaque here. */
const workspaceId = z.string().transform(value => brandString<WorkspaceId>(value))

/**
 * Durable shape of one worktree record. `path` is the canonical directory
 * observed after `git worktree add` succeeded; `branch` is the HEAD branch
 * read back from the new worktree at create time; timestamps are ISO-8601
 * strings.
 */
export const worktreeRecord = z.object({
  workspaceId,
  path: z.string(),
  branch: z.string(),
  createdAt: z.string(),
  updatedAt: z.string(),
})

/** One stored worktree record, inferred from {@link worktreeRecord}. */
export type WorktreeRecord = z.infer<typeof worktreeRecord>

/**
 * The worktree registry domain spec: one `worktrees` table keyed by
 * {@link WorktreeId}. No global state — `list` order is derived from record
 * fields, so the registry stays a single-table reader and writer.
 */
export const worktreeDomainSpec = defineDomain({
  name: 'worktree_registry',
  version: 1,
  tables: { worktrees: domainTable<WorktreeId, WorktreeRecord>(worktreeRecord) },
})
