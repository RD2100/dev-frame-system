/**
 * The DevFrame host command composition service: one per-composition owner
 * that lazily builds the {@link GoalBindingController} per controller Session
 * over the live native Goal service, selects completion evidence from the
 * controller Session's devframe projection, lands the admitted verdict as a
 * durable completion receipt, and owns the `/devframe-start`,
 * `/devframe-resume`, `/devframe-stop`, and `/devframe-abandon` lanes. Every
 * command handler is a production entry; `startBinding` stays the
 * composition's test-visible start lane.
 * @module @deepseek-ai/dsh-experimental-command-goal-binding/composition
 */

import { Service, type Context } from '@deepseek-ai/cordis'
import { realpathSync } from 'node:fs'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { CommandResult } from '@deepseek-ai/dsh-commands'
import type { Session } from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-session-projection'
import type { GoalId } from '@deepseek-ai/dsh-goal/types'
import { AgentEvidenceJournal } from '@deepseek-ai/dsh-experimental-agent-evidence'
import { ControllerSessionId, GoalBindingController, GoalServicePort, MemoryGoalBindingStore, createHumanAuthorization } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type {
  CompleteGoalRequest,
  CompletionAdmissionVerdict,
  FinalIntegrationContract,
  GoalAdmission,
  GoalBinding,
  GoalBindingIdentity,
  GoalBindingStore,
  GoalBudgetInput,
  GoalResultBinding,
  TaskId,
} from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { selectGoalCompletionEvidence } from '@deepseek-ai/dsh-experimental-project-controller'
import type { MainTreeIntegrationRecord } from '@deepseek-ai/dsh-experimental-project-controller'
import {
  acceptanceRegionStartOf,
  computeSourceFingerprint,
  stopProject,
} from '@deepseek-ai/dsh-experimental-devframe'
import type {
  StopProcess,
  StopProjectOptions,
} from '@deepseek-ai/dsh-experimental-devframe'
import { setTimeout as delay } from 'node:timers/promises'
import type {
  AcceptanceHash,
  DevFrameSnapshotId,
  SourceFingerprint,
  WorkspaceId,
} from '@deepseek-ai/dsh-experimental-devframe/shared'
import { ConfigurationConfirmationId, DevFrameSnapshotId as makeSnapshotId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { MemoryRequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe'
import type { RequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe'
import { devFrameProjectionDefinition } from '@deepseek-ai/dsh-experimental-devframe'
import type { DevFrameProjectionState } from '@deepseek-ai/dsh-experimental-devframe'
import { DevFrameSessionJournal } from '@deepseek-ai/dsh-experimental-devframe'
import type { DevFrameFlush, DevFrameReviewEventData, DevFrameVerificationEventData } from '@deepseek-ai/dsh-experimental-devframe'
import { taskWarningListener as taskWarningListenerPlugin, taskFailDisarm as taskFailDisarmPlugin } from '@deepseek-ai/dsh-experimental-devframe'
import {
  ABANDON_INPUT_UNEXPECTED_TEXT,
  ABANDON_NO_BINDING_RECORD_TEXT,
  ABANDON_NO_CURRENT_GOAL_TEXT,
  ABANDON_UNRESOLVED_STATE_TEXT,
  GOAL_ALREADY_COMPLETE_TEXT,
  NO_BINDING_TEXT,
  NO_CURRENT_GOAL_TEXT,
  NO_REVIEW_TEXT,
  NO_VERIFICATION_TEXT,
  PROJECTION_FAILURE_TEXT,
  RESUME_INPUT_UNEXPECTED_TEXT,
  RESUME_NO_BINDING_RECORD_TEXT,
  RESUME_NO_CURRENT_GOAL_TEXT,
  RESUME_STOP_PENDING_TEXT,
  REVIEW_SUPERSEDED_TEXT,
  START_GOAL_RUNNING_TEXT,
  START_OBJECTIVE_REQUIRED_TEXT,
  START_WORKTREE_REQUIRED_TEXT,
  STOP_ALREADY_PENDING_TEXT,
  STOP_ALREADY_STOPPED_TEXT,
  STOP_CHAIN_INVENTORY_UNVERIFIED_NOTE,
  STOP_IN_PROGRESS_TEXT,
  STOP_INPUT_UNEXPECTED_TEXT,
  STOP_NO_BINDING_RECORD_TEXT,
  STOP_NO_CURRENT_GOAL_TEXT,
  VERIFICATION_SUPERSEDED_TEXT,
  WORKTREE_REQUIRED_TEXT,
  completionAdmissionEvidence,
  devframeAbandonDescriptor,
  devframeResumeDescriptor,
  devframeStartDescriptor,
  devframeStopDescriptor,
  goalCompleteDescriptor,
  parseDevframeAbandonInput,
  parseDevframeResumeInput,
  parseDevframeStartInput,
  parseDevframeStopInput,
  parseGoalCompleteInput,
  renderAbandonSuccess,
  renderCompletionRejection,
  renderCompletionSuccess,
  renderFinalMergeIncomplete,
  renderResumeAdoptedSuccess,
  renderResumeSuccess,
  renderStartSuccess,
  renderStopChainBookkeepingUnsettledText,
  renderStopChainNeedsAttentionText,
  renderStopChainStoppedText,
  renderStopSuccess,
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
  /**
   * Durable integration receipts scoped to the invoking controller Session.
   * Loader activation reads the owning project controller. Missing receipts
   * refuse completion once a task delivers or merged evidence is recorded.
   */
  readonly goalCompletionIntegrations?: (controllerSessionId: Session['id']) => readonly MainTreeIntegrationRecord[]
  /** Validate live registered controller ownership of the authoritative final target. */
  readonly goalCompletionGuard?: (agent: Agent, targetPath: string, workspaceId: WorkspaceId) => void
  /**
   * Host-injected stop-chain adapters (AT4-06). `tree` returns the project's
   * participating agents — the receiving root plus every real descendant
   * agent — host-verified through the dispatch lineage: an agent belongs when
   * its session's `parentSession` chain reaches the given root, so workers on
   * independent worktrees are included and unrelated projects' sessions are
   * never drained. `processes` returns every captured descendant process
   * scoped to the receiving root; a composition without it has no provable
   * process inventory, and the chain fails closed on it instead of reading
   * emptiness as quiescence. `resumeResources` prepares the root-scoped
   * resources a resume lane reacquires after resource admission; it is
   * synchronous, prepare-all, and re-enterable. `acquireWriter` reacquires
   * the receiving root's writer lock during resume — the authorization
   * becomes effective only once the lock is held again, it must tolerate
   * repeat invocation because a retry after a later failure re-enters it,
   * and an acquire failure refuses the resume with the writer untouched.
   * `releaseWriter` is the owner-checked writer release for the given
   * receiving root; it may be asynchronous and the chain reports `stopped`
   * only after it settles, and it must tolerate repeat invocation because
   * the confirmed-stop recovery path retries it. The chain fails closed: a
   * missing or empty tree inventory refuses the writer release, and a
   * composition constructed without `releaseWriter` reports
   * `needs_attention` and retains the writer — never a silent release.
   */
  readonly stop?: {
    readonly tree?: (root: Agent) => readonly Agent[]
    readonly processes?: (root: Agent) => readonly StopProcess[]
    readonly resumeResources?: (root: Agent) => void
    readonly acquireWriter?: (root: Agent) => Promise<void>
    readonly releaseWriter?: (root: Agent) => void | Promise<void>
  }
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
 * `/devframe-start`, `/devframe-resume`, `/devframe-stop`, and
 * `/devframe-abandon` commands, and owns the controller
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
  /** Host-supplied durable integration rows for the final-merge completion gate. */
  private readonly goalCompletionIntegrations: (controllerSessionId: Session['id']) => readonly MainTreeIntegrationRecord[]
  private readonly goalCompletionGuard: NonNullable<GoalBindingCompositionStores['goalCompletionGuard']>
  /** One in-flight stop chain per agent; concurrent chains refuse. */
  private readonly stopChains = new Map<string, Promise<CommandResult>>()
  /** The native flush closure the journals and the stop chain share. */
  private readonly sessionFlusher: DevFrameFlush
  /** Host-captured descendant processes handed to the stop chain; absent means no provable inventory. */
  private readonly stopProcesses: ((root: Agent) => readonly StopProcess[]) | undefined
  /** Host-captured root-scoped resources a resume lane prepares after admission. */
  readonly stopResumeResources: ((root: Agent) => void) | undefined
  /** Host writer-lock reacquisition; the resume authorization-effective boundary. */
  private readonly stopAcquireWriter: ((root: Agent) => Promise<void>) | undefined
  /** Host-verified project tree (root plus descendants); absent fails closed. */
  private readonly stopTree: ((root: Agent) => readonly Agent[]) | undefined
  /** Host writer release; absent means the chain retains the writer loudly. */
  private readonly stopReleaseWriter: ((root: Agent) => void | Promise<void>) | undefined

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
    this.goalCompletionIntegrations = stores.goalCompletionIntegrations ?? (() => [])
    this.goalCompletionGuard = stores.goalCompletionGuard ?? (() => { throw new Error('Goal completion controller ownership is unavailable') })
    const flush = sessionFlush(ctx)
    this.sessionFlusher = flush
    this.stopProcesses = stores.stop?.processes
    this.stopResumeResources = stores.stop?.resumeResources
    this.stopAcquireWriter = stores.stop?.acquireWriter
    this.stopTree = stores.stop?.tree
    this.stopReleaseWriter = stores.stop?.releaseWriter
    const reviewerDirectory = new ProjectionEvidenceReviewerDirectory(ctx)
    this.journal = compositionDevFrameJournal(flush, reviewerDirectory)
    this.evidenceJournal = new AgentEvidenceJournal({ flush, reviewerDirectory })
    ctx.sessionProjections.register(devFrameProjectionDefinition)
    // The graded-listener family mounts here, on the composition fiber — same
    // lifetime in, same lifetime out. The grading listener lands the per-task
    // memory-degradation records; the fail-disarm listener withdraws automatic
    // goal continuation from a fail-graded record through the native goal
    // port the goal-round-driver obeys.
    void ctx.plugin(taskWarningListenerPlugin)
    void ctx.plugin(taskFailDisarmPlugin)
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
    ctx.effect(() => ctx.commands.register({
      ...devframeStopDescriptor(),
      handler: invocation => this.stopBoundGoal({
        agent: invocation.agent,
        rawInput: invocation.rawInput,
      }),
    }), 'command-goal-binding.register-stop')
    ctx.effect(() => ctx.commands.register({
      ...devframeAbandonDescriptor(),
      handler: invocation => this.abandonBoundGoal({
        agent: invocation.agent,
        rawInput: invocation.rawInput,
      }),
    }), 'command-goal-binding.register-abandon')
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
    const snapshotId = makeSnapshotId(`snapshot-v2-${computed.headCommit}-${computed.stateHash}`)
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
   * When the deployment's approved checks hash differently from the stored
   * acceptance (AT1-10), the lane adopts the recomputed acceptance into a
   * new binding generation, re-verifies the real approved checks for it,
   * and reports the adoption; the superseded generation's evidence and
   * review stop counting while usage bridges by Goal identity.
   * @param invocation - the receiving agent plus the verbatim command text.
   * @returns a success result, or a stable error result for the expected
   *   data refusals (unexpected input, no current goal, already complete, no
   *   binding record, pending stop). Structural failures propagate unchanged.
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
    // A pending stop (`stop_requested`/`quiescence_confirmed`) is the
    // uncertain state the lifecycle fold refuses to leave for
    // `admission_open`: resuming here would latch a replay failure, so the
    // lane refuses as data while the stop flow is unresolved.
    const currentLifecycle = projected?.lifecycle ?? stored?.lifecycle
    if (currentLifecycle === 'stop_requested' || currentLifecycle === 'quiescence_confirmed') {
      return { kind: 'error', text: RESUME_STOP_PENDING_TEXT }
    }
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
    // AT1-10: changing the approved checks invalidates the running goal's
    // evidence without resetting its usage. The binding freezes the
    // acceptance of (objective, checks at start); when the deployment's
    // current approved checks hash differently, the resume opens a new
    // binding generation that adopts the recomputed acceptance behind a
    // fresh human confirmation, and this lane re-verifies the real approved
    // checks for the new generation — the superseded generation's evidence
    // and review stop counting while usage keeps bridging by Goal identity.
    const bindingForAdoption = projected ?? stored
    if (bindingForAdoption === undefined) {
      return { kind: 'error', text: RESUME_NO_BINDING_RECORD_TEXT }
    }
    const expectedHash = acceptanceHashOf(current.objective, this.config.checks)
    const adoption = expectedHash === bindingForAdoption.acceptanceHash ? undefined : {
      acceptanceHash: expectedHash,
      confirmation: {
        id: ConfigurationConfirmationId(`devframe-resume:${invocation.agent.id}:${Date.now()}`),
        acceptanceHash: expectedHash,
      },
    }
    const resumed = await this.controllerFor(invocation.agent).resume(
      { controllerSessionId, goalId: current.id },
      createHumanAuthorization(`devframe-resume:${invocation.agent.id}:${Date.now()}`),
      adoption,
    )
    // Writer reacquisition is the authorization-effective boundary: the
    // resumed binding counts on the host only once the root's writer lock is
    // held again, and an acquire failure refuses the resume with the writer
    // untouched. The resource face is prepare-all synchronous and
    // re-enterable, so a retry after a later failure re-enters both faces.
    if (this.stopAcquireWriter !== undefined) await this.stopAcquireWriter(invocation.agent)
    if (this.stopResumeResources !== undefined) this.stopResumeResources(invocation.agent)
    await landGoalBinding(this.journal, invocation.agent.session, resumed)
    if (adoption !== undefined) {
      const requiredChecksDigest = await this.requiredChecksStore.save(this.config.checks)
      await this.evidenceJournal.recordVerification({
        session: invocation.agent.session,
        binding: resultTupleOf(resumed),
        requiredChecksDigest,
        requiredChecksStore: this.requiredChecksStore,
      })
      return { kind: 'success', text: renderResumeAdoptedSuccess() }
    }
    return { kind: 'success', text: renderResumeSuccess() }
  }

  /**
   * Execute one `/devframe-stop` invocation: record a human-authorized stop
   * request for the agent's current unfinished bound goal. The lane resolves
   * the binding between the log projection and the binding store, refuses
   * the expected data refusals as stable errors (unexpected input, no
   * current goal, already complete, no binding record, stop already
   * pending), and delegates the structural work to the controller's
   * {@link GoalBindingController.stop}: admission closes, the native Goal is
   * disarmed, and the binding persists at `stop_requested`, which the lane
   * lands on the session log as the durable authority. The terminal
   * `stopped` state stays reachable through the existing lifecycle
   * vocabulary; the stop flow owns quiescence confirmation and writer
   * release. Structural failures propagate unchanged.
   *
   * With `stopChain` enabled (AT4-06), the invocation additionally runs the
   * real reliability stop chain over the same binding: admission fences,
   * owned jobs and captured processes drain within the configured grace, the
   * session state flushes, and the writer releases only after the confirmed
   * chain. Concurrent chains refuse; a chain that cannot confirm quiescence
   * reports the unresolved resources, retains the writer, and leaves the
   * goal in the stop flow. Without the flag the vocabulary face is
   * byte-identical to the pre-chain lane.
   * @param invocation - the receiving agent plus the verbatim command text.
   * @returns a success result after the stop-requested binding lands (or the
   *   chain confirms the stop), or a stable error result.
   */
  async stopBoundGoal(invocation: {
    readonly agent: Agent
    readonly rawInput: string
  }): Promise<CommandResult> {
    if (parseDevframeStopInput(invocation.rawInput).length > 0) {
      return { kind: 'error', text: STOP_INPUT_UNEXPECTED_TEXT }
    }
    const current = this.ctx.goals.get(invocation.agent)
    if (current === undefined) return { kind: 'error', text: STOP_NO_CURRENT_GOAL_TEXT }
    if (current.phase === 'complete') return { kind: 'error', text: GOAL_ALREADY_COMPLETE_TEXT }
    if (!this.config.stopChain) {
      const controllerSessionId = ControllerSessionId(invocation.agent.id)
      const projected = devFrameStateOf(this.ctx, invocation.agent.session)
        .bindings.find(binding => binding.goalId === current.id)
      const stored = (await this.bindingStore.load(controllerSessionId))
        .find(binding => binding.goalId === current.id)
      if (projected === undefined && stored === undefined) {
        return { kind: 'error', text: STOP_NO_BINDING_RECORD_TEXT }
      }
      const currentLifecycle = projected?.lifecycle ?? stored?.lifecycle
      if (currentLifecycle === 'stop_requested' || currentLifecycle === 'quiescence_confirmed') {
        return { kind: 'error', text: STOP_ALREADY_PENDING_TEXT }
      }
      const stopped = await this.controllerFor(invocation.agent).stop(
        { controllerSessionId, goalId: current.id },
        createHumanAuthorization(`devframe-stop:${invocation.agent.id}:${Date.now()}`),
      )
      await landGoalBinding(this.journal, invocation.agent.session, stopped)
      return { kind: 'success', text: renderStopSuccess() }
    }
    // The in-flight guard must run synchronously: between the stored promise
    // and its first await no other invocation can slip past the check.
    if (this.stopChains.has(invocation.agent.id)) {
      return { kind: 'error', text: STOP_IN_PROGRESS_TEXT }
    }
    const chain = Promise.resolve()
      .then(() => this.runStopChain(invocation.agent, current))
      .finally(() => { this.stopChains.delete(invocation.agent.id) })
    this.stopChains.set(invocation.agent.id, chain)
    return chain
  }

  /**
   * Run the reliability stop chain for one agent's current goal: the
   * controller's stop request lands first (the vocabulary face), then the
   * real chain drains jobs and captured processes and flushes the session
   * state; the confirmed-quiescence record is the durable pre-release
   * prerequisite, and the stopped terminal record, store entry, and
   * checkpoint land only AFTER the writer release actually succeeded — a
   * release failure never lands `stopped`, and both terminal landings are
   * bounded by the stop grace so a never-settling persistence face cannot
   * hang the command. Every unconfirmed resource
   * retains the writer and reports `needs_attention`; the goal stays in the
   * stop flow for a rerun. A log left at `quiescence_confirmed` (a release
   * that failed, or a crash between the confirmation and the release)
   * converges through {@link finishConfirmedStop}; a log left at
   * `stop_requested` (a crash during the drain) re-enters the drain through
   * {@link resumeStopRequestedStop} — the repeat stop is not refused in
   * either state.
   * @param agent - the receiving agent whose writer the chain drains.
   * @param current - the goal read before the chain serialized.
   * @returns a success result after the confirmed stop, or a stable error.
   */
  private async runStopChain(agent: Agent, current: { readonly id: GoalId }): Promise<CommandResult> {
    const controllerSessionId = ControllerSessionId(agent.id)
    const projected = devFrameStateOf(this.ctx, agent.session)
      .bindings.find(binding => binding.goalId === current.id)
    const stored = (await this.bindingStore.load(controllerSessionId))
      .find(binding => binding.goalId === current.id)
    if (projected === undefined && stored === undefined) {
      return { kind: 'error', text: STOP_NO_BINDING_RECORD_TEXT }
    }
    const currentLifecycle = projected?.lifecycle ?? stored?.lifecycle
    if (currentLifecycle === 'stopped') {
      return { kind: 'error', text: STOP_ALREADY_STOPPED_TEXT }
    }
    if (currentLifecycle === 'stop_requested') {
      // A crash while the chain waited in its drain leaves the log here —
      // a normal failure window for a stop the human explicitly asked for.
      // Re-enter the drain instead of refusing the repeat.
      const requested = projected ?? stored
      if (requested !== undefined) return this.resumeStopRequestedStop(agent, requested)
      return { kind: 'error', text: STOP_NO_BINDING_RECORD_TEXT }
    }
    if (currentLifecycle === 'quiescence_confirmed') {
      // The drain already confirmed; only the release and the terminal
      // bookkeeping remain. Re-enter there instead of refusing the repeat.
      const confirmed = projected ?? stored
      if (confirmed !== undefined) return this.finishConfirmedStop(agent, confirmed)
      return { kind: 'error', text: STOP_NO_BINDING_RECORD_TEXT }
    }
    const controller = this.controllerFor(agent)
    const stopped = await controller.stop(
      { controllerSessionId, goalId: current.id },
      createHumanAuthorization(`devframe-stop:${agent.id}:${Date.now()}`),
    )
    await landGoalBinding(this.journal, agent.session, stopped)
    return this.stopChainDrain(agent, controller, stopped)
  }

  /**
   * Re-enter a stop flow whose request already landed: a crash while the
   * chain waited in its drain leaves the log at `stop_requested` — a normal
   * failure window for a stop the human explicitly asked for, and the cold
   * restart must be able to finish it. The recovery mirrors the fresh chain:
   * rebuild the admission fence and re-run the drain over the host's
   * verified inventory and live registry identities, then finish honestly.
   * A missing live identity or an unverifiable inventory surfaces as
   * `needs_attention` with the writer held — never a silent bypass, and no
   * goal work is restarted.
   * @param agent - the receiving agent whose writer the chain drains.
   * @param base - the persisted stop_requested binding carrying the flow's identity.
   * @returns a success result after the confirmed stop, or a stable error.
   */
  private async resumeStopRequestedStop(agent: Agent, base: GoalBinding): Promise<CommandResult> {
    const controller = this.controllerFor(agent)
    return this.stopChainDrain(agent, controller, base)
  }

  /**
   * Run the drain-and-finish body of the stop chain from one stop-flow
   * base: the primitive re-observes the flow (an idempotent `stop_requested`
   * repeat), drains the tree's jobs and processes, flushes every
   * participating session, and releases the writer only on confirmed
   * quiescence. The confirmed-quiescence record is the durable pre-release
   * prerequisite; the stopped terminal record, store entry, and checkpoint
   * land only AFTER the writer release actually succeeded — a release
   * failure never lands `stopped`, and both terminal landings are bounded
   * by the stop grace so a never-settling persistence face cannot hang the
   * command. Every unconfirmed resource retains the writer and reports
   * `needs_attention`; the goal stays in the stop flow for a rerun.
   * @param agent - the receiving agent whose writer the chain drains.
   * @param controller - the admission fence controller for the invoking agent.
   * @param base - the stop-flow binding whose identity the observations carry.
   * @returns a success result after the confirmed stop, or a stable error.
   */
  private async stopChainDrain(agent: Agent, controller: GoalBindingController, base: GoalBinding): Promise<CommandResult> {
    // The chain's observation callbacks are synchronous, while each landed
    // record owns a trailing flush promise: the chain's own flush drains
    // those first, so an unlandable observation fails the chain's flush and
    // retains the writer instead of releasing over a lost record.
    const recordLandings: Array<Promise<unknown>> = []
    // Project-tree stop (AT4-06): the host's verified tree face supplies the
    // receiving root plus every real descendant agent, so the primitive's
    // owner filters see descendant jobs and processes and the flush covers
    // every participating session. A missing or empty inventory is fail-closed:
    // the root still drains, but the writer release is refused instead of
    // claiming a clean tree stop over an unverifiable inventory. The process
    // inventory is fail-closed the same way: a composition without a mounted
    // capture face has no provable inventory, and the primitive's inventory
    // attempt turns that refusal into a chain issue instead of reading
    // emptiness as quiescence.
    const treeAgents = this.stopTree?.(agent) ?? []
    const inventoryUnverified = this.stopTree === undefined || treeAgents.length === 0
    const agents = [agent, ...treeAgents.filter(candidate => candidate.id !== agent.id)]
    const treeSessions = new Map<string, Session>()
    for (const treeAgent of agents) treeSessions.set(treeAgent.id, treeAgent.session)
    // A missing jobs registry is a fail-closed misconfiguration, not a
    // verified zero-jobs state: the throwing adapter turns into a chain
    // issue, so the primitive refuses the release instead of trusting an
    // unverifiable empty job inventory (absent ≠ quiet).
    const jobs = this.ctx.jobs ?? {
      list: () => { throw new Error('no jobs registry is mounted for this composition') },
      kill: () => { throw new Error('no jobs registry is mounted for this composition') },
      wait: async () => { throw new Error('no jobs registry is mounted for this composition') },
    }
    const options: StopProjectOptions = {
      agents,
      registry: this.ctx.agents,
      goals: this.ctx.goals,
      jobs,
      processes: () => {
        if (this.stopProcesses === undefined) {
          throw new Error('no captured process inventory is mounted for this composition')
        }
        return this.stopProcesses(agent)
      },
      graceMs: this.config.stopGraceMs,
      closeAdmission: () => {
        controller.closeAdmission()
        // Fence every cached controller of this workspace-scoped
        // composition: the tree's goal dispatch faces stop admitting.
        for (const treeController of this.controllers.values()) treeController.closeAdmission()
      },
      record: (observation) => {
        recordLandings.push(landGoalBinding(this.journal, agent.session, {
          ...base,
          lifecycle: observation.status,
        }))
      },
      flush: async () => {
        await Promise.all(recordLandings)
        // Every participating session's state must be durable before the
        // release — not just the invoking root session. The confirmed
        // quiescence record is the chain's durable pre-release
        // prerequisite; the stopped terminal lands only after the release
        // actually succeeded.
        for (const treeSession of treeSessions.values()) await this.sessionFlusher(treeSession)
      },
      releaseWriter: () => {
        if (inventoryUnverified) {
          throw new Error('the project tree inventory is missing or empty; the writer release is refused')
        }
        if (this.stopReleaseWriter === undefined) {
          throw new Error('the writer release is not wired for this composition')
        }
        // The face's promise IS the release: returning it lets the primitive
        // await the actual settlement, so a pending or rejected release folds
        // needs_attention instead of reporting stopped over a held writer.
        return this.stopReleaseWriter(agent)
      },
    }
    const result = await stopProject(options)
    this.controllers.delete(agent.id)
    // The stopped terminal lands only after the release actually succeeded;
    // needs_attention keeps the flow re-stoppable. Both landings are bounded
    // by the stop grace: a persistence face that never settles must not hang
    // the command past the chain's own bound.
    if (result.status === 'stopped') {
      try {
        await this.landTerminalBookkeeping(agent, { ...base, lifecycle: 'stopped' })
      } catch {
        return { kind: 'error', text: renderStopChainBookkeepingUnsettledText(true) }
      }
      return { kind: 'success', text: renderStopChainStoppedText() }
    }
    try {
      await this.landTerminalBookkeeping(agent, { ...base, lifecycle: 'needs_attention' })
    } catch {
      return { kind: 'error', text: renderStopChainBookkeepingUnsettledText(false) }
    }
    const text = renderStopChainNeedsAttentionText(result.remaining)
    return {
      kind: 'error',
      text: inventoryUnverified ? `${text} ${STOP_CHAIN_INVENTORY_UNVERIFIED_NOTE}` : text,
    }
  }

  /**
   * Bound one stop-path work promise by the stop grace: a persistence face
   * that never settles must not hang the composition past the chain's own
   * bound. The losing work keeps running and converges the durable state
   * late; the next stop reconciles against whatever landed.
   * @param work - the bookkeeping or flush work to bound.
   * @throws when the work does not settle within the configured stop grace.
   */
  private async boundedStopWork(work: Promise<void>): Promise<void> {
    const bound = delay(this.config.stopGraceMs).then(() => {
      throw new Error('the stop work did not settle within the grace bound')
    })
    await Promise.race([work, bound])
  }

  /**
   * Land one terminal binding as the stop flow's bookkeeping: the record
   * append first (the log is the binding authority), then the store entry
   * and the checkpoint, all bounded by the stop grace.
   * @param agent - the receiving agent whose session carries the record.
   * @param finalBinding - the terminal binding to land durably.
   * @throws when the bookkeeping fails or does not settle within the bound.
   */
  private async landTerminalBookkeeping(agent: Agent, finalBinding: GoalBinding): Promise<void> {
    await this.boundedStopWork((async () => {
      await landGoalBinding(this.journal, agent.session, finalBinding)
      await this.bindingStore.save(finalBinding)
      await this.bindingStore.write({
        workspaceId: finalBinding.workspaceId,
        controllerSessionId: finalBinding.controllerSessionId,
        goalId: finalBinding.goalId,
        goalRevision: finalBinding.goalRevision,
        acceptanceHash: finalBinding.acceptanceHash,
        sourceFingerprint: finalBinding.sourceFingerprint,
        confirmation: { ...finalBinding.confirmation },
        lifecycle: finalBinding.lifecycle,
      })
    })())
  }

  /**
   * Converge a stop flow whose drain already confirmed quiescence but whose
   * writer state never resolved: a release that threw, or a crash between
   * the confirmation and the release, leaves the log at
   * `quiescence_confirmed`. The repeat stop is not refused here: flush the
   * participating sessions again, retry the release (the host hook
   * tolerates repeat invocation), and land the stopped terminal. A failed
   * release folds `needs_attention` so the flow stays retryable — a release
   * failure never lands `stopped`.
   * @param agent - the receiving agent whose writer the flow finishes.
   * @param confirmed - the quiescence-confirmed binding carrying the flow's identity.
   * @returns a success result after the released stop, or a stable error.
   */
  private async finishConfirmedStop(agent: Agent, confirmed: GoalBinding): Promise<CommandResult> {
    const treeAgents = this.stopTree?.(agent) ?? []
    const inventoryUnverified = this.stopTree === undefined || treeAgents.length === 0
    try {
      await this.boundedStopWork((async () => {
        for (const treeAgent of [agent, ...treeAgents.filter(candidate => candidate.id !== agent.id)]) {
          await this.sessionFlusher(treeAgent.session)
        }
      })())
    } catch {
      return { kind: 'error', text: renderStopChainBookkeepingUnsettledText(false) }
    }
    if (inventoryUnverified || this.stopReleaseWriter === undefined) {
      await this.landTerminalBookkeeping(agent, { ...confirmed, lifecycle: 'needs_attention' })
      const text = renderStopChainNeedsAttentionText([{ resource: 'writer:release', reason: 'operation_failed' }])
      return {
        kind: 'error',
        text: inventoryUnverified ? `${text} ${STOP_CHAIN_INVENTORY_UNVERIFIED_NOTE}` : text,
      }
    }
    try {
      // The release settles inside the grace bound: a pending or rejected
      // async release folds needs_attention, so `stopped` never lands over a
      // writer the host has not provably released.
      await this.boundedStopWork(Promise.resolve(this.stopReleaseWriter(agent)))
    } catch {
      await this.landTerminalBookkeeping(agent, { ...confirmed, lifecycle: 'needs_attention' })
      return {
        kind: 'error',
        text: renderStopChainNeedsAttentionText([{ resource: 'writer:release', reason: 'operation_failed' }]),
      }
    }
    await this.landTerminalBookkeeping(agent, { ...confirmed, lifecycle: 'stopped' })
    this.controllers.delete(agent.id)
    return { kind: 'success', text: renderStopChainStoppedText() }
  }

  /**
   * Execute one `/devframe-abandon` invocation: record a human-authorized
   * abandon of the agent's current stopped or unfinished bound goal. The
   * controller's {@link GoalBindingController.abandon} closes admission,
   * disarms the native Goal, persists the stop-requested stop-mark for a
   * previously unfinished Goal, and clears the native Goal behind its
   * durable tombstone — the existing vocabulary's expression of "no longer
   * resumable" — while the binding history is retained and no completion is
   * claimed. A fresh stop-mark lands on the session log; an already stopped
   * binding adds no record (a repeat would fold as recorded twice).
   * Structural failures propagate unchanged.
   * @param invocation - the receiving agent plus the verbatim command text.
   * @returns a success result after the abandon, or a stable error result.
   */
  async abandonBoundGoal(invocation: {
    readonly agent: Agent
    readonly rawInput: string
  }): Promise<CommandResult> {
    if (parseDevframeAbandonInput(invocation.rawInput).length > 0) {
      return { kind: 'error', text: ABANDON_INPUT_UNEXPECTED_TEXT }
    }
    const current = this.ctx.goals.get(invocation.agent)
    if (current === undefined) return { kind: 'error', text: ABANDON_NO_CURRENT_GOAL_TEXT }
    if (current.phase === 'complete') return { kind: 'error', text: GOAL_ALREADY_COMPLETE_TEXT }
    const controllerSessionId = ControllerSessionId(invocation.agent.id)
    const projected = devFrameStateOf(this.ctx, invocation.agent.session)
      .bindings.find(binding => binding.goalId === current.id)
    const stored = (await this.bindingStore.load(controllerSessionId))
      .find(binding => binding.goalId === current.id)
    if (projected === undefined && stored === undefined) {
      return { kind: 'error', text: ABANDON_NO_BINDING_RECORD_TEXT }
    }
    const currentLifecycle = projected?.lifecycle ?? stored?.lifecycle
    if (currentLifecycle !== 'admission_open' && currentLifecycle !== 'stopped') {
      return { kind: 'error', text: ABANDON_UNRESOLVED_STATE_TEXT }
    }
    // The log is the binding authority: when the stop flow advanced the
    // projected lifecycle past the store's (stop_requested → … → stopped),
    // reconcile the store and evict the stale cached controller so abandon
    // validates against the terminal binding.
    if (projected !== undefined && stored !== undefined && projected.lifecycle !== stored.lifecycle) {
      await this.bindingStore.save(projected)
      await this.bindingStore.write({
        workspaceId: projected.workspaceId,
        controllerSessionId: projected.controllerSessionId,
        goalId: projected.goalId,
        goalRevision: projected.goalRevision,
        acceptanceHash: projected.acceptanceHash,
        sourceFingerprint: projected.sourceFingerprint,
        confirmation: { ...projected.confirmation },
        lifecycle: projected.lifecycle,
      })
      this.controllers.delete(invocation.agent.id)
    }
    const retained = await this.controllerFor(invocation.agent).abandon(
      { controllerSessionId, goalId: current.id },
      createHumanAuthorization(`devframe-abandon:${invocation.agent.id}:${Date.now()}`),
    )
    if (retained.lifecycle === 'stop_requested') {
      await landGoalBinding(this.journal, invocation.agent.session, retained)
    }
    return { kind: 'success', text: renderAbandonSuccess() }
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
    const durableEvidenceUnchanged = await this.journal.checkpoint(invocation.agent.session)
    const state = devFrameStateOf(this.ctx, invocation.agent.session)
    if (state.failure !== null) return { kind: 'error', text: PROJECTION_FAILURE_TEXT }
    // AT1-10: the completion evidence must belong to the goal's current
    // acceptance generation. After a checks-change adoption the superseded
    // generation's verification and review stay attributed in the log but
    // cannot satisfy the adopted acceptance — each refusal names which
    // record is stale so the human knows what to renew. The generation gate
    // stays behind the structural attribution checks the controller enforces
    // (a foreign review propagates its GoalBindingError instead).
    const currentBinding = state.bindings.find(binding => binding.goalId === current.id)
    const regionStart = acceptanceRegionStartOf(state, current.id)
    const verification = latestAttributedVerification(state, current.id)
    if (verification === undefined) return { kind: 'error', text: NO_VERIFICATION_TEXT }
    if (currentBinding === undefined || !isCurrentGeneration(verification, currentBinding, regionStart)) {
      return { kind: 'error', text: VERIFICATION_SUPERSEDED_TEXT }
    }
    // The review is the log's latest gate decision; goal attribution is
    // enforced structurally by the controller, so a foreign review reaches
    // that check instead of being silently filtered here.
    const review = latestReview(state)
    if (review === undefined) return { kind: 'error', text: NO_REVIEW_TEXT }
    if (currentBinding !== undefined && review.binding.goalId === current.id
      && !isCurrentGeneration(review, currentBinding, regionStart)) {
      return { kind: 'error', text: REVIEW_SUPERSEDED_TEXT }
    }
    // Delivered work requires whole-Goal evidence and durable integration receipts.
    let finalIntegration: FinalIntegrationContract | undefined
    try {
      finalIntegration = selectGoalCompletionEvidence({
        state,
        goalId: current.id,
        boundTaskIds: bindings.find(binding => binding.goalId === current.id)?.taskIds ?? [],
        integrations: this.goalCompletionIntegrations(invocation.agent.session.id),
      })
      if (finalIntegration !== undefined) {
        if (realpathSync(worktreePath) !== realpathSync(finalIntegration.targetPath)) {
          throw new Error('Goal completion must use the controller worktree named by its integration receipts')
        }
        this.goalCompletionGuard(invocation.agent, finalIntegration.targetPath, currentBinding.workspaceId)
      }
    } catch (error) {
      return { kind: 'error', text: renderFinalMergeIncomplete(error instanceof Error ? error.message : String(error)) }
    }
    // Merged evidence must retain the current acceptance generation.
    if (finalIntegration !== undefined) {
      if (currentBinding === undefined || !isCurrentGeneration(finalIntegration.verification, currentBinding, regionStart)) {
        return { kind: 'error', text: VERIFICATION_SUPERSEDED_TEXT }
      }
      if (!isCurrentGeneration(finalIntegration.review, currentBinding, regionStart)) {
        return { kind: 'error', text: REVIEW_SUPERSEDED_TEXT }
      }
    }
    // The graded memory-degradation records attributed to the current goal's
    // bound tasks (AT3-07): a fail-graded record is the task's real failure
    // evidence the admission consumes.
    const boundTaskIds = new Set(
      bindings.find(binding => binding.goalId === current.id)?.taskIds.map(taskId => String(taskId)) ?? [],
    )
    const taskWarnings = state.taskWarnings.filter(warning => boundTaskIds.has(String(warning.taskId)))
    const request: CompleteGoalRequest = {
      beforeComplete: () => {
        durableEvidenceUnchanged()
        if (finalIntegration !== undefined) {
          this.goalCompletionGuard(invocation.agent, finalIntegration.targetPath, currentBinding.workspaceId)
          const latest = selectGoalCompletionEvidence({ state: devFrameStateOf(this.ctx, invocation.agent.session),
            goalId: current.id, boundTaskIds: bindings.find(binding => binding.goalId === current.id)!.taskIds,
            integrations: this.goalCompletionIntegrations(invocation.agent.session.id) })
          if (JSON.stringify(latest) !== JSON.stringify(finalIntegration)) throw new Error('Goal completion integration evidence changed during admission')
        }
      },
      worktreePath,
      checks: (finalIntegration?.verification ?? verification).checks,
      requiredChecksDigest: (finalIntegration?.verification ?? verification).requiredChecks.digest,
      requiredChecksStore: this.requiredChecksStore,
      review: finalIntegration?.review ?? review,
      taskWarnings,
      ...(finalIntegration === undefined ? {} : { finalIntegration }),
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
        repairLimit: this.config.repairLimit,
        repairAdmissions: {
          admit: (identity, cause, repairLimit, options) =>
            this.journal.admitRepair(agent.session, { identity, cause, repairLimit }, options),
          state: (identity, repairLimit) => this.journal.repairRoundState(agent.session, identity, repairLimit),
        },
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
    const repair = await controller.beginRepairRound(identity, { kind: 'task-warning', taskId: verdict.taskId })
    if (repair.kind === 'admitted') {
      return `${text} Repair round ${repair.repairRound} was charged (${repair.remainingRepairRounds} remaining); resuming the goal requires a human-authorized resume.`
    }
    return `${text} The repair limit (${repair.repairLimit}) is exhausted after ${repair.consumedRepairRounds} charged rounds; continuing requires a human-authorized resume.`
  }
}

/**
 * Whether one evidence record belongs to the binding's current acceptance
 * generation (AT1-10): the acceptance hash must match AND the record's
 * revision must sit at or above the hash's region start. The hash alone
 * cannot distinguish a swung-back acceptance — when the approved checks
 * change A→B and back B→A, the re-adopted hash equals the original — so
 * the region start revision (moved by every hash-changing adoption, kept
 * by a plain same-hash resume) fences evidence produced before the current
 * acceptance took hold. An absent region (a degraded pre-field checkpoint
 * cache) refuses fail-closed.
 * @param record - the evidence record whose attribution is tested.
 * @param binding - the goal's current projected binding.
 * @param regionStart - the current acceptance's region start revision.
 * @returns `true` when the record may satisfy the current acceptance.
 */
function isCurrentGeneration(
  record: { readonly binding: GoalResultBinding },
  binding: GoalBinding,
  regionStart: number | undefined,
): boolean {
  return record.binding.acceptanceHash === binding.acceptanceHash
    && regionStart !== undefined
    && record.binding.goalRevision >= regionStart
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
