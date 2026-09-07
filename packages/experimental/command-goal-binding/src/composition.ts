/**
 * The DevFrame host command composition service: one per-composition owner
 * that lazily builds the {@link GoalBindingController} per controller Session
 * over the live native Goal service, selects completion evidence from the
 * controller Session's devframe projection, lands the admitted verdict as a
 * durable completion receipt, and owns the `/devframe-start` and
 * `/devframe-resume` lanes. Every command handler is a production entry;
 * `startBinding` stays the composition's test-visible start lane.
 * @module @deepseek-ai/dsh-experimental-command-goal-binding/composition
 */

import { Service, type Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { CommandResult } from '@deepseek-ai/dsh-commands'
import type {} from '@deepseek-ai/dsh-session-projection'
import type { GoalId } from '@deepseek-ai/dsh-goal/types'
import { AgentEvidenceJournal } from '@deepseek-ai/dsh-experimental-agent-evidence'
import { ControllerSessionId, GoalBindingController, GoalServicePort, MemoryGoalBindingStore, createHumanAuthorization } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type {
  CompleteGoalRequest,
  CompletionAdmissionVerdict,
  GoalAdmission,
  GoalBinding,
  GoalBindingIdentity,
  GoalBindingStore,
  GoalBudgetInput,
  TaskId,
} from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { computeSourceFingerprint } from '@deepseek-ai/dsh-experimental-devframe'
import type { AcceptanceHash, DevFrameSnapshotId, SourceFingerprint } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { DevFrameSnapshotId as makeSnapshotId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { MemoryRequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe'
import type { RequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe'
import { devFrameProjectionDefinition } from '@deepseek-ai/dsh-experimental-devframe'
import type { DevFrameProjectionState } from '@deepseek-ai/dsh-experimental-devframe'
import { DevFrameSessionJournal } from '@deepseek-ai/dsh-experimental-devframe'
import type { DevFrameReviewEventData, DevFrameVerificationEventData } from '@deepseek-ai/dsh-experimental-devframe'
import {
  GOAL_ALREADY_COMPLETE_TEXT,
  NO_BINDING_TEXT,
  NO_CURRENT_GOAL_TEXT,
  NO_REVIEW_TEXT,
  NO_VERIFICATION_TEXT,
  PROJECTION_FAILURE_TEXT,
  RESUME_INPUT_UNEXPECTED_TEXT,
  RESUME_NO_BINDING_RECORD_TEXT,
  RESUME_NO_CURRENT_GOAL_TEXT,
  START_GOAL_RUNNING_TEXT,
  START_OBJECTIVE_REQUIRED_TEXT,
  START_WORKTREE_REQUIRED_TEXT,
  WORKTREE_REQUIRED_TEXT,
  completionAdmissionEvidence,
  devframeResumeDescriptor,
  devframeStartDescriptor,
  goalCompleteDescriptor,
  parseDevframeResumeInput,
  parseDevframeStartInput,
  parseGoalCompleteInput,
  renderCompletionRejection,
  renderCompletionSuccess,
  renderResumeSuccess,
  renderStartSuccess,
} from './command.ts'
import {
  ProjectionEvidenceReviewerDirectory,
  acceptanceHashOf,
  compositionDevFrameJournal,
  devFrameStateOf,
  landGoalBinding,
  landRolePolicyIfAbsent,
  resultTupleOf,
  sessionFlush,
} from './host-evidence.ts'
import type { ResolvedCommandGoalBindingConfig } from './config.ts'

/** Replaceable storage boundaries of one composition. */
export interface GoalBindingCompositionStores {
  /** Durable binding store; defaults to the in-memory reference implementation. */
  readonly bindings?: GoalBindingStore
  /** Approved-checks configuration store; defaults to the in-memory reference implementation. */
  readonly requiredChecks?: RequiredChecksConfigStore
}

/** Start-lane request accepted by {@link GoalBindingComposition.startBinding}. */
export interface StartGoalBindingRequest {
  /** Non-empty goal objective. */
  readonly objective: string
  /** At least one unique native team task id bound to the goal. */
  readonly taskIds: readonly TaskId[]
  /** Digest of the user-approved objective and check configuration. */
  readonly acceptanceHash: AcceptanceHash
  /** Fingerprint of the source tree the work starts from. */
  readonly sourceFingerprint: SourceFingerprint
  /** Snapshot whose content the source fingerprint describes. */
  readonly snapshotId: DevFrameSnapshotId
  /** Attempt budget frozen into the binding. */
  readonly budget: GoalBudgetInput
  /** Identifier of the human-approved confirmation minted into the authorization. */
  readonly confirmationId: string
  /** Optional continuation round cap. */
  readonly maxGoalRounds?: number
}

/**
 * Process-local composition owner registering as the `commandGoalBinding`
 * service (deliberately without a Context merge declaration: this is a
 * private experimental seam, so in-process readers use `ctx.reflect.get`).
 * It registers the devframe projection unit and the `/goal-complete`,
 * `/devframe-start`, and `/devframe-resume` commands, and owns the controller
 * registry, both replaceable reference stores, and the evidence wiring: the
 * composition-owned DevFrame Session journal for role-policy and
 * goal-binding records, plus the `AgentEvidenceJournal` whose default
 * execution face runs required checks as real subprocesses.
 */
export class GoalBindingComposition extends Service {
  /** Durable binding store backing every controller of this composition. */
  readonly bindingStore: GoalBindingStore
  /** Approved-checks configuration store resolving evidence digests. */
  readonly requiredChecksStore: RequiredChecksConfigStore
  /** Composition-owned journal landing role-policy and goal-binding records. */
  readonly journal: DevFrameSessionJournal
  /** Evidence producer executing required checks through the real subprocess face. */
  readonly evidenceJournal: AgentEvidenceJournal

  private readonly controllers = new Map<string, GoalBindingController>()

  /**
   * Construct the composition inside the owning plugin fiber: registering the
   * projection unit and the commands here ties all registrations to that
   * fiber's lifetime (the Goal service registers its own projection the same
   * way). The evidence journals share one native flush closure and one
   * projection-derived role directory; constructing the evidence journal
   * without a reviewer directory is impossible by construction, so an
   * unwired review gate cannot be instantiated.
   * @param ctx - the plugin fiber's context carrying `commands`, `goals`,
   *   `sessions`, and `sessionProjections`.
   * @param config - validated workspace configuration.
   * @param stores - optional store overrides; memory reference
   *   implementations otherwise.
   */
  constructor(
    ctx: Context,
    private readonly config: ResolvedCommandGoalBindingConfig,
    stores: GoalBindingCompositionStores = {},
  ) {
    super(ctx, 'commandGoalBinding')
    this.bindingStore = stores.bindings ?? new MemoryGoalBindingStore()
    this.requiredChecksStore = stores.requiredChecks ?? new MemoryRequiredChecksConfigStore()
    const flush = sessionFlush(ctx)
    const reviewerDirectory = new ProjectionEvidenceReviewerDirectory(ctx)
    this.journal = compositionDevFrameJournal(flush, reviewerDirectory)
    this.evidenceJournal = new AgentEvidenceJournal({ flush, reviewerDirectory })
    ctx.sessionProjections.register(devFrameProjectionDefinition)
    ctx.effect(() => ctx.commands.register({
      ...goalCompleteDescriptor(),
      handler: invocation => this.completeCurrent({
        agent: invocation.agent,
        worktreePath: parseGoalCompleteInput(invocation.rawInput),
      }),
    }), 'command-goal-binding.register')
    ctx.effect(() => ctx.commands.register({
      ...devframeStartDescriptor(),
      handler: invocation => this.startBoundGoal({
        agent: invocation.agent,
        rawInput: invocation.rawInput,
      }),
    }), 'command-goal-binding.register-start')
    ctx.effect(() => ctx.commands.register({
      ...devframeResumeDescriptor(),
      handler: invocation => this.resumeBoundGoal({
        agent: invocation.agent,
        rawInput: invocation.rawInput,
      }),
    }), 'command-goal-binding.register-resume')
  }

  /**
   * Start one bound goal through this composition's controller so the command
   * and the start lane share the same controller registry and stores. The
   * human authorization capability is minted here, inside the host adapter,
   * from the caller's confirmation id — per the devframe contract, only the
   * command adapter creates it, and only after human approval.
   * @param agent - live agent whose session owns the goal.
   * @param request - start parameters plus the human confirmation id.
   * @returns the persisted binding of the created goal.
   */
  async startBinding(agent: Agent, request: StartGoalBindingRequest): Promise<GoalBinding> {
    return this.controllerFor(agent).start({
      objective: request.objective,
      taskIds: request.taskIds,
      acceptanceHash: request.acceptanceHash,
      sourceFingerprint: request.sourceFingerprint,
      snapshotId: request.snapshotId,
      budget: request.budget,
      ...(request.maxGoalRounds === undefined ? {} : { maxGoalRounds: request.maxGoalRounds }),
      authorization: createHumanAuthorization(request.confirmationId),
    })
  }

  /**
   * Execute one `/devframe-start` invocation: parse the objective, compute
   * the real source fingerprint of the configured worktree, start the bound
   * goal through the controller, and land the fold-required evidence chain —
   * role-policy (only when the projection holds none), goal-binding, and a
   * real verification — on the controller Session log. The host collects
   * every recorded fact; model input never writes evidence.
   *
   * Expected data refusals return stable error results; the structural
   * failures (`SourceFingerprintError`, `GoalBindingError`,
   * `DevFramePersistenceError`, `RequiredChecksError`) propagate unchanged so
   * the command registry settles them as dispatch failures. A journal landing
   * failure after the native goal exists is the registered partial-failure
   * window: it throws fail-closed, and the resume lane provides the repair
   * surface.
   * @param invocation - the receiving agent plus the verbatim command text.
   * @returns a success result carrying the honest check count and
   *   verification status, or a stable error result.
   */
  async startBoundGoal(invocation: {
    readonly agent: Agent
    readonly rawInput: string
  }): Promise<CommandResult> {
    const objective = parseDevframeStartInput(invocation.rawInput)
    if (objective.length === 0) return { kind: 'error', text: START_OBJECTIVE_REQUIRED_TEXT }
    const worktreePath = this.config.workspaceRoot
    if (worktreePath === undefined) return { kind: 'error', text: START_WORKTREE_REQUIRED_TEXT }
    const current = this.ctx.goals.get(invocation.agent)
    if (current !== undefined && current.phase !== 'complete') {
      return { kind: 'error', text: START_GOAL_RUNNING_TEXT }
    }
    const computed = await computeSourceFingerprint({ worktreePath })
    const snapshotId = makeSnapshotId(`snapshot-v1-${computed.headCommit}-${computed.trackedStateHash}`)
    const requiredChecksDigest = await this.requiredChecksStore.save(this.config.checks)
    const binding = await this.startBinding(invocation.agent, {
      objective,
      taskIds: this.config.taskIds,
      acceptanceHash: acceptanceHashOf(objective, this.config.checks),
      sourceFingerprint: computed.fingerprint,
      snapshotId,
      budget: { maxAttempts: this.config.maxAttempts },
      confirmationId: `devframe-start:${invocation.agent.id}:${Date.now()}`,
      ...(this.config.maxGoalRounds === undefined ? {} : { maxGoalRounds: this.config.maxGoalRounds }),
    })
    const session = invocation.agent.session
    await landRolePolicyIfAbsent(this.ctx, this.journal, session, this.config.workspaceId)
    await landGoalBinding(this.journal, session, binding)
    const verification = await this.evidenceJournal.recordVerification({
      session,
      binding: resultTupleOf(binding),
      requiredChecksDigest,
      requiredChecksStore: this.requiredChecksStore,
    })
    return {
      kind: 'success',
      text: renderStartSuccess(verification.checks.length, verification.status),
    }
  }

  /**
   * Execute one `/devframe-resume` invocation: align the binding between the
   * log projection and the binding store, rebuild what a restart or a start
   * partial failure lost, resume the exact current goal through the
   * controller, and land the revision-advanced binding back on the log so it
   * stays the durable authority across the next restart.
   *
   * After a restart the in-memory store is empty while the restored log
   * rebuilds the projection: the projected binding is restored into the
   * store, and a controller cached with the empty store is evicted so the
   * rebuilt controller loads the restored binding. After a start partial
   * failure the store holds the binding while the projection lacks it: the
   * role-policy (when absent) and the stored binding are landed on the log.
   * @param invocation - the receiving agent plus the verbatim command text.
   * @returns a success result, or a stable error result for the expected
   *   data refusals (unexpected input, no current goal, already complete, no
   *   binding record). Structural failures propagate unchanged.
   */
  async resumeBoundGoal(invocation: {
    readonly agent: Agent
    readonly rawInput: string
  }): Promise<CommandResult> {
    if (parseDevframeResumeInput(invocation.rawInput).length > 0) {
      return { kind: 'error', text: RESUME_INPUT_UNEXPECTED_TEXT }
    }
    const current = this.ctx.goals.get(invocation.agent)
    if (current === undefined) return { kind: 'error', text: RESUME_NO_CURRENT_GOAL_TEXT }
    if (current.phase === 'complete') return { kind: 'error', text: GOAL_ALREADY_COMPLETE_TEXT }
    const controllerSessionId = ControllerSessionId(invocation.agent.id)
    const projected = devFrameStateOf(this.ctx, invocation.agent.session)
      .bindings.find(binding => binding.goalId === current.id)
    const stored = (await this.bindingStore.load(controllerSessionId))
      .find(binding => binding.goalId === current.id)
    let restoredStore = false
    if (stored === undefined && projected !== undefined) {
      await this.bindingStore.save(projected)
      restoredStore = true
    } else if (stored !== undefined && projected === undefined) {
      const session = invocation.agent.session
      await landRolePolicyIfAbsent(this.ctx, this.journal, session, this.config.workspaceId)
      await landGoalBinding(this.journal, session, stored)
    } else if (stored === undefined && projected === undefined) {
      return { kind: 'error', text: RESUME_NO_BINDING_RECORD_TEXT }
    }
    if (restoredStore && this.controllers.has(invocation.agent.id)) {
      this.controllers.delete(invocation.agent.id)
    }
    const resumed = await this.controllerFor(invocation.agent).resume(
      { controllerSessionId, goalId: current.id },
      createHumanAuthorization(`devframe-resume:${invocation.agent.id}:${Date.now()}`),
    )
    await landGoalBinding(this.journal, invocation.agent.session, resumed)
    return { kind: 'success', text: renderResumeSuccess() }
  }

  /**
   * Read the admission state of the agent's controller without constructing
   * one. This is the fail-closed observation point: a rejected or structural
   * completion attempt must leave the value at `closed`.
   * @param agent - live agent identifying the controller.
   * @returns the controller's admission state, or `undefined` when this
   *   composition has not built a controller for the agent yet.
   */
  admissionOf(agent: Agent): GoalAdmission | undefined {
    return this.controllers.get(agent.id)?.admissionState
  }

  /**
   * Execute one `/goal-complete` invocation against the invoking agent's
   * current goal. Expected domain refusals return stable error results; the
   * structural admission errors (`GoalBindingError`, `SourceFingerprintError`,
   * `RequiredChecksError`) propagate unchanged so the command registry
   * settles them as dispatch failures. The worktree path is resolved
   * explicitly at this command entry — the command parameter wins, the
   * configured `workspaceRoot` is the fallback, and both missing is a stable
   * data error rather than a hidden default.
   * @param invocation - the receiving agent plus the optional explicit
   *   worktree path parsed from the command line.
   * @returns a success result after the receipt lands, or a stable error
   *   result carrying the refusal or rejection text.
   */
  async completeCurrent(invocation: {
    readonly agent: Agent
    readonly worktreePath?: string | undefined
  }): Promise<CommandResult> {
    const current = this.ctx.goals.get(invocation.agent)
    if (current === undefined) return { kind: 'error', text: NO_CURRENT_GOAL_TEXT }
    if (current.phase === 'complete') return { kind: 'error', text: GOAL_ALREADY_COMPLETE_TEXT }
    const worktreePath = invocation.worktreePath ?? this.config.workspaceRoot
    if (worktreePath === undefined) return { kind: 'error', text: WORKTREE_REQUIRED_TEXT }
    const controller = this.controllerFor(invocation.agent)
    const controllerSessionId = ControllerSessionId(invocation.agent.id)
    const bindings = await this.bindingStore.load(controllerSessionId)
    if (!bindings.some(binding => binding.goalId === current.id)) {
      return { kind: 'error', text: NO_BINDING_TEXT }
    }
    const state = devFrameStateOf(this.ctx, invocation.agent.session)
    if (state.failure !== null) return { kind: 'error', text: PROJECTION_FAILURE_TEXT }
    const verification = latestAttributedVerification(state, current.id)
    if (verification === undefined) return { kind: 'error', text: NO_VERIFICATION_TEXT }
    // The review is the log's latest gate decision; goal attribution is
    // enforced structurally by the controller, so a foreign review reaches
    // that check instead of being silently filtered here.
    const review = latestReview(state)
    if (review === undefined) return { kind: 'error', text: NO_REVIEW_TEXT }
    // The graded memory-degradation records attributed to the current goal's
    // bound tasks (AT3-07): a fail-graded record is the task's real failure
    // evidence the admission consumes.
    const boundTaskIds = new Set(
      bindings.find(binding => binding.goalId === current.id)?.taskIds.map(taskId => String(taskId)) ?? [],
    )
    const taskWarnings = state.taskWarnings.filter(warning => boundTaskIds.has(String(warning.taskId)))
    const request: CompleteGoalRequest = {
      worktreePath,
      checks: verification.checks,
      requiredChecksDigest: verification.requiredChecks.digest,
      requiredChecksStore: this.requiredChecksStore,
      review,
      taskWarnings,
    }
    const verdict = await controller.complete({ controllerSessionId, goalId: current.id }, request)
    if (verdict.kind !== 'admitted') {
      const text = await this.renderRejectedCompletion(
        controller,
        { controllerSessionId, goalId: current.id },
        verdict,
      )
      return { kind: 'error', text }
    }
    const completed = this.ctx.goals.get(invocation.agent)
    if (completed === undefined) {
      throw new TypeError('admitted completion left no current goal to receipt')
    }
    this.ctx.goals.recordReceipt(
      invocation.agent,
      { id: completed.id, revision: completed.revision },
      [completionAdmissionEvidence(completed.id, verdict)],
    )
    return { kind: 'success', text: renderCompletionSuccess() }
  }

  /** Lazily build and cache the controller bound to one live agent. */
  private controllerFor(agent: Agent): GoalBindingController {
    let controller = this.controllers.get(agent.id)
    if (controller === undefined) {
      controller = new GoalBindingController({
        workspaceId: this.config.workspaceId,
        controllerSessionId: ControllerSessionId(agent.id),
        goals: new GoalServicePort({ goals: this.ctx.goals, agent }),
        store: this.bindingStore,
      })
      this.controllers.set(agent.id, controller)
    }
    return controller
  }

  /**
   * Render a completion rejection, consuming a fail-graded terminal into the
   * bounded repair cycle (AT1-08): a task-warning rejection charges one
   * repair round at the same call point a `changes_required` rejection uses,
   * so the post-fail resume stays inside the repair budget — an admitted
   * round reports its charge, and exhaustion names the human-authorized
   * resume as the only continuation. Every other stage renders unchanged.
   * @param controller - the controller whose repair accounting is charged.
   * @param identity - the controller Session and Goal the rejection belongs to.
   * @param verdict - the rejected admission verdict.
   * @returns the stage-prefixed rejection text with the repair-cycle outcome.
   */
  private async renderRejectedCompletion(
    controller: GoalBindingController,
    identity: GoalBindingIdentity,
    verdict: Exclude<CompletionAdmissionVerdict, { kind: 'admitted' }>,
  ): Promise<string> {
    const text = renderCompletionRejection(verdict)
    if (verdict.stage !== 'task-warning') return text
    const repair = await controller.beginRepairRound(identity)
    if (repair.kind === 'admitted') {
      return `${text} Repair round ${repair.repairRound} was charged (${repair.remainingRepairRounds} remaining); resuming the goal requires a human-authorized resume.`
    }
    return `${text} The repair limit (${repair.repairLimit}) is exhausted after ${repair.consumedRepairRounds} charged rounds; continuing requires a human-authorized resume.`
  }
}

/**
 * Return the newest verification record attributed to one goal.
 * @param state - the devframe projection state of the controller session.
 * @param goalId - the goal the evidence must be attributed to.
 * @returns the latest attributed record in log order, or `undefined`.
 */
function latestAttributedVerification(
  state: DevFrameProjectionState,
  goalId: GoalId,
): DevFrameVerificationEventData | undefined {
  for (let index = state.verifications.length - 1; index >= 0; index -= 1) {
    const record = state.verifications[index]
    if (record !== undefined && record.binding.goalId === goalId) return record
  }
  return undefined
}

/**
 * Return the newest review record of the projection, regardless of goal.
 * @param state - the devframe projection state of the controller session.
 * @returns the latest record in log order, or `undefined` when none exists.
 */
function latestReview(state: DevFrameProjectionState): DevFrameReviewEventData | undefined {
  return state.reviews[state.reviews.length - 1]
}
