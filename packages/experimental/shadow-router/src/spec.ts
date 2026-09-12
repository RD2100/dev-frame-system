/**
 * The shadow-router domain declaration: the controller-binding, delivery, and
 * request-record schemas plus the `defineDomain` spec. The record interfaces
 * and branded ids live in `@deepseek-ai/dsh-experimental-shadow-routing`; the
 * schemas here bind them to the `shadow_router` domain. The three tables are
 * the only durable authority for Shadow routing state; every mutation is
 * written through and rebuilt from them on start.
 * @module @deepseek-ai/dsh-experimental-shadow-router/spec
 */

import { z } from 'zod'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { defineDomain, domainTable } from '@deepseek-ai/dsh-storage-domain'
import { AcceptanceHash, ShadowMessageId, ShadowRequestId } from '@deepseek-ai/dsh-experimental-shadow-routing'
import type {
  ShadowBindingRecord,
  ShadowDeliveryRecord,
  ShadowRequestRecord,
} from '@deepseek-ai/dsh-experimental-shadow-routing'

/** Session identity schema at the durable boundary; the id is opaque here. */
const sessionId = z.string().min(1).transform(value => brandString<SessionId>(value))

/** Workspace identity schema at the durable boundary; the id is opaque here. */
const workspaceId = z.string().min(1).transform(value => brandString<WorkspaceId>(value))

/** Request id schema; validation owns the brand factory. */
const requestId = z.string().min(1).transform(value => ShadowRequestId(value))

/** Message id schema; validation owns the brand factory. */
const messageId = z.string().min(1).transform(value => ShadowMessageId(value))

/** Acceptance hash schema; validation owns the brand factory. */
const acceptanceHash = z.string().min(1).transform(value => AcceptanceHash(value))

/**
 * Durable shape of one controller binding, projected onto the
 * {@link ShadowBindingRecord} interface. The cast binds the schema to the
 * interface so shape drift fails to compile.
 */
export const shadowBindingRecordSchema = z.object({
  workspaceId,
  canonicalPath: z.string().min(1),
  controllerSessionId: sessionId,
  profileKey: z.string().min(1),
  bindingRevision: z.number().int().min(1),
  requestId: z.string().min(1),
  state: z.enum(['reserving', 'provisioning', 'ready', 'stopping', 'stopped', 'needs_attention', 'failed']),
  failureReason: z.string().min(1).optional(),
  activeGoalId: z.string().min(1).optional(),
  activeAcceptanceHash: z.string().min(1).optional(),
  createdAt: z.string().min(1),
  updatedAt: z.string().min(1),
}) as z.ZodType<ShadowBindingRecord>

/**
 * Durable shape of one cross-root delivery, projected onto the
 * {@link ShadowDeliveryRecord} interface.
 */
export const shadowDeliveryRecordSchema = z.object({
  messageId,
  requestId,
  sourceSessionId: sessionId,
  workspaceId,
  bindingRevision: z.number().int().min(1),
  goalId: z.string().min(1),
  acceptanceHash,
  mode: z.enum(['work', 'note']),
  text: z.string().min(1),
  state: z.enum(['queued', 'received', 'completed', 'cancelled']),
  cancelReason: z.string().min(1).optional(),
  createdAt: z.string().min(1),
  updatedAt: z.string().min(1),
  receivedAt: z.string().min(1).optional(),
  completedAt: z.string().min(1).optional(),
}) as z.ZodType<ShadowDeliveryRecord>

/**
 * Durable shape of one request result, projected onto the
 * {@link ShadowRequestRecord} interface.
 */
export const shadowRequestRecordSchema = z.object({
  requestId,
  kind: z.enum(['open', 'send', 'stop']),
  inputHash: z.string().min(1),
  result: z.unknown(),
  createdAt: z.string().min(1),
}) as z.ZodType<ShadowRequestRecord>

/**
 * The shadow-router domain spec: one `bindings` table keyed by the workspace
 * registry's {@link WorkspaceId}, one `deliveries` table keyed by
 * {@link ShadowMessageId}, and one `requests` table keyed by the raw request
 * id. Records are written through on every mutation and rebuilt from these
 * tables on start, so the domain is the only durable authority.
 */
export const shadowRouterDomainSpec = defineDomain({
  name: 'shadow_router',
  version: 1,
  tables: {
    bindings: domainTable<WorkspaceId, ShadowBindingRecord>(shadowBindingRecordSchema),
    deliveries: domainTable<ShadowMessageId, ShadowDeliveryRecord>(shadowDeliveryRecordSchema),
    requests: domainTable<string, ShadowRequestRecord>(shadowRequestRecordSchema),
  },
})
