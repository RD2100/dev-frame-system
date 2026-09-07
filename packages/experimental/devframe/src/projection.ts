/** Host-only DevFrame projection folded from the controller Session log. */

import { brandString } from '@deepseek-ai/dsh-brand'
import type {
  SessionEvent,
  SessionHeader,
  SessionId,
  SessionLogOffset,
} from '@deepseek-ai/dsh-session'
import type { ProjectionDefinition } from '@deepseek-ai/dsh-session-projection'
import { z } from 'zod'
import {
  decodeDevFramePayload,
  isDevFrameEvent,
  type DevFrameLifecycleEventData,
  type DevFrameReviewEventData,
  type DevFrameRolePolicyEventData,
  type DevFrameTaskWarningEventData,
  type DevFrameUsageEventData,
  type DevFrameVerificationEventData,
} from './events.ts'
import type {
  GoalBinding,
  GoalResultBinding,
} from './controller/goal-binding.ts'
import type {
  ProjectLifecycleState,
  WorkspaceId,
} from './shared/types.ts'

/** Current host state reconstructed from DevFrame durable events. */
export interface DevFrameProjectionState {
  /** Controller Session identity selected by the projection owner. */
  readonly controllerSessionId: SessionId
  /** Workspace identity established by the first DevFrame record. */
  workspaceId: WorkspaceId | null
  /** Latest complete role-policy snapshot. */
  rolePolicy: DevFrameRolePolicyEventData | null
  /** Historical Goal bindings keyed by Goal identity. */
  bindings: GoalBinding[]
  /** Reservation and settlement records keyed by operation identity. */
  usage: DevFrameUsageEventData[]
  /** Immutable verification records keyed by verification identity. */
  verifications: DevFrameVerificationEventData[]
  /** Immutable review records keyed by review identity. */
  reviews: DevFrameReviewEventData[]
  /** Graded memory-degradation records, at most one per task. */
  taskWarnings: DevFrameTaskWarningEventData[]
  /** Latest explicit stop/recovery observation. */
  lifecycle: DevFrameLifecycleEventData | null
  /** First replay failure; subsequent records are not interpreted. */
  failure: string | null
}

declare module '@deepseek-ai/dsh-session-projection/types' {
  interface SessionProjectionStateMap {
    devframe: DevFrameProjectionState
  }
}

const trimmedString = z.string().min(1).refine(value => value === value.trim(), 'must be trimmed and non-empty')
const sessionIdSchema = trimmedString.transform(value => brandString<SessionId>(value))
const workspaceIdSchema = trimmedString.transform(value => brandString<WorkspaceId>(value))

/** Validate and decode one checkpoint state without accepting unvalidated nested records. */
const devFrameStateSchema = z.object({
  controllerSessionId: trimmedString,
  workspaceId: z.union([trimmedString, z.null()]),
  rolePolicy: z.unknown().nullable(),
  bindings: z.array(z.unknown()),
  usage: z.array(z.unknown()),
  verifications: z.array(z.unknown()),
  reviews: z.array(z.unknown()),
  taskWarnings: z.array(z.unknown()),
  lifecycle: z.unknown().nullable(),
  failure: z.string().nullable(),
}).strict().transform((value, context) => {
  try {
    return {
      controllerSessionId: sessionIdSchema.parse(value.controllerSessionId),
      workspaceId: value.workspaceId === null ? null : workspaceIdSchema.parse(value.workspaceId),
      rolePolicy: value.rolePolicy === null
        ? null
        : decodeDevFramePayload('devframe/role-policy', value.rolePolicy),
      bindings: value.bindings.map(binding => decodeDevFramePayload('devframe/goal-binding', binding)),
      usage: value.usage.map(usage => decodeDevFramePayload('devframe/usage', usage)),
      verifications: value.verifications.map(verification => decodeDevFramePayload('devframe/verification', verification)),
      reviews: value.reviews.map(review => decodeDevFramePayload('devframe/review', review)),
      taskWarnings: value.taskWarnings.map(warning => decodeDevFramePayload('devframe/task-warning', warning)),
      lifecycle: value.lifecycle === null
        ? null
        : decodeDevFramePayload('devframe/lifecycle', value.lifecycle),
      failure: value.failure,
    } satisfies DevFrameProjectionState
  } catch (error: unknown) {
    context.addIssue({
      code: 'custom',
      message: error instanceof Error ? error.message : String(error),
    })
    return z.NEVER
  }
}) as unknown as z.ZodType<DevFrameProjectionState>

/** Create the empty projection for one controller Session. */
function initialState(header: SessionHeader): DevFrameProjectionState {
  return {
    controllerSessionId: header.id,
    workspaceId: null,
    rolePolicy: null,
    bindings: [],
    usage: [],
    verifications: [],
    reviews: [],
    taskWarnings: [],
    lifecycle: null,
    failure: null,
  }
}

/** Return a detached Goal binding for the mutable projection state. */
function cloneBinding(binding: GoalBinding): GoalBinding {
  return {
    ...binding,
    taskIds: [...binding.taskIds],
    confirmation: { ...binding.confirmation },
    budget: { ...binding.budget },
  }
}

/** Return a detached result identity for a mutable projection state. */
function cloneResultBinding(binding: GoalResultBinding): GoalResultBinding {
  return { ...binding, taskIds: [...binding.taskIds] }
}

/** Return a detached role-policy snapshot for a mutable projection state. */
function cloneRolePolicy(policy: DevFrameRolePolicyEventData): DevFrameRolePolicyEventData {
  return {
    ...policy,
    config: {
      controller: {
        ...policy.config.controller,
        inheritedTools: [...policy.config.controller.inheritedTools],
        denyScopedTools: [...policy.config.controller.denyScopedTools],
      },
      worker: {
        ...policy.config.worker,
        inheritedTools: [...policy.config.worker.inheritedTools],
        denyScopedTools: [...policy.config.worker.denyScopedTools],
      },
      reviewer: {
        ...policy.config.reviewer,
        inheritedTools: [...policy.config.reviewer.inheritedTools],
        denyScopedTools: [...policy.config.reviewer.denyScopedTools],
      },
    },
    assignments: policy.assignments.map(assignment => ({ ...assignment })),
  }
}

/** Return a detached usage record for a mutable projection state. */
function cloneUsage(usage: DevFrameUsageEventData): DevFrameUsageEventData {
  return {
    ...usage,
    binding: cloneResultBinding(usage.binding),
    ...usage.tokenUsage === undefined ? {} : { tokenUsage: { ...usage.tokenUsage } },
  }
}

/** Return a detached verification record for a mutable projection state. */
function cloneVerification(verification: DevFrameVerificationEventData): DevFrameVerificationEventData {
  return {
    ...verification,
    binding: cloneResultBinding(verification.binding),
    checks: verification.checks.map(check => ({ ...check, arguments: [...check.arguments] })),
    requiredChecks: {
      config: {
        ...verification.requiredChecks.config,
        checks: verification.requiredChecks.config.checks.map(check => ({ ...check, arguments: [...check.arguments] })),
      },
      digest: verification.requiredChecks.digest,
    },
  }
}

/** Return a detached review record for a mutable projection state. */
function cloneReview(review: DevFrameReviewEventData): DevFrameReviewEventData {
  return {
    ...review,
    binding: cloneResultBinding(review.binding),
    findings: review.findings.map(finding => ({ ...finding })),
  }
}

/** Return a detached lifecycle record for a mutable projection state. */
function cloneLifecycle(lifecycle: DevFrameLifecycleEventData): DevFrameLifecycleEventData {
  return {
    ...lifecycle,
    binding: cloneResultBinding(lifecycle.binding),
    remaining: lifecycle.remaining.map(issue => ({ ...issue })),
  }
}

/** Compare two ordered string arrays. */
function sameStrings(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index])
}

/** Compare role-policy configuration without relying on object key order. */
function sameRolePolicyConfig(
  left: DevFrameRolePolicyEventData['config'],
  right: DevFrameRolePolicyEventData['config'],
): boolean {
  return (['controller', 'worker', 'reviewer'] as const).every((role) => {
    const a = left[role]
    const b = right[role]
    return sameStrings(a.inheritedTools, b.inheritedTools) && sameStrings(a.denyScopedTools, b.denyScopedTools)
  })
}

/** Compare complete role assignments without treating array order as identity. */
function sameAssignments(
  left: DevFrameRolePolicyEventData['assignments'],
  right: DevFrameRolePolicyEventData['assignments'],
): boolean {
  if (left.length !== right.length) return false
  return left.every(assignment => right.some(candidate =>
    candidate.role === assignment.role && candidate.sessionId === assignment.sessionId))
}

/** Compare the immutable fields of a Goal binding. */
function sameBindingIdentity(left: GoalBinding, right: GoalBinding): boolean {
  return left.workspaceId === right.workspaceId
    && left.controllerSessionId === right.controllerSessionId
    && left.goalId === right.goalId
    && left.taskIds.length === right.taskIds.length
    && left.taskIds.every((taskId, index) => taskId === right.taskIds[index])
    && left.acceptanceHash === right.acceptanceHash
    && left.sourceFingerprint === right.sourceFingerprint
    && left.confirmation.id === right.confirmation.id
    && left.confirmation.acceptanceHash === right.confirmation.acceptanceHash
    && left.budget.maxAttempts === right.budget.maxAttempts
}

/** Compare a result tuple with a persisted Goal binding, allowing later CAS revisions. */
function sameResultTuple(binding: GoalBinding, result: GoalResultBinding): boolean {
  return binding.workspaceId === result.workspaceId
    && binding.controllerSessionId === result.controllerSessionId
    && binding.goalId === result.goalId
    && binding.taskIds.length === result.taskIds.length
    && binding.taskIds.every((taskId, index) => taskId === result.taskIds[index])
    && binding.acceptanceHash === result.acceptanceHash
    && binding.sourceFingerprint === result.sourceFingerprint
    && binding.snapshotId === result.snapshotId
}

/** Find one historical binding by its stable Goal identity. */
function bindingFor(state: DevFrameProjectionState, goalId: GoalBinding['goalId']): GoalBinding | undefined {
  return state.bindings.find(binding => binding.goalId === goalId)
}

/** Require a payload to belong to this projection's controller and workspace. */
function assertProjectIdentity(
  state: DevFrameProjectionState,
  controllerSessionId: SessionId,
  workspaceId: WorkspaceId,
): void {
  if (controllerSessionId !== state.controllerSessionId) {
    throw new Error(`DevFrame record belongs to controller Session "${controllerSessionId}" instead of "${state.controllerSessionId}"`)
  }
  if (state.workspaceId === null) {
    state.workspaceId = workspaceId
  } else if (state.workspaceId !== workspaceId) {
    throw new Error(`DevFrame record belongs to workspace "${workspaceId}" instead of "${state.workspaceId}"`)
  }
}

/** Validate the exact identity tuple carried by an evidence or lifecycle record. */
function assertResultBinding(state: DevFrameProjectionState, binding: GoalResultBinding): GoalBinding {
  if (binding.controllerSessionId !== state.controllerSessionId) {
    throw new Error(`DevFrame result belongs to controller Session "${binding.controllerSessionId}" instead of "${state.controllerSessionId}"`)
  }
  assertProjectIdentity(state, binding.controllerSessionId, binding.workspaceId)
  const current = bindingFor(state, binding.goalId)
  if (current === undefined) throw new Error(`DevFrame result references unknown Goal "${binding.goalId}"`)
  if (!sameResultTuple(current, binding)) {
    throw new Error(`DevFrame result tuple for Goal "${binding.goalId}" does not match its binding`)
  }
  return current
}

/** Return the lifecycle states permitted after one prior state. */
function nextLifecycleStates(state: ProjectLifecycleState): readonly ProjectLifecycleState[] {
  switch (state) {
    case 'ambiguous':
      return ['admission_open', 'stop_requested', 'stopped', 'needs_attention']
    case 'admission_open':
      return ['stop_requested', 'ambiguous', 'needs_attention']
    case 'stop_requested':
      return ['quiescence_confirmed', 'needs_attention', 'ambiguous']
    case 'quiescence_confirmed':
      return ['stopped', 'needs_attention']
    case 'stopped':
      return ['admission_open', 'ambiguous', 'needs_attention']
    case 'needs_attention':
      return ['stop_requested', 'admission_open', 'stopped', 'ambiguous']
    /* v8 ignore next 2 -- ProjectLifecycleState is a closed union. */
    default:
      return []
  }
}

/** Validate one lifecycle transition and reject duplicate observations. */
function assertLifecycleTransition(
  prior: ProjectLifecycleState | undefined,
  next: ProjectLifecycleState,
): void {
  if (prior === undefined) {
    if (next !== 'ambiguous' && next !== 'admission_open') {
      throw new Error(`DevFrame lifecycle cannot begin at ${next}`)
    }
    return
  }
  if (!nextLifecycleStates(prior).includes(next)) {
    throw new Error(`DevFrame lifecycle cannot transition from ${prior} to ${next}`)
  }
}

/** Validate role assignment uniqueness and controller ownership. */
function assertRoleAssignments(
  state: DevFrameProjectionState,
  policy: DevFrameRolePolicyEventData,
): void {
  const roles = new Set<string>()
  const sessions = new Set<string>()
  for (const assignment of policy.assignments) {
    if (roles.has(assignment.role)) throw new Error(`DevFrame role "${assignment.role}" is assigned twice`)
    if (sessions.has(assignment.sessionId)) throw new Error(`DevFrame Session "${assignment.sessionId}" has multiple roles`)
    roles.add(assignment.role)
    sessions.add(assignment.sessionId)
    if (assignment.role === 'controller' && assignment.sessionId !== state.controllerSessionId) {
      throw new Error('DevFrame controller role must use the owning controller Session')
    }
  }
}

/** Apply a complete role-policy snapshot. */
function applyRolePolicy(state: DevFrameProjectionState, policy: DevFrameRolePolicyEventData): void {
  assertProjectIdentity(state, policy.controllerSessionId, policy.workspaceId)
  assertRoleAssignments(state, policy)
  const prior = state.rolePolicy
  if (prior !== null) {
    if (prior.policyVersion === policy.policyVersion && !sameRolePolicyConfig(prior.config, policy.config)) {
      throw new Error(`DevFrame policy version "${policy.policyVersion}" changed its tool configuration`)
    }
    if (prior.policyVersion === policy.policyVersion
      && sameRolePolicyConfig(prior.config, policy.config)
      && sameAssignments(prior.assignments, policy.assignments)) {
      throw new Error(`DevFrame role policy "${policy.policyVersion}" was recorded twice`)
    }
  }
  state.rolePolicy = cloneRolePolicy(policy)
}

/** Apply a complete Goal binding and retain only monotonic lifecycle/budget changes. */
function applyGoalBinding(state: DevFrameProjectionState, binding: GoalBinding): void {
  assertProjectIdentity(state, binding.controllerSessionId, binding.workspaceId)
  if (binding.confirmation.acceptanceHash !== binding.acceptanceHash) {
    throw new Error(`DevFrame Goal "${binding.goalId}" confirmation does not match its acceptance hash`)
  }
  const index = state.bindings.findIndex(candidate => candidate.goalId === binding.goalId)
  const prior = index < 0 ? undefined : state.bindings[index]
  if (prior === undefined) {
    assertLifecycleTransition(undefined, binding.lifecycle)
    state.bindings.push(cloneBinding(binding))
    if (state.lifecycle !== null && state.lifecycle.binding.goalId !== binding.goalId) {
      state.lifecycle = null
    }
    return
  }
  if (!sameBindingIdentity(prior, binding)) {
    throw new Error(`DevFrame Goal "${binding.goalId}" changed its immutable binding`)
  }
  if (binding.goalRevision < prior.goalRevision) {
    throw new Error(`DevFrame Goal "${binding.goalId}" revision moved backwards`)
  }
  if (binding.budget.consumedAttempts < prior.budget.consumedAttempts) {
    throw new Error(`DevFrame Goal "${binding.goalId}" consumed-attempt count moved backwards`)
  }
  if (binding.goalRevision === prior.goalRevision && binding.lifecycle === prior.lifecycle
    && binding.budget.consumedAttempts === prior.budget.consumedAttempts) {
    throw new Error(`DevFrame Goal "${binding.goalId}" binding was recorded twice`)
  }
  if (binding.lifecycle !== prior.lifecycle) assertLifecycleTransition(prior.lifecycle, binding.lifecycle)
  state.bindings[index] = cloneBinding(binding)
}

/** Apply one reservation or settlement while rejecting duplicate operation identities. */
function applyUsage(state: DevFrameProjectionState, usage: DevFrameUsageEventData): void {
  const binding = assertResultBinding(state, usage.binding)
  if (usage.maxAttempts !== binding.budget.maxAttempts) {
    throw new Error(`DevFrame operation "${usage.operationId}" has a different attempt limit`)
  }
  if (usage.attempt > usage.maxAttempts) throw new Error(`DevFrame operation "${usage.operationId}" exceeds its attempt limit`)
  const prior = state.usage.find(record => record.operationId === usage.operationId)
  if (prior === undefined) {
    if (usage.phase !== 'reserved') throw new Error(`DevFrame operation "${usage.operationId}" settled before reservation`)
    const consumed = state.usage
      .filter(record => record.binding.goalId === usage.binding.goalId)
      .reduce((maximum, record) => Math.max(maximum, record.consumedAttempts), binding.budget.consumedAttempts)
    if (usage.consumedAttempts !== consumed + 1) {
      throw new Error(`DevFrame operation "${usage.operationId}" did not advance consumed attempts by one`)
    }
    state.usage.push(cloneUsage(usage))
    return
  }
  if (!sameResultTuple(binding, prior.binding) || prior.attempt !== usage.attempt || prior.role !== usage.role) {
    throw new Error(`DevFrame operation "${usage.operationId}" changed its identity`)
  }
  if (prior.phase === 'settled') throw new Error(`DevFrame operation "${usage.operationId}" was settled twice`)
  if (usage.phase !== 'settled') throw new Error(`DevFrame operation "${usage.operationId}" was reserved twice`)
  if (usage.consumedAttempts !== prior.consumedAttempts) {
    throw new Error(`DevFrame operation "${usage.operationId}" changed its consumed-attempt count`)
  }
  state.usage.push(cloneUsage(usage))
}

/** Apply one immutable verification record. */
function applyVerification(state: DevFrameProjectionState, verification: DevFrameVerificationEventData): void {
  assertResultBinding(state, verification.binding)
  if (state.verifications.some(record => record.verificationId === verification.verificationId)) {
    throw new Error(`DevFrame verification "${verification.verificationId}" was recorded twice`)
  }
  state.verifications.push(cloneVerification(verification))
}

/** Apply one independent review record tied to an existing verification snapshot. */
function applyReview(state: DevFrameProjectionState, review: DevFrameReviewEventData): void {
  assertResultBinding(state, review.binding)
  if (state.rolePolicy === null || state.rolePolicy.policyVersion !== review.policyVersion) {
    throw new Error(`DevFrame review "${review.reviewId}" uses an unavailable role policy version`)
  }
  if (!state.rolePolicy.assignments.some(assignment =>
    assignment.role === 'reviewer' && assignment.sessionId === review.reviewerSessionId)) {
    throw new Error(`DevFrame review "${review.reviewId}" was submitted by Session "${review.reviewerSessionId}" without the reviewer role`)
  }
  if (!state.verifications.some(record => record.snapshotId === review.snapshotId
    && record.binding.goalId === review.binding.goalId)) {
    throw new Error(`DevFrame review "${review.reviewId}" references an unknown verification snapshot`)
  }
  if (state.reviews.some(record => record.reviewId === review.reviewId)) {
    throw new Error(`DevFrame review "${review.reviewId}" was recorded twice`)
  }
  state.reviews.push(cloneReview(review))
}

/** Apply one stop or recovery observation. */
function applyLifecycle(state: DevFrameProjectionState, lifecycle: DevFrameLifecycleEventData): void {
  const binding = assertResultBinding(state, lifecycle.binding)
  const prior = state.lifecycle
  if (prior !== null && prior.binding.goalId !== lifecycle.binding.goalId) {
    throw new Error('DevFrame lifecycle changed Goal identity')
  }
  assertLifecycleTransition(prior?.state ?? binding.lifecycle, lifecycle.state)
  if ((lifecycle.state === 'stopped' || lifecycle.state === 'quiescence_confirmed')
    && lifecycle.remaining.length > 0) {
    throw new Error(`DevFrame lifecycle ${lifecycle.state} cannot retain unresolved resources`)
  }
  state.lifecycle = cloneLifecycle(lifecycle)
}

/**
 * Apply one graded memory-degradation record. The listener guarantees at most
 * one record per task; a replayed log holding two for one task is corruption
 * and fails the fold loud.
 */
function applyTaskWarning(state: DevFrameProjectionState, warning: DevFrameTaskWarningEventData): void {
  if (state.taskWarnings.some(candidate => String(candidate.taskId) === String(warning.taskId))) {
    throw new Error(`DevFrame task warning for task "${String(warning.taskId)}" was recorded twice`)
  }
  state.taskWarnings.push(warning)
}

/** Apply one decoded DevFrame event to a projection state. */
function applyEvent(state: DevFrameProjectionState, event: SessionEvent): void {
  if (state.failure !== null || !isDevFrameEvent(event)) return
  try {
    switch (event.type) {
      case 'devframe/role-policy':
        applyRolePolicy(state, decodeDevFramePayload(event.type, event.data))
        break
      case 'devframe/goal-binding':
        applyGoalBinding(state, decodeDevFramePayload(event.type, event.data))
        break
      case 'devframe/usage':
        applyUsage(state, decodeDevFramePayload(event.type, event.data))
        break
      case 'devframe/verification':
        applyVerification(state, decodeDevFramePayload(event.type, event.data))
        break
      case 'devframe/review':
        applyReview(state, decodeDevFramePayload(event.type, event.data))
        break
      case 'devframe/task-warning':
        applyTaskWarning(state, decodeDevFramePayload(event.type, event.data))
        break
      case 'devframe/lifecycle':
        applyLifecycle(state, decodeDevFramePayload(event.type, event.data))
        break
      default:
        return
    }
  } catch (error: unknown) {
    state.failure = error instanceof Error ? error.message : String(error)
  }
}

/**
 * Fold a complete Session log into the host-only DevFrame state.
 * @param events - Ordered native Session events to replay.
 * @param header - Session header that supplies the controller identity.
 * @returns The validated projection state, with the first replay failure latched.
 */
export function foldDevFrameState(
  events: readonly SessionEvent[],
  header: SessionHeader,
): DevFrameProjectionState {
  const state = initialState(header)
  for (const event of events) applyEvent(state, event)
  return state
}

/** Host-only projection definition registered by the DevFrame profile. */
export const devFrameProjectionDefinition = {
  key: 'devframe',
  stateVersion: 1,
  stateSchema: devFrameStateSchema,
  init: (header: SessionHeader, _inheritedEventCount: SessionLogOffset) => initialState(header),
  apply: (state: DevFrameProjectionState, event: SessionEvent) => {
    applyEvent(state, event)
    return state
  },
} satisfies ProjectionDefinition<'devframe', DevFrameProjectionState>
