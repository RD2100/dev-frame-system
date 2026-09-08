/**
 * Single-project Goal admission and work binding.
 *
 * This module owns the small controller-side seam between a human start
 * command, the native Goal service, and durable project binding records. It
 * deliberately does not execute model or tool work; callers must pass the
 * returned identity to their execution admission hook. It also hosts the
 * completion admission conjunction ({@link evaluateCompletionAdmission}) that
 * reuses the source fingerprint verify face the binding domain recorded, and
 * the controller completion operation ({@link GoalBindingController.complete})
 * — the production call point that gates the native Goal lifecycle's complete
 * mutation behind that conjunction through the {@link NativeGoalPort} seam.
 * @module @deepseek-ai/dsh-experimental-devframe/controller/goal-binding
 */

import type { Agent } from '@deepseek-ai/dsh-agent'
import { SessionId } from '@deepseek-ai/dsh-session'
import { GoalId as nativeGoalId } from '@deepseek-ai/dsh-goal'
import type { GoalId as NativeGoalId } from '@deepseek-ai/dsh-goal/types'
import type { GoalService, GoalView } from '@deepseek-ai/dsh-goal'
import type { Branded } from '@deepseek-ai/dsh-brand'
import type {
  DevFrameCheckResult,
  DevFrameReviewEventData,
  DevFrameReviewFinding,
  DevFrameReviewId,
  DevFrameRepairCause,
  DevFrameTaskWarningEventData,
  DevFrameVerificationEventData,
} from '../events.ts'
import { evaluateRequiredChecks } from '../required-checks.ts'
import type {
  RequiredChecksConfigStore,
  RequiredChecksDigest,
  RequiredChecksUnsatisfied,
} from '../required-checks.ts'
import { resolveRepairLimit } from '../repair-limit.ts'
import type { RepairRoundAdmission } from '../repair-limit.ts'
import type { DevFrameAppendOptions } from '../session-journal.ts'
import { verifySourceFingerprint } from '../source-fingerprint.ts'
import type { SourceFingerprintMismatch } from '../source-fingerprint.ts'
import {
  AcceptanceHash as makeAcceptanceHash,
  ConfigurationConfirmationId as makeConfirmationId,
  DevFrameSnapshotId as makeSnapshotId,
  SourceFingerprint as makeSourceFingerprint,
} from '../shared/types.ts'
import type {
  AcceptanceHash,
  ConfigurationConfirmation,
  DevFrameSnapshotId,
  ProjectBindingPersistence,
  ProjectBindingRecord,
  ProjectWorkBinding,
  SourceFingerprint,
  WorkspaceId,
} from '../shared/types.ts'

/** Compile-time-only identifier for one controller Session. */
export type ControllerSessionId = ProjectWorkBinding['controllerSessionId']

/** Native Team task identity; validation happens at this controller boundary. */
export type TaskId = Branded<'TeamTaskId'>

/** Shared branded fingerprint of approved acceptance configuration. */
export type { AcceptanceHash } from '../shared/types.ts'

/**
 * Brand one non-empty controller Session identifier.
 * @param value - non-empty trimmed identifier text.
 * @returns the branded controller Session identifier.
 */
export function ControllerSessionId(value: string): ControllerSessionId {
  return SessionId(nonEmptyId(value, 'controllerSessionId'))
}

/**
 * Brand one non-empty native Team task identifier.
 * @param value - non-empty trimmed identifier text.
 * @returns the branded Team task identifier.
 */
export function TaskId(value: string): TaskId {
  return nonEmptyId(value, 'taskId') as TaskId
}

/** Durable identity used to route execution and late results to one Goal. */
export type GoalBindingIdentity = Pick<ProjectWorkBinding, 'controllerSessionId' | 'goalId'>

/** Budget values frozen into one Goal binding at admission. */
export interface GoalBudget {
  /** Maximum charged attempts for this Goal. */
  readonly maxAttempts: number
  /** Attempts already charged before this binding was restored. */
  readonly consumedAttempts: number
}

/** Input budget accepted by a new start; consumption defaults to zero. */
export interface GoalBudgetInput {
  readonly maxAttempts: number
  readonly consumedAttempts?: number
}

/** Complete immutable binding persisted before a Goal is resumed. */
export interface GoalBinding extends ProjectBindingRecord {
  readonly version: 1
  readonly taskIds: readonly TaskId[]
  readonly budget: GoalBudget
  /** Snapshot whose content the source fingerprint describes. */
  readonly snapshotId: DevFrameSnapshotId
}

/** Tuple required when a result or evidence record is associated with a Goal. */
export interface GoalResultBinding extends GoalBindingIdentity {
  /** Native Goal revision captured by the operation producing this result. */
  readonly goalRevision: number
  readonly taskIds: readonly TaskId[]
  readonly acceptanceHash: AcceptanceHash
  readonly workspaceId: WorkspaceId
  readonly sourceFingerprint: SourceFingerprint
  /** Snapshot whose content the source fingerprint describes. */
  readonly snapshotId: DevFrameSnapshotId
}

/**
 * Host-authorized adoption of changed approved checks across one binding
 * generation: the host composition recomputes the acceptance hash of the
 * same objective under the current approved checks and mints a fresh human
 * confirmation; the resumed binding carries both instead of the stored
 * acceptance. The projection admits the change only across a strict
 * revision advance, so the superseded generation's evidence stops
 * satisfying completion while usage keeps bridging by Goal identity.
 */
export interface GenerationAdoption {
  /** The recomputed acceptance hash of (objective, current approved checks). */
  readonly acceptanceHash: AcceptanceHash
  /** Fresh human confirmation minted for the adopted generation. */
  readonly confirmation: ConfigurationConfirmation
}

/** Durable storage needed by the controller. Implementations may use JSONL, SQLite, or memory. */
export interface GoalBindingStore extends ProjectBindingPersistence {
  /** Load every binding for one controller Session, including completed Goals. */
  load(controllerSessionId: ControllerSessionId): Promise<readonly GoalBinding[]>
  /**
   * Persist one binding; identical retries must be idempotent. Besides an
   * equal-or-advanced identical tuple, a legal generation advance
   * ({@link isGenerationAdvance}: strictly higher revision, unchanged
   * structural identity, consumption not moved backwards) may carry changed
   * acceptance fields — the resume lane's authorized adoption of changed
   * approved checks (AT1-10).
   */
  save(binding: GoalBinding): Promise<void>
}

/** In-memory binding store for focused tests and disposable integrations. */
export class MemoryGoalBindingStore implements GoalBindingStore {
  private readonly values = new Map<ControllerSessionId, GoalBinding[]>()
  private readonly current = new Map<WorkspaceId, ProjectBindingRecord>()

  /**
   * Load detached binding copies for one controller Session.
   * @param controllerSessionId - controller identity selecting the records.
   * @returns immutable binding snapshots detached from the store.
   */
  load(controllerSessionId: ControllerSessionId): Promise<readonly GoalBinding[]> {
    return new Promise((resolve) => {
      resolve(this.values.get(controllerSessionId)?.map(copyBinding) ?? [])
    })
  }

  /** Read the current shared project binding for one workspace. */
  read(workspaceId: WorkspaceId): Promise<ProjectBindingRecord | undefined> {
    return new Promise((resolve) => {
      const record = this.current.get(workspaceId)
      resolve(record === undefined ? undefined : copyProjectBindingRecord(record))
    })
  }

  /** Write the current shared project binding for one workspace. */
  write(record: ProjectBindingRecord): Promise<void> {
    return new Promise((resolve) => {
      this.current.set(record.workspaceId, copyProjectBindingRecord(record))
      resolve()
    })
  }

  /**
   * Save one binding, accepting an identical retry, a legal generation
   * advance ({@link isGenerationAdvance}), and rejecting identity reuse
   * with changed task, acceptance, or budget data outside those rules.
   * @param binding - Goal binding to retain.
   */
  save(binding: GoalBinding): Promise<void> {
    return new Promise((resolve) => {
      const records = this.values.get(binding.controllerSessionId) ?? []
      const index = records.findIndex(record => record.goalId === binding.goalId)
      if (index !== -1) {
        const current = records[index]
        if (current !== undefined
          && ((sameBinding(current, binding) && binding.goalRevision >= current.goalRevision)
            || isGenerationAdvance(current, binding))) {
          records[index] = copyBinding(binding)
          this.values.set(binding.controllerSessionId, records)
          resolve()
          return
        }
        throw new GoalBindingError(
          `Goal "${binding.goalId}" already has a different binding`,
          'GOAL_BINDING_CONFLICT',
        )
      }
      records.push(copyBinding(binding))
      this.values.set(binding.controllerSessionId, records)
      resolve()
    })
  }
}

/** Native phase values needed for admission checks. */
export type NativeGoalPhase = 'active' | 'paused' | 'blocked' | 'complete'

/** Native Goal state returned by the injected Goal adapter. */
export interface NativeGoalState {
  readonly id: NativeGoalId
  readonly revision: number
  readonly phase: NativeGoalPhase
}

/**
 * Minimal adapter over the native Goal service. The adapter owns the live
 * Agent argument and keeps this controller independent from execution.
 */
export interface NativeGoalPort {
  /** Create one native Goal; native creation arms continuation automatically. */
  create(request: { readonly objective: string; readonly maxGoalRounds?: number }): NativeGoalState
  /** Remove process-local continuation authority without changing Goal phase. */
  disarm(): NativeGoalState | undefined
  /** Read the native current Goal for this controller Session. */
  get(): NativeGoalState | undefined
  /** Resume one exact native Goal revision and arm continuation. */
  resume(ref: { readonly id: NativeGoalId; readonly revision: number }): NativeGoalState
  /** Record a disarmed resume and return its guarded continuation activation. */
  prepareResume?(ref: { readonly id: NativeGoalId; readonly revision: number }): {
    readonly goal: NativeGoalState
    readonly activate: (commit?: () => void) => NativeGoalState
  }
  /** Mark the current native Goal complete at one exact revision and disarm it. */
  complete(ref: { readonly id: NativeGoalId; readonly revision: number }): NativeGoalState
  /**
   * Clear the current native Goal at one exact revision behind the native
   * durable tombstone, retaining its history. Optional because only the
   * human-authorized abandon consumes it; a port without it fails abandon
   * loud instead of degrading into a silent non-clear.
   */
  clear?(ref: { readonly id: NativeGoalId; readonly revision: number }): { readonly id: NativeGoalId; readonly revision: number }
}

/**
 * Production {@link NativeGoalPort} over the live native Goal service: every
 * verb delegates to the resolved native service on the exact live Agent this
 * port binds, and native rejections (`GOAL_AGENT_NOT_LIVE`,
 * `GOAL_STALE_REVISION`, `GOAL_INVALID_TRANSITION`) propagate unchanged. This
 * is the adapter a host composition wires behind a
 * {@link GoalBindingController}; there is no second, softer path into the
 * native Goal lifecycle.
 */
export class GoalServicePort implements NativeGoalPort {
  /**
   * @param options - the resolved native Goal service and the one live Agent
   *   every verb acts on.
   */
  constructor(private readonly options: {
    readonly goals: GoalService
    readonly agent: Agent
  }) {}

  create(request: { readonly objective: string; readonly maxGoalRounds?: number }): NativeGoalState {
    return toNativeGoalState(this.options.goals.create(this.options.agent, request))
  }

  disarm(): NativeGoalState | undefined {
    return mapNativeGoalState(this.options.goals.disarm(this.options.agent))
  }

  get(): NativeGoalState | undefined {
    return mapNativeGoalState(this.options.goals.get(this.options.agent))
  }

  resume(ref: { readonly id: NativeGoalId; readonly revision: number }): NativeGoalState {
    return toNativeGoalState(this.options.goals.resume(this.options.agent, ref))
  }

  prepareResume(ref: { readonly id: NativeGoalId; readonly revision: number }): {
    readonly goal: NativeGoalState
    readonly activate: (commit?: () => void) => NativeGoalState
  } {
    const prepared = this.options.goals.prepareResume(this.options.agent, ref)
    return { goal: toNativeGoalState(prepared.goal), activate: commit => toNativeGoalState(prepared.activate(commit)) }
  }

  complete(ref: { readonly id: NativeGoalId; readonly revision: number }): NativeGoalState {
    return toNativeGoalState(this.options.goals.complete(this.options.agent, ref))
  }

  clear(ref: { readonly id: NativeGoalId; readonly revision: number }): { readonly id: NativeGoalId; readonly revision: number } {
    return this.options.goals.clear(this.options.agent, ref)
  }
}

/** Project a native Goal view onto the controller's narrow state triple. */
function toNativeGoalState(view: GoalView): NativeGoalState {
  return { id: view.id, revision: view.revision, phase: view.phase }
}

/** Project an optional native Goal view onto the controller's narrow state. */
function mapNativeGoalState(view: GoalView | undefined): NativeGoalState | undefined {
  return view === undefined ? undefined : toNativeGoalState(view)
}

/** Human-issued capability required for start and resume. */
export interface HumanAuthorization {
  readonly kind: 'human'
  readonly confirmationId: string
}

const HUMAN_AUTHORIZATION = Symbol('devframe-human-authorization')

/**
 * Create an authorization value that model-produced object literals cannot
 * satisfy. The command adapter should create this only after human approval.
 * @param confirmationId - identifier of the approved command or preview.
 * @returns a host-issued authorization capability.
 */
export function createHumanAuthorization(confirmationId: string): HumanAuthorization {
  if (confirmationId.trim().length === 0) {
    throw new GoalBindingError(
      'human authorization requires a non-empty confirmation id',
      'GOAL_BINDING_AUTHORIZATION_REQUIRED',
    )
  }
  return Object.freeze({
    kind: 'human' as const,
    confirmationId: confirmationId.trim(),
    [HUMAN_AUTHORIZATION]: true,
  })
}

/** Input for starting one new native Goal and binding its approved work. */
export interface StartGoalRequest {
  readonly objective: string
  readonly taskIds: readonly TaskId[]
  readonly acceptanceHash: AcceptanceHash
  readonly sourceFingerprint: SourceFingerprint
  /** Captured source tree the fingerprint describes; recorded with the binding. */
  readonly snapshotId: DevFrameSnapshotId
  readonly budget: GoalBudgetInput
  readonly authorization: HumanAuthorization
  readonly maxGoalRounds?: number
}

/**
 * Durable evidence that the final merged result of one Goal's bound tasks is
 * real, verified, and independently reviewed. The host composition builds it
 * from the durable integration domain and the controller's session projection;
 * the completion admission never accepts it for a task the binding does not
 * name.
 */
export interface FinalIntegrationContract {
  /** Authoritative controller worktree named by every applied integration receipt. */
  readonly targetPath: string
  /**
   * One applied integration receipt per bound task, read from the durable
   * integration domain. The receipt's applied state is what the integration
   * domain recorded after its Git merge; admission requires the set of task
   * ids to equal the binding's.
   */
  readonly tasks: readonly {
    readonly taskId: TaskId
    /** The head the applied integration recorded for the target worktree. */
    readonly appliedHead: string
  }[]
  /**
   * Whole-Goal verification covering the final merged result: `deliveryId`
   * absent, and its binding carries the merged tree's fingerprint, which the
   * admission recomputes against the live worktree instead of the binding's
   * initial start fingerprint.
   */
  readonly verification: DevFrameVerificationEventData
  /**
   * Whole-Goal review covering the final merged result: `deliveryId` absent,
   * same work tuple as the verification, issued by a Session that delivered
   * none of the bound tasks — the per-task lead reviews do not substitute.
   */
  readonly review: DevFrameReviewEventData
  /** Session identities that delivered each bound task; the independence anchor. */
  readonly workerSessionIds: readonly SessionId[]
}

/**
 * Evidence-side input for one controller completion attempt: everything
 * {@link evaluateCompletionAdmission} consumes except the recorded source
 * fingerprint, which {@link GoalBindingController.complete} takes from the
 * durable binding instead of trusting the caller — or, when
 * {@link FinalIntegrationContract} evidence is supplied, from that evidence's
 * merged-tree fingerprint after the final-integration stage validates it.
 */
export interface CompleteGoalRequest {
  /** Recheck durable evidence and live host ownership immediately before native completion. */
  readonly beforeComplete?: () => void
  /**
   * Worktree to fingerprint for plain completion. Final-integration completion
   * always fingerprints the authoritative targetPath carried by its receipts.
   */
  readonly worktreePath: string
  /** Real executed check results, e.g. `checks` from the decoded verification evidence. */
  readonly checks: readonly DevFrameCheckResult[]
  /** Canonical digest of the approved configuration, registered in the store at approval time. */
  readonly requiredChecksDigest: RequiredChecksDigest
  /** Configuration store resolving `requiredChecksDigest` to the stored approved checklist. */
  readonly requiredChecksStore: RequiredChecksConfigStore
  /**
   * The durable, gate-authorized review evidence attributed to this Goal:
   * the journal write gate already enforced reviewer authorization before
   * this record entered the log, so admission consumes only its pass
   * decision, and the controller rejects evidence naming another Goal. With
   * final-merge evidence supplied this must be that evidence's review.
   */
  readonly review: DevFrameReviewEventData
  /**
   * The graded memory-degradation records decoded from the task's session
   * log (AT3-07): each carries the grade the host's explicit requirement
   * context produced. A `fail` grade is the task's real failure evidence —
   * the acceptance required the memory operation — and refuses completion;
   * `complete-with-warning` records never reject. Empty when the task's
   * memory operations all succeeded or recorded no degradation.
   */
  readonly taskWarnings: readonly DevFrameTaskWarningEventData[]
  /**
   * Final-merge evidence for a Goal whose bound tasks were integrated into
   * the controller worktree. Supplied, it replaces the binding's initial
   * fingerprint as the admission anchor with the merged-tree fingerprint the
   * whole-Goal verification carries; the binding record itself is never
   * rewritten. Absent, completion anchors to the initial fingerprint exactly
   * as before.
   */
  readonly finalIntegration?: FinalIntegrationContract
}

/** Stable error classifications emitted by this controller seam. */
export type GoalBindingErrorCode =
  | 'GOAL_BINDING_AUTHORIZATION_REQUIRED'
  | 'GOAL_BINDING_ADMISSION_CLOSED'
  | 'GOAL_BINDING_ALREADY_RUNNING'
  | 'GOAL_BINDING_IDENTITY_MISMATCH'
  | 'GOAL_BINDING_INVALID_REQUEST'
  | 'GOAL_BINDING_NOT_FOUND'
  | 'GOAL_BINDING_NOT_READY'
  | 'GOAL_BINDING_PERSISTENCE'
  | 'GOAL_BINDING_CONFLICT'

/** Structured failure from binding validation or admission. */
export class GoalBindingError extends Error {
  /** Stable machine-routable classification of this binding failure. */
  readonly code: GoalBindingErrorCode

  /**
   * @param message - human-readable rejection reason.
   * @param code - stable machine-routable error classification.
   */
  constructor(message: string, code: GoalBindingErrorCode, options?: ErrorOptions) {
    super(message, options)
    this.name = 'GoalBindingError'
    this.code = code
  }
}

/** Whether this controller admits model/tool work for its current binding. */
export type GoalAdmission = 'closed' | 'open'

/** Session journal operations required for durable correction accounting. */
export interface GoalRepairAdmissions {
  /** Persist or reuse one cause's correction admission through the controller Session journal. */
  admit(
    identity: GoalBindingIdentity, cause: DevFrameRepairCause, repairLimit: number, options: DevFrameAppendOptions,
  ): Promise<RepairRoundAdmission>
  /** Read correction consumption reconstructed from the controller Session log. */
  state(identity: GoalBindingIdentity, repairLimit: number): RepairRoundState
}

/** Current correction consumption for an exact Goal. */
export interface RepairRoundState {
  readonly repairLimit: number
  readonly consumedRepairRounds: number
  readonly remainingRepairRounds: number
}

/** Construction dependencies for one controller Session. */
export interface GoalBindingControllerOptions {
  readonly workspaceId: WorkspaceId
  readonly controllerSessionId: ControllerSessionId
  readonly goals: NativeGoalPort
  readonly store: GoalBindingStore
  /** Required before any repair operation; absence fails closed. */
  readonly repairAdmissions?: GoalRepairAdmissions
  /**
   * Deployment-varying repair-round limit for the review-repair cycle
   * (AT1-08): the maximum correction/retest/review rounds admitted after the
   * initial review. Validated with {@link resolveRepairLimit} at
   * construction; unset resolves to the acceptance-defined default of 2.
   */
  readonly repairLimit?: number
}

/**
 * Controller-side Goal admission and immutable binding history.
 *
 * `start()` closes admission before native Goal creation, immediately disarms
 * the native Goal, persists its complete binding, and only then resumes it and
 * opens admission. Any setup failure leaves admission closed. `resume()` uses
 * an explicitly supplied historical identity, so a late result for Goal A can
 * never be resolved through the current Goal B.
 */
export class GoalBindingController {
  private admission: GoalAdmission = 'closed'
  private activeIdentity: GoalBindingIdentity | undefined
  private readonly ready: Promise<void>
  private loaded = false
  private loadFailure: unknown
  private bindings: GoalBinding[] = []
  private tail: Promise<void> = Promise.resolve()
  /** Validated repair-round limit resolved from the construction config. */
  private readonly repairLimit: number

  /**
   * @param options - controller Session identity, native Goal adapter, and store.
   * @throws {@link RepairLimitError} when `repairLimit` is set and not a
   *   positive safe integer — misconfiguration fails loud at construction.
   */
  constructor(private readonly options: GoalBindingControllerOptions) {
    this.repairLimit = resolveRepairLimit(
      options.repairLimit === undefined ? {} : { repairLimit: options.repairLimit },
    )
    this.ready = Promise.resolve()
      .then(async () => await Promise.all([
        options.store.load(options.controllerSessionId),
        options.store.read(options.workspaceId),
      ]))
      .then(([values, current]) => {
        this.bindings = values.map(copyBinding)
        this.assertLoadedIdentityUniqueness()
        if (current !== undefined) {
          if (current.controllerSessionId !== options.controllerSessionId) {
            throw new GoalBindingError(
              `workspace "${options.workspaceId}" is bound to controller "${current.controllerSessionId}"`,
              'GOAL_BINDING_IDENTITY_MISMATCH',
            )
          }
          const binding = this.bindings.find(candidate => candidate.goalId === current.goalId)
          if (binding === undefined || !sameProjectBinding(binding, current)) {
            throw new GoalBindingError(
              `workspace "${options.workspaceId}" has no matching durable Goal binding`,
              'GOAL_BINDING_PERSISTENCE',
            )
          }
        }
        this.loaded = true
      }, (error: unknown) => {
        this.loadFailure = error
      })
  }

  /** Current admission state; construction always starts closed. */
  get admissionState(): GoalAdmission {
    return this.admission
  }

  /**
   * Start one human-authorized Goal with fresh task, acceptance, and budget
   * bindings.
   * @param request - objective, task set, acceptance fingerprint, budget, and authorization.
   * @returns the persisted binding used by subsequent execution and results.
   */
  start(request: StartGoalRequest): Promise<GoalBinding> {
    return this.enqueue(async () => {
      await this.ensureReady()
      assertHumanAuthorization(request.authorization)
      const input = resolveStartRequest(request)

      const current = this.options.goals.get()
      if (current !== undefined && current.phase !== 'complete') {
        throw new GoalBindingError(
          `native Goal "${current.id}" is still ${current.phase}`,
          'GOAL_BINDING_ALREADY_RUNNING',
        )
      }
      this.closeAdmission()

      const created = this.options.goals.create({
        objective: input.objective,
        ...input.maxGoalRounds === undefined ? {} : { maxGoalRounds: input.maxGoalRounds },
      })
      assertNativeRevision(created.revision)
      const goalId = nativeGoalId(nonEmptyId(created.id, 'goalId'))
      const binding: GoalBinding = {
        version: 1,
        workspaceId: this.options.workspaceId,
        controllerSessionId: this.options.controllerSessionId,
        goalId,
        goalRevision: created.revision,
        taskIds: input.taskIds,
        acceptanceHash: input.acceptanceHash,
        sourceFingerprint: input.sourceFingerprint,
        snapshotId: input.snapshotId,
        confirmation: {
          id: makeConfirmationId(nonEmptyId(request.authorization.confirmationId, 'confirmationId')),
          acceptanceHash: input.acceptanceHash,
        },
        lifecycle: 'ambiguous',
        budget: input.budget,
      }

      // Native create() arms automatically. This synchronous disarm happens
      // before the first async persistence turn can admit another operation.
      this.options.goals.disarm()
      await this.saveBinding(binding)

      const resumed = this.options.goals.resume({ id: created.id, revision: created.revision })
      if (resumed.id !== created.id) {
        throw new GoalBindingError(
          `native resume returned Goal "${resumed.id}" for "${created.id}"`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      assertRevisionAdvance(created.revision, resumed.revision)
      const admitted = {
        ...binding,
        goalRevision: resumed.revision,
        lifecycle: 'admission_open' as const,
      }
      await this.saveBinding(admitted)
      this.activeIdentity = identityOf(admitted)
      this.admission = 'open'
      return copyBinding(admitted)
    })
  }

  /**
   * Resume one previously persisted Goal after a human stop or process
   * restart. The exact identity is required; this method never selects the
   * whichever Goal happens to be current.
   * @param identity - controller Session and Goal identity to resume.
   * @param authorization - host-issued human authorization for this resume.
   * @param adopt - optional host-authorized adoption of changed approved
   *   checks: the resumed binding opens a new generation that carries the
   *   recomputed acceptance hash and a fresh human confirmation instead of
   *   the stored ones. The projection accepts acceptance changes only
   *   across this strict revision advance, the superseded generation's
   *   evidence stops satisfying completion, and usage bridges by Goal
   *   identity; the fold enforces the confirmation/hash match.
   * @param activation - optional host preparation and durable journal hooks;
   *   continuation stays disarmed until the journal, store, and resource commit settle.
   * @returns the binding retained for the resumed Goal — the historical
   *   acceptance, or the adopted generation when `adopt` was given.
   */
  resume(
    identity: GoalBindingIdentity,
    authorization: HumanAuthorization,
    adopt?: GenerationAdoption,
    activation?: {
      readonly prepare: () => Promise<() => void>
      readonly persist: (binding: GoalBinding) => Promise<void>
    },
  ): Promise<GoalBinding> {
    return this.enqueue(async () => {
      await this.ensureReady()
      assertHumanAuthorization(authorization)
      const binding = this.findBinding(identity)
      this.closeAdmission()

      const current = this.options.goals.get()
      if (current === undefined || current.id !== identity.goalId) {
        throw new GoalBindingError(
          `native Goal does not match "${identity.goalId}"`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      assertNativeRevision(current.revision)
      if (current.revision < binding.goalRevision) {
        throw new GoalBindingError(
          `native Goal "${identity.goalId}" revision ${current.revision} precedes bound revision ${binding.goalRevision}`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      if (current.phase === 'complete') {
        throw new GoalBindingError(
          `Goal "${identity.goalId}" is already complete`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }

      const prepareResume = this.options.goals.prepareResume?.bind(this.options.goals)
      if (activation !== undefined && prepareResume === undefined) {
        throw new GoalBindingError('the native Goal port cannot defer resume activation', 'GOAL_BINDING_IDENTITY_MISMATCH')
      }
      const commitResources = await activation?.prepare()
      const prepared = activation === undefined ? undefined
        : prepareResume?.({ id: current.id, revision: current.revision })
      const resumed = prepared?.goal ?? this.options.goals.resume({ id: current.id, revision: current.revision })
      assertNativeRevision(resumed.revision)
      if (resumed.id !== identity.goalId) {
        throw new GoalBindingError(
          `native resume returned Goal "${resumed.id}" for "${identity.goalId}"`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      assertRevisionAdvance(current.revision, resumed.revision)
      const admitted = {
        ...binding,
        goalRevision: resumed.revision,
        lifecycle: 'admission_open' as const,
        ...(adopt === undefined ? {} : {
          acceptanceHash: adopt.acceptanceHash,
          confirmation: adopt.confirmation,
        }),
      }
      try {
        if (activation !== undefined) await this.saveBinding({ ...admitted, lifecycle: 'ambiguous' }, adopt !== undefined)
        await activation?.persist(admitted)
        await this.saveBinding(admitted, adopt !== undefined)
        const admit = (): void => {
          commitResources?.()
          this.activeIdentity = identityOf(admitted)
          this.admission = 'open'
        }
        if (prepared === undefined) admit()
        else prepared.activate(admit)
      } catch (error) {
        this.closeAdmission()
        const failures: unknown[] = []
        try { this.options.goals.disarm() } catch (disarmError) { failures.push(disarmError) }
        if (activation !== undefined) {
          const failed = { ...admitted, lifecycle: 'needs_attention' as const }
          const repairs = await Promise.allSettled([
            this.saveBinding(failed, adopt !== undefined),
            activation.persist(failed),
          ])
          failures.push(...repairs.filter(result => result.status === 'rejected').map(result => result.reason as unknown))
        }
        if (failures.length > 0) throw new AggregateError([error, ...failures], 'resume failed and recovery bookkeeping is incomplete')
        throw error
      }
      return copyBinding(admitted)
    })
  }

  /**
   * Record one human-authorized stop request for an exact unfinished bound
   * Goal: admission closes for the controller's own steps, the native Goal
   * loses continuation authority through the same disarm the start lane
   * performs, and the binding persists at `stop_requested` — the honest
   * statement that a stop was requested while quiescence (draining jobs,
   * processes, and the flush) is still unconfirmed. The terminal `stopped`
   * state stays reachable through the existing lifecycle vocabulary
   * (`stop_requested` → `quiescence_confirmed` → `stopped`); the stop flow,
   * not this seam, owns those observations and the writer release.
   * @param identity - controller Session and Goal identity to stop.
   * @param authorization - host-issued human authorization for this stop.
   * @returns the persisted binding at `stop_requested`.
   * @throws {@link GoalBindingError} when the authorization is not
   *   host-issued, the identity is unknown or foreign, the native Goal
   *   diverged from the binding or is already complete, the binding's
   *   lifecycle cannot legally enter `stop_requested`, or persistence fails.
   */
  stop(identity: GoalBindingIdentity, authorization: HumanAuthorization): Promise<GoalBinding> {
    return this.enqueue(async () => {
      await this.ensureReady()
      assertHumanAuthorization(authorization)
      const binding = this.findBinding(identity)
      this.closeAdmission()

      const current = this.options.goals.get()
      if (current === undefined || current.id !== identity.goalId) {
        throw new GoalBindingError(
          `native Goal does not match "${identity.goalId}"`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      assertNativeRevision(current.revision)
      if (current.revision < binding.goalRevision) {
        throw new GoalBindingError(
          `native Goal "${identity.goalId}" revision ${current.revision} precedes bound revision ${binding.goalRevision}`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      if (current.phase === 'complete') {
        throw new GoalBindingError(
          `Goal "${identity.goalId}" is already complete`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      assertStoppableLifecycle(binding.lifecycle)

      this.options.goals.disarm()
      const stopped = { ...binding, lifecycle: 'stop_requested' as const }
      await this.saveBinding(stopped)
      return copyBinding(stopped)
    })
  }

  /**
   * Record one human-authorized abandon of an exact stopped or unfinished
   * bound Goal: admission closes, the native Goal loses continuation
   * authority, and the native Goal is cleared behind its durable tombstone —
   * the existing vocabulary's expression of "no longer resumable", since a
   * cleared Goal can never again satisfy the native-state match every resume
   * performs. The binding history is retained and no completion is claimed.
   * An unfinished (`admission_open`) binding first persists the same
   * `stop_requested` stop-mark the stop lane writes, because the abandon
   * stops the work without quiescence confirmation; a `stopped` binding
   * needs no new record.
   * @param identity - controller Session and Goal identity to abandon.
   * @param authorization - host-issued human authorization for this abandon.
   * @returns the retained binding: at `stop_requested` for a previously
   *   unfinished Goal, unchanged (`stopped`) for an already stopped one.
   * @throws {@link GoalBindingError} when the authorization is not
   *   host-issued, the identity is unknown or foreign, the native Goal
   *   diverged from the binding or is already complete, the binding's
   *   lifecycle is neither `admission_open` nor `stopped`, the injected
   *   native port cannot clear, or persistence fails.
   */
  abandon(identity: GoalBindingIdentity, authorization: HumanAuthorization): Promise<GoalBinding> {
    return this.enqueue(async () => {
      await this.ensureReady()
      assertHumanAuthorization(authorization)
      const binding = this.findBinding(identity)
      this.closeAdmission()

      const current = this.options.goals.get()
      if (current === undefined || current.id !== identity.goalId) {
        throw new GoalBindingError(
          `native Goal does not match "${identity.goalId}"`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      assertNativeRevision(current.revision)
      if (current.revision < binding.goalRevision) {
        throw new GoalBindingError(
          `native Goal "${identity.goalId}" revision ${current.revision} precedes bound revision ${binding.goalRevision}`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      if (current.phase === 'complete') {
        throw new GoalBindingError(
          `Goal "${identity.goalId}" is already complete and cannot be abandoned; completion already claimed it`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      if (binding.lifecycle !== 'admission_open' && binding.lifecycle !== 'stopped') {
        throw new GoalBindingError(
          `Goal "${identity.goalId}" lifecycle "${binding.lifecycle}" is neither admission_open nor stopped; resolve the pending stop flow before abandoning`,
          'GOAL_BINDING_INVALID_REQUEST',
        )
      }
      if (this.options.goals.clear === undefined) {
        throw new GoalBindingError(
          'native Goal port cannot clear Goals; abandon requires the production GoalServicePort',
          'GOAL_BINDING_INVALID_REQUEST',
        )
      }

      this.options.goals.disarm()
      const retained = binding.lifecycle === 'admission_open'
        ? { ...binding, lifecycle: 'stop_requested' as const }
        : binding
      if (binding.lifecycle === 'admission_open') await this.saveBinding(retained)

      this.options.goals.clear({ id: current.id, revision: current.revision })
      return copyBinding(retained)
    })
  }

  /**
   * Attempt one admission-evaluated completion of an exact bound Goal: the
   * production call point where the {@link evaluateCompletionAdmission}
   * conjunction gates the native Goal lifecycle's complete mutation.
   *
   * The attempt resolves the binding by exact identity, closes admission for
   * its whole duration (the evaluation runs real git subprocesses and must
   * not race admitted model steps; a rejected attempt leaves the safe state,
   * so continuing work requires a human-authorized {@link resume}), and
   * validates that the native Goal is still this binding's Goal, not behind
   * the bound revision, and not already complete, and that the review
   * evidence is attributed to this Goal. The three predicates then evaluate
   * in their fixed evidence-chain order against the durable binding's own
   * recorded fingerprint. A rejection is data: the native Goal stays
   * untouched. An admission completes the native Goal at its current
   * revision, persists the binding at the revision the native service
   * returned, and leaves admission closed.
   *
   * Structural failures are never converted into rejections; every throw
   * propagates to the caller unchanged.
   * @param identity - controller Session and Goal identity to complete.
   * @param request - worktree path, executed checks, registered
   *   required-checks configuration reference, and the review evidence
   *   attributed to this Goal. With {@link CompleteGoalRequest.finalIntegration}
   *   supplied, the admission first validates that final-merge contract and
   *   re-anchors the fingerprint stage at the merged-tree fingerprint its
   *   whole-Goal verification carries; the binding's recorded fingerprint is
   *   left untouched either way.
   * @returns the {@link CompletionAdmissionAdmitted} verdict after the native
   *   Goal completed, or the first failing stage's rejection verdict with the
   *   native Goal untouched.
   * @throws {@link GoalBindingError} when the identity is unknown or foreign,
   *   the native Goal diverged from the binding (missing, foreign, behind the
   *   bound revision, or already complete), the review evidence names another
   *   Goal, persistence fails, or the native completion returned an
   *   unexpected identity or revision.
   * @throws {@link SourceFingerprintError} when the worktree fingerprint
   *   recompute is unusable; `RequiredChecksError` when the digest has no
   *   registered configuration or its stored bytes fail their schema.
   */
  complete(identity: GoalBindingIdentity, request: CompleteGoalRequest): Promise<CompletionAdmissionVerdict> {
    return this.enqueue(async () => {
      await this.ensureReady()
      const binding = this.findBinding(identity)
      this.closeAdmission()

      const current = this.options.goals.get()
      if (current === undefined || current.id !== binding.goalId) {
        throw new GoalBindingError(
          `native Goal does not match "${identity.goalId}"`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      assertNativeRevision(current.revision)
      if (current.revision < binding.goalRevision) {
        throw new GoalBindingError(
          `native Goal "${identity.goalId}" revision ${current.revision} precedes bound revision ${binding.goalRevision}`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      if (current.phase === 'complete') {
        throw new GoalBindingError(
          `Goal "${identity.goalId}" is already complete`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      const reviewBinding = request.review.binding
      if (reviewBinding.goalId !== binding.goalId) {
        throw new GoalBindingError(
          `completion review evidence is attributed to Goal "${reviewBinding.goalId}", not "${binding.goalId}"`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      if (reviewBinding.controllerSessionId !== binding.controllerSessionId) {
        throw new GoalBindingError(
          'completion review evidence is recorded under controller Session'
            + ` "${reviewBinding.controllerSessionId}", not "${binding.controllerSessionId}"`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      if (reviewBinding.workspaceId !== binding.workspaceId) {
        throw new GoalBindingError(
          'completion review evidence is recorded for workspace'
            + ` "${reviewBinding.workspaceId}", not "${binding.workspaceId}"`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }

      // The final-merge lane: with whole-Goal merged-result evidence supplied,
      // the stage validates the contract, the submitted review must be that
      // evidence's review, and the admission re-anchors at the merged-tree
      // fingerprint the whole-Goal verification carries — the binding's
      // initial start fingerprint is neither consulted for the final state
      // nor rewritten into it.
      let admission = {
        worktreePath: request.worktreePath,
        sourceFingerprint: binding.sourceFingerprint,
        checks: request.checks,
        requiredChecksDigest: request.requiredChecksDigest,
        requiredChecksStore: request.requiredChecksStore,
        review: request.review,
        taskWarnings: request.taskWarnings,
      }
      if (request.finalIntegration !== undefined) {
        const final = evaluateFinalIntegrationStage({
          contract: request.finalIntegration,
          boundTaskIds: binding.taskIds,
        })
        if (final.kind === 'rejected') return final
        if (request.review.reviewId !== final.review.reviewId
          || request.requiredChecksDigest !== final.verification.requiredChecks.digest) {
          throw new GoalBindingError(
            'completion evidence must be the supplied final-merge evidence',
            'GOAL_BINDING_INVALID_REQUEST',
          )
        }
        admission = {
          ...admission,
          worktreePath: request.finalIntegration.targetPath,
          sourceFingerprint: final.verification.binding.sourceFingerprint,
          checks: final.verification.checks,
          requiredChecksDigest: final.verification.requiredChecks.digest,
          review: final.review,
        }
      }

      const verdict = await evaluateCompletionAdmission(admission)
      if (verdict.kind === 'rejected') return verdict

      if (request.finalIntegration !== undefined) {
        // Approved-check resolution may await storage after the first source observation.
        const finalSource = await verifySourceFingerprint(admission.worktreePath, admission.sourceFingerprint)
        if (finalSource.kind === 'mismatch') return { kind: 'rejected', stage: 'source-fingerprint', mismatch: finalSource }
      }
      request.beforeComplete?.()
      const completed = this.options.goals.complete({ id: current.id, revision: current.revision })
      assertNativeRevision(completed.revision)
      if (completed.id !== binding.goalId) {
        throw new GoalBindingError(
          `native complete returned Goal "${completed.id}" for "${binding.goalId}"`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      assertRevisionAdvance(current.revision, completed.revision)
      await this.saveBinding({ ...binding, goalRevision: completed.revision })
      return verdict
    })
  }

  /** Close model-step admission while retaining the current identity for resume. */
  closeAdmission(): void {
    this.admission = 'closed'
  }

  /**
   * Admit one correction/retest/review round for an exact bound Goal
   * (AT1-08): the call point after a `changes_required` completion rejection
   * sends work back to the same worker. The initial review consumes no round;
   * each admitted round is charged when it starts. Exhaustion returns the
   * rejection as data — remaining issues then require human input through the
   * human-authorized {@link GoalBindingController.resume} face, with no
   * replacement-member or new-run bypass through this seam. The injected Session
   * journal owns durable round accounting; retries for one cause reuse its receipt.
   * @param identity - controller Session and Goal identity returning to repair.
   * @param cause - Existing durable failure evidence that requires correction.
   * @param options - Live authority guards executed at the journal write boundary.
   * @returns the admitted verdict with the charged round number, or the
   *   `repair-limit-exhausted` rejection as data.
   * @throws {@link GoalBindingError} when the identity is unknown, foreign, or
   *   belongs to another workspace.
   */
  beginRepairRound(
    identity: GoalBindingIdentity, cause: DevFrameRepairCause, options: DevFrameAppendOptions = {},
  ): Promise<RepairRoundAdmission> {
    return this.enqueue(async () => {
      await this.ensureReady()
      const binding = this.findBinding(identity)
      if (this.options.repairAdmissions === undefined) throw new GoalBindingError(
        'Repair admission requires a durable controller Session journal', 'GOAL_BINDING_PERSISTENCE',
      )
      return await this.options.repairAdmissions.admit(identityOf(binding), cause, this.repairLimit, options)
    })
  }

  /**
   * Read the repair-round accounting for an exact bound Goal.
   * @param identity - controller Session and Goal identity to inspect.
   * @returns the validated limit, the rounds already charged, and the rounds
   *   still available (clamped at zero once exhausted).
   * @throws {@link GoalBindingError} when the identity is unknown, foreign, or
   *   belongs to another workspace.
   */
  repairRoundState(identity: GoalBindingIdentity): RepairRoundState {
    const binding = this.findBinding(identity)
    if (this.options.repairAdmissions === undefined) throw new GoalBindingError(
      'Repair admission requires a durable controller Session journal', 'GOAL_BINDING_PERSISTENCE',
    )
    return this.options.repairAdmissions.state(identityOf(binding), this.repairLimit)
  }

  /**
   * Return the currently admitted binding, if this process has one.
   * @returns a detached binding or `undefined` while admission is closed.
   */
  currentBinding(): GoalBinding | undefined {
    if (this.admission !== 'open' || this.activeIdentity === undefined) return undefined
    return this.findBinding(this.activeIdentity)
  }

  /**
   * Check one exact identity before a model or tool step is dispatched.
   * @param identity - identity carried by the proposed operation.
   * @returns the matching current binding.
   * @throws {@link GoalBindingError} when admission is closed or stale.
   */
  assertAdmitted(identity: GoalBindingIdentity): GoalBinding {
    if (this.admission !== 'open' || this.activeIdentity === undefined) {
      throw new GoalBindingError('Goal admission is closed', 'GOAL_BINDING_ADMISSION_CLOSED')
    }
    if (!sameIdentity(this.activeIdentity, identity)) {
      throw new GoalBindingError(
        `work identity does not match the admitted Goal "${this.activeIdentity.goalId}"`,
        'GOAL_BINDING_IDENTITY_MISMATCH',
      )
    }
    return this.findBinding(identity)
  }

  /**
   * Resolve an explicitly identified result, including results arriving after
   * a later Goal has started.
   * @param reference - identity and, when supplied, exact task/acceptance tuple.
   * @returns the historical binding that owns the result.
   */
  resolveResultBinding(reference: GoalBindingIdentity | GoalResultBinding): GoalBinding {
    const binding = this.findBinding(reference)
    if ('taskIds' in reference && 'acceptanceHash' in reference) {
      assertResultTuple(binding, reference)
    }
    return binding
  }

  /**
   * Whether a result identity belongs to the currently admitted Goal.
   * @param identity - result identity to test against the active binding.
   * @returns true only while admission is open and the identity matches the active binding.
   */
  isCurrent(identity: GoalBindingIdentity): boolean {
    return this.admission === 'open'
      && this.activeIdentity !== undefined
      && sameIdentity(this.activeIdentity, identity)
  }

  /** Wait until initial binding restoration has completed. */
  private async ensureReady(): Promise<void> {
    await this.ready
    if (this.loadFailure !== undefined) {
      throw new GoalBindingError(
        'Goal binding persistence could not be loaded',
        'GOAL_BINDING_PERSISTENCE',
        { cause: this.loadFailure },
      )
    }
    if (!this.loaded) {
      throw new GoalBindingError('Goal binding persistence is not ready', 'GOAL_BINDING_NOT_READY')
    }
  }

  /** Serialize starts and resumes per controller Session. */
  private enqueue<T>(operation: () => Promise<T>): Promise<T> {
    const run = this.tail.then(operation, operation)
    this.tail = run.then(() => undefined, () => undefined)
    return run
  }

  /**
   * Persist and cache one binding only after native disarm has completed.
   * With `adoptGeneration` the acceptance fields may change across the
   * strict revision advance (the resume lane's authorized checks adoption,
   * mirroring the projection's generation rule); every other difference
   * from the cached binding stays a conflict, and consumption may never
   * move backwards.
   */
  private async saveBinding(binding: GoalBinding, adoptGeneration = false): Promise<void> {
    const current = this.bindings.find(candidate => candidate.goalId === binding.goalId)
    const generationAdvance = adoptGeneration
      && current !== undefined
      && isGenerationAdvance(current, binding)
    if (current !== undefined && !generationAdvance
      && (!sameBinding(current, binding) || binding.goalRevision < current.goalRevision)) {
      throw new GoalBindingError(
        `Goal "${binding.goalId}" already has a different binding`,
        'GOAL_BINDING_CONFLICT',
      )
    }
    try {
      await this.options.store.save(binding)
      await this.options.store.write(toProjectBindingRecord(binding))
    } catch (error: unknown) {
      throw new GoalBindingError(
        `Goal binding "${binding.goalId}" could not be persisted`,
        'GOAL_BINDING_PERSISTENCE',
        { cause: error },
      )
    }
    if (current === undefined) this.bindings.push(copyBinding(binding))
    else this.bindings[this.bindings.indexOf(current)] = copyBinding(binding)
  }

  /** Find one binding by its complete stable identity. */
  private findBinding(identity: GoalBindingIdentity): GoalBinding {
    if (identity.controllerSessionId !== this.options.controllerSessionId) {
      throw new GoalBindingError(
        `binding belongs to controller "${identity.controllerSessionId}", not "${this.options.controllerSessionId}"`,
        'GOAL_BINDING_IDENTITY_MISMATCH',
      )
    }
    const binding = this.bindings.find(candidate => candidate.goalId === identity.goalId)
    if (binding === undefined) {
      throw new GoalBindingError(
        `no binding exists for Goal "${identity.goalId}"`,
        'GOAL_BINDING_NOT_FOUND',
      )
    }
    if (binding.workspaceId !== this.options.workspaceId) {
      throw new GoalBindingError(
        `Goal "${identity.goalId}" belongs to workspace "${binding.workspaceId}", not "${this.options.workspaceId}"`,
        'GOAL_BINDING_IDENTITY_MISMATCH',
      )
    }
    return copyBinding(binding)
  }

  /** Reject duplicate Goal identities restored from storage. */
  private assertLoadedIdentityUniqueness(): void {
    const ids = new Set<NativeGoalId>()
    for (const binding of this.bindings) {
      if (ids.has(binding.goalId)) {
        throw new GoalBindingError(
          `duplicate persisted binding for Goal "${binding.goalId}"`,
          'GOAL_BINDING_CONFLICT',
        )
      }
      ids.add(binding.goalId)
    }
  }
}

/**
 * Input for one completion admission evaluation: the three already-landed
 * predicates conjuncted by {@link evaluateCompletionAdmission}, in the fixed
 * evidence-chain order fingerprint → required checks → review.
 */
export interface CompletionAdmissionRequest {
  /**
   * Absolute path to any directory inside the git worktree the fingerprint is
   * recomputed against. The recompute is an explicit admission call (three
   * git subprocesses) and never runs on the binding hot path.
   */
  readonly worktreePath: string
  /** The recorded source fingerprint (e.g. `GoalResultBinding.sourceFingerprint`). */
  readonly sourceFingerprint: SourceFingerprint
  /** Real executed check results, e.g. `checks` from the decoded verification evidence. */
  readonly checks: readonly DevFrameCheckResult[]
  /** Canonical digest of the approved configuration, registered in the store at approval time. */
  readonly requiredChecksDigest: RequiredChecksDigest
  /** Configuration store resolving `requiredChecksDigest` to the stored approved checklist. */
  readonly requiredChecksStore: RequiredChecksConfigStore
  /**
   * The durable, gate-authorized review evidence: the journal write gate
   * already enforced reviewer authorization before this record entered the
   * log, so admission consumes only its pass decision.
   */
  readonly review: DevFrameReviewEventData
  /**
   * The graded memory-degradation records decoded from the task's session
   * log (AT3-07). A `fail` grade is the task's real failure evidence — the
   * acceptance required the memory operation — and refuses completion;
   * `complete-with-warning` records never reject.
   */
  readonly taskWarnings: readonly DevFrameTaskWarningEventData[]
}

/** Pass arm of the completion admission conjunction: all predicates hold. */
export interface CompletionAdmissionAdmitted {
  /** Discriminant tag of the {@link CompletionAdmissionVerdict} union. */
  readonly kind: 'admitted'
  /** The verified fingerprint: the recorded claim equals the fresh computation. */
  readonly fingerprint: SourceFingerprint
  /** Canonical identity of the stored configuration the evidence covered. */
  readonly requiredChecksDigest: RequiredChecksDigest
}

/**
 * Rejection at the first stage: the session log holds a memory degradation
 * graded `fail` for this task — the acceptance required the memory operation,
 * so the task's real outcome is failure, not completion.
 */
export interface CompletionTaskWarningRejection {
  /** Task identity of the durable warning used to request correction. */
  readonly taskId: DevFrameTaskWarningEventData['taskId']
  /** Discriminant tag of the {@link CompletionAdmissionVerdict} union. */
  readonly kind: 'rejected'
  /** Evaluation stage that rejected the completion. */
  readonly stage: 'task-warning'
  /** The verbatim memory failure classification of the fail-graded record. */
  readonly warning: DevFrameTaskWarningEventData['warning']
  /** The memory tool whose execution failed. */
  readonly tool: string
  /** The fail grade the host's explicit requirement context produced. */
  readonly grade: 'fail'
}

/** Rejection at the first stage: the worktree no longer matches the recorded fingerprint. */
export interface CompletionFingerprintRejection {
  /** Discriminant tag of the {@link CompletionAdmissionVerdict} union. */
  readonly kind: 'rejected'
  /** Evaluation stage that rejected the completion. */
  readonly stage: 'source-fingerprint'
  /** Dual-value evidence: the recorded claim vs the fresh computation. */
  readonly mismatch: SourceFingerprintMismatch
}

/** Rejection at the second stage: the evidence does not fully cover the stored approved checklist. */
export interface CompletionChecksRejection {
  /** Discriminant tag of the {@link CompletionAdmissionVerdict} union. */
  readonly kind: 'rejected'
  /** Evaluation stage that rejected the completion. */
  readonly stage: 'required-checks'
  /** The unsatisfied verdict; each violation's `reason` is the machine-routable code. */
  readonly verdict: RequiredChecksUnsatisfied
}

/** Rejection at the final stage: the authorized review did not pass. */
export interface CompletionReviewRejection {
  /** Discriminant tag of the {@link CompletionAdmissionVerdict} union. */
  readonly kind: 'rejected'
  /** Evaluation stage that rejected the completion. */
  readonly stage: 'review'
  /** Identity of the review that did not pass. */
  readonly reviewId: DevFrameReviewId
  /** The review's non-pass decision. */
  readonly decision: 'changes_required'
  /** Bounded findings explaining the non-pass decision. */
  readonly findings: readonly DevFrameReviewFinding[]
}

/** Why the supplied final-merge evidence cannot anchor this completion. */
export type FinalIntegrationRejectionReason =
  | 'coverage'
  | 'delivery-bound-evidence'
  | 'binding-mismatch'
  | 'reviewer-not-independent'

/** Rejection at the final-integration stage: the merged-result evidence is not usable as supplied. */
export interface CompletionFinalIntegrationRejection {
  /** Discriminant tag of the {@link CompletionAdmissionVerdict} union. */
  readonly kind: 'rejected'
  /** Evaluation stage that rejected the completion. */
  readonly stage: 'final-integration'
  /** Which final-merge obligation the evidence failed. */
  readonly reason: FinalIntegrationRejectionReason
  /** The bound task the evidence fails for, when the reason is task-scoped. */
  readonly taskId?: TaskId
}

/** Discriminated union returned by {@link evaluateCompletionAdmission} and {@link evaluateFinalIntegrationStage}. */
export type CompletionAdmissionVerdict =
  | CompletionAdmissionAdmitted
  | CompletionTaskWarningRejection
  | CompletionFingerprintRejection
  | CompletionChecksRejection
  | CompletionReviewRejection
  | CompletionFinalIntegrationRejection

/**
 * Evaluate the final-integration stage of one completion: whether the supplied
 * {@link FinalIntegrationContract} can anchor the completion at the final
 * merged result. The stage runs before the regular conjunction, which then
 * consumes the contract's evidence with the merged-tree fingerprint as the
 * recorded claim. Structural rules, each naming its obligation:
 *
 * - `coverage` — the contract's applied receipts name exactly the binding's
 *   task set: no bound task may lack its applied integration and no extra
 *   task may ride in.
 * - `delivery-bound-evidence` — both the verification and the review must be
 *   whole-Goal records (`deliveryId` absent). A delivery-bound record is one
 *   task's own evidence and cannot stand in for the final-merge gate.
 * - `binding-mismatch` — the verification and the review must carry the same
 *   work tuple; their common binding is what anchors the merged tree.
 * - `reviewer-not-independent` — the final review's Session must differ from
 *   every bound task's delivering worker Session.
 *
 * @param request - the contract plus the binding's task ids it must cover.
 * @returns the contract's verification and review when the stage holds, or
 *   the first failing obligation's rejection.
 */
export function evaluateFinalIntegrationStage(request: {
  readonly contract: FinalIntegrationContract
  readonly boundTaskIds: readonly TaskId[]
}): { kind: 'ok'; verification: DevFrameVerificationEventData; review: DevFrameReviewEventData }
  | CompletionFinalIntegrationRejection {
  const { contract, boundTaskIds } = request
  const contractTaskIds = contract.tasks.map(task => task.taskId)
  const missing = boundTaskIds.filter(id => !contractTaskIds.some(candidate => candidate === id))
  const extra = contract.tasks.filter(task => !boundTaskIds.some(id => id === task.taskId))
  if (missing.length > 0 || extra.length > 0) {
    const firstMissing = missing[0]
    const firstExtra = extra[0]
    if (firstMissing !== undefined) {
      return { kind: 'rejected', stage: 'final-integration', reason: 'coverage', taskId: firstMissing }
    }
    if (firstExtra !== undefined) {
      return { kind: 'rejected', stage: 'final-integration', reason: 'coverage', taskId: firstExtra.taskId }
    }
    return { kind: 'rejected', stage: 'final-integration', reason: 'coverage' }
  }
  if (contract.verification.deliveryId !== undefined || contract.review.deliveryId !== undefined) {
    return { kind: 'rejected', stage: 'final-integration', reason: 'delivery-bound-evidence' }
  }
  if (!sameResultBinding(contract.verification.binding, contract.review.binding)) {
    return { kind: 'rejected', stage: 'final-integration', reason: 'binding-mismatch' }
  }
  if (contract.workerSessionIds.some(worker => worker === contract.review.reviewerSessionId)) {
    return { kind: 'rejected', stage: 'final-integration', reason: 'reviewer-not-independent' }
  }
  return { kind: 'ok', verification: contract.verification, review: contract.review }
}

/** Compare the complete work identity of two result bindings; task order is not authority. */
function sameResultBinding(left: GoalResultBinding, right: GoalResultBinding): boolean {
  return left.controllerSessionId === right.controllerSessionId
    && left.goalId === right.goalId && left.goalRevision === right.goalRevision
    && left.workspaceId === right.workspaceId && left.acceptanceHash === right.acceptanceHash
    && left.sourceFingerprint === right.sourceFingerprint && left.snapshotId === right.snapshotId
    && left.taskIds.length === right.taskIds.length
    && left.taskIds.every(id => right.taskIds.includes(id))
}

/**
 * Completion admission for the AT1-05 completion domain: the conjunction of
 * four already-landed predicates, evaluated in the fixed evidence-chain
 * order — the graded task warnings first (they are the task's own recorded
 * outcome evidence and the cheapest invalidation: a `fail` grade means the
 * acceptance required a memory operation that failed, so no later evidence
 * can cure it), the fingerprint match second (it anchors which tree the
 * evidence is about), required checks third (they anchor what really ran on
 * that tree, against the configuration resolved from the store), and the
 * authorized review decision last (it anchors who judged). Rejections are
 * data carrying each stage's own evidence shape (recorded claim vs
 * trustworthy side). The recorded fingerprint is the caller's anchor claim:
 * the plain completion lane passes the binding's initial fingerprint, and the
 * final-merge lane passes the whole-Goal verification's merged-tree
 * fingerprint after {@link evaluateFinalIntegrationStage} validated the
 * contract, so the live recompute always names the tree the evidence claims.
 *
 * Structural errors fail loud and are never converted into rejections:
 * `SourceFingerprintError` codes from the fingerprint recompute and
 * `RequiredChecksError` codes from the store resolution
 * (`REQUIRED_CHECKS_CONFIG_NOT_FOUND`, `REQUIRED_CHECKS_INVALID_CONFIG`)
 * propagate to the caller unchanged.
 * @param request - worktree, recorded fingerprint, executed checks, registered
 *   configuration reference, the durable review evidence, and the graded
 *   memory-degradation records decoded from the task's session log.
 * @returns a {@link CompletionAdmissionAdmitted} verdict, or the rejection of
 *   the first failing stage.
 */
export async function evaluateCompletionAdmission(
  request: CompletionAdmissionRequest,
): Promise<CompletionAdmissionVerdict> {
  const failedWarning = request.taskWarnings.find(candidate => candidate.grade === 'fail')
  if (failedWarning !== undefined) {
    return {
      kind: 'rejected',
      stage: 'task-warning',
      taskId: failedWarning.taskId,
      warning: failedWarning.warning,
      tool: failedWarning.tool,
      grade: 'fail',
    }
  }
  const verify = await verifySourceFingerprint(request.worktreePath, request.sourceFingerprint)
  if (verify.kind === 'mismatch') {
    return { kind: 'rejected', stage: 'source-fingerprint', mismatch: verify }
  }
  const config = await request.requiredChecksStore.load(request.requiredChecksDigest)
  const verdict = evaluateRequiredChecks(config, request.checks)
  if (verdict.kind === 'unsatisfied') {
    return { kind: 'rejected', stage: 'required-checks', verdict }
  }
  if (request.review.decision !== 'pass') {
    return {
      kind: 'rejected',
      stage: 'review',
      reviewId: request.review.reviewId,
      decision: request.review.decision,
      findings: [...request.review.findings],
    }
  }
  return {
    kind: 'admitted',
    fingerprint: verify.fingerprint,
    requiredChecksDigest: request.requiredChecksDigest,
  }
}

/** Validate a user authorization capability before native Goal calls. */
function assertHumanAuthorization(value: unknown): asserts value is HumanAuthorization {
  if (typeof value !== 'object' || value === null
    || (value as { kind?: unknown }).kind !== 'human'
    || typeof (value as { confirmationId?: unknown }).confirmationId !== 'string'
    || !(value as Record<PropertyKey, unknown>)[HUMAN_AUTHORIZATION]) {
    throw new GoalBindingError(
      'Goal start and resume require host-issued human authorization',
      'GOAL_BINDING_AUTHORIZATION_REQUIRED',
    )
  }
}

/** Validate and detach one start request before mutating native state. */
function resolveStartRequest(request: StartGoalRequest): {
  readonly objective: string
  readonly taskIds: readonly TaskId[]
  readonly acceptanceHash: AcceptanceHash
  readonly sourceFingerprint: SourceFingerprint
  readonly snapshotId: DevFrameSnapshotId
  readonly budget: GoalBudget
  readonly maxGoalRounds?: number
} {
  const objective = request.objective.trim()
  if (objective.length === 0) {
    throw new GoalBindingError('Goal objective must be non-empty', 'GOAL_BINDING_INVALID_REQUEST')
  }
  if (request.taskIds.length === 0) {
    throw new GoalBindingError('Goal binding requires at least one task id', 'GOAL_BINDING_INVALID_REQUEST')
  }
  const taskIds = request.taskIds.map(value => TaskId(value))
  if (new Set(taskIds).size !== taskIds.length) {
    throw new GoalBindingError('Goal binding task ids must be unique', 'GOAL_BINDING_INVALID_REQUEST')
  }
  const acceptance = makeAcceptanceHash(nonEmptyId(request.acceptanceHash, 'acceptanceHash'))
  const sourceFingerprint = makeSourceFingerprint(nonEmptyId(request.sourceFingerprint, 'sourceFingerprint'))
  const snapshotId = makeSnapshotId(nonEmptyId(request.snapshotId, 'snapshotId'))
  const budget = resolveBudget(request.budget)
  const maxGoalRounds = request.maxGoalRounds
  if (maxGoalRounds !== undefined && (!Number.isSafeInteger(maxGoalRounds) || maxGoalRounds < 1)) {
    throw new GoalBindingError('maxGoalRounds must be a positive safe integer', 'GOAL_BINDING_INVALID_REQUEST')
  }
  return {
    objective,
    taskIds,
    acceptanceHash: acceptance,
    sourceFingerprint,
    snapshotId,
    budget,
    ...maxGoalRounds === undefined ? {} : { maxGoalRounds },
  }
}

/** Validate the native CAS revision before persisting or resuming a binding. */
function assertNativeRevision(revision: number): void {
  if (!Number.isSafeInteger(revision) || revision < 1) {
    throw new GoalBindingError(
      'native Goal revision must be a positive safe integer',
      'GOAL_BINDING_INVALID_REQUEST',
    )
  }
}

/** Require native resume to publish the next compare-and-set revision. */
function assertRevisionAdvance(previous: number, next: number): void {
  assertNativeRevision(next)
  if (next !== previous + 1) {
    throw new GoalBindingError(
      `native Goal resume must advance revision from ${previous} to ${previous + 1}; received ${next}`,
      'GOAL_BINDING_IDENTITY_MISMATCH',
    )
  }
}

/**
 * Restrict the stop request to lifecycles from which `stop_requested` is a
 * legal fold transition (the projection's lifecycle graph: ambiguous,
 * admission_open, and needs_attention may enter stop_requested; a pending or
 * reached stop must not issue a second request).
 */
function assertStoppableLifecycle(lifecycle: GoalBinding['lifecycle']): void {
  if (lifecycle !== 'admission_open' && lifecycle !== 'ambiguous' && lifecycle !== 'needs_attention') {
    throw new GoalBindingError(
      `Goal lifecycle "${lifecycle}" cannot enter stop_requested; a stop is already pending or reached`,
      'GOAL_BINDING_INVALID_REQUEST',
    )
  }
}

/** Validate and materialize one immutable budget. */
function resolveBudget(input: GoalBudgetInput): GoalBudget {
  const consumedAttempts = input.consumedAttempts ?? 0
  if (!Number.isSafeInteger(input.maxAttempts) || input.maxAttempts < 1
    || !Number.isSafeInteger(consumedAttempts) || consumedAttempts < 0
    || consumedAttempts > input.maxAttempts) {
    throw new GoalBindingError(
      'Goal budget requires maxAttempts >= 1 and consumedAttempts within its limit',
      'GOAL_BINDING_INVALID_REQUEST',
    )
  }
  return { maxAttempts: input.maxAttempts, consumedAttempts }
}

/** Validate one non-empty identifier before applying its compile-time brand. */
function nonEmptyId(value: string, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0 || value !== value.trim()) {
    throw new GoalBindingError(`${field} must be a non-empty trimmed string`, 'GOAL_BINDING_INVALID_REQUEST')
  }
  return value
}

/** Return one stable identity projection from a full binding. */
function identityOf(binding: GoalBinding): GoalBindingIdentity {
  return {
    controllerSessionId: binding.controllerSessionId,
    goalId: binding.goalId,
  }
}

/** Compare the stable pair that owns a run or result. */
function sameIdentity(left: GoalBindingIdentity, right: GoalBindingIdentity): boolean {
  return left.controllerSessionId === right.controllerSessionId && left.goalId === right.goalId
}

/** Compare the immutable work tuple while allowing lifecycle transitions. */
function sameBinding(left: GoalBinding, right: GoalBinding): boolean {
  return sameIdentity(left, right)
    && left.workspaceId === right.workspaceId
    && left.acceptanceHash === right.acceptanceHash
    && left.sourceFingerprint === right.sourceFingerprint
    && left.snapshotId === right.snapshotId
    && left.confirmation.id === right.confirmation.id
    && left.confirmation.acceptanceHash === right.confirmation.acceptanceHash
    && left.budget.maxAttempts === right.budget.maxAttempts
    && left.budget.consumedAttempts === right.budget.consumedAttempts
    && left.taskIds.length === right.taskIds.length
    && left.taskIds.every((id, index) => id === right.taskIds[index])
}

/**
 * Whether one binding update is a legal generation advance over the stored
 * one: the structural identity is unchanged, the native revision strictly
 * advances, and consumption never moves backwards. A generation advance may
 * carry changed acceptance fields (hash and confirmation) — the resume
 * lane's authorized adoption of changed approved checks (AT1-10: changing
 * checks invalidates the superseded generation's evidence without resetting
 * usage). Any other difference stays an identity-reuse conflict.
 */
export function isGenerationAdvance(current: GoalBinding, binding: GoalBinding): boolean {
  return binding.goalRevision > current.goalRevision
    && current.workspaceId === binding.workspaceId
    && current.controllerSessionId === binding.controllerSessionId
    && current.goalId === binding.goalId
    && current.sourceFingerprint === binding.sourceFingerprint
    && current.snapshotId === binding.snapshotId
    && current.budget.maxAttempts === binding.budget.maxAttempts
    && current.budget.consumedAttempts <= binding.budget.consumedAttempts
    && current.taskIds.length === binding.taskIds.length
    && current.taskIds.every((id, index) => id === binding.taskIds[index])
}

/** Compare the shared persisted projection restored for the current workspace. */
function sameProjectBinding(binding: GoalBinding, record: ProjectBindingRecord): boolean {
  return binding.workspaceId === record.workspaceId
    && binding.controllerSessionId === record.controllerSessionId
    && binding.goalId === record.goalId
    && binding.goalRevision === record.goalRevision
    && binding.acceptanceHash === record.acceptanceHash
    && binding.sourceFingerprint === record.sourceFingerprint
    && binding.confirmation.id === record.confirmation.id
    && binding.confirmation.acceptanceHash === record.confirmation.acceptanceHash
    && binding.lifecycle === record.lifecycle
}

/** Project the controller binding onto the shared persistence contract. */
function toProjectBindingRecord(binding: GoalBinding): ProjectBindingRecord {
  return {
    workspaceId: binding.workspaceId,
    controllerSessionId: binding.controllerSessionId,
    goalId: binding.goalId,
    goalRevision: binding.goalRevision,
    acceptanceHash: binding.acceptanceHash,
    sourceFingerprint: binding.sourceFingerprint,
    confirmation: { ...binding.confirmation },
    lifecycle: binding.lifecycle,
  }
}

/** Detach a shared persistence record before exposing it to a caller. */
function copyProjectBindingRecord(record: ProjectBindingRecord): ProjectBindingRecord {
  return {
    workspaceId: record.workspaceId,
    controllerSessionId: record.controllerSessionId,
    goalId: record.goalId,
    goalRevision: record.goalRevision,
    acceptanceHash: record.acceptanceHash,
    sourceFingerprint: record.sourceFingerprint,
    confirmation: { ...record.confirmation },
    lifecycle: record.lifecycle,
  }
}

/** Reject a result that carries another Goal's task, acceptance, or snapshot tuple. */
function assertResultTuple(binding: GoalBinding, reference: GoalResultBinding): void {
  if (binding.workspaceId !== reference.workspaceId
    || binding.sourceFingerprint !== reference.sourceFingerprint
    || binding.snapshotId !== reference.snapshotId
    || binding.goalRevision !== reference.goalRevision
    || binding.acceptanceHash !== reference.acceptanceHash
    || binding.taskIds.length !== reference.taskIds.length
    || !binding.taskIds.every((id, index) => id === reference.taskIds[index])) {
    throw new GoalBindingError(
      `result tuple does not match Goal "${binding.goalId}" binding`,
      'GOAL_BINDING_IDENTITY_MISMATCH',
    )
  }
}

/** Detach nested arrays and budget values before returning a binding. */
function copyBinding(binding: GoalBinding): GoalBinding {
  return {
    version: 1,
    workspaceId: binding.workspaceId,
    controllerSessionId: binding.controllerSessionId,
    goalId: binding.goalId,
    goalRevision: binding.goalRevision,
    taskIds: [...binding.taskIds],
    acceptanceHash: binding.acceptanceHash,
    sourceFingerprint: binding.sourceFingerprint,
    snapshotId: binding.snapshotId,
    confirmation: { ...binding.confirmation },
    lifecycle: binding.lifecycle,
    budget: {
      maxAttempts: binding.budget.maxAttempts,
      consumedAttempts: binding.budget.consumedAttempts,
    },
  }
}
