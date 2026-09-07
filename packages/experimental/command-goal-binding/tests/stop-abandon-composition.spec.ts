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
import type { DevFrameRequiredChecksConfig } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import type { GoalBinding } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { createCommittedWorktree, drainWorktreeFixtures } from '../../devframe/tests/completion-fixtures.ts'
import * as commandGoalBinding from '../src/index.ts'
import type { GoalBindingComposition } from '../src/composition.ts'
import {
  ABANDON_INPUT_UNEXPECTED_TEXT,
  ABANDON_NO_CURRENT_GOAL_TEXT,
  ABANDON_UNRESOLVED_STATE_TEXT,
  GOAL_ALREADY_COMPLETE_TEXT,
  RESUME_NO_CURRENT_GOAL_TEXT,
  RESUME_STOP_PENDING_TEXT,
  STOP_ALREADY_PENDING_TEXT,
  STOP_INPUT_UNEXPECTED_TEXT,
  STOP_NO_BINDING_RECORD_TEXT,
  STOP_NO_CURRENT_GOAL_TEXT,
  renderAbandonSuccess,
  renderResumeSuccess,
  renderStartSuccess,
  renderStopSuccess,
} from '../src/command.ts'
import { devFrameStateOf } from '../src/host-evidence.ts'

const WORKSPACE_ID = WorkspaceId('ws-v14-stop-abandon')
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
function startChecks(root: string): DevFrameRequiredChecksConfig {
  return {
    version: 1,
    checks: [{
      checkId: 'probe-pass',
      executable: 'node',
      arguments: ['-e', 'process.exit(0)'],
      cwd: root,
    }],
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
  readonly sessionId: SessionId
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

/** Boot one REAL composition through the function plugin under test. */
async function boot(options: BootOptions): Promise<TestComposition> {
  const ctx = new Context()
  contexts.push(ctx)
  const storageRoot = mkdtempSync(join(tmpdir(), `dsh-command-goal-binding-stop-${++bootNumber}-`))
  roots.push(storageRoot)
  await ctx.plugin(SessionStore)
  await ctx.plugin(JsonlSessionPersistence, { root: storageRoot })
  await ctx.plugin(CommandRuntime)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(GoalService)
  await ctx.plugin(commandGoalBinding, {
    workspaceId: WORKSPACE_ID,
    requiredChecksPath: join(storageRoot, 'required-checks.json'),
    checks: options.checks,
    taskIds: ['task-v14-stop-abandon'],
    maxAttempts: 3,
    ...(options.workspaceRoot === undefined ? {} : { workspaceRoot: options.workspaceRoot }),
  })
  const session = ctx.sessions.create(options.sessionId)
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

/** Every logged goal-binding event payload, in log order. */
function goalBindingEvents(test: TestComposition): GoalBinding[] {
  return test.session.snapshotEvents()
    .filter(candidate => candidate.type === 'devframe/goal-binding')
    .map(candidate => (candidate as { readonly data: GoalBinding }).data)
}

/** Whether the session log holds a native goal lifecycle change of one operation. */
function hasGoalChange(test: TestComposition, operation: 'clear' | 'receipt'): boolean {
  return test.session.snapshotEvents().some(candidate =>
    candidate.type === 'goal/change' && (candidate.data as { operation?: string }).operation === operation)
}

/**
 * The stop flow's vocabulary journey on the binding face: the pending stop
 * request advances to quiescence-confirmed and then to the terminal stopped
 * state — the fold-legal path the unwired reliability stop flow records
 * while the binding tuple stays frozen.
 */
function stoppedJourney(binding: GoalBinding): GoalBinding[] {
  return [
    { ...binding, lifecycle: 'quiescence_confirmed' },
    { ...binding, lifecycle: 'stopped' },
  ]
}

/** Start one bound goal through the real start lane and return its binding. */
async function startBoundGoal(test: TestComposition): Promise<GoalBinding> {
  const started = await execute(test, '/devframe-start fix the login bug')
  if (started.result.kind !== 'success') throw new Error('expected a success result')
  expect(started.result.text).toBe(renderStartSuccess(1, 'passed'))
  const binding = goalBindingEvents(test)[0]
  if (binding === undefined) throw new Error('started binding is missing')
  return binding
}

describe('/devframe-stop composition', { timeout: 120_000 }, () => {
  it('records the stop-requested binding, disarms continuation, and closes admission', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      sessionId: SessionId('controller-v14-stop'),
    })
    const binding = await startBoundGoal(test)
    const goal = test.ctx.goals.get(test.agent)
    if (goal === undefined) throw new Error('goal is missing after start')

    const stopped = await execute(test, '/devframe-stop')

    if (stopped.result.kind !== 'success') throw new Error('expected a success result')
    expect(stopped.result.text).toBe(renderStopSuccess())
    expect(test.ctx.goals.get(test.agent)).toMatchObject({
      id: goal.id,
      revision: goal.revision,
      phase: 'active',
      activation: 'disarmed',
    })
    expect(test.composition.admissionOf(test.agent)).toBe('closed')
    const bindings = goalBindingEvents(test)
    expect(bindings).toHaveLength(2)
    expect(bindings[1]).toMatchObject({
      goalId: goal.id,
      goalRevision: binding.goalRevision,
      lifecycle: 'stop_requested',
    })
    await expect(test.composition.bindingStore.load(ControllerSessionId(test.session.id)))
      .resolves.toEqual([expect.objectContaining({ goalId: goal.id, lifecycle: 'stop_requested' })])
    expect(devFrameStateOf(test.ctx, test.session).failure).toBeNull()
    expect(hasGoalChange(test, 'clear')).toBe(false)
    expect(stopped.result.text).not.toContain(goal.id)
  })

  it('answers stable data errors with zero structural side effects', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      sessionId: SessionId('controller-v14-stop-d1'),
    })

    const noGoal = await execute(test, '/devframe-stop')
    if (noGoal.result.kind !== 'error') throw new Error('expected an error result')
    expect(noGoal.result.text).toBe(STOP_NO_CURRENT_GOAL_TEXT)

    const residue = await execute(test, '/devframe-stop now')
    if (residue.result.kind !== 'error') throw new Error('expected an error result')
    expect(residue.result.text).toBe(STOP_INPUT_UNEXPECTED_TEXT)
    expect(test.ctx.goals.get(test.agent)).toBeUndefined()

    test.ctx.goals.create(test.agent, { objective: 'unbound native goal' })
    const unbound = await execute(test, '/devframe-stop')
    if (unbound.result.kind !== 'error') throw new Error('expected an error result')
    expect(unbound.result.text).toBe(STOP_NO_BINDING_RECORD_TEXT)
    const beforeStop = test.ctx.goals.get(test.agent)
    expect(beforeStop?.phase).toBe('active')
    expect(test.session.snapshotEvents().some(event => event.type.startsWith('devframe/'))).toBe(false)

    const completed = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      sessionId: SessionId('controller-v14-stop-d2'),
    })
    expect((await execute(completed, '/devframe-start fix the login bug')).result.kind).toBe('success')
    const goal = completed.ctx.goals.get(completed.agent)
    if (goal === undefined) throw new Error('goal is missing after start')
    completed.ctx.goals.complete(completed.agent, { id: goal.id, revision: goal.revision })
    const complete = await execute(completed, '/devframe-stop')
    if (complete.result.kind !== 'error') throw new Error('expected an error result')
    expect(complete.result.text).toBe(GOAL_ALREADY_COMPLETE_TEXT)
    expect(hasGoalChange(completed, 'clear')).toBe(false)
  })

  it('refuses a second stop request while the stop flow is unresolved', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      sessionId: SessionId('controller-v14-stop-twice'),
    })
    await startBoundGoal(test)
    expect((await execute(test, '/devframe-stop')).result.kind).toBe('success')

    const again = await execute(test, '/devframe-stop')

    if (again.result.kind !== 'error') throw new Error('expected an error result')
    expect(again.result.text).toBe(STOP_ALREADY_PENDING_TEXT)
    expect(goalBindingEvents(test)).toHaveLength(2)
    expect(devFrameStateOf(test.ctx, test.session).failure).toBeNull()
  })

  it('blocks resume while the stop is pending and never corrupts the log', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      sessionId: SessionId('controller-v14-stop-resume'),
    })
    await startBoundGoal(test)
    expect((await execute(test, '/devframe-stop')).result.kind).toBe('success')

    const resumed = await execute(test, '/devframe-resume')

    if (resumed.result.kind !== 'error') throw new Error('expected an error result')
    expect(resumed.result.text).toBe(RESUME_STOP_PENDING_TEXT)
    expect(goalBindingEvents(test)).toHaveLength(2)
    expect(devFrameStateOf(test.ctx, test.session).failure).toBeNull()
    expect(test.ctx.goals.get(test.agent)?.activation).toBe('disarmed')
  })

  it('reaches the terminal stopped state through the existing vocabulary and resumes after it', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      sessionId: SessionId('controller-v14-stop-journey'),
    })
    const binding = await startBoundGoal(test)
    const goal = test.ctx.goals.get(test.agent)
    if (goal === undefined) throw new Error('goal is missing after start')
    expect((await execute(test, '/devframe-stop')).result.kind).toBe('success')
    for (const record of stoppedJourney(goalBindingEvents(test)[1]!)) {
      test.session.append('devframe/goal-binding', record)
    }
    expect(devFrameStateOf(test.ctx, test.session).failure).toBeNull()

    const resumed = await execute(test, '/devframe-resume')

    if (resumed.result.kind !== 'success') throw new Error('expected a success result')
    expect(resumed.result.text).toBe(renderResumeSuccess())
    expect(test.ctx.goals.get(test.agent)?.revision).toBe(goal.revision + 1)
    const bindings = goalBindingEvents(test)
    expect(bindings.map(record => record.lifecycle)).toEqual([
      'admission_open',
      'stop_requested',
      'quiescence_confirmed',
      'stopped',
      'admission_open',
    ])
    expect(bindings[4]?.goalRevision).toBe(binding.goalRevision + 1)
    expect(test.composition.admissionOf(test.agent)).toBe('open')
    expect(devFrameStateOf(test.ctx, test.session).failure).toBeNull()
  })
})

describe('/devframe-abandon composition', { timeout: 120_000 }, () => {
  it('clears the native Goal behind the tombstone after a stopped journey and retains history', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      sessionId: SessionId('controller-v14-abandon-stopped'),
    })
    await startBoundGoal(test)
    const goal = test.ctx.goals.get(test.agent)
    if (goal === undefined) throw new Error('goal is missing after start')
    expect((await execute(test, '/devframe-stop')).result.kind).toBe('success')
    for (const record of stoppedJourney(goalBindingEvents(test)[1]!)) {
      test.session.append('devframe/goal-binding', record)
    }

    const abandoned = await execute(test, '/devframe-abandon')

    if (abandoned.result.kind !== 'success') throw new Error('expected a success result')
    expect(abandoned.result.text).toBe(renderAbandonSuccess())
    expect(test.ctx.goals.get(test.agent)).toBeUndefined()
    expect(hasGoalChange(test, 'clear')).toBe(true)
    expect(hasGoalChange(test, 'receipt')).toBe(false)
    expect(goalBindingEvents(test)).toHaveLength(4)
    expect(goalBindingEvents(test).at(-1)?.lifecycle).toBe('stopped')
    await expect(test.composition.bindingStore.load(ControllerSessionId(test.session.id)))
      .resolves.toEqual([expect.objectContaining({ goalId: goal.id, lifecycle: 'stopped' })])
    expect(devFrameStateOf(test.ctx, test.session).failure).toBeNull()

    const resumed = await execute(test, '/devframe-resume')
    if (resumed.result.kind !== 'error') throw new Error('expected an error result')
    expect(resumed.result.text).toBe(RESUME_NO_CURRENT_GOAL_TEXT)
    expect(abandoned.result.text).not.toContain(goal.id)
  })

  it('abandons an unfinished goal: stop-marks the binding, clears the Goal, frees the workspace', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      sessionId: SessionId('controller-v14-abandon-running'),
    })
    const binding = await startBoundGoal(test)
    const goal = test.ctx.goals.get(test.agent)
    if (goal === undefined) throw new Error('goal is missing after start')

    const abandoned = await execute(test, '/devframe-abandon')

    if (abandoned.result.kind !== 'success') throw new Error('expected a success result')
    expect(abandoned.result.text).toBe(renderAbandonSuccess())
    expect(test.ctx.goals.get(test.agent)).toBeUndefined()
    expect(hasGoalChange(test, 'clear')).toBe(true)
    expect(hasGoalChange(test, 'receipt')).toBe(false)
    const bindings = goalBindingEvents(test)
    expect(bindings).toHaveLength(2)
    expect(bindings[1]).toMatchObject({
      goalId: goal.id,
      goalRevision: binding.goalRevision,
      lifecycle: 'stop_requested',
    })
    expect(devFrameStateOf(test.ctx, test.session).failure).toBeNull()

    const resumed = await execute(test, '/devframe-resume')
    if (resumed.result.kind !== 'error') throw new Error('expected an error result')
    expect(resumed.result.text).toBe(RESUME_NO_CURRENT_GOAL_TEXT)

    const restarted = await execute(test, '/devframe-start migrate the schema')
    if (restarted.result.kind !== 'success') throw new Error('expected a success result')
    const nextGoal = test.ctx.goals.get(test.agent)
    expect(nextGoal?.id).not.toBe(goal.id)
    expect(goalBindingEvents(test).at(-1)).toMatchObject({
      goalId: nextGoal?.id,
      lifecycle: 'admission_open',
    })
    expect(devFrameStateOf(test.ctx, test.session).failure).toBeNull()
  })

  it('answers stable data errors with zero structural side effects', async () => {
    const fixture = await createCommittedWorktree()
    const test = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      sessionId: SessionId('controller-v14-abandon-d1'),
    })

    const noGoal = await execute(test, '/devframe-abandon')
    if (noGoal.result.kind !== 'error') throw new Error('expected an error result')
    expect(noGoal.result.text).toBe(ABANDON_NO_CURRENT_GOAL_TEXT)

    const residue = await execute(test, '/devframe-abandon everything')
    if (residue.result.kind !== 'error') throw new Error('expected an error result')
    expect(residue.result.text).toBe(ABANDON_INPUT_UNEXPECTED_TEXT)

    await startBoundGoal(test)
    expect((await execute(test, '/devframe-stop')).result.kind).toBe('success')
    const midStop = await execute(test, '/devframe-abandon')
    if (midStop.result.kind !== 'error') throw new Error('expected an error result')
    expect(midStop.result.text).toBe(ABANDON_UNRESOLVED_STATE_TEXT)
    expect(goalBindingEvents(test)).toHaveLength(2)
    expect(hasGoalChange(test, 'clear')).toBe(false)

    const goal = test.ctx.goals.get(test.agent)
    if (goal === undefined) throw new Error('goal is missing')
    test.ctx.goals.complete(test.agent, { id: goal.id, revision: goal.revision })
    const complete = await execute(test, '/devframe-abandon')
    if (complete.result.kind !== 'error') throw new Error('expected an error result')
    expect(complete.result.text).toBe(GOAL_ALREADY_COMPLETE_TEXT)
    expect(hasGoalChange(test, 'clear')).toBe(false)
    expect(devFrameStateOf(test.ctx, test.session).failure).toBeNull()
  })
})
