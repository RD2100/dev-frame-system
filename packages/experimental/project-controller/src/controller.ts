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
import type { KvTable } from '@deepseek-ai/dsh-storage-domain'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { ProjectLifecycleState } from '@deepseek-ai/dsh-experimental-devframe/shared'
import type { PluginId, TaskId, TaskRecord, TaskState } from '@deepseek-ai/dsh-experimental-project-contracts'
// Loads the session-identity Context augmentation so `ctx.agentBindings` types the merge-gate lookup.
import type {} from '@deepseek-ai/dsh-experimental-session-identity'
import { ProjectControllerError } from './errors.ts'
import { projectTasksDomainSpec } from './spec.ts'

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
  })

  /** Validated config (schemastery applied the defaults before construction). */
  private readonly config: ResolvedConfig

  private table?: KvTable<TaskId, TaskRecord>
  private readonly tasks = new Map<TaskId, TaskRecord>()
  private readonly pendingMarkers = new Map<string, MainTreeMergeMarker>()
  private lifecycleState: ProjectLifecycleState = 'stopped'
  private tail: Promise<unknown> = Promise.resolve()

  /**
   * @param ctx - Mounting context.
   * @param config - Schema-validated config; `maxActiveTasks` must be a positive safe integer.
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
  }

  protected async [Service.init](): Promise<void> {
    const domain = await this.ctx.storageDomain.open(projectTasksDomainSpec)
    this.ctx.effect(() => () => domain.close(), 'project-controller.domainClose')
    this.table = domain.table('tasks')
    // Cold restore: the board comes back verbatim; in-flight records need the
    // host's attention because their live workers died with the old process.
    // The map holds a detached frozen copy so the durable row stays untouched.
    for (const [id, record] of [...this.table.entries()]
      .sort(([leftId, left], [rightId, right]) =>
        left.createdAt.localeCompare(right.createdAt) || String(leftId).localeCompare(String(rightId)))) {
      this.tasks.set(id, Object.freeze({ ...record }))
    }
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
   * @returns the stored record.
   */
  async createTask(request: { readonly taskId: TaskId; readonly pluginId: PluginId; readonly title: string }): Promise<TaskRecord> {
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
      return await this.persist(record)
    })
  }

  /**
   * Assign a planned task to a session.
   * @param taskId - Task to move.
   * @param assigneeSessionId - Session bound to execute the task.
   * @returns the updated record.
   */
  async assign(taskId: TaskId, assigneeSessionId: SessionId): Promise<TaskRecord> {
    return await this.enqueue(async () => {
      const current = this.requireTask(taskId)
      this.requireTransition(current, 'planned', 'assigned')
      this.requireAdmissionOpen()
      return await this.persist({ ...stamped(current, 'assigned'), assigneeSessionId })
    })
  }

  /**
   * Move an assigned task into development, consuming one dispatch slot.
   * @param taskId - Task to move.
   * @returns the updated record.
   */
  async startDevelopment(taskId: TaskId): Promise<TaskRecord> {
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
      return await this.persist(stamped(current, 'developing'))
    })
  }

  /**
   * Move a developing task into lead review.
   * @param taskId - Task to move.
   * @returns the updated record.
   */
  async beginReview(taskId: TaskId): Promise<TaskRecord> {
    return await this.enqueue(async () => {
      const current = this.requireTask(taskId)
      this.requireTransition(current, 'developing', 'reviewing')
      this.requireAdmissionOpen()
      return await this.persist(stamped(current, 'reviewing'))
    })
  }

  /**
   * Submit a reviewed task for integration.
   * @param taskId - Task to move.
   * @returns the updated record.
   */
  async submit(taskId: TaskId): Promise<TaskRecord> {
    return await this.enqueue(async () => {
      const current = this.requireTask(taskId)
      this.requireTransition(current, 'reviewing', 'submitted')
      this.requireAdmissionOpen()
      return await this.persist(stamped(current, 'submitted'))
    })
  }

  /**
   * Mint a main-tree merge marker for a submitted task. Only a session whose
   * binding carries the `controller` role may trigger the merge; the marker
   * is single-use and process-local.
   * @param callerSessionId - Session requesting the merge.
   * @param taskId - Task to merge.
   * @returns the marker to hand to {@link ProjectController.integrate}.
   */
  async requestMainTreeMerge(callerSessionId: SessionId, taskId: TaskId): Promise<MainTreeMergeMarker> {
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
      const marker: MainTreeMergeMarker = Object.freeze({
        mergeId: randomUUID(),
        taskId,
        callerSessionId,
        createdAt: new Date().toISOString(),
      })
      this.pendingMarkers.set(marker.mergeId, marker)
      return marker
    })
  }

  /**
   * Consume one merge marker and move the task to `integrated`.
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
      this.pendingMarkers.delete(marker.mergeId)
      return await this.persist(stamped(current, 'integrated'))
    })
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
}
