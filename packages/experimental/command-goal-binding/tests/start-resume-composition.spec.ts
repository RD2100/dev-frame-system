import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import AgentRegistry, { Inbox } from '@deepseek-ai/dsh-agent'
import type { Agent } from '@deepseek-ai/dsh-agent'
import CommandRuntime from '@deepseek-ai/dsh-commands'
import type { CommandExecution } from '@deepseek-ai/dsh-commands'
import GoalService from '@deepseek-ai/dsh-goal'
import SessionStore, { Session, SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import { DevFrameOperationId, DevFrameReviewId } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import type {
  DevFrameReviewEventData,
  DevFrameRolePolicyEventData,
  DevFrameUsageEventData,
} from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import type { DevFrameRequiredChecksConfig } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { ControllerSessionId, TaskId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type { GoalBinding } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { createCommittedWorktree, drainWorktreeFixtures } from '../../devframe/tests/completion-fixtures.ts'
import * as commandGoalBinding from '../src/index.ts'
import { GoalBindingComposition } from '../src/composition.ts'
import {
  GOAL_ALREADY_COMPLETE_TEXT,
  RESUME_INPUT_UNEXPECTED_TEXT,
  RESUME_NO_BINDING_RECORD_TEXT,
  RESUME_NO_CURRENT_GOAL_TEXT,
  START_GOAL_RUNNING_TEXT,
  START_OBJECTIVE_REQUIRED_TEXT,
  START_WORKTREE_REQUIRED_TEXT,
  renderCompletionSuccess,
  renderResumeSuccess,
  renderStartSuccess,
} from '../src/command.ts'
import { acceptanceHashOf, compositionRolePolicy, devFrameStateOf, resultTupleOf } from '../src/host-evidence.ts'

const WORKSPACE_ID = WorkspaceId('ws-v14-compos')
/** The deterministic policy version the composition lands (host-evidence). */
const POLICY_VERSION = `policy-${WORKSPACE_ID}-v1`

const roots: string[] = []
const contexts: Context[] = []
let bootNumber = 0

afterEach(async () => {
  for (const ctx of contexts.splice(0).reverse()) await ctx.fiber.dispose()
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
  await drainWorktreeFixtures()
})

/** The approved checklist /devframe-start executes for real on one worktree. */
function startChecks(root: string, variant: 'pass' | 'fail' = 'pass'): DevFrameRequiredChecksConfig {
  return {
    version: 1,
    checks: [
      {
        checkId: 'probe-pass',
        executable: 'node',
        arguments: ['-e', 'process.exit(0)'],
        cwd: root,
      },
      ...(variant === 'pass' ? [] : [{
        checkId: 'probe-fail',
        executable: 'node',
        arguments: ['-e', 'process.exit(1)'],
        cwd: root,
      }]),
    ],
  }
}

interface TestComposition {
  readonly ctx: Context
  readonly agent: Agent
  readonly session: Session
  readonly composition: GoalBindingComposition
}

interface BootOptions {
  readonly checks: DevFrameRequiredChecksConfig
  readonly workspaceRoot?: string
  /** Reuse an existing persistence root (the restart test boots twice on one root). */
  readonly storageRoot?: string
  readonly sessionId: SessionId
  /** Restore the session from persistence instead of creating it fresh. */
  readonly restore?: boolean
  /** Omit the JSONL persistence backend (the unavailable-backend propagation case). */
  readonly withoutPersistence?: boolean
}

/** Build a live idle agent accepted by the exact-identity goal service. */
function stubAgent(session: Session): Agent {
  const inbox = new Inbox(session, { inserted: () => {}, discarded: () => {}, claimed: () => {} })
  return {
    id: session.id,
    options: {},
    session,
    inbox,
    ctx: new Context(),
    status: 'idle',
    send: () => {},
    followup: () => {},
    steer: () => {},
    inject(input) { inbox.append('next-step', input) },
    cancel() {},
    runMaintenance: task => task(new AbortController().signal),
    whenIdle() { return Promise.resolve() },
  }
}

/**
 * Boot one REAL composition: native session store, JSONL persistence, the
 * real command registry, the native goal service, the projection registry,
 * and the function plugin under test — then attach one live agent. With
 * `restore`, the session is rebuilt from the persisted log through the
 * persistence service's prepare face and published into the fresh store
 * (the agent-loop resume transaction's enter+announce shape) instead of
 * being created fresh.
 */
async function boot(options: BootOptions): Promise<TestComposition> {
  const ctx = new Context()
  contexts.push(ctx)
  const ownedRoot = options.storageRoot ?? mkdtempSync(join(tmpdir(), `dsh-command-goal-binding-start-${++bootNumber}-`))
  if (options.storageRoot === undefined) roots.push(ownedRoot)
  await ctx.plugin(SessionStore)
  if (options.withoutPersistence !== true) {
    await ctx.plugin(JsonlSessionPersistence, { root: ownedRoot })
  }
  await ctx.plugin(CommandRuntime)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(GoalService)
  await ctx.plugin(commandGoalBinding, {
    workspaceId: WORKSPACE_ID,
    checks: options.checks,
    taskIds: [TaskId('task-v14-compos')],
    maxAttempts: 3,
    ...(options.workspaceRoot === undefined ? {} : { workspaceRoot: options.workspaceRoot }),
  })
  let session: Session
  if (options.restore === true) {
    const preparation = await ctx.sessionPersistence.prepare(options.sessionId)
    session = preparation.session
    ctx.effect(function* () {
      yield ctx.sessions.enter(session)
      ctx.sessions.announce(session)
    }, 'test-restore-publish')
    preparation[Symbol.dispose]()
  } else {
    session = ctx.sessions.create(options.sessionId)
  }
  const agent = stubAgent(session)
  ctx.agents.register(agent)
  return {
    ctx,
    agent,
    session,
    composition: Reflect.get(ctx, 'commandGoalBinding') as GoalBindingComposition,
  }
}

/** Execute one slash command through the same registry boundary as a UI adapter. */
async function execute(test: TestComposition, line: string): Promise<CommandExecution> {
  const execution = await test.ctx.commands.execute(test.agent, line, [], new AbortController().signal)
  if (execution === undefined) throw new Error('expected command was not registered')
  return execution
}

/** The single logged event of one DevFrame event type. */
function devframeEvent(
  test: TestComposition,
  type: 'devframe/role-policy' | 'devframe/goal-binding' | 'devframe/verification',
): { readonly type: string; readonly data: unknown } & Record<string, unknown> {
  const event = test.session.snapshotEvents().find(candidate => candidate.type === type)
  if (event === undefined) throw new Error(`${type} event is missing`)
  return event
}

/** Every logged goal-binding event payload, in log order. */
function goalBindingEvents(test: TestComposition): GoalBinding[] {
  return test.session.snapshotEvents()
    .filter(candidate => candidate.type === 'devframe/goal-binding')
    .map(candidate => (candidate as { readonly data: GoalBinding }).data)
}

/** Whether the session log holds any DevFrame record at all. */
function hasDevframeEvents(test: TestComposition): boolean {
  return test.session.snapshotEvents().some(candidate => candidate.type.startsWith('devframe/'))
}

/** Whether the session log holds any goal lifecycle change. */
function hasGoalChanges(test: TestComposition): boolean {
  return test.session.snapshotEvents().some(candidate => candidate.type === 'goal/change')
}

/**
 * The reviewer-authorized role-policy replacement the /goal-complete
 * error-face cases append: the composition's deterministic policy under the
 * same version, plus one reviewer assignment (a legal replacement fold).
 */
function reviewerPolicyRecord(
  controllerSessionId: SessionId,
  reviewerSessionId: SessionId,
): DevFrameRolePolicyEventData {
  const policy = compositionRolePolicy(WORKSPACE_ID, controllerSessionId)
  return {
    ...policy,
    assignments: [
      { role: 'controller', sessionId: controllerSessionId },
      { role: 'reviewer', sessionId: reviewerSessionId },
    ],
  }
}

/** One durable review record attributed to the landed binding. */
function reviewRecord(binding: GoalBinding, reviewerSessionId: SessionId): DevFrameReviewEventData {
  return {
    version: 1,
    reviewId: DevFrameReviewId('review-v14-compos'),
    binding: resultTupleOf(binding),
    snapshotId: binding.snapshotId,
    reviewerSessionId,
    policyVersion: POLICY_VERSION,
    decision: 'pass',
    findings: [],
  }
}

describe('/devframe-start composition', { timeout: 60_000 }, () => {
  it('starts the bound goal and lands real role-policy, goal-binding, and verification evidence', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      sessionId: SessionId('controller-v14-compos-start'),
    })

    const execution = await execute(test, '/devframe-start fix the login bug')

    if (execution.result.kind !== 'success') throw new Error('expected a success result')
    expect(execution.result.text).toBe(renderStartSuccess(1, 'passed'))
    const goal = test.ctx.goals.get(test.agent)
    expect(goal?.phase).toBe('active')
    expect(test.composition.admissionOf(test.agent)).toBe('open')

    const rolePolicy = devframeEvent(test, 'devframe/role-policy')
    expect(rolePolicy.data).toMatchObject({
      version: 1,
      policyVersion: POLICY_VERSION,
      controllerSessionId: test.session.id,
      assignments: [{ role: 'controller', sessionId: test.session.id }],
    })
    const goalBinding = devframeEvent(test, 'devframe/goal-binding')
    expect(goalBinding.data).toMatchObject({
      lifecycle: 'admission_open',
      goalId: goal?.id,
      controllerSessionId: test.session.id,
    })
    const verification = devframeEvent(test, 'devframe/verification')
    expect(verification.data).toMatchObject({
      status: 'passed',
      requiredChecks: { config: startChecks(fixture.root) },
      checks: [{
        checkId: 'probe-pass',
        executable: 'node',
        arguments: ['-e', 'process.exit(0)'],
        cwd: fixture.root,
        status: 'passed',
        exitCode: 0,
      }],
    })

    const text = execution.result.text
    expect(text).not.toContain('snapshot-v2-')
    expect(text).not.toContain('dsh-source-fp-v2-')
    expect(text).not.toContain('devframe-start:')
    if (goal === undefined) throw new Error('goal is missing')
    expect(text).not.toContain(goal.id)

    const run = test.session.snapshotEvents().find(event => event.type === 'command/run')
    if (run === undefined || run.type !== 'command/run') throw new Error('command/run event is missing')
    expect(run.data.name).toBe('devframe-start')
    const done = test.session.snapshotEvents().find(event =>
      event.type === 'command/done' && event.data.commandId === run.data.commandId)
    if (done === undefined || done.type !== 'command/done') throw new Error('command/done event is missing')
    expect(done.data.kind).toBe('success')

    // The completion command reads the real verification evidence and stops
    // honestly at the review gate: no review production exists in this wave.
    const completion = await execute(test, '/goal-complete')
    if (completion.result.kind !== 'error') throw new Error('expected an error result')
    expect(completion.result.text).toContain('no review record')
    expect(test.ctx.goals.get(test.agent)?.phase).toBe('active')
  })

  it('lands honest failed verification and lets /goal-complete reject at required-checks', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({
      checks: startChecks(fixture.root, 'fail'),
      workspaceRoot: fixture.root,
      sessionId: SessionId('controller-v14-compos-failed'),
    })

    const execution = await execute(test, '/devframe-start fix the logout bug')

    if (execution.result.kind !== 'success') throw new Error('expected a success result')
    expect(execution.result.text).toBe(renderStartSuccess(2, 'failed'))
    const verification = devframeEvent(test, 'devframe/verification')
    expect(verification.data).toMatchObject({ status: 'failed' })

    // Test assembly for the completion error face: authorize a reviewer and
    // append one passing review so the admission reaches the required-checks
    // stage, where the honest failed evidence must reject completion.
    const binding = goalBindingEvents(test)[0]
    if (binding === undefined) throw new Error('goal-binding payload is missing')
    const reviewerSessionId = SessionId('reviewer-v14-compos-failed')
    test.session.append('devframe/role-policy', reviewerPolicyRecord(test.session.id, reviewerSessionId))
    test.session.append('devframe/review', reviewRecord(binding, reviewerSessionId))

    const completion = await execute(test, '/goal-complete')
    if (completion.result.kind !== 'error') throw new Error('expected an error result')
    expect(completion.result.text).toContain('required-checks')
    expect(completion.result.text).toContain('REQUIRED_CHECKS_NOT_PASSED')
    expect(test.ctx.goals.get(test.agent)?.phase).toBe('active')
    expect(test.composition.admissionOf(test.agent)).toBe('closed')
  })

  it('answers stable data errors with zero structural side effects', async () => {
    const fixture = await createCommittedWorktree()
    const withoutRoot = await boot({
      checks: startChecks(fixture.root),
      sessionId: SessionId('controller-v14-compos-d1'),
    })
    const empty = await execute(withoutRoot, '/devframe-start   ')
    if (empty.result.kind !== 'error') throw new Error('expected an error result')
    expect(empty.result.text).toBe(START_OBJECTIVE_REQUIRED_TEXT)

    const missingRoot = await execute(withoutRoot, '/devframe-start build the thing')
    if (missingRoot.result.kind !== 'error') throw new Error('expected an error result')
    expect(missingRoot.result.text).toBe(START_WORKTREE_REQUIRED_TEXT)
    expect(withoutRoot.ctx.goals.get(withoutRoot.agent)).toBeUndefined()
    expect(hasDevframeEvents(withoutRoot)).toBe(false)
    expect(hasGoalChanges(withoutRoot)).toBe(false)

    const test = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      sessionId: SessionId('controller-v14-compos-d2'),
    })
    test.ctx.goals.create(test.agent, { objective: 'already running' })
    const before = test.ctx.goals.get(test.agent)
    const running = await execute(test, '/devframe-start build another thing')
    if (running.result.kind !== 'error') throw new Error('expected an error result')
    expect(running.result.text).toBe(START_GOAL_RUNNING_TEXT)
    expect(test.ctx.goals.get(test.agent)?.id).toBe(before?.id)
    expect(test.ctx.goals.get(test.agent)?.revision).toBe(before?.revision)
    expect(hasDevframeEvents(test)).toBe(false)
  })
})

describe('/devframe-resume composition', { timeout: 60_000 }, () => {
  it('resumes the bound goal after a restart against the same persistence root', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-command-goal-binding-restart-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-compos-restart')
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
    })
    const started = await execute(first, '/devframe-start fix the billing bug')
    if (started.result.kind !== 'success') throw new Error('expected a success result')
    const goalBefore = first.ctx.goals.get(first.agent)
    if (goalBefore === undefined) throw new Error('goal is missing after start')
    await first.ctx.sessions.flush(first.session)
    // Replace the afterEach-owned disposal for this context with an explicit
    // one: the restart needs the first fiber truly gone before boot two.
    contexts.splice(contexts.indexOf(first.ctx), 1)
    await first.ctx.fiber.dispose()

    const second = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      restore: true,
    })
    // A probe completion caches a controller over the (still empty) store;
    // the resume must evict it so the rebuilt controller sees the restored
    // binding instead of failing on the stale cache.
    const probe = await execute(second, '/goal-complete')
    if (probe.result.kind !== 'error') throw new Error('expected an error result')
    expect(probe.result.text).toContain('no completion binding')

    const goalRestored = second.ctx.goals.get(second.agent)
    expect(goalRestored?.id).toBe(goalBefore.id)
    expect(goalRestored?.phase).toBe('active')

    const execution = await execute(second, '/devframe-resume')

    if (execution.result.kind !== 'success') throw new Error('expected a success result')
    expect(execution.result.text).toBe(renderResumeSuccess())
    const goal = second.ctx.goals.get(second.agent)
    expect(goal?.phase).toBe('active')
    expect(goal?.revision).toBe(goalBefore.revision + 1)
    expect(second.composition.admissionOf(second.agent)).toBe('open')

    const bindings = await second.composition.bindingStore.load(ControllerSessionId(sessionId))
    expect(bindings.find(record => record.goalId === goal?.id)?.goalRevision).toBe(goal?.revision)
    const landed = goalBindingEvents(second)
    expect(landed).toHaveLength(2)
    expect(landed[1]?.goalRevision).toBe(goal?.revision)
    expect(landed[1]?.lifecycle).toBe('admission_open')

    // The pre-restart verification stays readable: the result tuple compare
    // does not include the revision, so completion evidence survives restart.
    const completion = await execute(second, '/goal-complete')
    if (completion.result.kind !== 'error') throw new Error('expected an error result')
    expect(completion.result.text).toContain('no review record')
  })

  it('answers stable data errors for unexpected input and missing goal states', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      sessionId: SessionId('controller-v14-compos-r1'),
    })

    const unexpected = await execute(test, '/devframe-resume please')
    if (unexpected.result.kind !== 'error') throw new Error('expected an error result')
    expect(unexpected.result.text).toBe(RESUME_INPUT_UNEXPECTED_TEXT)

    const noGoal = await execute(test, '/devframe-resume')
    if (noGoal.result.kind !== 'error') throw new Error('expected an error result')
    expect(noGoal.result.text).toBe(RESUME_NO_CURRENT_GOAL_TEXT)

    const unbound = test.ctx.goals.create(test.agent, { objective: 'unbound goal' })
    const noBinding = await execute(test, '/devframe-resume')
    if (noBinding.result.kind !== 'error') throw new Error('expected an error result')
    expect(noBinding.result.text).toBe(RESUME_NO_BINDING_RECORD_TEXT)

    test.ctx.goals.complete(test.agent, { id: unbound.id, revision: unbound.revision })
    const complete = await execute(test, '/devframe-resume')
    if (complete.result.kind !== 'error') throw new Error('expected an error result')
    expect(complete.result.text).toBe(GOAL_ALREADY_COMPLETE_TEXT)
    expect(hasDevframeEvents(test)).toBe(false)
  })
})

describe('structural propagation and registration lifetime', { timeout: 60_000 }, () => {
  it('propagates SourceFingerprintError when the configured worktree is unusable', async () => {
    const test = await boot({
      checks: startChecks(tmpdir()),
      workspaceRoot: join(tmpdir(), 'definitely-not-a-worktree-v14-compos'),
      sessionId: SessionId('controller-v14-compos-fp'),
    })

    await expect(execute(test, '/devframe-start fix the thing')).rejects
      .toMatchObject({ name: 'SourceFingerprintError' })
    expect(test.ctx.goals.get(test.agent)).toBeUndefined()
    expect(hasDevframeEvents(test)).toBe(false)
    expect(hasGoalChanges(test)).toBe(false)
  })

  it('propagates DevFramePersistenceError when no persistence backend is configured', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      sessionId: SessionId('controller-v14-compos-nopersist'),
      withoutPersistence: true,
    })

    await expect(execute(test, '/devframe-start fix the thing')).rejects.toMatchObject({
      name: 'DevFramePersistenceError',
      code: 'unavailable',
    })
    expect(test.composition.journal.isBlocked(test.session)).toBe(true)
  })

  it('registers the start and resume commands through effects that disappear with the plugin fiber', async () => {
    const ctx = new Context()
    contexts.push(ctx)
    await ctx.plugin(SessionStore)
    await ctx.plugin(CommandRuntime)
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(GoalService)
    const plugin = await ctx.plugin(commandGoalBinding, {
      workspaceId: WORKSPACE_ID,
      checks: startChecks(tmpdir()),
      taskIds: [TaskId('task-v14-compos')],
      maxAttempts: 3,
    })
    const session = ctx.sessions.create(SessionId(`controller-lifetime-start-${++bootNumber}`))
    const agent = stubAgent(session)
    ctx.agents.register(agent)
    expect(ctx.commands.find(agent, 'devframe-start')).toBeDefined()
    expect(ctx.commands.find(agent, 'devframe-resume')).toBeDefined()

    await plugin.dispose()

    expect(ctx.commands.find(agent, 'devframe-start')).toBeUndefined()
    expect(ctx.commands.find(agent, 'devframe-resume')).toBeUndefined()
  })
})

describe('configuration loud failure', { timeout: 60_000 }, () => {
  /**
   * Start one plugin activation over the real stack and return its promise;
   * every caller asserts the rejection, and a successful activation can only
   * resolve to the plugin fiber, which no case reaches.
   */
  async function expectActivationRejection(config: Record<string, unknown>): Promise<unknown> {
    const ctx = new Context()
    contexts.push(ctx)
    const storageRoot = mkdtempSync(join(tmpdir(), `dsh-command-goal-binding-config-${++bootNumber}-`))
    roots.push(storageRoot)
    await ctx.plugin(SessionStore)
    await ctx.plugin(JsonlSessionPersistence, { root: storageRoot })
    await ctx.plugin(CommandRuntime)
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(GoalService)
    return ctx.plugin(commandGoalBinding, config as never)
  }

  const validChecks = startChecks(tmpdir())

  it('rejects missing checks, taskIds, and maxAttempts at activation', async () => {
    await expect(expectActivationRejection({ workspaceId: WORKSPACE_ID, taskIds: ['t'], maxAttempts: 3 }))
      .rejects.toThrow()
    await expect(expectActivationRejection({ workspaceId: WORKSPACE_ID, checks: validChecks, maxAttempts: 3 }))
      .rejects.toThrow()
    await expect(expectActivationRejection({ workspaceId: WORKSPACE_ID, checks: validChecks, taskIds: ['t'] }))
      .rejects.toThrow()
  })

  it('rejects malformed checks and work parameters loudly', async () => {
    await expect(expectActivationRejection({
      workspaceId: WORKSPACE_ID,
      checks: { version: 1, checks: [] },
      taskIds: ['t'],
      maxAttempts: 3,
    })).rejects.toThrow()

    await expect(expectActivationRejection({
      workspaceId: WORKSPACE_ID,
      checks: {
        version: 1,
        checks: [{ checkId: 'probe', executable: 'node', arguments: [], cwd: 'relative/path' }],
      },
      taskIds: ['t'],
      maxAttempts: 3,
    })).rejects.toThrow(/absolute cwd/)

    await expect(expectActivationRejection({
      workspaceId: WORKSPACE_ID,
      checks: validChecks,
      taskIds: ['same', 'same'],
      maxAttempts: 3,
    })).rejects.toThrow(/taskIds must be unique/)

    await expect(expectActivationRejection({
      workspaceId: WORKSPACE_ID,
      checks: validChecks,
      taskIds: ['t'],
      maxAttempts: 0,
    })).rejects.toThrow(/maxAttempts must be a positive safe integer/)

    await expect(expectActivationRejection({
      workspaceId: WORKSPACE_ID,
      checks: validChecks,
      taskIds: ['t'],
      maxAttempts: 1.5,
    })).rejects.toThrow(/maxAttempts must be a positive safe integer/)

    await expect(expectActivationRejection({
      workspaceId: WORKSPACE_ID,
      checks: validChecks,
      taskIds: ['t'],
      maxAttempts: 3,
      maxGoalRounds: 0,
    })).rejects.toThrow(/maxGoalRounds must be a positive safe integer/)
  })
})

describe('AT1-09 A to B journey composition', { timeout: 120_000 }, () => {
  /**
   * One schema-valid usage record attributed to a binding's result tuple: the
   * attempt-budget consumption face the projection folds per Goal identity
   * (the same judge shape the DevFrame event fixtures use).
   */
  function usageRecord(
    binding: GoalBinding,
    operationId: string,
    fields: Pick<DevFrameUsageEventData, 'attempt' | 'consumedAttempts'>
      & Partial<Pick<DevFrameUsageEventData, 'phase' | 'outcome'>>,
  ): DevFrameUsageEventData {
    return {
      version: 1,
      operationId: DevFrameOperationId(operationId),
      binding: resultTupleOf(binding),
      role: 'worker',
      attempt: fields.attempt,
      phase: fields.phase ?? 'reserved',
      ...(fields.outcome === undefined ? {} : { outcome: fields.outcome }),
      consumedAttempts: fields.consumedAttempts,
      maxAttempts: binding.budget.maxAttempts,
    }
  }

  /** One passing review record attributed to a binding under its own review id. */
  function journeyReview(
    binding: GoalBinding,
    reviewerSessionId: SessionId,
    reviewId: string,
  ): DevFrameReviewEventData {
    return {
      ...reviewRecord(binding, reviewerSessionId),
      reviewId: DevFrameReviewId(reviewId),
    }
  }

  it('drives the AT1-09 A to B journey: isolation, stale review, budget across restart, late results', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-command-goal-binding-journey-'))
    roots.push(storageRoot)
    const sessionId = SessionId('controller-v14-compos-journey')
    const reviewerSessionId = SessionId('reviewer-v14-compos-journey')
    const objectiveA = 'fix the billing bug'
    const objectiveB = 'migrate the billing schema'

    // Boot 1: Goal A starts on the workspace binding, produces its evidence
    // chain, consumes one charged attempt, and completes on its own evidence.
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
    })
    const startedA = await execute(first, `/devframe-start ${objectiveA}`)
    if (startedA.result.kind !== 'success') throw new Error('expected a success result')
    expect(startedA.result.text).toBe(renderStartSuccess(1, 'passed'))
    const goalA = first.ctx.goals.get(first.agent)
    if (goalA === undefined) throw new Error('goal A is missing after start')
    expect(goalA.phase).toBe('active')
    expect(first.composition.admissionOf(first.agent)).toBe('open')
    const bindingA = goalBindingEvents(first)[0]
    if (bindingA === undefined) throw new Error('goal A binding is missing')
    expect(bindingA.goalId).toBe(goalA.id)
    expect(bindingA.budget).toEqual({ maxAttempts: 3, consumedAttempts: 0 })
    expect(bindingA.acceptanceHash).toBe(acceptanceHashOf(objectiveA, startChecks(fixture.root)))

    // The requirement change cannot start while A is still running: the same
    // binding refuses a second unfinished Goal.
    const refusedB = await execute(first, `/devframe-start ${objectiveB}`)
    if (refusedB.result.kind !== 'error') throw new Error('expected an error result')
    expect(refusedB.result.text).toBe(START_GOAL_RUNNING_TEXT)
    expect(first.ctx.goals.get(first.agent)?.id).toBe(goalA.id)

    // A consumes one charged attempt through the usage face.
    first.session.append('devframe/usage', usageRecord(bindingA, 'operation-v14-compos-a', { attempt: 1, consumedAttempts: 1 }))
    expect(devFrameStateOf(first.ctx, first.session).failure).toBeNull()
    expect(devFrameStateOf(first.ctx, first.session).usage).toHaveLength(1)

    // A completes on its own evidence: reviewer authorized, the review
    // attributed to A, and the real verification and fingerprint admitted.
    first.session.append('devframe/role-policy', reviewerPolicyRecord(first.session.id, reviewerSessionId))
    first.session.append('devframe/review', journeyReview(bindingA, reviewerSessionId, 'review-v14-compos-a'))
    const completedA = await execute(first, '/goal-complete')
    if (completedA.result.kind !== 'success') throw new Error('expected a success result')
    expect(completedA.result.text).toBe(renderCompletionSuccess())
    expect(first.ctx.goals.get(first.agent)?.phase).toBe('complete')
    expect(first.composition.admissionOf(first.agent)).toBe('closed')

    await first.ctx.sessions.flush(first.session)
    contexts.splice(contexts.indexOf(first.ctx), 1)
    await first.ctx.fiber.dispose()

    // Boot 2: the restart keeps A's consumption readable, the completed A
    // refuses resume and completion faces, and the requirement change starts
    // Goal B on the same workspace binding with a new acceptance hash.
    const second = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      restore: true,
    })
    const staleA = await execute(second, '/goal-complete')
    if (staleA.result.kind !== 'error') throw new Error('expected an error result')
    expect(staleA.result.text).toBe(GOAL_ALREADY_COMPLETE_TEXT)
    expect(second.ctx.goals.get(second.agent)?.id).toBe(goalA.id)
    expect(second.ctx.goals.get(second.agent)?.phase).toBe('complete')

    const startedB = await execute(second, `/devframe-start ${objectiveB}`)
    if (startedB.result.kind !== 'success') throw new Error('expected a success result')
    const goalB = second.ctx.goals.get(second.agent)
    if (goalB === undefined) throw new Error('goal B is missing after start')
    expect(goalB.id).not.toBe(goalA.id)
    expect(second.composition.admissionOf(second.agent)).toBe('open')
    const bindingB = goalBindingEvents(second).at(-1)
    if (bindingB === undefined) throw new Error('goal B binding is missing')
    expect(bindingB.goalId).toBe(goalB.id)
    expect(bindingB.acceptanceHash).toBe(acceptanceHashOf(objectiveB, startChecks(fixture.root)))
    expect(bindingB.acceptanceHash).not.toBe(bindingA.acceptanceHash)
    expect(bindingB.budget).toEqual({ maxAttempts: 3, consumedAttempts: 0 })

    // B consumes one charged attempt; A's earlier consumption stays on A.
    second.session.append('devframe/usage', usageRecord(bindingB, 'operation-v14-compos-b', { attempt: 1, consumedAttempts: 1 }))
    const usageAfterB = devFrameStateOf(second.ctx, second.session).usage
    expect(usageAfterB).toHaveLength(2)
    expect(usageAfterB.map(record => record.binding.goalId)).toEqual([goalA.id, goalB.id])

    await second.ctx.sessions.flush(second.session)
    contexts.splice(contexts.indexOf(second.ctx), 1)
    await second.ctx.fiber.dispose()

    // Boot 3: B resumes across the restart at revision+1, its consumption
    // count survives (the next charge must be 2, not a from-zero 1), and A's
    // late result lands on A's identity tuple without counting into B.
    const third = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      restore: true,
    })
    const probe = await execute(third, '/goal-complete')
    if (probe.result.kind !== 'error') throw new Error('expected an error result')
    expect(probe.result.text).toContain('no completion binding')

    const resumed = await execute(third, '/devframe-resume')
    if (resumed.result.kind !== 'success') throw new Error('expected a success result')
    expect(resumed.result.text).toBe(renderResumeSuccess())
    const goalResumed = third.ctx.goals.get(third.agent)
    expect(goalResumed?.id).toBe(goalB.id)
    expect(goalResumed?.revision).toBe(goalB.revision + 1)
    expect(third.composition.admissionOf(third.agent)).toBe('open')
    const landed = goalBindingEvents(third)
    expect(landed).toHaveLength(3)
    expect(landed[2]?.goalId).toBe(goalB.id)
    expect(landed[2]?.goalRevision).toBe(goalB.revision + 1)
    expect(landed[2]?.lifecycle).toBe('admission_open')
    expect(landed[2]?.budget).toEqual({ maxAttempts: 3, consumedAttempts: 0 })

    // The preserved count refuses a from-zero charge: the fold only accepts
    // consumedAttempts 2 when the restored count is still 1, and a failed
    // fold would latch a projection failure.
    third.session.append('devframe/usage', usageRecord(bindingB, 'operation-v14-compos-b-2', { attempt: 2, consumedAttempts: 2 }))
    const usageAfterResume = devFrameStateOf(third.ctx, third.session).usage
    expect(usageAfterResume.filter(record => record.binding.goalId === goalB.id)).toHaveLength(2)

    // A's late result settles after B exists: it lands on A's identity tuple
    // and B's consumption stays exactly its own two charges.
    third.session.append('devframe/usage', {
      ...usageRecord(bindingA, 'operation-v14-compos-a', { attempt: 1, consumedAttempts: 1 }),
      phase: 'settled',
      outcome: 'succeeded',
    })
    const usageAfterLateA = devFrameStateOf(third.ctx, third.session).usage
    const lateA = usageAfterLateA.find(record =>
      record.operationId === DevFrameOperationId('operation-v14-compos-a') && record.phase === 'settled')
    if (lateA === undefined) throw new Error('late A settlement is missing')
    expect(lateA.binding).toEqual(resultTupleOf(bindingA))
    expect(lateA.binding.goalId).toBe(goalA.id)
    expect(lateA.binding.acceptanceHash).toBe(bindingA.acceptanceHash)
    expect(lateA.binding.snapshotId).toBe(bindingA.snapshotId)
    expect(usageAfterLateA.filter(record => record.binding.goalId === goalB.id).map(record => record.consumedAttempts))
      .toEqual([1, 2])
    expect(devFrameStateOf(third.ctx, third.session).failure).toBeNull()

    // A's old review is the log's latest review: B's completion must reject
    // it at the attribution gate before any predicate runs.
    await expect(execute(third, '/goal-complete')).rejects.toThrow(
      `completion review evidence is attributed to Goal "${goalA.id}"`,
    )
    expect(third.ctx.goals.get(third.agent)?.phase).toBe('active')
    expect(third.composition.admissionOf(third.agent)).toBe('closed')

    // With B's own review as the latest one, the completion face passes the
    // task-warning and source-fingerprint stages (a fingerprint rejection
    // would be a verdict, not this throw) and then reports the unregistered
    // digest: the required-checks store is per-process, so the post-restart
    // completion stops at that structural boundary.
    third.session.append('devframe/review', journeyReview(bindingB, reviewerSessionId, 'review-v14-compos-b'))
    await expect(execute(third, '/goal-complete')).rejects.toMatchObject({
      name: 'RequiredChecksError',
      code: 'REQUIRED_CHECKS_CONFIG_NOT_FOUND',
    })
    expect(third.ctx.goals.get(third.agent)?.phase).toBe('active')
    expect(third.composition.admissionOf(third.agent)).toBe('closed')
  })
})
