/**
 * The project controller (`ctx.projectController`): the Cordis service that
 * owns the project task board and the project lifecycle.
 *
 * Task dispatch follows the shared `TaskState` order
 * (`planned → assigned → developing → reviewing → submitted → integrated →
 * completed`); every move into `blocked` or `failed` must carry a reason, a
 * next action, and a wake condition, and a resume re-enters dispatch through
 * `assigned`. The `developing` budget is bounded by the `maxActiveTasks`
 * config (default 2, aligned with the two-model-request account ceiling).
 * Main-tree integration is gated twice: only a session bound as
 * `controller` may mint a merge marker, and a marker is required — and
 * consumed — by the `integrate` move.
 *
 * Records persist through the `project_tasks` storage domain and are
 * restored verbatim on start. The lifecycle itself is process-local run
 * state: a fresh process starts `stopped` and the host calls
 * {@link ProjectController.startProject} to open admission, mirroring the
 * writer-ownership rule that a human restart re-opens a project.
 *
 * @module @deepseek-ai/dsh-experimental-project-controller/controller
 */

import { randomUUID } from 'node:crypto'
import z from '@deepseek-ai/schemastery'
import { Service, type Context } from '@deepseek-ai/cordis'
import type { Domain, KvTable } from '@deepseek-ai/dsh-storage-domain'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { ProjectLifecycleState } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { evaluateCompletionAdmission } from '@deepseek-ai/dsh-experimental-devframe/controller'
import type { RequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {} from '@deepseek-ai/dsh-worktree-registry'
import type {} from '@deepseek-ai/dsh-workspace'
import type { PluginId, TaskId, TaskRecord, TaskState } from '@deepseek-ai/dsh-experimental-project-contracts'
// Loads the session-identity Context augmentation so `ctx.agentBindings` types the merge-gate lookup.
import type {} from '@deepseek-ai/dsh-experimental-session-identity'
import { ProjectControllerError } from './errors.ts'
import { projectTasksDomainSpec, type MainTreeIntegrationRecord } from './spec.ts'
import { selectIntegrationEvidence } from './integration-evidence.ts'
import {
  executeIntegrationGit,
  inspectIntegrationGit,
  reconcileIntegrationGit,
  type IntegrationGitOptions,
  type IntegrationGitRequest,
  type IntegrationGitObservation,
} from './git-integration.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    projectController: ProjectController
  }
}

/** Plugin config (all optional — `static Config` supplies the defaults). */
export interface ProjectControllerConfig {
  /**
   * Maximum tasks simultaneously in `developing`. The default 2 aligns the
   * dispatch budget with the two-model-request account ceiling.
   */
  readonly maxActiveTasks?: number
  /**
   * Cumulative request budget charged to this project (AT4-05): the maximum
   * granted-and-billed model requests the run may send, raced by controller
   * and child sessions through {@link ProjectController.chargeModelRequest}.
   * Charging is durable, so provider retries and process restarts never reset
   * usage. The default 1 mirrors the acceptance-named scenario (请求预算=1);
   * deployments raise it via cordis.yml.
   */
  readonly requestBudget?: number
}

/** The config shape after schemastery applied the default. */
type ResolvedConfig = Required<ProjectControllerConfig>

/** The reason/next-action/wake-condition triple a `blocked` or `failed` move must carry. */
export interface TaskBlockDetail {
  /** Why the task stopped making progress. */
  readonly blockedReason: string
  /** What must happen next. */
  readonly nextAction: string
  /** What unblocks the task. */
  readonly wakeCondition: string
}

/** The receipt minted by the controller-only main-tree merge gate. */
export interface MainTreeMergeMarker {
  /** Stable marker identity; consumed exactly once by `integrate`. */
  readonly mergeId: string
  /** The task the marker merges. */
  readonly taskId: TaskId
  /** The controller session that triggered the merge. */
  readonly callerSessionId: SessionId
  /** ISO-8601 minting instant. */
  readonly createdAt: string
}

/** Host authority recheck at the task mutation's serialized persistence boundary. */
export interface TaskMutationOptions {
  /** Synchronous check run immediately before the task write; a throw prevents that write. */
  readonly beforePersist?: () => void
}

/** Host-owned merge preparation; evidence itself is read from the controller Session projection. */
export interface MainTreeMergeRequest {
  /** Exact source and target selected by the registered worktree owners. */
  readonly git: IntegrationGitRequest
  /** Deployment-resolved process limits. */
  readonly options: IntegrationGitOptions
  /** Existing approved-checks store; never supplied by model JSON. */
  readonly requiredChecksStore: RequiredChecksConfigStore
  /** Explicitly re-admit an unchanged prepared operation; never enabled by normal dispatch. */
  readonly retryUnchanged?: boolean
  /** Host cancellation, retained only for the live attempt. */
  readonly signal?: AbortSignal
}

/** Receipt for one model request charged against the project request budget. */
export interface RequestChargeReceipt {
  /** Cumulative charged requests after this charge. */
  readonly chargedRequests: number
  /** The configured cumulative budget. */
  readonly requestBudget: number
  /** Budget units left after this charge. */
  readonly remainingRequests: number
}

/** The states a task may be blocked or failed from: every active state. */
const BLOCKABLE_STATES: readonly TaskState[] = ['planned', 'assigned', 'developing', 'reviewing', 'submitted']

/** The states that carry in-flight model work and hold quiescence back. */
const IN_FLIGHT_STATES: readonly TaskState[] = ['assigned', 'developing', 'reviewing']

/** The project lifecycle states that still admit or record task moves. */
const OPEN_LIFECYCLES: readonly ProjectLifecycleState[] = ['admission_open', 'stop_requested', 'needs_attention', 'ambiguous']

/** Whether a non-empty trimmed string carries the value. */
function assertDetailField(value: string, field: string): void {
  if (typeof value !== 'string' || value.length === 0 || value !== value.trim()) {
    throw new ProjectControllerError(
      `${field} must be a non-empty trimmed string`,
      'PROJECT_CONTROLLER_INVALID_DETAIL',
    )
  }
}

/** Stamp the common fields of one state move onto a current record. */
function stamped(current: TaskRecord, state: TaskState): TaskRecord {
  return { ...current, state, updatedAt: new Date().toISOString() }
}

/** The project controller: task board, dispatch budget, lifecycle, and merge gate. */
export class ProjectController extends Service {
  static inject = ['agentBindings', 'storageDomain']

  static Config: z<ProjectControllerConfig> = z.object({
    maxActiveTasks: z.number().default(2),
    requestBudget: z.number().default(1),
  })

  /** Validated config (schemastery applied the defaults before construction). */
  private readonly config: ResolvedConfig

  private domain?: Domain<typeof projectTasksDomainSpec>
  private table?: KvTable<TaskId, TaskRecord>
  private readonly tasks = new Map<TaskId, TaskRecord>()
  private readonly pendingMarkers = new Map<string, MainTreeMergeMarker>()
  private readonly pendingGit = new Map<string, MainTreeMergeRequest>()
  private lifecycleState: ProjectLifecycleState = 'stopped'
  /** In-process mirror of the durable request-budget usage global. */
  private chargedRequests = 0
  private requestChargeFailure?: ProjectControllerError
  private tail: Promise<unknown> = Promise.resolve()

  /**
   * @param ctx - Mounting context.
   * @param config - Schema-validated config; `maxActiveTasks` and
   *   `requestBudget` must be positive safe integers.
   */
  constructor(ctx: Context, config: ProjectControllerConfig) {
    super(ctx, 'projectController')
    // Schemastery fills the default before construction; the type does not encode that step.
    this.config = config as ResolvedConfig
    if (!Number.isSafeInteger(this.config.maxActiveTasks) || this.config.maxActiveTasks < 1) {
      throw new ProjectControllerError(
        'maxActiveTasks must be a positive safe integer',
        'PROJECT_CONTROLLER_INVALID_CONFIG',
      )
    }
    if (!Number.isSafeInteger(this.config.requestBudget) || this.config.requestBudget < 1) {
      throw new ProjectControllerError(
        'requestBudget must be a positive safe integer',
        'PROJECT_CONTROLLER_INVALID_CONFIG',
      )
    }
  }

  protected async [Service.init](): Promise<void> {
    const domain = await this.ctx.storageDomain.open(projectTasksDomainSpec)
    this.ctx.effect(() => async () => {
      this.lifecycleState = 'stopped'
      await this.tail
      this.pendingMarkers.clear()
      this.pendingGit.clear()
      await domain.close()
    }, 'project-controller.domainClose')
    this.domain = domain
    this.table = domain.table('tasks')
    // Cold restore: the board comes back verbatim; in-flight records need the
    // host's attention because their live workers died with the old process.
    // The map holds a detached frozen copy so the durable row stays untouched.
    for (const [id, record] of [...this.table.entries()]
      .sort(([leftId, left], [rightId, right]) =>
        left.createdAt.localeCompare(right.createdAt) || String(leftId).localeCompare(String(rightId)))) {
      this.tasks.set(id, Object.freeze({ ...record }))
    }
    // Charged request usage survives the restart: a resumed run re-enters
    // dispatch with the budget already spent by its earlier requests.
    this.chargedRequests = domain.global.get().chargedRequests
  }

  // ---- project lifecycle -------------------------------------------------

  /** The current process-local project lifecycle; a fresh process starts `stopped`. */
  get lifecycle(): ProjectLifecycleState {
    return this.lifecycleState
  }

  /**
   * Open project admission after a fresh boot or a completed stop.
   * @returns the new lifecycle state.
   */
  startProject(): ProjectLifecycleState {
    return this.moveLifecycle('stopped', 'admission_open')
  }

  /**
   * Begin the stop: admission closes and in-flight work must drain.
   * @returns the new lifecycle state.
   */
  requestStop(): ProjectLifecycleState {
    if (this.lifecycleState !== 'admission_open' && this.lifecycleState !== 'needs_attention') {
      throw new ProjectControllerError(
        `requestStop requires admission_open or needs_attention, got ${this.lifecycleState}`,
        'PROJECT_CONTROLLER_ILLEGAL_TRANSITION',
      )
    }
    this.lifecycleState = 'stop_requested'
    return this.lifecycleState
  }

  /**
   * Confirm quiescence: every task must be out of in-flight work.
   * @returns the new lifecycle state.
   */
  confirmQuiescence(): ProjectLifecycleState {
    if (this.lifecycleState !== 'stop_requested') {
      throw new ProjectControllerError(
        `confirmQuiescence requires stop_requested, got ${this.lifecycleState}`,
        'PROJECT_CONTROLLER_ILLEGAL_TRANSITION',
      )
    }
    const inFlight = this.list().filter(record => IN_FLIGHT_STATES.includes(record.state))
    if (inFlight.length > 0) {
      throw new ProjectControllerError(
        `quiescence cannot be confirmed while ${inFlight.length} task(s) are in flight: `
          + inFlight.map(record => String(record.taskId)).join(', '),
        'PROJECT_CONTROLLER_QUIESCENCE_INCOMPLETE',
      )
    }
    this.lifecycleState = 'quiescence_confirmed'
    return this.lifecycleState
  }

  /**
   * Complete the stop after the writer-release commit.
   * @returns the new lifecycle state.
   */
  completeStop(): ProjectLifecycleState {
    return this.moveLifecycle('quiescence_confirmed', 'stopped')
  }

  /**
   * Record that the project needs host attention.
   * @returns the new lifecycle state.
   */
  markNeedsAttention(): ProjectLifecycleState {
    if (this.lifecycleState !== 'admission_open' && this.lifecycleState !== 'stop_requested'
      && this.lifecycleState !== 'ambiguous') {
      throw new ProjectControllerError(
        `markNeedsAttention cannot follow ${this.lifecycleState}`,
        'PROJECT_CONTROLLER_ILLEGAL_TRANSITION',
      )
    }
    this.lifecycleState = 'needs_attention'
    return this.lifecycleState
  }

  /**
   * Record that the project's durable state cannot be interpreted right now.
   * @returns the new lifecycle state.
   */
  markAmbiguous(): ProjectLifecycleState {
    if (this.lifecycleState === 'stopped') {
      throw new ProjectControllerError(
        'markAmbiguous cannot follow stopped',
        'PROJECT_CONTROLLER_ILLEGAL_TRANSITION',
      )
    }
    this.lifecycleState = 'ambiguous'
    return this.lifecycleState
  }

  /** Move between two exact lifecycle states or fail loud. */
  private moveLifecycle(from: ProjectLifecycleState, to: ProjectLifecycleState): ProjectLifecycleState {
    if (this.lifecycleState !== from) {
      throw new ProjectControllerError(
        `lifecycle move ${from} → ${to} requires ${from}, got ${this.lifecycleState}`,
        'PROJECT_CONTROLLER_ILLEGAL_TRANSITION',
      )
    }
    this.lifecycleState = to
    return this.lifecycleState
  }

  // ---- task board --------------------------------------------------------

  /**
   * Add one task in the `planned` state.
   * @param request - Task identity, plugin scope, and title.
   * @param options - Host authority guard at the serialized write boundary.
   * @returns the stored record.
   */
  async createTask(
    request: { readonly taskId: TaskId; readonly pluginId: PluginId; readonly title: string },
    options: TaskMutationOptions = {},
  ): Promise<TaskRecord> {
    return await this.enqueue(async () => {
      this.requireAdmissionOpen()
      if (this.tasks.has(request.taskId)) {
        throw new ProjectControllerError(`task "${String(request.taskId)}" already exists`, 'PROJECT_CONTROLLER_TASK_EXISTS')
      }
      if (request.title.length === 0 || request.title !== request.title.trim()) {
        throw new ProjectControllerError('title must be a non-empty trimmed string', 'PROJECT_CONTROLLER_INVALID_DETAIL')
      }
      const now = new Date().toISOString()
      const record: TaskRecord = Object.freeze({
        taskId: request.taskId,
        pluginId: request.pluginId,
        title: request.title,
        state: 'planned',
        createdAt: now,
        updatedAt: now,
      })
      options.beforePersist?.()
      return await this.persist(record)
    })
  }

  /**
   * Assign a planned task to a session.
   * @param taskId - Task to move.
   * @param assigneeSessionId - Session bound to execute the task.
   * @param options - Host authority guard at the serialized write boundary.
   * @returns the updated record.
   */
  async assign(taskId: TaskId, assigneeSessionId: SessionId, options: TaskMutationOptions = {}): Promise<TaskRecord> {
    return await this.enqueue(async () => {
      const current = this.requireTask(taskId)
      this.requireTransition(current, 'planned', 'assigned')
      this.requireAdmissionOpen()
      options.beforePersist?.()
      return await this.persist({ ...stamped(current, 'assigned'), assigneeSessionId })
    })
  }

  /**
   * Move an assigned task into development, consuming one dispatch slot.
   * @param taskId - Task to move.
   * @param options - Host authority guard at the serialized write boundary.
   * @returns the updated record.
   */
  async startDevelopment(taskId: TaskId, options: TaskMutationOptions = {}): Promise<TaskRecord> {
    return await this.enqueue(async () => {
      const current = this.requireTask(taskId)
      this.requireTransition(current, 'assigned', 'developing')
      this.requireAdmissionOpen()
      const developing = this.list().filter(record => record.state === 'developing').length
      if (developing >= this.config.maxActiveTasks) {
        throw new ProjectControllerError(
          `the developing budget of ${this.config.maxActiveTasks} is exhausted`,
          'PROJECT_CONTROLLER_CONCURRENCY_EXCEEDED',
        )
      }
      options.beforePersist?.()
      return await this.persist(stamped(current, 'developing'))
    })
  }

  /**
   * Move a developing task into lead review.
   * @param taskId - Task to move.
   * @param options - Host authority guard at the serialized write boundary.
   * @returns the updated record.
   */
  async beginReview(taskId: TaskId, options: TaskMutationOptions = {}): Promise<TaskRecord> {
    return await this.enqueue(async () => {
      const current = this.requireTask(taskId)
      this.requireTransition(current, 'developing', 'reviewing')
      this.requireAdmissionOpen()
      options.beforePersist?.()
      return await this.persist(stamped(current, 'reviewing'))
    })
  }

  /**
   * Submit a reviewed task for integration.
   * @param taskId - Task to move.
   * @param options - Host authority guard at the serialized write boundary.
   * @returns the updated record.
   */
  async submit(taskId: TaskId, options: TaskMutationOptions = {}): Promise<TaskRecord> {
    return await this.enqueue(async () => {
      const current = this.requireTask(taskId)
      this.requireTransition(current, 'reviewing', 'submitted')
      this.requireAdmissionOpen()
      options.beforePersist?.()
      return await this.persist(stamped(current, 'submitted'))
    })
  }

  /**
   * Return a reviewed task for correction after an explicit negative review.
   * @param taskId - Reviewing task to return to its assigned Worker.
   * @param options - Host authority guard at the serialized write boundary.
   * @returns Task in developing, consuming one development slot.
   */
  async returnToDevelopment(taskId: TaskId, options: TaskMutationOptions = {}): Promise<TaskRecord> {
    return await this.enqueue(async () => {
      const current = this.requireTask(taskId)
      this.requireTransition(current, 'reviewing', 'developing')
      this.requireAdmissionOpen()
      if (this.list().filter(task => task.state === 'developing').length >= this.config.maxActiveTasks) {
        throw new ProjectControllerError('The developing budget is exhausted', 'PROJECT_CONTROLLER_CONCURRENCY_EXCEEDED')
      }
      options.beforePersist?.()
      return await this.persist(stamped(current, 'developing'))
    })
  }

  /**
   * Mint a main-tree merge marker for a submitted task. Only a session whose
   * binding carries the `controller` role may trigger the merge; the marker
   * is single-use and process-local.
   * @param callerSessionId - Session requesting the merge.
   * @param taskId - Task to merge.
   * @param request - Exact Git inputs and the host-owned approved-checks store.
   * @returns the marker to hand to {@link ProjectController.integrate}.
   */
  async requestMainTreeMerge(
    callerSessionId: SessionId,
    taskId: TaskId,
    request: MainTreeMergeRequest,
  ): Promise<MainTreeMergeMarker> {
    return await this.enqueue(async () => {
      this.requireAdmissionOpen()
      const binding = this.ctx.agentBindings.find(callerSessionId)
      if (binding === undefined) {
        throw new ProjectControllerError(
          `session "${callerSessionId}" has no agent binding`,
          'PROJECT_CONTROLLER_NOT_CONTROLLER',
        )
      }
      if (binding.role !== 'controller') {
        throw new ProjectControllerError(
          `session "${callerSessionId}" carries role "${binding.role}", not "controller"`,
          'PROJECT_CONTROLLER_NOT_CONTROLLER',
        )
      }
      const current = this.requireTask(taskId)
      this.requireTransition(current, 'submitted', 'integrated')
      const table = this.requireDomain().table('integrations')
      const previous = table.get(taskId)
      if (previous !== undefined) {
        if (request.retryUnchanged !== true || previous.state !== 'prepared' || previous.controllerSessionId !== callerSessionId
          || previous.targetPath !== request.git.targetPath || previous.targetHead !== request.git.targetHead
          || (await reconcileIntegrationGit(previous, request.options)).kind !== 'unchanged') {
          throw new Error('Integration already has a durable intent; reconcile before another attempt')
        }
      }
      const { evidence, guard } = await this.admitIntegration(callerSessionId, current, request)
      await inspectIntegrationGit(request.git, request.options)
      guard()
      const now = new Date().toISOString()
      await table.put(taskId, {
        taskId, controllerSessionId: callerSessionId,
        reviewId: evidence.review.reviewId, verificationId: evidence.verification.verificationId,
        ...request.git, state: 'prepared', createdAt: now, updatedAt: now,
      })
      const marker: MainTreeMergeMarker = Object.freeze({
        mergeId: randomUUID(),
        taskId,
        callerSessionId,
        createdAt: new Date().toISOString(),
      })
      for (const [id, pending] of this.pendingMarkers) {
        if (pending.taskId === taskId) {
          this.pendingMarkers.delete(id)
          this.pendingGit.delete(id)
        }
      }
      this.pendingMarkers.set(marker.mergeId, marker)
      this.pendingGit.set(marker.mergeId, { ...request, git: { ...request.git }, options: { ...request.options } })
      return marker
    })
  }

  /**
   * Execute the admitted fast-forward once, then record integration only after observing the exact clean target.
   * @param taskId - Task to move; the marker must name it.
   * @param marker - The marker minted by {@link ProjectController.requestMainTreeMerge}.
   * @returns the updated record.
   */
  async integrate(taskId: TaskId, marker: MainTreeMergeMarker): Promise<TaskRecord> {
    return await this.enqueue(async () => {
      // The marker is validated before the state check so a consumed marker
      // reports MARKER_INVALID even when the task has already moved on.
      if (marker.taskId !== taskId || this.pendingMarkers.get(marker.mergeId) !== marker) {
        throw new ProjectControllerError(
          `merge marker "${marker.mergeId}" does not name a pending merge for task "${String(taskId)}"`,
          'PROJECT_CONTROLLER_MARKER_INVALID',
        )
      }
      const current = this.requireTask(taskId)
      this.requireTransition(current, 'submitted', 'integrated')
      this.requireAdmissionOpen()
      const request = this.pendingGit.get(marker.mergeId)
      const intent = this.requireDomain().table('integrations').get(taskId)
      if (request === undefined || intent === undefined || intent.controllerSessionId !== marker.callerSessionId) {
        throw new Error('Integration marker has no matching durable Git intent')
      }
      this.pendingMarkers.delete(marker.mergeId)
      this.pendingGit.delete(marker.mergeId)
      const { evidence, guard } = await this.admitIntegration(marker.callerSessionId, current, request)
      if (evidence.review.reviewId !== intent.reviewId || evidence.verification.verificationId !== intent.verificationId) {
        throw new Error('Integration evidence superseded the prepared intent; prepare again')
      }
      const result = await executeIntegrationGit(intent, request.options, request.signal, guard)
      if (result.observation.kind !== 'applied' || result.commandError !== undefined) {
        throw new Error(`Integration requires reconciliation: ${result.observation.kind}`, { cause: result.commandError })
      }
      return await this.recordAppliedIntegration(current, intent)
    })
  }

  /**
   * Reconcile a durable intent after interruption without issuing another Git merge.
   * @param callerSessionId - The same controller that admitted the original operation.
   * @param taskId - Task whose retained intent is being reconciled.
   * @param options - Explicit deployment process limits for read-only Git observations.
   * @returns The actual Git observation; only `applied` advances the task board.
   */
  async reconcileMainTreeIntegration(
    callerSessionId: SessionId,
    taskId: TaskId,
    options: IntegrationGitOptions,
  ): Promise<IntegrationGitObservation> {
    return await this.enqueue(async () => {
      this.requireAdmissionOpen()
      const binding = this.ctx.agentBindings.find(callerSessionId)
      const intent = this.requireDomain().table('integrations').get(taskId)
      if (binding?.role !== 'controller' || intent?.controllerSessionId !== callerSessionId
        || binding.worktreePath !== intent.targetPath) {
        throw new Error('Integration reconciliation requires its original registered controller')
      }
      const registries = this.integrationWorktrees()
      const target = registries.workspaces.list().flatMap(workspace => registries.worktrees.list(workspace.id))
        .find(row => row.id === binding.worktreeId)
      if (target?.path !== intent.targetPath || String(target.lockedBy) !== String(callerSessionId)) {
        throw new Error('Integration reconciliation requires the controller writer lock')
      }
      const current = this.requireTask(taskId)
      if (current.state !== 'submitted' && current.state !== 'integrated') {
        throw new Error('Integration reconciliation requires a submitted or integrated task')
      }
      const observation = await reconcileIntegrationGit(intent, options)
      if (observation.kind === 'applied' && current.state === 'submitted') await this.recordAppliedIntegration(current, intent)
      return observation
    })
  }

  /** Integration requires registries at its execution entry, independently of any tool consumer. */
  private integrationWorktrees() {
    const workspaces = this.ctx.get('workspaceRegistry')
    const worktrees = this.ctx.get('worktreeRegistry')
    if (workspaces === undefined || worktrees === undefined) throw new Error('Integration requires workspace and worktree registries')
    return { workspaces, worktrees }
  }

  /** Read registry and projection evidence afresh; no marker substitutes for current authority. */
  private readIntegrationAdmission(callerSessionId: SessionId, current: TaskRecord, request: MainTreeMergeRequest) {
    const taskId = current.taskId
    const binding = this.ctx.agentBindings.find(callerSessionId)
    if (binding?.role !== 'controller') throw new Error('Integration requires its registered controller')
    const session = this.ctx.get('sessions')?.get(callerSessionId)
    const state = session === undefined ? undefined : this.ctx.get('sessionProjections')?.stateOf(session, 'devframe')
    if (state === undefined) throw new Error('Integration requires the live controller evidence projection')
    const expected = state.bindings.at(-1)
    if (expected?.lifecycle !== 'admission_open'
      || (state.lifecycle !== null && state.lifecycle.binding.goalId === expected.goalId && state.lifecycle.state !== 'admission_open')
      || !expected.taskIds.some(id => String(id) === String(taskId))) {
      throw new Error('Integration requires the task in the current Goal with open admission')
    }
    const worker = current.assigneeSessionId === undefined ? undefined : this.ctx.agentBindings.find(current.assigneeSessionId)
    const lead = worker?.parentSessionId === undefined ? undefined : this.ctx.agentBindings.find(worker.parentSessionId)
    if (worker === undefined || lead === undefined) {
      throw new Error('Integration requires the current Goal binding and registered task hierarchy')
    }
    const evidence = selectIntegrationEvidence({ state, expected, controller: binding, task: current, worker, lead })
    if (request.git.sourceCommit !== evidence.delivery.sourceCommit) {
      throw new Error('Integration source commit does not match the current task delivery')
    }
    if (request.git.sourcePath !== worker.worktreePath || request.git.targetPath !== binding.worktreePath) {
      throw new Error('Integration paths must match the registered Worker and controller worktrees')
    }
    const registries = this.integrationWorktrees()
    const rows = registries.workspaces.list().flatMap(workspace => registries.worktrees.list(workspace.id))
    const target = rows.find(row => row.id === binding.worktreeId)
    const source = rows.find(row => row.id === worker.worktreeId)
    const reviewer = rows.find(row => row.id === lead.worktreeId)
    if (target === undefined || source === undefined || reviewer === undefined
      || target.path !== binding.worktreePath || source.path !== worker.worktreePath || reviewer.path !== lead.worktreePath
      || target.workspaceId !== source.workspaceId || target.workspaceId !== reviewer.workspaceId
      || String(target.workspaceId) !== String(expected.workspaceId)
      || String(target.lockedBy) !== String(callerSessionId) || String(source.lockedBy) !== String(worker.sessionId)) {
      throw new Error('Integration requires registered worktrees and current controller/Worker writer locks in its workspace')
    }
    const taskWarnings = state.taskWarnings.filter(warning => String(warning.taskId) === String(taskId))
    return {
      evidence,
      signature: JSON.stringify({ expected, evidence, taskWarnings, binding, worker, lead, target, source, reviewer }),
      input: {
        worktreePath: request.git.sourcePath,
        sourceFingerprint: evidence.delivery.sourceFingerprint,
        checks: evidence.verification.checks,
        requiredChecksDigest: evidence.verification.requiredChecks.digest,
        requiredChecksStore: request.requiredChecksStore,
        review: evidence.review,
        taskWarnings,
      },
    }
  }

  /** Evaluate source checks and retain a synchronous admission guard for the Git spawn. */
  private async admitIntegration(callerSessionId: SessionId, current: TaskRecord, request: MainTreeMergeRequest) {
    const admission = this.readIntegrationAdmission(callerSessionId, current, request)
    const verdict = await evaluateCompletionAdmission(admission.input)
    if (verdict.kind !== 'admitted') throw new Error(`Integration admission rejected at ${verdict.stage}`)
    const guard = () => {
      request.signal?.throwIfAborted()
      this.requireAdmissionOpen()
      if (this.readIntegrationAdmission(callerSessionId, current, request).signature !== admission.signature) {
        throw new Error('Integration evidence changed during admission; prepare again')
      }
    }
    guard()
    return { evidence: admission.evidence, guard }
  }

  /** Persist the observed Git result before updating the task; a failed task write remains reconcilable. */
  private async recordAppliedIntegration(current: TaskRecord, intent: MainTreeIntegrationRecord): Promise<TaskRecord> {
    await this.requireDomain().table('integrations').put(current.taskId, {
      ...intent, state: 'applied', updatedAt: new Date().toISOString(),
    })
    return await this.persist(stamped(current, 'integrated'))
  }

  /**
   * Complete an integrated task.
   * @param taskId - Task to move.
   * @returns the updated record.
   */
  async complete(taskId: TaskId): Promise<TaskRecord> {
    return await this.enqueue(async () => {
      const current = this.requireTask(taskId)
      this.requireTransition(current, 'integrated', 'completed')
      this.requireOpenLifecycle()
      return await this.persist(stamped(current, 'completed'))
    })
  }

  /**
   * Block a task from any active state; the recovery triple is mandatory.
   * @param taskId - Task to move.
   * @param detail - Reason, next action, and wake condition.
   * @returns the updated record.
   */
  async block(taskId: TaskId, detail: TaskBlockDetail): Promise<TaskRecord> {
    return await this.enqueue(async () => {
      const current = this.requireTask(taskId)
      this.requireTransitionFrom(current, BLOCKABLE_STATES, 'blocked')
      this.requireOpenLifecycle()
      this.assertDetail(detail)
      return await this.persist({
        ...stamped(current, 'blocked'),
        blockedReason: detail.blockedReason,
        nextAction: detail.nextAction,
        wakeCondition: detail.wakeCondition,
      })
    })
  }

  /**
   * Fail a task from any active state; the recovery triple is mandatory.
   * @param taskId - Task to move.
   * @param detail - Reason, next action, and wake condition.
   * @returns the updated record.
   */
  async fail(taskId: TaskId, detail: TaskBlockDetail): Promise<TaskRecord> {
    return await this.enqueue(async () => {
      const current = this.requireTask(taskId)
      this.requireTransitionFrom(current, BLOCKABLE_STATES, 'failed')
      this.requireOpenLifecycle()
      this.assertDetail(detail)
      return await this.persist({
        ...stamped(current, 'failed'),
        blockedReason: detail.blockedReason,
        nextAction: detail.nextAction,
        wakeCondition: detail.wakeCondition,
      })
    })
  }

  /**
   * Resume a blocked or failed task back into dispatch through `assigned`;
   * the recovery triple is cleared on the way out.
   * @param taskId - Task to move.
   * @param assigneeSessionId - Replacement assignee; omitted, the previous one is kept.
   * @returns the updated record.
   */
  async resume(taskId: TaskId, assigneeSessionId?: SessionId): Promise<TaskRecord> {
    return await this.enqueue(async () => {
      const current = this.requireTask(taskId)
      this.requireTransitionFrom(current, ['blocked', 'failed'], 'assigned')
      this.requireAdmissionOpen()
      const { blockedReason: _reason, nextAction: _action, wakeCondition: _wake, ...kept } = current
      const next: TaskRecord = stamped(kept, 'assigned')
      if (assigneeSessionId !== undefined) return await this.persist({ ...next, assigneeSessionId })
      return await this.persist(next)
    })
  }

  // ---- request budget (AT4-05) -------------------------------------------

  /**
   * Reserve one model sending attempt against the project's
   * cumulative budget. The request that fills the last budget slot is
   * admitted; any further charge is rejected until the deployment raises
   * `requestBudget`. Concurrent charges from racing controller/child sessions
   * serialize on the controller's write chain, so a full budget admits
   * exactly one of them, and the charge persists before the receipt returns —
   * a retry or a process restart never resets usage. A reservation does not
   * prove supplier billing and is not refunded after cancellation. An uncertain
   * storage write closes further charging until the service is reloaded.
   * @param options - Host authority guard checked inside the charge queue.
   * @returns the receipt with the cumulative charged count, the configured
   *   budget, and the remaining allowance after this charge.
   * @throws {@link ProjectControllerError} with
   *   `PROJECT_CONTROLLER_REQUEST_BUDGET_EXHAUSTED` when every budget unit is
   *   already spent, `PROJECT_CONTROLLER_ADMISSION_CLOSED` when the project
   *   lifecycle is not admitting dispatch work, or
   *   `PROJECT_CONTROLLER_PERSISTENCE` when the usage write failed.
   */
  async chargeModelRequest(options?: TaskMutationOptions): Promise<RequestChargeReceipt> {
    return await this.enqueue(async () => {
      this.requireAdmissionOpen()
      if (this.requestChargeFailure) throw this.requestChargeFailure
      const requestBudget = this.config.requestBudget
      if (this.chargedRequests >= requestBudget) {
        throw new ProjectControllerError(
          `the request budget of ${requestBudget} is exhausted (${this.chargedRequests} charged)`,
          'PROJECT_CONTROLLER_REQUEST_BUDGET_EXHAUSTED',
        )
      }
      const chargedRequests = this.chargedRequests + 1
      options?.beforePersist?.()
      try {
        await this.requireDomain().global.set({ chargedRequests })
      } catch (error: unknown) {
        this.requestChargeFailure = new ProjectControllerError(
          'request-budget usage could not be persisted',
          'PROJECT_CONTROLLER_PERSISTENCE',
          { cause: error },
        )
        throw this.requestChargeFailure
      }
      this.chargedRequests = chargedRequests
      return {
        chargedRequests,
        requestBudget,
        remainingRequests: requestBudget - chargedRequests,
      }
    })
  }

  /**
   * Read the request-budget accounting without charging.
   * @returns the configured budget, the cumulative charged count, and the
   *   remaining allowance (clamped at zero once exhausted).
   */
  requestBudgetUsage(): {
    readonly requestBudget: number
    readonly chargedRequests: number
    readonly remainingRequests: number
  } {
    return {
      requestBudget: this.config.requestBudget,
      chargedRequests: this.chargedRequests,
      remainingRequests: Math.max(0, this.config.requestBudget - this.chargedRequests),
    }
  }

  // ---- queries -----------------------------------------------------------

  /**
   * Read one task from the restored board.
   * @param taskId - Task identity selecting the record.
   * @returns the record, or `undefined` when the task does not exist.
   */
  find(taskId: TaskId): TaskRecord | undefined {
    return this.tasks.get(taskId)
  }

  /**
   * Read every task carrying one state.
   * @param state - State to filter by.
   * @returns the matching records in stable (createdAt, taskId) order.
   */
  byState(state: TaskState): readonly TaskRecord[] {
    return this.list().filter(record => record.state === state)
  }

  /**
   * Read the whole board in stable (createdAt, taskId) order.
   * @returns all restored or written records.
   */
  list(): readonly TaskRecord[] {
    return [...this.tasks.values()].sort((left, right) =>
      left.createdAt.localeCompare(right.createdAt) || String(left.taskId).localeCompare(String(right.taskId)))
  }

  // ---- internals ---------------------------------------------------------

  /** Serialize mutations so concurrent transitions cannot interleave validation and writes. */
  private enqueue<T>(operation: () => Promise<T>): Promise<T> {
    const run = this.tail.then(operation, operation)
    this.tail = run.then(() => undefined, () => undefined)
    return run
  }

  /** The task, or a loud unknown-task failure. */
  private requireTask(taskId: TaskId): TaskRecord {
    const record = this.tasks.get(taskId)
    if (record === undefined) {
      throw new ProjectControllerError(`task "${String(taskId)}" does not exist`, 'PROJECT_CONTROLLER_TASK_UNKNOWN')
    }
    return record
  }

  /** Require one exact from-state for the pending move. */
  private requireTransition(current: TaskRecord, from: TaskState, to: TaskState): void {
    if (current.state !== from) {
      throw new ProjectControllerError(
        `task "${String(current.taskId)}" cannot move ${current.state} → ${to}`,
        'PROJECT_CONTROLLER_ILLEGAL_TRANSITION',
      )
    }
  }

  /** Require the current state to be one of the legal sources for the move. */
  private requireTransitionFrom(current: TaskRecord, from: readonly TaskState[], to: TaskState): void {
    if (!from.includes(current.state)) {
      throw new ProjectControllerError(
        `task "${String(current.taskId)}" cannot move ${current.state} → ${to}`,
        'PROJECT_CONTROLLER_ILLEGAL_TRANSITION',
      )
    }
  }

  /** Dispatch-path moves require open admission. */
  private requireAdmissionOpen(): void {
    if (this.lifecycleState !== 'admission_open') {
      throw new ProjectControllerError(
        `admission is ${this.lifecycleState}; this move requires admission_open`,
        'PROJECT_CONTROLLER_ADMISSION_CLOSED',
      )
    }
  }

  /** Recording moves stay available while the project has not stopped. */
  private requireOpenLifecycle(): void {
    if (!OPEN_LIFECYCLES.includes(this.lifecycleState)) {
      throw new ProjectControllerError(
        `the project lifecycle is ${this.lifecycleState}; this move is no longer accepted`,
        'PROJECT_CONTROLLER_ADMISSION_CLOSED',
      )
    }
  }

  /** Validate the mandatory recovery triple. */
  private assertDetail(detail: TaskBlockDetail): void {
    assertDetailField(detail.blockedReason, 'blockedReason')
    assertDetailField(detail.nextAction, 'nextAction')
    assertDetailField(detail.wakeCondition, 'wakeCondition')
  }

  /** Persist one state move through the durable table, then mirror it into the board. */
  private async persist(record: TaskRecord): Promise<TaskRecord> {
    const frozen = Object.freeze(record)
    try {
      await this.requireTable().put(frozen.taskId, frozen)
    } catch (error: unknown) {
      throw new ProjectControllerError(
        `task "${String(frozen.taskId)}" could not be persisted`,
        'PROJECT_CONTROLLER_PERSISTENCE',
        { cause: error },
      )
    }
    this.tasks.set(frozen.taskId, frozen)
    return frozen
  }

  /** The opened domain table; absent only before Service.init completed. */
  private requireTable(): KvTable<TaskId, TaskRecord> {
    if (this.table === undefined) {
      throw new ProjectControllerError('the project_tasks domain is not open yet', 'PROJECT_CONTROLLER_PERSISTENCE')
    }
    return this.table
  }

  /** The opened domain; absent only before Service.init completed. */
  private requireDomain(): Domain<typeof projectTasksDomainSpec> {
    if (this.domain === undefined) {
      throw new ProjectControllerError('the project_tasks domain is not open yet', 'PROJECT_CONTROLLER_PERSISTENCE')
    }
    return this.domain
  }
}
