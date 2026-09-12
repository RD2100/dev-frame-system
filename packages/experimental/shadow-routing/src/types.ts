/**
 * Vocabulary for the shadow routing Service Definition: the controller-binding
 * and delivery records, the provisioning and delivery state machines, the
 * bounded request/receipt shapes, and the router config type. Storage schemas
 * and the durable domain spec belong to the Service Provider
 * (`@deepseek-ai/dsh-experimental-shadow-router`); these interfaces are the
 * contract every family consumer compiles against.
 * @module @deepseek-ai/dsh-experimental-shadow-routing/types
 */

import type { SessionId } from '@deepseek-ai/dsh-session'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type { AcceptanceHash, ShadowMessageId, ShadowRequestId } from './ids.ts'

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

/** The receipt `project_open` returns: one workspace's controller association. */
export interface ProjectOpenResult {
  /** The workspace registry's stable project identity. */
  readonly workspaceId: WorkspaceId
  /** The reserved (then actual) controller root session. */
  readonly controllerSessionId: SessionId
  /** Association version after the open. */
  readonly bindingRevision: number
  /** Provisioning state at return; `ready` is the usable one. */
  readonly state: ShadowBindingState
  /** Canonical root the registry recorded. */
  readonly canonicalPath: string
}

/**
 * The receipt `project_send` returns. `status` is `received`: durable target
 * acceptance of the input — never a claim that the work ran or succeeded.
 */
export interface ProjectSendResult {
  /** Stable delivery identity, derived from the request id. */
  readonly messageId: ShadowMessageId
  /** Receiving project. */
  readonly workspaceId: WorkspaceId
  /** The durable receipt state; always `received` at send time. */
  readonly status: 'received'
}

/** The receipt `project_stop` returns for one project's stop. */
export interface ProjectStopResult {
  /** The stopped project. */
  readonly workspaceId: WorkspaceId
  /** `stopping` until the host confirms quiescence, then `stopped`. */
  readonly status: 'stopping' | 'stopped'
  /** Pending deliveries cancelled by this stop; they stay visible, never dropped. */
  readonly cancelledDeliveries: number
  /** Association version after the stop. */
  readonly bindingRevision: number
}

/** One bounded delivery row inside a status read. */
export interface ProjectDeliverySummary {
  /** Stable delivery identity. */
  readonly messageId: ShadowMessageId
  /** Delivery mode. */
  readonly mode: ShadowDeliveryMode
  /** Work ownership the delivery asserts. */
  readonly goalId: string
  /** Durable delivery state; `received` is never read as `completed`. */
  readonly state: ShadowDeliveryState
  /** ISO-8601 sender-intent instant. */
  readonly createdAt: string
  /** ISO-8601 target-acceptance instant, when received. */
  readonly receivedAt?: string
  /** ISO-8601 completion instant, when completed. */
  readonly completedAt?: string
  /** Why the delivery was cancelled, when cancelled. */
  readonly cancelReason?: string
}

/** One project row inside a status read. */
export interface ProjectStatusEntry {
  /** The workspace registry's stable project identity. */
  readonly workspaceId: WorkspaceId
  /** Canonical root the registry recorded. */
  readonly canonicalPath: string
  /** The current controller root session. */
  readonly controllerSessionId: SessionId
  /** Whether the controller session is live in this process right now. */
  readonly controllerLive: boolean
  /** Controller profile the binding pins. */
  readonly profileKey: string
  /** Association version. */
  readonly bindingRevision: number
  /** Provisioning/operation state. */
  readonly state: ShadowBindingState
  /** Durable failure reason, when `needs_attention` or `failed`. */
  readonly failureReason?: string
  /** The authorized open run's Goal, when one is recorded. */
  readonly activeGoalId?: string
  /** What blocks the project, computed from durable state at read time. */
  readonly blockedReason?: string
  /** First page of the project's deliveries, oldest first. */
  deliveries: ProjectDeliverySummary[]
  /** Whether more delivery rows exist beyond the bounded page. */
  readonly deliveriesTruncated: boolean
}

/** The bounded, read-only result `project_status` returns. */
export interface ProjectStatusResult {
  /** One page of authorized projects. */
  projects: ProjectStatusEntry[]
  /** Offset of the next page, when more projects exist. */
  readonly nextCursor?: number
  /** ISO-8601 instant the observation was taken. */
  readonly observedAt: string
}

/** One binding row projected for host status surfaces: association facts only. */
export interface ShadowStatusBinding {
  /** The workspace registry's stable project identity. */
  readonly workspaceId: WorkspaceId
  /** Canonical root the registry recorded. */
  readonly canonicalPath: string
  /** Association version. */
  readonly bindingRevision: number
  /** Provisioning/operation state; see the type for the order. */
  readonly state: ShadowBindingState
}

/**
 * The read-only aggregate host status surfaces (the Web Shadow card) display:
 * designation, controller liveness, authorized roots, and the binding index.
 * Unlike `projectStatus` it is host-plane (no Shadow-caller gate), synchronous,
 * and unpaginated — the deployment's own facts, not a model-facing readout.
 */
export interface ShadowRouterStatus {
  /** Controller session id the host composition declared, absent when unconfigured. */
  readonly shadowSessionId?: string
  /** Whether the designated session is currently marked as the Shadow. */
  readonly shadowLive: boolean
  /** Canonical authorized roots resolved at load, in configuration order. */
  readonly authorizedRoots: readonly string[]
  /** Every binding in stable (createdAt, workspaceId) order. */
  readonly bindings: readonly ShadowStatusBinding[]
}

/** Host-level request to open one project; the model-facing wrappers live in the provider's tools. */
export interface ProjectOpenRequest {
  /** Existing, authorized root directory. */
  readonly path: string
  /** Stable request id; replays return the prior result. */
  readonly requestId: string
}

/** Host-level request to deliver one message into an authorized project. */
export interface ProjectSendRequest {
  /** Receiving project. */
  readonly workspaceId: string
  /** Association version the sender asserts. */
  readonly bindingRevision: number
  /** Work ownership the message asserts. */
  readonly goalId: string
  /** Acceptance association the message asserts. */
  readonly acceptanceHash: string
  /** Stable request id; retries reuse it. */
  readonly requestId: string
  /** `work` schedules follow-up; `note` is quiet input. */
  readonly mode: ShadowDeliveryMode
  /** Bounded message text. */
  readonly text: string
}

/** Host-level request to stop one authorized project. */
export interface ProjectStopRequest {
  /** Project to stop. */
  readonly workspaceId: string
  /** Association version the caller asserts. */
  readonly expectedRevision: number
  /** Stable request id; replays return the prior result. */
  readonly requestId: string
}
