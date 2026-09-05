/** The session-identity domain declaration: record schema and the `defineDomain` spec. */

import { z } from 'zod'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import { defineDomain, domainTable } from '@deepseek-ai/dsh-storage-domain'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { AgentBindingRecord } from '@deepseek-ai/dsh-experimental-project-contracts'

/** Session identity schema at the durable boundary; the id is opaque here. */
const sessionId = z.string().min(1).transform(value => brandString<SessionId>(value))

/** Plugin scope schema; validation owns the brand factory. */
const pluginId = z.string().min(1).transform(value => PluginId(value))

/** Task identity schema; validation owns the brand factory. */
const taskId = z.string().min(1).transform(value => TaskId(value))

/** Worktree identity schema; the id is opaque here. */
const worktreeId = z.string().min(1).transform(value => brandString<WorktreeId>(value))

/**
 * Durable shape of one agent binding record, projected onto the shared
 * {@link AgentBindingRecord} contract. The cast binds the schema to the
 * contract type so shape drift fails to compile.
 */
export const agentBindingRecordSchema = z.object({
  agentId: sessionId,
  sessionId: sessionId,
  parentSessionId: sessionId.optional(),
  role: z.enum(['controller', 'lead', 'worker']),
  pluginId: pluginId.optional(),
  taskId: taskId.optional(),
  worktreeId: worktreeId.optional(),
  worktreePath: z.string().min(1).optional(),
  branch: z.string().min(1).optional(),
  createdAt: z.string().min(1),
}) as z.ZodType<AgentBindingRecord>

/**
 * The session-identity domain spec: one `bindings` table keyed by the live
 * Agent registry identity. Records are written through to the backing store
 * on every mutation and rebuilt from this table on start, so the table is the
 * only durable authority.
 */
export const sessionIdentityDomainSpec = defineDomain({
  name: 'session_identity',
  version: 1,
  tables: { bindings: domainTable<SessionId, AgentBindingRecord>(agentBindingRecordSchema) },
})
