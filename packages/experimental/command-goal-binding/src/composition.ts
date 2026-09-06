/**
 * The `/goal-complete` composition service: one per-composition owner that
 * lazily builds the {@link GoalBindingController} per controller Session over
 * the live native Goal service, selects completion evidence from the
 * controller Session's devframe projection, and lands the admitted verdict as
 * a durable completion receipt. The command handler is its only production
 * entry; `startBinding` is the composition's test-visible start lane and is
 * deliberately not a command verb.
 * @module @deepseek-ai/dsh-experimental-command-goal-binding/composition
 */

import { Service, type Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { CommandResult } from '@deepseek-ai/dsh-commands'
import type {} from '@deepseek-ai/dsh-session-projection'
import type { GoalId } from '@deepseek-ai/dsh-goal/types'
import { ControllerSessionId, GoalBindingController, GoalServicePort, MemoryGoalBindingStore, createHumanAuthorization } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type {
  CompleteGoalRequest,
  GoalAdmission,
  GoalBinding,
  GoalBindingStore,
  GoalBudgetInput,
  TaskId,
} from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type { AcceptanceHash, DevFrameSnapshotId, SourceFingerprint } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { MemoryRequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import type { RequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { devFrameProjectionDefinition } from '@deepseek-ai/dsh-experimental-devframe/src/projection.ts'
import type { DevFrameProjectionState } from '@deepseek-ai/dsh-experimental-devframe/src/projection.ts'
import type { DevFrameReviewEventData, DevFrameVerificationEventData } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import {
  GOAL_ALREADY_COMPLETE_TEXT,
  NO_BINDING_TEXT,
  NO_CURRENT_GOAL_TEXT,
  NO_REVIEW_TEXT,
  NO_VERIFICATION_TEXT,
  PROJECTION_FAILURE_TEXT,
  WORKTREE_REQUIRED_TEXT,
  completionAdmissionEvidence,
  goalCompleteDescriptor,
  parseGoalCompleteInput,
  renderCompletionRejection,
  renderCompletionSuccess,
} from './command.ts'
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
 * It registers the devframe projection unit and the `/goal-complete` command,
 * and owns the controller registry plus both replaceable reference stores.
 */
export class GoalBindingComposition extends Service {
  /** Durable binding store backing every controller of this composition. */
  readonly bindingStore: GoalBindingStore
  /** Approved-checks configuration store resolving evidence digests. */
  readonly requiredChecksStore: RequiredChecksConfigStore

  private readonly controllers = new Map<string, GoalBindingController>()

  /**
   * Construct the composition inside the owning plugin fiber: registering the
   * projection unit and the command here ties both registrations to that
   * fiber's lifetime (the Goal service registers its own projection the same
   * way).
   * @param ctx - the plugin fiber's context carrying `commands`, `goals`, and
   *   `sessionProjections`.
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
    ctx.sessionProjections.register(devFrameProjectionDefinition)
    ctx.effect(() => ctx.commands.register({
      ...goalCompleteDescriptor(),
      handler: invocation => this.completeCurrent({
        agent: invocation.agent,
        worktreePath: parseGoalCompleteInput(invocation.rawInput),
      }),
    }), 'command-goal-binding.register')
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
    const state = this.ctx.sessionProjections.stateOf(invocation.agent.session, 'devframe')
    /* v8 ignore next 1 -- this service registers the devframe unit in its constructor, so the key cannot be absent while its own command runs */
    if (state === undefined) throw new TypeError('devframe projection state is unavailable for the controller session')
    if (state.failure !== null) return { kind: 'error', text: PROJECTION_FAILURE_TEXT }
    const verification = latestAttributedVerification(state, current.id)
    if (verification === undefined) return { kind: 'error', text: NO_VERIFICATION_TEXT }
    // The review is the log's latest gate decision; goal attribution is
    // enforced structurally by the controller, so a foreign review reaches
    // that check instead of being silently filtered here.
    const review = latestReview(state)
    if (review === undefined) return { kind: 'error', text: NO_REVIEW_TEXT }
    const request: CompleteGoalRequest = {
      worktreePath,
      checks: verification.checks,
      requiredChecksDigest: verification.requiredChecks.digest,
      requiredChecksStore: this.requiredChecksStore,
      review,
    }
    const verdict = await controller.complete({ controllerSessionId, goalId: current.id }, request)
    if (verdict.kind !== 'admitted') {
      return { kind: 'error', text: renderCompletionRejection(verdict) }
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
