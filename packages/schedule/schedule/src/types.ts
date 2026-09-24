/**
 * Durable and model-facing Schedule value types.
 * @module @deepseek-ai/dsh-schedule
 */

import type { Branded } from '@deepseek-ai/dsh-brand'
import type {} from '@deepseek-ai/dsh-session/types'
import type {} from '@deepseek-ai/dsh-llm'
import type { SessionId } from '@deepseek-ai/dsh-session'

/** Stable reminder identity that is unique and never reused within one session. */
export type ScheduleId = Branded<'ScheduleId'>

/** Browser request addressing one Schedule record in one Session. */
export interface ScheduleSessionRequest {
  readonly sessionId: SessionId
  readonly id: ScheduleId
}

/** Result of pausing one Schedule record. */
export interface SchedulePauseRemoteValue {
  readonly id: ScheduleId
  readonly paused: true
}

/** Result of resuming one Schedule record. */
export interface ScheduleResumeRemoteValue {
  readonly id: ScheduleId
  readonly resumed: true
}

/** Result of deleting one Schedule record. */
export interface ScheduleDeleteRemoteValue {
  readonly id: ScheduleId
  readonly deleted: true
}

/** Result of queuing one immediate Schedule delivery. */
export interface ScheduleRunRemoteValue {
  readonly id: ScheduleId
  readonly started: true
}

/** Stable human-selected key used to make a create request idempotent. */
export type ScheduleDedupeKey = Branded<'ScheduleDedupeKey'>

/** Model-visible correlation carried by an automatically queued reminder. */
export interface ScheduleMessageSource {
  readonly kind: 'schedule'
  readonly scheduleIds: readonly ScheduleId[]
}

declare module '@deepseek-ai/dsh-llm' {
  interface MessageSourceMap { schedule: ScheduleMessageSource }
}

/** Final result recorded for one queued reminder turn. */
export type ScheduleExecutionOutcome = 'success' | 'failure' | 'cancelled'

/** One durable execution result entry. */
export interface ScheduleResultHistoryEntry {
  readonly outcome: ScheduleExecutionOutcome
  readonly error?: string
}

/** One durable execution or lifecycle entry retained in the session log. */
export interface ScheduleHistoryEntry {
  /** Session-local schedule identity. */
  readonly id: ScheduleId
  /** Durable transition that produced this entry. */
  readonly operation: 'create' | 'pause' | 'resume' | 'dispatch' | 'delete' | 'result'
  /** Result metadata for an execution outcome entry. */
  readonly result?: ScheduleResultHistoryEntry
  /** Unix epoch milliseconds rendered as an RFC 3339 UTC instant. */
  readonly occurredAt: string
}

/** One reusable task-center suggestion. Templates are immutable metadata. */
export interface ScheduleTemplate {
  /** Stable template identity used by clients and model prompts. */
  readonly id: string
  /** Human-facing short name. */
  readonly label: string
  /** Description of the rule the template suggests. */
  readonly description: string
  /** Default rule selector supplied by the template. */
  readonly rule: { readonly afterSeconds: number } | { readonly everySeconds: number }
}

/** Built-in task-center suggestions shared by host tools and browser clients. */
export const SCHEDULE_TEMPLATES: readonly ScheduleTemplate[] = Object.freeze([
  Object.freeze({
    id: 'follow-up',
    label: 'Follow up',
    description: 'One reminder after one hour.',
    rule: Object.freeze({ afterSeconds: 3_600 }),
  }),
  Object.freeze({
    id: 'daily-check',
    label: 'Daily check',
    description: 'Repeat every 24 hours.',
    rule: Object.freeze({ everySeconds: 86_400 }),
  }),
])

/** Durable one-shot reminder created from a positive delay. */
export interface AfterScheduleRecord {
  /** Session-local stable identity. */
  readonly id: ScheduleId
  /** Rule discriminator for a delayed one-shot reminder. */
  readonly kind: 'after'
  /** Trimmed reminder content supplied at creation. */
  readonly prompt: string
  /** Positive safe-integer delay accepted at creation. */
  readonly afterSeconds: number
  /** Four-digit-year RFC 3339 UTC target. */
  readonly scheduledAt: string
  /** Optional request key used for active-create deduplication. */
  readonly dedupeKey?: ScheduleDedupeKey
  /** Paused records remain durable but do not dispatch until resumed. */
  readonly paused?: true
}

/** Durable one-shot reminder created from an absolute instant. */
export interface AtScheduleRecord {
  /** Session-local stable identity. */
  readonly id: ScheduleId
  /** Rule discriminator for an absolute one-shot reminder. */
  readonly kind: 'at'
  /** Trimmed reminder content supplied at creation. */
  readonly prompt: string
  /** Four-digit-year RFC 3339 UTC target. */
  readonly scheduledAt: string
  /** Optional request key used for active-create deduplication. */
  readonly dedupeKey?: ScheduleDedupeKey
  /** Paused records remain durable but do not dispatch until resumed. */
  readonly paused?: true
}

/** Durable fixed-rate reminder whose next target remains creation-anchor-aligned. */
export interface EveryScheduleRecord {
  /** Session-local stable identity. */
  readonly id: ScheduleId
  /** Rule discriminator for a fixed-rate recurring reminder. */
  readonly kind: 'every'
  /** Trimmed reminder content supplied at creation. */
  readonly prompt: string
  /** Fixed safe-integer interval, never below five minutes. */
  readonly everySeconds: number
  /** Earliest anchor-aligned occurrence not yet dispatched. */
  readonly scheduledAt: string
  /** Optional request key used for active-create deduplication. */
  readonly dedupeKey?: ScheduleDedupeKey
  /** Paused records remain durable but do not dispatch until resumed. */
  readonly paused?: true
}

/** Structured local-calendar input accepted by `schedule_create`. */
export interface LocalAtInput {
  /** Four-digit ISO calendar date. */
  readonly date: string
  /** Local wall-clock time with optional one-to-three digit milliseconds. */
  readonly time: string
  /** Explicit UTC or IANA Area/Location zone. */
  readonly time_zone: string
}

/** Absolute selector accepted by `schedule_create`. */
export type AtInput = string | LocalAtInput

/** One-shot record variants that terminate on an id-only dispatch. */
export type OneShotScheduleRecord = AfterScheduleRecord | AtScheduleRecord

/** The v1 durable reminder record union. */
export type ScheduleRecord = OneShotScheduleRecord | EveryScheduleRecord

/** Creates one durable reminder record. */
export interface ScheduleCreateChange {
  readonly version: 1
  readonly operation: 'create'
  readonly schedule: ScheduleRecord
}

/** Deletes one currently active reminder. */
export interface ScheduleDeleteChange {
  readonly version: 1
  readonly operation: 'delete'
  readonly id: ScheduleId
}

/** Pause one active reminder without deleting its durable rule. */
export interface SchedulePauseChange {
  readonly version: 1
  readonly operation: 'pause'
  readonly id: ScheduleId
}

/** Resume one paused reminder and retain its original target. */
export interface ScheduleResumeChange {
  readonly version: 1
  readonly operation: 'resume'
  readonly id: ScheduleId
}

/** Records that one active one-shot reminder entered the durable dispatch history. */
export interface OneShotScheduleDispatchChange {
  readonly version: 1
  readonly operation: 'dispatch'
  readonly id: ScheduleId
}

/** Records one fixed-rate decision and advances directly past missed occurrences. */
export interface EveryScheduleDispatchChange {
  readonly version: 1
  readonly operation: 'dispatch'
  readonly id: ScheduleId
  /** Wall-clock decision time used to select the latest due occurrence. */
  readonly acceptedAt: string
}

/** Durable dispatch shapes supported by the current rule set. */
export type ScheduleDispatchChange = OneShotScheduleDispatchChange | EveryScheduleDispatchChange

/** Strict version-1 durable Schedule mutation union. */
export type ScheduleChange =
  | ScheduleCreateChange
  | ScheduleDeleteChange
  | SchedulePauseChange
  | ScheduleResumeChange
  | ScheduleDispatchChange
  | { readonly version: 1; readonly operation: 'result'; readonly id: ScheduleId; readonly outcome: ScheduleExecutionOutcome; readonly error?: string }

/** Current delivery timing derived from the durable record and wall clock. */
export type ScheduleState = 'scheduled' | 'overdue' | 'paused'

/** Fixed v1 delivery boundary: the original session must be live. */
export type ScheduleDeliveryMode = 'session-local'

/** Complete model-facing view of one active reminder. */
export type ScheduleView = ScheduleRecord & {
  /** Whether the target remains in the future. */
  readonly state: ScheduleState
  /** Reminder delivery never leaves the owning session. */
  readonly deliveryMode: ScheduleDeliveryMode
}

/** Management operations whose persistence barrier may be uncertain. */
export type SchedulePersistenceOperation =
  | 'create'
  | 'list'
  | 'delete'
  | 'pause'
  | 'resume'
  | 'run'
  | 'history'

/** Stable error returned for an empty reminder prompt. */
export interface InvalidPromptError {
  readonly code: 'invalid_prompt'
  readonly message: string
}

/** Stable error returned for a missing, conflicting, or unsupported rule selector. */
export interface InvalidSelectorError {
  readonly code: 'invalid_selector'
  readonly message: string
}

/** Stable error returned for an invalid rule or management argument. */
export interface InvalidRuleError {
  readonly code: 'invalid_rule'
  readonly message: string
}

/** Stable error returned for an invalid or unsupported IANA time zone. */
export interface InvalidTimeZoneError {
  readonly code: 'invalid_time_zone'
  readonly message: string
}

/** Stable error returned when an absolute target is not strictly future. */
export interface NotFutureError {
  readonly code: 'not_future'
  readonly message: string
}

/** Stable error returned when the computed instant cannot use a four-digit UTC year. */
export interface TimeOutOfRangeError {
  readonly code: 'time_out_of_range'
  readonly message: string
}

/** Stable error returned when a fixed-rate rule runs more often than supported. */
export interface FrequencyTooHighError {
  readonly code: 'frequency_too_high'
  readonly message: string
}

/** Stable error returned when the durable Schedule stream is malformed. */
export interface CorruptScheduleLogError {
  readonly code: 'corrupt_schedule_log'
  readonly message: string
}

/** Stable error returned when a required persistence checkpoint did not complete. */
export interface PersistenceUncertainError {
  readonly code: 'persistence_uncertain'
  readonly message: string
  readonly operation: SchedulePersistenceOperation
  readonly id?: ScheduleId
}

/** Stable fallback that does not disclose an internal exception. */
export interface InternalScheduleError {
  readonly code: 'internal_error'
  readonly message: string
}

/** Closed v1 Schedule management error union. */
export type ScheduleToolError =
  | InvalidPromptError
  | InvalidSelectorError
  | InvalidRuleError
  | InvalidTimeZoneError
  | NotFutureError
  | TimeOutOfRangeError
  | FrequencyTooHighError
  | CorruptScheduleLogError
  | PersistenceUncertainError
  | InternalScheduleError

/** Canonical `schedule_create` value. */
export type ScheduleCreateValue = ScheduleView | ScheduleToolError

/** Canonical `schedule_list` value. */
export type ScheduleListValue = ScheduleView[] | ScheduleToolError

/** Successful `schedule_delete` value, including the non-mutating not-found result. */
export type ScheduleDeleteResult =
  | { readonly id: ScheduleId; readonly deleted: true }
  | { readonly id: ScheduleId; readonly deleted: false; readonly code: 'schedule_not_found' }

/** Canonical `schedule_delete` value. */
export type ScheduleDeleteValue = ScheduleDeleteResult | ScheduleToolError

/** Successful pause result, including idempotent repeated-pause handling. */
export type SchedulePauseValue =
  | { readonly id: ScheduleId; readonly paused: true }
  | { readonly id: ScheduleId; readonly paused: false; readonly code: 'schedule_not_found' | 'schedule_already_paused' }
  | ScheduleToolError

/** Successful resume result, including idempotent repeated-resume handling. */
export type ScheduleResumeValue =
  | { readonly id: ScheduleId; readonly resumed: true }
  | { readonly id: ScheduleId; readonly resumed: false; readonly code: 'schedule_not_found' | 'schedule_already_active' }
  | ScheduleToolError

/** Successful immediate-run result. */
export type ScheduleRunValue =
  | { readonly id: ScheduleId; readonly started: true }
  | { readonly id: ScheduleId; readonly started: false; readonly code: 'schedule_not_found' | 'schedule_paused' }
  | ScheduleToolError

/** Canonical durable execution and lifecycle history value. */
export type ScheduleHistoryValue = ScheduleHistoryEntry[] | ScheduleToolError

/** Canonical immutable template catalog value. */
export type ScheduleTemplateValue = ScheduleTemplate[]

declare module '@deepseek-ai/dsh-session/types' {
  interface SessionEventMap {
    /**
     * Versioned Schedule mutation. The owning package validates the complete
     * session-local transition stream before accepting a candidate event.
     */
    'schedule/change': ScheduleChange
  }
}

declare module '@deepseek-ai/dsh-session-projection/types' {
  interface SessionProjectionMap {
    /** Complete active reminders owned by this Session's post-fork suffix. */
    schedule: readonly ScheduleRecord[]
    /** Durable Schedule lifecycle and dispatch history owned by this Session. */
    scheduleHistory: readonly ScheduleHistoryEntry[]
  }
}
