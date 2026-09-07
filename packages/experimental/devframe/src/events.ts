/** Durable DevFrame records stored in the owning controller Session. */

import { brandString, type Branded } from '@deepseek-ai/dsh-brand'
import type { GoalId } from '@deepseek-ai/dsh-goal/types'
import type { SessionEventMap, SessionId, SessionEvent } from '@deepseek-ai/dsh-session/types'
import { z } from 'zod'
import type { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import type {
  GoalBinding,
  GoalBindingIdentity,
  GoalResultBinding,
  TaskId,
} from './controller/goal-binding.ts'
import {
  requiredChecksConfigSchema,
  requiredChecksDigest,
  sameRequiredCheckCommand,
} from './required-checks.ts'
import type { DevFrameRequiredChecksConfig, RequiredChecksDigest } from './required-checks.ts'
import type { RolePolicyConfig } from './permissions/index.ts'
import type { StopIssue } from './reliability/stop.ts'
import type {
  AcceptanceHash,
  ConfigurationConfirmationId,
  ProjectLifecycleState,
  SourceFingerprint,
  WorkspaceId,
} from './shared/types.ts'
import { DevFrameSnapshotId } from './shared/types.ts'

/** Stable identifier for one captured source tree; declared with the shared binding contracts. */
export { DevFrameSnapshotId } from './shared/types.ts'

/** Stable identifier for one explicit Worker delivery. */
export type DevFrameDeliveryId = Branded<'DevFrameDeliveryId'>

/**
 * Brand a validated delivery identity.
 * @param value - Non-empty delivery identity.
 * @returns Branded delivery identity.
 */
export function DevFrameDeliveryId(value: string): DevFrameDeliveryId {
  return brandString<DevFrameDeliveryId>(value)
}

/** A committed task output attributed to its unchanged authorized Goal input. */
export interface DevFrameTaskDeliveryEventData {
  /** Payload format version. */
  readonly version: 1
  /** Unique identity of this explicit delivery. */
  readonly deliveryId: DevFrameDeliveryId
  /** The delivered task within the authorized Goal. */
  readonly taskId: TaskId
  /** Original complete Goal input identity, unchanged by development. */
  readonly binding: GoalResultBinding
  /** Registered Worker that explicitly delivered the output. */
  readonly workerSessionId: SessionId
  /** Registered worktree holding the output. */
  readonly worktreeId: WorktreeId
  /** Canonical source worktree path observed by the host. */
  readonly worktreePath: string
  /** Exact committed output object id observed by Git. */
  readonly sourceCommit: string
  /** Fingerprint of the delivered output, distinct from the Goal input. */
  readonly sourceFingerprint: SourceFingerprint
  /** Snapshot identity of the delivered output. */
  readonly snapshotId: DevFrameSnapshotId
}

/**
 * Derive the evidence identity for one delivered output without changing its Goal authorization.
 * @param delivery - Persisted task delivery with its original Goal binding.
 * @returns Detached output binding for verification and review.
 */
export function deliveryResultBinding(delivery: DevFrameTaskDeliveryEventData): GoalResultBinding {
  return { ...delivery.binding, taskIds: [...delivery.binding.taskIds],
    sourceFingerprint: delivery.sourceFingerprint, snapshotId: delivery.snapshotId }
}

/** Stable identifier for one host-recorded verification. */
export type DevFrameVerificationId = Branded<'DevFrameVerificationId'>

/** Stable identifier for one host-recorded review. */
export type DevFrameReviewId = Branded<'DevFrameReviewId'>

/** Stable identifier for one charged model or tool operation. */
export type DevFrameOperationId = Branded<'DevFrameOperationId'>

/**
 * Brand one verification identifier after its producer has validated it.
 * @param value - Non-empty verification identifier.
 * @returns The branded verification identifier.
 */
export function DevFrameVerificationId(value: string): DevFrameVerificationId {
  return brandString<DevFrameVerificationId>(value)
}

/**
 * Brand one review identifier after its producer has validated it.
 * @param value - Non-empty review identifier.
 * @returns The branded review identifier.
 */
export function DevFrameReviewId(value: string): DevFrameReviewId {
  return brandString<DevFrameReviewId>(value)
}

/**
 * Brand one operation identifier after its producer has validated it.
 * @param value - Non-empty operation identifier.
 * @returns The branded operation identifier.
 */
export function DevFrameOperationId(value: string): DevFrameOperationId {
  return brandString<DevFrameOperationId>(value)
}

/**
 * Roles recognized by the DevFrame host policy. `lead` is the
 * hierarchy-authorized tier-1 lead: the host records the assignment only for
 * Sessions the deployed hierarchy bindings back, and a lead is
 * reviewer-eligible for its own subtree — the hierarchy truth (real lead,
 * same plugin, parent, reviewed-Worker independence) stays with the host's
 * durable agent bindings, and a review consumer re-verifies it.
 */
export type DevFrameRole = 'controller' | 'lead' | 'worker' | 'reviewer'

/** One role assignment restored into the exact live Agent identity. */
export interface DevFrameRoleAssignment {
  /** The host-owned role. */
  readonly role: DevFrameRole
  /** Session identity of the Agent receiving the role. */
  readonly sessionId: SessionId
}

/** Resolved inherited and scope-local tool restrictions for one role. */
export interface DevFrameRoleToolPolicy {
  /** Inherited tools allowed in the role's Agent scope. */
  readonly inheritedTools: readonly string[]
  /** Scope-local tools rejected by the role guard. */
  readonly denyScopedTools: readonly string[]
}

/** Complete role configuration written with every role-policy snapshot. */
export interface DevFrameRolePolicyConfig {
  /** Effective controller restrictions. */
  readonly controller: DevFrameRoleToolPolicy
  /** Effective worker restrictions. */
  readonly worker: DevFrameRoleToolPolicy
  /** Effective reviewer restrictions. */
  readonly reviewer: DevFrameRoleToolPolicy
}

/**
 * Complete role-policy value required to recreate the host guard after a
 * process restart. Assignments are a whole snapshot, not an append-only delta.
 */
export interface DevFrameRolePolicyEventData {
  /** Payload schema version. */
  readonly version: 1
  /** Project identity selected by the human-facing host. */
  readonly workspaceId: WorkspaceId
  /** Controller Session that owns this event. */
  readonly controllerSessionId: SessionId
  /** Host policy revision used by evidence and review. */
  readonly policyVersion: string
  /** Effective restrictions, including scope-local denials. */
  readonly config: DevFrameRolePolicyConfig
  /** Exact live-session identities currently assigned to roles. */
  readonly assignments: readonly DevFrameRoleAssignment[]
}

/** One operation's measured, estimated, or unavailable token usage. */
export interface DevFrameTokenUsage {
  /** Whether the provider measured the values or the host estimated them. */
  readonly kind: 'measured' | 'estimated' | 'unknown'
  /** Input tokens, when available. */
  readonly input?: number
  /** Output tokens, when available. */
  readonly output?: number
  /** Combined tokens, when available. */
  readonly total?: number
}

/** A reservation or settlement for one bounded model/tool attempt. */
export interface DevFrameUsageEventData {
  /** Payload schema version. */
  readonly version: 1
  /** Stable operation identity; retries retain the same Goal binding. */
  readonly operationId: DevFrameOperationId
  /** Complete work identity captured before the operation was dispatched. */
  readonly binding: GoalResultBinding
  /** Host role that owns the attempt. */
  readonly role: DevFrameRole
  /** Positive attempt number within the Goal budget. */
  readonly attempt: number
  /** Reservation before execution or settlement after execution. */
  readonly phase: 'reserved' | 'settled'
  /** Settlement outcome; absent on a reservation. */
  readonly outcome?: 'succeeded' | 'failed' | 'aborted' | 'ambiguous'
  /** Current consumed-attempt count after this record. */
  readonly consumedAttempts: number
  /** Maximum charged attempts frozen at admission. */
  readonly maxAttempts: number
  /** Provider usage when measured, estimated, or explicitly unavailable. */
  readonly tokenUsage?: DevFrameTokenUsage
}

/** One configured check's real execution result. */
export interface DevFrameCheckResult {
  /** Stable check identifier from the human-approved configuration. */
  readonly checkId: string
  /** Executable actually invoked by the host. */
  readonly executable: string
  /** Exact argument vector passed to the executable. */
  readonly arguments: readonly string[]
  /** Absolute working directory used for the check. */
  readonly cwd: string
  /** Real process result, including cancellation and timeout. */
  readonly status: 'passed' | 'failed' | 'skipped' | 'timed_out' | 'cancelled' | 'unknown'
  /** Process exit code when the process produced one. */
  readonly exitCode?: number
  /** Wall-clock duration in milliseconds. */
  readonly durationMs: number
  /** Bounded artifact reference for stdout/stderr, when captured. */
  readonly outputRef?: string
}

/**
 * The approved required-checks checklist one verification evidence claims to
 * fully cover. The payload is self-describing: `digest` pins the canonical
 * identity of `config`, and the event schema rejects the payload unless every
 * declared check is exactly executed by the recorded `checks` — so a weakened
 * verification (a dropped check or a swapped command under a required name)
 * can no longer decode at all.
 */
export interface DevFrameVerificationCoverage {
  /** The human-approved configuration this evidence declares. */
  readonly config: DevFrameRequiredChecksConfig
  /** Canonical digest of `config`; schema-checked for self-consistency. */
  readonly digest: RequiredChecksDigest
}

/** Complete evidence produced for one exact source snapshot and work tuple. */
export interface DevFrameVerificationEventData {
  /** Payload schema version. */
  readonly version: 1
  /** Stable host-issued verification identity. */
  readonly verificationId: DevFrameVerificationId
  /** Explicit task output; absent for whole-Goal evidence. */
  readonly deliveryId?: DevFrameDeliveryId
  /** Complete work identity used to attribute the evidence. */
  readonly binding: GoalResultBinding
  /** Source snapshot referenced by this evidence. */
  readonly snapshotId: DevFrameSnapshotId
  /** Aggregate result derived from the listed real check executions. */
  readonly status: 'passed' | 'failed'
  /** The approved checklist this evidence declares and must exactly execute. */
  readonly requiredChecks: DevFrameVerificationCoverage
  /** All required checks executed for the snapshot. */
  readonly checks: readonly DevFrameCheckResult[]
}

/** One bounded reviewer finding attached to a named source snapshot. */
export interface DevFrameReviewFinding {
  /** Stable finding identity within the review. */
  readonly id: string
  /** Severity used by the host's completion policy. */
  readonly severity: 'blocking' | 'warning' | 'note'
  /** Sanitized explanation; raw prompts and command output stay in artifacts. */
  readonly message: string
  /** Repository-relative path, when the finding names one. */
  readonly path?: string
  /** One-based source line, when the finding names one. */
  readonly line?: number
}

/** Independent review result bound to the same source and work identity. */
export interface DevFrameReviewEventData {
  /** Payload schema version. */
  readonly version: 1
  /** Stable host-issued review identity. */
  readonly reviewId: DevFrameReviewId
  /** Explicit task output; absent for whole-Goal evidence. */
  readonly deliveryId?: DevFrameDeliveryId
  /** Complete work identity used to attribute the review. */
  readonly binding: GoalResultBinding
  /** Source snapshot examined by the reviewer. */
  readonly snapshotId: DevFrameSnapshotId
  /** Exact reviewer Session identity. */
  readonly reviewerSessionId: SessionId
  /** Role-policy revision active during review. */
  readonly policyVersion: string
  /** Review decision used by completion admission. */
  readonly decision: 'pass' | 'changes_required'
  /** Bounded findings explaining a non-pass decision. */
  readonly findings: readonly DevFrameReviewFinding[]
}

/** Lifecycle observation retained for stop, recovery, and writer ownership. */
export interface DevFrameLifecycleEventData {
  /** Payload schema version. */
  readonly version: 1
  /** Complete work identity whose lifecycle changed. */
  readonly binding: GoalResultBinding
  /** Durable project state after the observation. */
  readonly state: ProjectLifecycleState
  /** Owned resources that remain unresolved at this observation. */
  readonly remaining: readonly StopIssue[]
}

/**
 * Memory-save degradation codes the host grades as task warnings, verbatim
 * from the project-memory failure table. Request- and content-shape codes
 * (`MEMORY_INVALID_*`, `MEMORY_CONTENT_REJECTED`, `MEMORY_PATH_REJECTED`,
 * scope and size rejections) are ordinary tool errors the model corrects and
 * never grade as degradations. Extend by adding members; never widen to
 * `string`.
 */
export type DevFrameTaskWarningCode =
  | 'MEMORY_UNAVAILABLE'
  | 'MEMORY_WRITE_FAILED'
  | 'MEMORY_RECEIPT_FAILED'
  | 'MEMORY_APPEND_DISABLED'

/**
 * Host-graded degradation record for one task's memory surface. It records
 * only degradations: a successful save is recorded solely by the memory
 * receipt (`memory/receipt`) and is never duplicated here. At most one event
 * per task lands in a session log. The grade is the decision the host's
 * explicit requirement context produced: `complete-with-warning` for a task
 * whose acceptance tolerates the degradation, `fail` for a task whose
 * acceptance required the memory operation — the completion admission
 * consumes the latter as the task's real failure evidence.
 */
export interface DevFrameTaskWarningEventData {
  /** Payload schema version. */
  readonly version: 1
  /** The task whose memory surface degraded. */
  readonly taskId: TaskId
  /** The verbatim memory failure classification. */
  readonly warning: DevFrameTaskWarningCode
  /** The memory tool whose execution failed. */
  readonly tool: string
  /** The grading the host's explicit requirement context produced. */
  readonly grade: DevFrameMemoryGrading
}

/** DevFrame event names merged into the native session log vocabulary. */
export type DevFrameEventType =
  | 'devframe/role-policy'
  | 'devframe/goal-binding'
  | 'devframe/usage'
  | 'devframe/task-delivery'
  | 'devframe/verification'
  | 'devframe/review'
  | 'devframe/lifecycle'
  | 'devframe/task-warning'

declare module '@deepseek-ai/dsh-session/types' {
  interface SessionEventMap {
    /** Complete role policy and live Agent assignments used for cold guard restoration. */
    'devframe/role-policy': DevFrameRolePolicyEventData
    /** Complete Goal-to-task binding and admission budget for one project Goal. */
    'devframe/goal-binding': GoalBinding
    /** Reservation or settlement of one bounded project execution attempt. */
    'devframe/usage': DevFrameUsageEventData
    /** Explicit Worker output snapshot. */
    'devframe/task-delivery': DevFrameTaskDeliveryEventData
    /** Real configured-check results for one exact source snapshot. */
    'devframe/verification': DevFrameVerificationEventData
    /** Independent reviewer decision and bounded findings for one source snapshot. */
    'devframe/review': DevFrameReviewEventData
    /** Whole lifecycle observation used to recover stop and writer ownership state. */
    'devframe/lifecycle': DevFrameLifecycleEventData
    /** Host-graded memory degradation, recorded at most once per task. */
    'devframe/task-warning': DevFrameTaskWarningEventData
  }
}

const safeInteger = z.number().int().refine(Number.isSafeInteger, 'must be a safe integer')
const nonNegativeInteger = safeInteger.nonnegative()
const positiveInteger = nonNegativeInteger.min(1)
const trimmedString = z.string().min(1).refine(value => value === value.trim(), 'must be trimmed and non-empty')
const uniqueStrings = z.array(trimmedString).refine(values => new Set(values).size === values.length, 'must contain unique values')
const sessionIdSchema = trimmedString.transform(value => brandString<SessionId>(value))
const workspaceIdSchema = trimmedString.transform(value => brandString<WorkspaceId>(value))
const acceptanceHashSchema = trimmedString.transform(value => brandString<AcceptanceHash>(value))
const sourceFingerprintSchema = trimmedString.transform(value => brandString<SourceFingerprint>(value))
const confirmationIdSchema = trimmedString.transform(value => brandString<ConfigurationConfirmationId>(value))
const goalIdSchema = trimmedString.transform(value => brandString<GoalId>(value))
const taskIdSchema = trimmedString.transform(value => brandString<TaskId>(value))
const snapshotIdSchema = trimmedString.transform(value => brandString<DevFrameSnapshotId>(value))
const verificationIdSchema = trimmedString.transform(value => brandString<DevFrameVerificationId>(value))
const reviewIdSchema = trimmedString.transform(value => brandString<DevFrameReviewId>(value))
const operationIdSchema = trimmedString.transform(value => brandString<DevFrameOperationId>(value))
const requiredChecksDigestSchema = trimmedString.transform(value => brandString<RequiredChecksDigest>(value))

const lifecycleStateSchema = z.enum([
  'admission_open',
  'stop_requested',
  'quiescence_confirmed',
  'stopped',
  'ambiguous',
  'needs_attention',
])

const roleSchema = z.enum(['controller', 'lead', 'worker', 'reviewer'])
const roleToolPolicySchema = z.object({
  inheritedTools: uniqueStrings,
  denyScopedTools: uniqueStrings,
}).strict()
const rolePolicyConfigSchema = z.object({
  controller: roleToolPolicySchema,
  worker: roleToolPolicySchema,
  reviewer: roleToolPolicySchema,
}).strict()
const roleAssignmentSchema = z.object({
  role: roleSchema,
  sessionId: sessionIdSchema,
}).strict()

const rolePolicyEventSchema = z.object({
  version: z.literal(1),
  workspaceId: workspaceIdSchema,
  controllerSessionId: sessionIdSchema,
  policyVersion: trimmedString,
  config: rolePolicyConfigSchema,
  assignments: z.array(roleAssignmentSchema),
}).strict().superRefine((value, context) => {
  const roles = new Set<string>()
  const sessions = new Set<string>()
  for (const assignment of value.assignments) {
    // The three legacy roles are singletons per snapshot; leads are many —
    // one per subtree of the three-tier tree.
    if (assignment.role !== 'lead' && roles.has(assignment.role)) {
      context.addIssue({ code: 'custom', path: ['assignments'], message: `role "${assignment.role}" is assigned twice` })
    }
    if (sessions.has(assignment.sessionId)) {
      context.addIssue({ code: 'custom', path: ['assignments'], message: `Session "${assignment.sessionId}" has multiple roles` })
    }
    roles.add(assignment.role)
    sessions.add(assignment.sessionId)
    if (assignment.role === 'controller' && assignment.sessionId !== value.controllerSessionId) {
      context.addIssue({ code: 'custom', path: ['assignments'], message: 'controller role must use the owning controller Session' })
    }
  }
}) as z.ZodType<SessionEventMap['devframe/role-policy']>

const goalBindingSchema = z.object({
  version: z.literal(1),
  workspaceId: workspaceIdSchema,
  controllerSessionId: sessionIdSchema,
  goalId: goalIdSchema,
  goalRevision: positiveInteger,
  taskIds: z.array(taskIdSchema).min(1).refine(values => new Set(values).size === values.length, 'must contain unique task ids'),
  acceptanceHash: acceptanceHashSchema,
  sourceFingerprint: sourceFingerprintSchema,
  snapshotId: snapshotIdSchema,
  confirmation: z.object({
    id: confirmationIdSchema,
    acceptanceHash: acceptanceHashSchema,
  }).strict(),
  lifecycle: lifecycleStateSchema,
  budget: z.object({
    maxAttempts: positiveInteger,
    consumedAttempts: nonNegativeInteger,
  }).strict(),
}).strict().superRefine((value, context) => {
  if (value.confirmation.acceptanceHash !== value.acceptanceHash) {
    context.addIssue({ code: 'custom', path: ['confirmation', 'acceptanceHash'], message: 'must match acceptanceHash' })
  }
  if (value.budget.consumedAttempts > value.budget.maxAttempts) {
    context.addIssue({ code: 'custom', path: ['budget', 'consumedAttempts'], message: 'cannot exceed maxAttempts' })
  }
}) as z.ZodType<GoalBinding>

const goalResultBindingSchema = z.object({
  controllerSessionId: sessionIdSchema,
  goalId: goalIdSchema,
  goalRevision: positiveInteger,
  taskIds: z.array(taskIdSchema).min(1).refine(values => new Set(values).size === values.length, 'must contain unique task ids'),
  acceptanceHash: acceptanceHashSchema,
  workspaceId: workspaceIdSchema,
  sourceFingerprint: sourceFingerprintSchema,
  snapshotId: snapshotIdSchema,
}).strict() as z.ZodType<GoalResultBinding>

const tokenUsageSchema = z.object({
  kind: z.enum(['measured', 'estimated', 'unknown']),
  input: nonNegativeInteger.optional(),
  output: nonNegativeInteger.optional(),
  total: nonNegativeInteger.optional(),
}).strict().superRefine((value, context) => {
  if (value.kind === 'unknown' && (value.input !== undefined || value.output !== undefined || value.total !== undefined)) {
    context.addIssue({ code: 'custom', path: ['kind'], message: 'unknown usage cannot carry token counts' })
  }
})

const usageEventSchema = z.object({
  version: z.literal(1),
  operationId: operationIdSchema,
  binding: goalResultBindingSchema,
  role: roleSchema,
  attempt: positiveInteger,
  phase: z.enum(['reserved', 'settled']),
  outcome: z.enum(['succeeded', 'failed', 'aborted', 'ambiguous']).optional(),
  consumedAttempts: nonNegativeInteger,
  maxAttempts: positiveInteger,
  tokenUsage: tokenUsageSchema.optional(),
}).strict().superRefine((value, context) => {
  if (value.phase === 'reserved' && value.outcome !== undefined) {
    context.addIssue({ code: 'custom', path: ['outcome'], message: 'a reservation cannot carry an outcome' })
  }
  if (value.phase === 'settled' && value.outcome === undefined) {
    context.addIssue({ code: 'custom', path: ['outcome'], message: 'a settlement requires an outcome' })
  }
  if (value.consumedAttempts > value.maxAttempts) {
    context.addIssue({ code: 'custom', path: ['consumedAttempts'], message: 'cannot exceed maxAttempts' })
  }
}) as z.ZodType<DevFrameUsageEventData>

const checkResultSchema = z.object({
  checkId: trimmedString,
  executable: trimmedString,
  arguments: z.array(z.string()),
  cwd: trimmedString,
  status: z.enum(['passed', 'failed', 'skipped', 'timed_out', 'cancelled', 'unknown']),
  exitCode: safeInteger.optional(),
  durationMs: nonNegativeInteger,
  outputRef: trimmedString.optional(),
}).strict()

const verificationCoverageSchema = z.object({
  config: requiredChecksConfigSchema,
  digest: requiredChecksDigestSchema,
}).strict()

const taskDeliveryEventSchema = z.object({
  version: z.literal(1), deliveryId: trimmedString.transform(DevFrameDeliveryId),
  taskId: taskIdSchema, binding: goalResultBindingSchema,
  workerSessionId: sessionIdSchema,
  worktreeId: trimmedString.transform(value => brandString<WorktreeId>(value)),
  worktreePath: trimmedString,
  sourceCommit: z.string().regex(/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/),
  sourceFingerprint: sourceFingerprintSchema, snapshotId: snapshotIdSchema,
}).strict() as z.ZodType<DevFrameTaskDeliveryEventData>

const verificationEventSchema = z.object({
  version: z.literal(1),
  verificationId: verificationIdSchema,
  deliveryId: trimmedString.transform(DevFrameDeliveryId).optional(),
  binding: goalResultBindingSchema,
  snapshotId: snapshotIdSchema,
  status: z.enum(['passed', 'failed']),
  requiredChecks: verificationCoverageSchema,
  checks: z.array(checkResultSchema).min(1).refine(values => new Set(values.map(value => value.checkId)).size === values.length, 'check ids must be unique'),
}).strict().superRefine((value, context) => {
  if (value.snapshotId !== value.binding.snapshotId) {
    context.addIssue({ code: 'custom', path: ['snapshotId'], message: 'must match the binding snapshot' })
  }
  const allPassed = value.checks.every(check => check.status === 'passed')
  if (value.status === 'passed' && !allPassed) {
    context.addIssue({ code: 'custom', path: ['status'], message: 'passed evidence requires every check to pass' })
  }
  if (value.status === 'failed' && allPassed) {
    context.addIssue({ code: 'custom', path: ['status'], message: 'failed evidence requires a non-passing check' })
  }
  // Required-checks coverage rule: the evidence self-declares the approved
  // checklist it covers, and the schema rejects a payload whose declaration
  // does not hash to its claimed identity or whose checks do not exactly
  // execute every declared check (same checkId, exact command). A weakened
  // verification — a required check dropped or run under an altered command —
  // is therefore rejected at decode time; a declared check that ran exactly
  // but failed stays decodable as honest failed evidence, and the completion
  // admission (not this schema) rejects it for not passing. Executed checks
  // outside the declaration are still ignored: the config declares what is
  // required, not what is permitted.
  if (value.requiredChecks.digest !== requiredChecksDigest(value.requiredChecks.config)) {
    context.addIssue({
      code: 'custom',
      path: ['requiredChecks', 'digest'],
      message: 'must be the canonical digest of the declared required-checks configuration',
    })
  }
  for (const required of value.requiredChecks.config.checks) {
    const exactlyExecuted = value.checks.some(check =>
      check.checkId === required.checkId && sameRequiredCheckCommand(check, required))
    if (!exactlyExecuted) {
      context.addIssue({
        code: 'custom',
        path: ['requiredChecks', 'config', 'checks'],
        message: `required check "${required.checkId}" is not exactly executed by the recorded checks`,
      })
    }
  }
}) as z.ZodType<DevFrameVerificationEventData>

const reviewFindingSchema = z.object({
  id: trimmedString,
  severity: z.enum(['blocking', 'warning', 'note']),
  message: trimmedString,
  path: trimmedString.optional(),
  line: positiveInteger.optional(),
}).strict()

const reviewEventSchema = z.object({
  version: z.literal(1),
  reviewId: reviewIdSchema,
  deliveryId: trimmedString.transform(DevFrameDeliveryId).optional(),
  binding: goalResultBindingSchema,
  snapshotId: snapshotIdSchema,
  reviewerSessionId: sessionIdSchema,
  policyVersion: trimmedString,
  decision: z.enum(['pass', 'changes_required']),
  findings: z.array(reviewFindingSchema).refine(values => new Set(values.map(value => value.id)).size === values.length, 'finding ids must be unique'),
}).strict().superRefine((value, context) => {
  if (value.snapshotId !== value.binding.snapshotId) {
    context.addIssue({ code: 'custom', path: ['snapshotId'], message: 'must match the binding snapshot' })
  }
  const blocking = value.findings.some(finding => finding.severity === 'blocking')
  if (value.decision === 'pass' && blocking) {
    context.addIssue({ code: 'custom', path: ['decision'], message: 'a passing review cannot retain blocking findings' })
  }
}) as z.ZodType<DevFrameReviewEventData>

const stopIssueSchema = z.object({
  resource: trimmedString,
  reason: z.enum(['timeout', 'identity_unknown', 'operation_failed', 'unconfirmed']),
}).strict()

const lifecycleEventSchema = z.object({
  version: z.literal(1),
  binding: goalResultBindingSchema,
  state: lifecycleStateSchema,
  remaining: z.array(stopIssueSchema),
}).strict().superRefine((value, context) => {
  if ((value.state === 'quiescence_confirmed' || value.state === 'stopped') && value.remaining.length > 0) {
    context.addIssue({ code: 'custom', path: ['remaining'], message: `${value.state} cannot retain unresolved resources` })
  }
}) as z.ZodType<DevFrameLifecycleEventData>

const taskWarningEventSchema = z.object({
  version: z.literal(1),
  taskId: taskIdSchema,
  warning: z.enum(['MEMORY_UNAVAILABLE', 'MEMORY_WRITE_FAILED', 'MEMORY_RECEIPT_FAILED', 'MEMORY_APPEND_DISABLED']),
  tool: trimmedString,
  grade: z.enum(['complete-with-warning', 'fail']),
}).strict() as z.ZodType<DevFrameTaskWarningEventData>

/**
 * Whether an arbitrary Session event belongs to the DevFrame log domain.
 * @param event - Event envelope to classify.
 * @returns Whether the event is one of the DevFrame event types.
 */
export function isDevFrameEvent(event: SessionEvent): event is SessionEvent<DevFrameEventType> {
  switch (event.type) {
    case 'devframe/role-policy':
    case 'devframe/goal-binding':
    case 'devframe/usage':
    case 'devframe/task-delivery':
    case 'devframe/verification':
    case 'devframe/review':
    case 'devframe/lifecycle':
    case 'devframe/task-warning':
      return true
    default:
      return false
  }
}

/**
 * Decode one DevFrame payload at the durable event boundary.
 * @param type - DevFrame event name selecting the schema.
 * @param value - Untrusted payload from a Session append or restore.
 * @returns The validated payload for the selected event name.
 */
export function decodeDevFramePayload<T extends DevFrameEventType>(
  type: T,
  value: unknown,
): SessionEventMap[T] {
  try {
    switch (type) {
      case 'devframe/role-policy':
        return rolePolicyEventSchema.parse(value) as SessionEventMap[T]
      case 'devframe/goal-binding':
        return goalBindingSchema.parse(value) as SessionEventMap[T]
      case 'devframe/usage':
        return usageEventSchema.parse(value) as SessionEventMap[T]
      case 'devframe/task-delivery':
        return taskDeliveryEventSchema.parse(value) as SessionEventMap[T]
      case 'devframe/verification':
        return verificationEventSchema.parse(value) as SessionEventMap[T]
      case 'devframe/review':
        return reviewEventSchema.parse(value) as SessionEventMap[T]
      case 'devframe/lifecycle':
        return lifecycleEventSchema.parse(value) as SessionEventMap[T]
      case 'devframe/task-warning':
        return taskWarningEventSchema.parse(value) as SessionEventMap[T]
      /* v8 ignore next 2 -- DevFrameEventType is closed and every member is handled above. */
      default:
        return assertNever(type)
    }
  } catch (error: unknown) {
    throw new Error(`DevFrame ${type} payload is invalid`, { cause: error })
  }
}

/** Require a compile-time closed union branch to be handled. */
function assertNever(value: never): never {
  throw new Error(`unhandled DevFrame event type ${String(value)}`)
}

/**
 * Route one memory failure code onto the task-warning vocabulary.
 * Request- and content-shape codes (`MEMORY_INVALID_*`, scope and size
 * rejections, `MEMORY_CONTENT_REJECTED`, `MEMORY_PATH_REJECTED`) are ordinary
 * tool errors the model corrects and never grade as degradations.
 * @param code - Raw failure classification from a tool result, when any.
 * @returns The warning vocabulary member, or `undefined` when the code does not grade.
 */
export function memoryWarningCode(code: string | undefined): DevFrameTaskWarningCode | undefined {
  switch (code) {
    case 'MEMORY_UNAVAILABLE':
    case 'MEMORY_WRITE_FAILED':
    case 'MEMORY_RECEIPT_FAILED':
    case 'MEMORY_APPEND_DISABLED':
      return code
    default:
      return undefined
  }
}

/** The host grading one memory failure produces, from the explicit requirement context. */
export type DevFrameMemoryGrading = 'complete-with-warning' | 'fail'

/**
 * Grade one memory failure from the host's explicit requirement context: a
 * task whose acceptance does not require memory completes carrying the
 * warning event; a task whose acceptance is the memory save itself fails
 * through the existing fail path. The context is declared by the host
 * assembly per session — never derived from a message dispatch mode.
 * @param grading - The declared memory requirement and the raw failure code.
 * @returns The grading, or `undefined` when the code does not grade.
 */
export function gradeMemoryFailure(grading: { readonly memory: 'optional' | 'required'; readonly code: string | undefined }): DevFrameMemoryGrading | undefined {
  if (memoryWarningCode(grading.code) === undefined) return undefined
  return grading.memory === 'optional' ? 'complete-with-warning' : 'fail'
}

/** Retain the binding fields used to match evidence to one Goal. */
export type { AcceptanceHash, ConfigurationConfirmationId, ProjectLifecycleState, SourceFingerprint, WorkspaceId }

/** Expose the controller's identity alias for event consumers without duplicating it. */
export type { GoalBinding, GoalBindingIdentity, GoalResultBinding, RolePolicyConfig, StopIssue, TaskId }
