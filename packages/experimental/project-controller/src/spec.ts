/** The project-controller domain declaration: record schema and the `defineDomain` spec. */

import { z } from 'zod'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import { defineDomain, domainTable } from '@deepseek-ai/dsh-storage-domain'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { TaskRecord } from '@deepseek-ai/dsh-experimental-project-contracts'

/** Task identity schema; validation owns the brand factory. */
const taskId = z.string().min(1).transform(value => TaskId(value))

/** Plugin scope schema; validation owns the brand factory. */
const pluginId = z.string().min(1).transform(value => PluginId(value))

/** Session identity schema at the durable boundary; the id is opaque here. */
const sessionId = z.string().min(1).transform(value => brandString<SessionId>(value))

/** Worktree identity schema at the durable boundary; the id is opaque here. */
const worktreeId = z.string().min(1).transform(value => brandString<WorktreeId>(value))

/**
 * The nine task states as a zod enum, spelled out next to the schema that is
 * cast to the shared {@link TaskRecord} contract: the cast makes any drift
 * between this vocabulary and the contract union fail to compile.
 */
const taskState = z.enum(['planned', 'assigned', 'developing', 'reviewing', 'submitted', 'integrated', 'completed', 'blocked', 'failed'])

/**
 * Durable shape of one task record, projected onto the shared
 * {@link TaskRecord} contract. The cast binds the schema to the contract
 * type so shape drift fails to compile.
 */
export const taskRecordSchema = z.object({
  taskId,
  pluginId,
  title: z.string().min(1),
  state: taskState,
  blockedReason: z.string().min(1).optional(),
  nextAction: z.string().min(1).optional(),
  wakeCondition: z.string().min(1).optional(),
  assigneeSessionId: sessionId.optional(),
  worktreeId: worktreeId.optional(),
  createdAt: z.string().min(1),
  updatedAt: z.string().min(1),
}) as z.ZodType<TaskRecord>

/**
 * The project-controller domain spec: one `tasks` table keyed by
 * {@link TaskId}. Records are written through on every transition and
 * rebuilt from this table on start, so the table is the only durable
 * authority for the board.
 */
export const projectTasksDomainSpec = defineDomain({
  name: 'project_tasks',
  version: 1,
  tables: { tasks: domainTable<TaskId, TaskRecord>(taskRecordSchema) },
})
