/**
 * The shadow-bridge domain declaration: the forwarded-delivery marker schema
 * plus the `defineDomain` spec. The single `forwarded` table is the only
 * durable authority for what this package has already turned into a
 * controller follow-up; it is rebuilt into the forwarder's in-memory set at
 * start, so a restart re-forwards nothing.
 * @module @deepseek-ai/dsh-experimental-shadow-bridge/spec
 */

import { z } from 'zod'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { ShadowMessageId } from '@deepseek-ai/dsh-experimental-shadow-routing'
import { defineDomain, domainTable } from '@deepseek-ai/dsh-storage-domain'

/**
 * Durable shape of one forwarded-delivery marker: proof that the delivery
 * named by {@link ShadowBridgeForwardedRecord.messageId} already became a
 * controller follow-up. The row is written after the follow-up enters the
 * controller's inbox and never rewritten or deleted by the bridge.
 */
export interface ShadowBridgeForwardedRecord {
  /** The forwarded router delivery identity; also this row's table key. */
  readonly messageId: ShadowMessageId
  /** The project the delivery belongs to, copied from the delivery row. */
  readonly workspaceId: WorkspaceId
  /** The controller session the follow-up was sent to. */
  readonly controllerSessionId: SessionId
  /** ISO-8601 instant the follow-up was queued. */
  readonly forwardedAt: string
}

/** Message identity schema at the durable boundary; the routing vocabulary owns the brand factory. */
const messageId = z.string().min(1).transform(value => ShadowMessageId(value))

/** Session identity schema at the durable boundary; the id is opaque here. */
const sessionId = z.string().min(1).transform(value => brandString<SessionId>(value))

/** Workspace identity schema at the durable boundary; the id is opaque here. */
const workspaceId = z.string().min(1).transform(value => brandString<WorkspaceId>(value))

/**
 * Durable shape of one forwarded-delivery marker, projected onto the
 * {@link ShadowBridgeForwardedRecord} interface. The cast binds the schema to
 * the interface so shape drift fails to compile.
 */
export const shadowBridgeForwardedRecordSchema = z.object({
  messageId,
  workspaceId,
  controllerSessionId: sessionId,
  forwardedAt: z.string().min(1),
}) as z.ZodType<ShadowBridgeForwardedRecord>

/**
 * The shadow-bridge domain spec: one `forwarded` table keyed by the router's
 * {@link ShadowMessageId}. Rows are written through on every forward and
 * rebuilt at start, so the domain is the only durable bridge state.
 */
export const shadowBridgeDomainSpec = defineDomain({
  name: 'shadow_bridge',
  version: 1,
  tables: {
    forwarded: domainTable<ShadowMessageId, ShadowBridgeForwardedRecord>(shadowBridgeForwardedRecordSchema),
  },
})
