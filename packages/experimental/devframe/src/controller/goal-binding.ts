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
} from '../events.ts'
import { evaluateRequiredChecks } from '../required-checks.ts'
import type {
  RequiredChecksConfigStore,
  RequiredChecksDigest,
  RequiredChecksUnsatisfied,
} from '../required-checks.ts'
import { evaluateRepairRoundAdmission, resolveRepairLimit } from '../repair-limit.ts'
import type { RepairRoundAdmission } from '../repair-limit.ts'
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

/** Durable storage needed by the controller. Implementations may use JSONL, SQLite, or memory. */
export interface GoalBindingStore extends ProjectBindingPersistence {
  /** Load every binding for one controller Session, including completed Goals. */
  load(controllerSessionId: ControllerSessionId): Promise<readonly GoalBinding[]>
  /** Persist one immutable binding; identical retries must be idempotent. */
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
  async load(controllerSessionId: ControllerSessionId): Promise<readonly GoalBinding[]> {
    return this.values.get(controllerSessionId)?.map(copyBinding) ?? []
  }

  /** Read the current shared project binding for one workspace. */
  async read(workspaceId: WorkspaceId): Promise<ProjectBindingRecord | undefined> {
    const record = this.current.get(workspaceId)
    return record === undefined ? undefined : copyProjectBindingRecord(record)
  }

  /** Write the current shared project binding for one workspace. */
  async write(record: ProjectBindingRecord): Promise<void> {
    this.current.set(record.workspaceId, copyProjectBindingRecord(record))
  }

  /**
   * Save one binding, accepting an identical retry and rejecting identity reuse
   * with changed task, acceptance, or budget data.
   * @param binding - immutable Goal binding to retain.
   */
  async save(binding: GoalBinding): Promise<void> {
    const records = this.values.get(binding.controllerSessionId) ?? []
    const index = records.findIndex(record => record.goalId === binding.goalId)
    if (index !== -1) {
      const current = records[index]
      if (current !== undefined && sameBinding(current, binding)
        && binding.goalRevision >= current.goalRevision) {
        records[index] = copyBinding(binding)
        this.values.set(binding.controllerSessionId, records)
        return
      }
      throw new GoalBindingError(
        `Goal "${binding.goalId}" already has a different binding`,
        'GOAL_BINDING_CONFLICT',
      )
    }
    records.push(copyBinding(binding))
    this.values.set(binding.controllerSessionId, records)
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
  /** Mark the current native Goal complete at one exact revision and disarm it. */
  complete(ref: { readonly id: NativeGoalId; readonly revision: number }): NativeGoalState
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

  complete(ref: { readonly id: NativeGoalId; readonly revision: number }): NativeGoalState {
    return toNativeGoalState(this.options.goals.complete(this.options.agent, ref))
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
 * Evidence-side input for one controller completion attempt: everything
 * {@link evaluateCompletionAdmission} consumes except the recorded source
 * fingerprint, which {@link GoalBindingController.complete} takes from the
 * durable binding instead of trusting the caller.
 */
export interface CompleteGoalRequest {
  /**
   * Absolute path to any directory inside the git worktree the fingerprint is
   * recomputed against; the recompute is an explicit admission call (three
   * git subprocesses) and never runs on the binding hot path.
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
   * decision, and the controller rejects evidence naming another Goal.
   */
  readonly review: DevFrameReviewEventData
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

/** Construction dependencies for one controller Session. */
export interface GoalBindingControllerOptions {
  readonly workspaceId: WorkspaceId
  readonly controllerSessionId: ControllerSessionId
  readonly goals: NativeGoalPort
  readonly store: GoalBindingStore
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
  /** Repair rounds charged per Goal in this process; the initial review consumes none. */
  private readonly repairRounds = new Map<NativeGoalId, number>()

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
      }, (error) => {
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
   * @returns the historical binding retained for the resumed Goal.
   */
  resume(identity: GoalBindingIdentity, authorization: HumanAuthorization): Promise<GoalBinding> {
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

      const resumed = this.options.goals.resume({ id: current.id, revision: current.revision })
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
      }
      await this.saveBinding(admitted)
      this.activeIdentity = identityOf(admitted)
      this.admission = 'open'
      return copyBinding(admitted)
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
   *   attributed to this Goal.
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
          `completion review evidence is recorded under controller Session`
            + ` "${reviewBinding.controllerSessionId}", not "${binding.controllerSessionId}"`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }
      if (reviewBinding.workspaceId !== binding.workspaceId) {
        throw new GoalBindingError(
          `completion review evidence is recorded for workspace`
            + ` "${reviewBinding.workspaceId}", not "${binding.workspaceId}"`,
          'GOAL_BINDING_IDENTITY_MISMATCH',
        )
      }

      const verdict = await evaluateCompletionAdmission({
        worktreePath: request.worktreePath,
        sourceFingerprint: binding.sourceFingerprint,
        checks: request.checks,
        requiredChecksDigest: request.requiredChecksDigest,
        requiredChecksStore: request.requiredChecksStore,
        review: request.review,
      })
      if (verdict.kind === 'rejected') return verdict

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
   * replacement-member or new-run bypass through this seam. Round accounting
   * is per Goal in this controller instance; the durable side of the cycle is
   * the evidence chain itself — each round's re-review must be fresh,
   * gate-authorized evidence naming this Goal with a new snapshot
   * (`docs/detailDesign-part1.md`), which {@link GoalBindingController.complete}
   * already consumes by exact identity.
   * @param identity - controller Session and Goal identity returning to repair.
   * @returns the admitted verdict with the charged round number, or the
   *   `repair-limit-exhausted` rejection as data.
   * @throws {@link GoalBindingError} when the identity is unknown, foreign, or
   *   belongs to another workspace.
   */
  beginRepairRound(identity: GoalBindingIdentity): Promise<RepairRoundAdmission> {
    return this.enqueue(async () => {
      await this.ensureReady()
      const binding = this.findBinding(identity)
      const verdict = evaluateRepairRoundAdmission({
        repairLimit: this.repairLimit,
        consumedRepairRounds: this.repairRounds.get(binding.goalId) ?? 0,
      })
      if (verdict.kind === 'admitted') this.repairRounds.set(binding.goalId, verdict.repairRound)
      return verdict
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
  repairRoundState(identity: GoalBindingIdentity): {
    readonly repairLimit: number
    readonly consumedRepairRounds: number
    readonly remainingRepairRounds: number
  } {
    const binding = this.findBinding(identity)
    const consumedRepairRounds = this.repairRounds.get(binding.goalId) ?? 0
    return {
      repairLimit: this.repairLimit,
      consumedRepairRounds,
      remainingRepairRounds: Math.max(0, this.repairLimit - consumedRepairRounds),
    }
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

  /** Persist and cache one binding only after native disarm has completed. */
  private async saveBinding(binding: GoalBinding): Promise<void> {
    const current = this.bindings.find(candidate => candidate.goalId === binding.goalId)
    if (current !== undefined && (!sameBinding(current, binding) || binding.goalRevision < current.goalRevision)) {
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
}

/** Pass arm of the completion admission conjunction: all three predicates hold. */
export interface CompletionAdmissionAdmitted {
  /** Discriminant tag of the {@link CompletionAdmissionVerdict} union. */
  readonly kind: 'admitted'
  /** The verified fingerprint: the recorded claim equals the fresh computation. */
  readonly fingerprint: SourceFingerprint
  /** Canonical identity of the stored configuration the evidence covered. */
  readonly requiredChecksDigest: RequiredChecksDigest
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

/** Discriminated union returned by {@link evaluateCompletionAdmission}. */
export type CompletionAdmissionVerdict =
  | CompletionAdmissionAdmitted
  | CompletionFingerprintRejection
  | CompletionChecksRejection
  | CompletionReviewRejection

/**
 * Completion admission for the AT1-05 completion domain: the conjunction of
 * three already-landed predicates, evaluated in the fixed evidence-chain
 * order — fingerprint match first (it anchors which tree the evidence is
 * about and is the cheapest invalidation), required checks second (they
 * anchor what really ran on that tree, against the configuration resolved
 * from the store), and the authorized review decision last (it anchors who
 * judged). Rejections are data carrying each stage's own evidence shape
 * (recorded claim vs trustworthy side); this face adds no new predicate.
 *
 * Structural errors fail loud and are never converted into rejections:
 * `SourceFingerprintError` codes from the fingerprint recompute and
 * `RequiredChecksError` codes from the store resolution
 * (`REQUIRED_CHECKS_CONFIG_NOT_FOUND`, `REQUIRED_CHECKS_INVALID_CONFIG`)
 * propagate to the caller unchanged.
 * @param request - worktree, recorded fingerprint, executed checks, registered
 *   configuration reference, and the durable review evidence.
 * @returns a {@link CompletionAdmissionAdmitted} verdict, or the rejection of
 *   the first failing stage.
 */
export async function evaluateCompletionAdmission(
  request: CompletionAdmissionRequest,
): Promise<CompletionAdmissionVerdict> {
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
