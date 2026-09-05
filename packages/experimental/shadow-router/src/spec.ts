/**
 * The shadow-router domain declaration: the controller-binding, delivery, and
 * request-record schemas plus the `defineDomain` spec. The three tables are
 * the only durable authority for Shadow routing state; every mutation is
 * written through and rebuilt from them on start.
 * @module @deepseek-ai/dsh-experimental-shadow-router/spec
 */

import { z } from 'zod'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { defineDomain, domainTable } from '@deepseek-ai/dsh-storage-domain'
import { AcceptanceHash, ShadowMessageId, ShadowRequestId } from './ids.ts'

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
 * Provisioning and operation states of one controller binding, in lifecycle
 * order. `reserving → provisioning → ready` is the creation path; a creation
 * failure rolls the row to `failed` (the reserved id was never entered, and a
 * later open may re-provision around a fresh reservation). `stopping` closes
 * receiving until the host confirms `stopped`. `needs_attention` keeps a
 * project whose reserved identity stopped matching its durable row.
 */
export type ShadowBindingState =
  | 'reserving'
  | 'provisioning'
  | 'ready'
  | 'stopping'
  | 'stopped'
  | 'needs_attention'
  | 'failed'

/** The two delivery modes. Both carry the same Goal ownership check. */
export type ShadowDeliveryMode = 'work' | 'note'

/**
 * Durable states of one cross-root delivery. `queued` is the persisted sender
 * intent, `received` the target-accepted input, and `completed` the finished
 * work — three distinct durable facts; a receipt is never read as completion.
 * `cancelled` keeps a stopped project's pending deliveries visible instead of
 * dropping them.
 */
export type ShadowDeliveryState = 'queued' | 'received' | 'completed' | 'cancelled'

/**
 * Durable shape of one controller binding: the only new project index Shadow
 * keeps. It stores association facts only — never project paths beyond the
 * canonical root the workspace registry already owns, never task rows, never
 * session transcripts, and never a completion verdict.
 */
export interface ShadowBindingRecord {
  /** The workspace registry's stable project identity. */
  readonly workspaceId: WorkspaceId
  /** Canonical root the registry recorded; aliases never reach this field. */
  readonly canonicalPath: string
  /** Reserved (then actual) controller root session identity. */
  readonly controllerSessionId: SessionId
  /** Controller profile the host deployment served at creation. */
  readonly profileKey: string
  /** Monotonic association version; bumps on every durable content change. */
  readonly bindingRevision: number
  /** The open requestId that created (or last re-provisioned) the binding. */
  readonly requestId: string
  /** Current provisioning/operation state; see the type for the order. */
  readonly state: ShadowBindingState
  /** Why the binding is `needs_attention` or `failed`; required in exactly those states. */
  readonly failureReason?: string
  /** The authorized open run's Goal, when the host has recorded one. */
  readonly activeGoalId?: string
  /** The authorized open run's acceptance association, alongside `activeGoalId`. */
  readonly activeAcceptanceHash?: string
  /** ISO-8601 creation instant, stamped once and never rewritten. */
  readonly createdAt: string
  /** ISO-8601 instant of the last durable mutation, including create. */
  readonly updatedAt: string
}

/**
 * Durable shape of one cross-root delivery. Identity and work ownership are
 * fixed before first persistence and never rewritten by retries.
 */
export interface ShadowDeliveryRecord {
  /** Stable delivery identity, derived from the request id. */
  readonly messageId: ShadowMessageId
  /** The sending request id; retries reuse it. */
  readonly requestId: ShadowRequestId
  /** The Shadow session that issued the delivery. */
  readonly sourceSessionId: SessionId
  /** Receiving project. */
  readonly workspaceId: WorkspaceId
  /** Binding revision the sender asserted. */
  readonly bindingRevision: number
  /** The work ownership the message asserts. */
  readonly goalId: string
  /** The acceptance association the message asserts. */
  readonly acceptanceHash: AcceptanceHash
  /** `work` schedules follow-up; `note` is quiet input. */
  readonly mode: ShadowDeliveryMode
  /** Bounded message text. */
  readonly text: string
  /** Current durable state; see the type for the order. */
  readonly state: ShadowDeliveryState
  /** Why the delivery was cancelled; required in exactly that state. */
  readonly cancelReason?: string
  /** ISO-8601 creation instant (sender intent persisted). */
  readonly createdAt: string
  /** ISO-8601 instant of the last durable state move. */
  readonly updatedAt: string
  /** ISO-8601 instant the target accepted the input; present from `received`. */
  readonly receivedAt?: string
  /** ISO-8601 instant the work completed; present only in `completed`. */
  readonly completedAt?: string
}

/** The kind of routing request a stored record replays. */
export type ShadowRequestKind = 'open' | 'send' | 'stop'

/**
 * Durable shape of one request result. Same requestId plus identical
 * normalized input replays the stored result; different input fails with
 * `SHADOW_REQUEST_CONFLICT` instead of overwriting the row.
 */
export interface ShadowRequestRecord {
  /** The stable caller request id. */
  readonly requestId: ShadowRequestId
  /** Which routing operation minted the result. */
  readonly kind: ShadowRequestKind
  /** SHA-256 of the operation's normalized input. */
  readonly inputHash: string
  /** The previously returned serializable result. */
  readonly result: unknown
  /** ISO-8601 creation instant. */
  readonly createdAt: string
}

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
