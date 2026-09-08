import { afterEach, describe, expect, it, vi } from 'vitest'
import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import AgentRegistry, { Inbox } from '@deepseek-ai/dsh-agent'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { GoalId } from '@deepseek-ai/dsh-goal'
import GoalService from '@deepseek-ai/dsh-goal'
import SessionStore, { Session, SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import { MemoryRequiredChecksConfigStore, requiredChecksDigest } from '../src/required-checks.ts'
import { computeSourceFingerprint } from '../src/source-fingerprint.ts'
import { AcceptanceHash, ConfigurationConfirmationId, DevFrameSnapshotId, SourceFingerprint, WorkspaceId } from '../src/shared/types.ts'
import { DevFrameDeliveryId, DevFrameReviewId, DevFrameVerificationId } from '../src/events.ts'
import {
  ControllerSessionId,
  GoalBindingController,
  GoalBindingError,
  GoalServicePort,
  MemoryGoalBindingStore,
  TaskId,
  createHumanAuthorization,
} from '../src/controller/goal-binding.ts'
import type {
  CompleteGoalRequest,
  GoalBinding,
  GoalBindingStore,
  NativeGoalPort,
  NativeGoalState,
} from '../src/controller/goal-binding.ts'
import {
  CONFIG,
  createCommittedWorktree,
  drainWorktreeFixtures,
  executionFor,
  reviewEvent,
  resultReference,
} from './completion-fixtures.ts'
import type { WorktreeFixture } from './completion-fixtures.ts'

afterEach(async () => {
  await drainWorktreeFixtures()
})

interface TraceGoal extends NativeGoalState {
  activation: 'armed' | 'disarmed'
}

/** Build a minimal live Agent for the native GoalService integration probe. */
function nativeAgent(session: Session): Agent {
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

/** Mount the native Goal service behind the controller's production port. */
async function realGoalPort(id: string): Promise<{
  readonly ctx: Context
  readonly agent: Agent
  readonly port: NativeGoalPort
}> {
  const ctx = new Context()
  await ctx.plugin(SessionStore)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(GoalService)
  const agent = nativeAgent(ctx.sessions.create(SessionId(id)))
  ctx.agents.register(agent)
  return {
    ctx,
    agent,
    port: new GoalServicePort({ goals: ctx.goals, agent }),
  }
}

function fakeGoals(trace: string[]): NativeGoalPort & { current: TraceGoal | undefined } {
  let nextGoal = 1
  const port: NativeGoalPort & { current: TraceGoal | undefined } = {
    current: undefined,
    create(request) {
      trace.push(`goal:create:${request.objective}`)
      const goal: TraceGoal = {
        id: GoalId(`goal-${nextGoal}`),
        revision: 1,
        phase: 'active',
        activation: 'armed',
      }
      nextGoal += 1
      port.current = goal
      return goal
    },
    disarm() {
      trace.push('goal:disarm')
      if (port.current !== undefined) port.current = { ...port.current, activation: 'disarmed' }
      return port.current
    },
    get() {
      trace.push('goal:get')
      return port.current
    },
    resume(ref) {
      trace.push(`goal:resume:${ref.id}:${ref.revision}`)
      if (port.current === undefined || port.current.id !== ref.id) {
        throw new Error('resume target mismatch')
      }
      port.current = {
        ...port.current,
        revision: port.current.revision + 1,
        activation: 'armed',
      }
      return port.current
    },
    complete(ref) {
      trace.push(`goal:complete:${ref.id}:${ref.revision}`)
      if (port.current === undefined || port.current.id !== ref.id) {
        throw new Error('complete target mismatch')
      }
      port.current = {
        ...port.current,
        revision: port.current.revision + 1,
        phase: 'complete',
        activation: 'disarmed',
      }
      return port.current
    },
    clear(ref) {
      trace.push(`goal:clear:${ref.id}:${ref.revision}`)
      if (port.current === undefined || port.current.id !== ref.id) {
        throw new Error('clear target mismatch')
      }
      port.current = undefined
      return { id: ref.id, revision: ref.revision + 1 }
    },
  }
  return port
}

function request(overrides: Partial<Parameters<GoalBindingController['start']>[0]> = {}) {
  return {
    objective: 'implement task',
    taskIds: [TaskId('task-1')],
    acceptanceHash: AcceptanceHash('acceptance-a'),
    sourceFingerprint: SourceFingerprint('source-a'),
    snapshotId: DevFrameSnapshotId('snapshot-a'),
    budget: { maxAttempts: 3 },
    authorization: createHumanAuthorization('confirm-a'),
    ...overrides,
  }
}

describe('GoalBindingController', () => {
  it('keeps admission closed through native create/disarm and persistence, then resumes', async () => {
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const store = new MemoryGoalBindingStore()
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-a'),
      controllerSessionId: ControllerSessionId('controller-a'),
      goals,
      store,
    })

    expect(controller.admissionState).toBe('closed')
    const binding = await controller.start(request())

    expect(trace).toEqual([
      'goal:get',
      'goal:create:implement task',
      'goal:disarm',
      'goal:resume:goal-1:1',
    ])
    expect(binding).toMatchObject({
      controllerSessionId: 'controller-a',
      goalId: 'goal-1',
      goalRevision: 2,
      taskIds: ['task-1'],
      acceptanceHash: 'acceptance-a',
      budget: { maxAttempts: 3, consumedAttempts: 0 },
    })
    expect(goals.current?.activation).toBe('armed')
    expect(controller.admissionState).toBe('open')
    expect(controller.assertAdmitted(binding)).toEqual(binding)
    await expect(store.read(WorkspaceId('workspace-a'))).resolves.toMatchObject({
      workspaceId: 'workspace-a',
      controllerSessionId: 'controller-a',
      goalId: 'goal-1',
      goalRevision: 2,
      acceptanceHash: 'acceptance-a',
      sourceFingerprint: 'source-a',
      confirmation: { id: 'confirm-a', acceptanceHash: 'acceptance-a' },
      lifecycle: 'admission_open',
    })
  })

  it('rejects model-shaped authorization before mutating native Goal state', async () => {
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-auth'),
      controllerSessionId: ControllerSessionId('controller-auth'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const forged = { kind: 'human', confirmationId: 'model-text' }

    await expect(controller.start(request({ authorization: forged as never }))).rejects.toMatchObject({
      code: 'GOAL_BINDING_AUTHORIZATION_REQUIRED',
    })
    expect(trace).toEqual([])
    expect(controller.admissionState).toBe('closed')
  })

  it('keeps admission closed and native continuation disarmed when persistence fails', async () => {
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const store: GoalBindingStore = {
      load: vi.fn(async () => []),
      save: vi.fn(async () => { throw new Error('disk unavailable') }),
      read: vi.fn(async () => undefined),
      write: vi.fn(async () => undefined),
    }
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-failure'),
      controllerSessionId: ControllerSessionId('controller-failure'),
      goals,
      store,
    })

    await expect(controller.start(request())).rejects.toMatchObject({
      code: 'GOAL_BINDING_PERSISTENCE',
    })
    expect(trace).toEqual(['goal:get', 'goal:create:implement task', 'goal:disarm'])
    expect(goals.current?.activation).toBe('disarmed')
    expect(controller.admissionState).toBe('closed')
    expect(() => controller.assertAdmitted({
      controllerSessionId: ControllerSessionId('controller-failure'),
      goalId: GoalId('goal-1'),
    })).toThrow(expect.objectContaining({ code: 'GOAL_BINDING_ADMISSION_CLOSED' }))
  })

  it('keeps Goal A results attached to A after a fresh Goal B starts', async () => {
    const goalsTrace: string[] = []
    const goals = fakeGoals(goalsTrace)
    const store = new MemoryGoalBindingStore()
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-consecutive'),
      controllerSessionId: ControllerSessionId('controller-consecutive'),
      goals,
      store,
    })
    const a = await controller.start(request())

    goals.current = { ...goals.current!, phase: 'complete' }
    controller.closeAdmission()
    const b = await controller.start(request({
      objective: 'implement task B',
      taskIds: [TaskId('task-2')],
      acceptanceHash: AcceptanceHash('acceptance-b'),
      sourceFingerprint: SourceFingerprint('source-b'),
      authorization: createHumanAuthorization('confirm-b'),
      budget: { maxAttempts: 2 },
    }))

    expect(b.goalId).not.toBe(a.goalId)
    expect(b.taskIds).toEqual([TaskId('task-2')])
    expect(controller.currentBinding()).toEqual(b)
    expect(controller.resolveResultBinding(resultReference(a))).toEqual(a)
    expect(() => controller.resolveResultBinding({
      ...resultReference(a),
      goalId: b.goalId,
      taskIds: a.taskIds,
      acceptanceHash: a.acceptanceHash,
    })).toThrow(expect.objectContaining({ code: 'GOAL_BINDING_IDENTITY_MISMATCH' }))
    expect(() => controller.resolveResultBinding({
      ...resultReference(a),
      snapshotId: DevFrameSnapshotId('snapshot-OTHER'),
    })).toThrow(expect.objectContaining({ code: 'GOAL_BINDING_IDENTITY_MISMATCH' }))
    expect(goalsTrace.filter(value => value.startsWith('goal:create'))).toEqual([
      'goal:create:implement task',
      'goal:create:implement task B',
    ])
  })

  it('rejects missing or blank snapshot ids before any native Goal mutation', async () => {
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-snapshot'),
      controllerSessionId: ControllerSessionId('controller-snapshot'),
      goals,
      store: new MemoryGoalBindingStore(),
    })

    await expect(controller.start(request({ snapshotId: undefined as unknown as DevFrameSnapshotId })))
      .rejects.toMatchObject({ code: 'GOAL_BINDING_INVALID_REQUEST' })
    await expect(controller.start(request({ snapshotId: DevFrameSnapshotId('  ') })))
      .rejects.toMatchObject({ code: 'GOAL_BINDING_INVALID_REQUEST' })
    expect(trace).toEqual([])
    expect(controller.admissionState).toBe('closed')
  })

  it('resumes an exact persisted Goal identity after restoration', async () => {
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const store = new MemoryGoalBindingStore()
    const first = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-resume'),
      controllerSessionId: ControllerSessionId('controller-resume'),
      goals,
      store,
    })
    const binding = await first.start(request())
    first.closeAdmission()
    goals.current = { ...goals.current!, activation: 'disarmed', phase: 'paused', revision: 2 }

    const restored = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-resume'),
      controllerSessionId: ControllerSessionId('controller-resume'),
      goals,
      store,
    })
    const resumed = await restored.resume(binding, createHumanAuthorization('resume-a'))

    expect(resumed).toMatchObject({ ...binding, goalRevision: 3 })
    expect(restored.assertAdmitted(binding)).toMatchObject({ ...binding, goalRevision: 3 })
    expect(restored.resolveResultBinding(resultReference(resumed))).toEqual(resumed)
    expect(trace.at(-1)).toBe('goal:resume:goal-1:2')
  })

  it('serializes concurrent starts and refuses a second unfinished Goal', async () => {
    const goals = fakeGoals([])
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-race'),
      controllerSessionId: ControllerSessionId('controller-race'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const first = controller.start(request())
    const second = controller.start(request({
      objective: 'racing task',
      acceptanceHash: AcceptanceHash('acceptance-race'),
      sourceFingerprint: SourceFingerprint('source-race'),
      authorization: createHumanAuthorization('confirm-race'),
    }))

    await expect(first).resolves.toMatchObject({ goalId: 'goal-1' })
    await expect(second).rejects.toMatchObject({ code: 'GOAL_BINDING_ALREADY_RUNNING' })
    expect(controller.admissionState).toBe('open')
    expect(goals.current?.activation).toBe('armed')
  })

  it('stores the revision returned by the native GoalService resume', async () => {
    const { ctx, agent, port } = await realGoalPort('controller-native-resume')
    try {
      const store = new MemoryGoalBindingStore()
      const controller = new GoalBindingController({
        workspaceId: WorkspaceId('workspace-native-resume'),
        controllerSessionId: agent.id,
        goals: port,
        store,
      })

      const binding = await controller.start(request())
      expect(binding.goalRevision).toBe(2)
      expect(ctx.goals.get(agent)).toMatchObject({ id: binding.goalId, revision: 2, activation: 'armed' })

      controller.closeAdmission()
      const current = ctx.goals.get(agent)
      if (current === undefined) throw new Error('expected native Goal after start')
      const paused = ctx.goals.pause(agent, { id: current.id, revision: current.revision })
      expect(paused.revision).toBe(3)

      const resumed = await controller.resume(binding, createHumanAuthorization('resume-native'))
      expect(resumed.goalRevision).toBe(4)
      await expect(store.read(WorkspaceId('workspace-native-resume'))).resolves.toMatchObject({ goalRevision: 4 })
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('adopts changed approved checks into a new binding generation on resume', async () => {
    const { ctx, agent, port } = await realGoalPort('controller-native-adopt')
    try {
      const store = new MemoryGoalBindingStore()
      const controller = new GoalBindingController({
        workspaceId: WorkspaceId('workspace-native-adopt'),
        controllerSessionId: agent.id,
        goals: port,
        store,
      })

      const binding = await controller.start(request())
      controller.closeAdmission()
      const current = ctx.goals.get(agent)
      if (current === undefined) throw new Error('expected native Goal after start')
      ctx.goals.pause(agent, { id: current.id, revision: current.revision })

      // The host composition recomputes the acceptance of (objective,
      // current checks) and mints a fresh confirmation; the resumed binding
      // carries both as the adopted generation's acceptance face.
      const adoptedHash = AcceptanceHash(`${binding.acceptanceHash}-adopted`)
      const resumed = await controller.resume(binding, createHumanAuthorization('resume-adopt'), {
        acceptanceHash: adoptedHash,
        confirmation: {
          id: ConfigurationConfirmationId('confirmation-adopted'),
          acceptanceHash: adoptedHash,
        },
      })
      expect(resumed.goalRevision).toBe(binding.goalRevision + 2)
      expect(resumed.lifecycle).toBe('admission_open')
      expect(resumed.acceptanceHash).toBe(adoptedHash)
      expect(resumed.confirmation).toMatchObject({ id: 'confirmation-adopted', acceptanceHash: adoptedHash })
      await expect(store.read(WorkspaceId('workspace-native-adopt'))).resolves.toMatchObject({
        goalRevision: binding.goalRevision + 2,
        acceptanceHash: adoptedHash,
      })
      expect(controller.admissionState).toBe('open')
    } finally {
      await ctx.fiber.dispose()
    }
  })
})

describe('GoalBindingError', () => {
  it('keeps a stable name and code', () => {
    const error = new GoalBindingError('closed', 'GOAL_BINDING_ADMISSION_CLOSED')
    expect(error).toBeInstanceOf(Error)
    expect(error.name).toBe('GoalBindingError')
    expect(error.code).toBe('GOAL_BINDING_ADMISSION_CLOSED')
  })
})

describe('GoalServicePort', () => {
  it('projects the native service views onto the narrow port state', async () => {
    const { ctx, port } = await realGoalPort('controller-port-projection')
    try {
      expect(port.get()).toBeUndefined()
      expect(port.disarm()).toBeUndefined()
      const created = port.create({ objective: 'port projection probe' })
      expect(created).toMatchObject({ revision: 1, phase: 'active' })
      expect(port.get()).toMatchObject({ id: created.id, phase: 'active' })
      expect(port.disarm()).toMatchObject({ id: created.id })
      expect(port.resume({ id: created.id, revision: 1 })).toMatchObject({ revision: 2, phase: 'active' })
      expect(port.complete({ id: created.id, revision: 2 })).toMatchObject({ revision: 3, phase: 'complete' })
    } finally {
      await ctx.fiber.dispose()
    }
  })
})

describe('GoalBindingController completion admission', { timeout: 30_000 }, () => {
  // Every case evaluates the three admission predicates against a real git
  // worktree; the per-test budget stays above the runner default to absorb
  // lane contention on that cost.

  it('completes the native Goal only after the three predicates admit', async () => {
    const fixture = await createCommittedWorktree()
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const store = new MemoryGoalBindingStore()
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-complete'),
      controllerSessionId: ControllerSessionId('controller-complete'),
      goals,
      store,
    })
    const binding = await controller.start(request({ sourceFingerprint: fixture.fingerprint }))

    const verdict = await controller.complete(binding, await completionRequest(fixture, binding))

    expect(trace).toEqual([
      'goal:get',
      'goal:create:implement task',
      'goal:disarm',
      'goal:resume:goal-1:1',
      'goal:get',
      'goal:complete:goal-1:2',
    ])
    expect(verdict).toEqual({
      kind: 'admitted',
      fingerprint: fixture.fingerprint,
      requiredChecksDigest: requiredChecksDigest(CONFIG),
    })
    expect(goals.current).toMatchObject({ id: 'goal-1', revision: 3, phase: 'complete', activation: 'disarmed' })
    expect(controller.admissionState).toBe('closed')
    await expect(store.read(WorkspaceId('workspace-complete'))).resolves.toMatchObject({ goalRevision: 3 })
  })

  it('completes through the real native GoalService via GoalServicePort', async () => {
    const fixture = await createCommittedWorktree()
    const { ctx, agent, port } = await realGoalPort('controller-native-complete')
    try {
      const store = new MemoryGoalBindingStore()
      const controller = new GoalBindingController({
        workspaceId: WorkspaceId('workspace-native-complete'),
        controllerSessionId: agent.id,
        goals: port,
        store,
      })
      const binding = await controller.start(request({ sourceFingerprint: fixture.fingerprint }))

      const verdict = await controller.complete(binding, await completionRequest(fixture, binding))

      expect(verdict).toEqual({
        kind: 'admitted',
        fingerprint: fixture.fingerprint,
        requiredChecksDigest: requiredChecksDigest(CONFIG),
      })
      expect(ctx.goals.get(agent)).toMatchObject({ id: binding.goalId, revision: 3, phase: 'complete' })
      await expect(store.read(WorkspaceId('workspace-native-complete'))).resolves.toMatchObject({ goalRevision: 3 })
      expect(controller.admissionState).toBe('closed')
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('rejects at the source-fingerprint stage and leaves the native Goal untouched', async () => {
    const fixture = await createCommittedWorktree()
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const store = new MemoryGoalBindingStore()
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-complete-fp'),
      controllerSessionId: ControllerSessionId('controller-complete-fp'),
      goals,
      store,
    })
    // The start records the `source-a` claim, which no real worktree matches;
    // the admission recompute therefore diverges from the durable binding.
    const binding = await controller.start(request())

    const verdict = await controller.complete(binding, await completionRequest(fixture, binding))

    expect(verdict.kind).toBe('rejected')
    if (verdict.kind !== 'rejected' || verdict.stage !== 'source-fingerprint') {
      throw new Error('expected a fingerprint rejection')
    }
    expect(verdict.mismatch.recordedFingerprint).toBe(binding.sourceFingerprint)
    expect(verdict.mismatch.computed.fingerprint).toBe(fixture.fingerprint)
    expect(trace.filter(entry => entry.startsWith('goal:complete'))).toEqual([])
    expect(goals.current).toMatchObject({ id: 'goal-1', revision: 2, phase: 'active' })
    expect(controller.admissionState).toBe('closed')
    expect(() => controller.assertAdmitted(binding))
      .toThrow(expect.objectContaining({ code: 'GOAL_BINDING_ADMISSION_CLOSED' }))
    await expect(store.read(WorkspaceId('workspace-complete-fp'))).resolves.toMatchObject({ goalRevision: 2 })
  })

  it('rejects at the required-checks stage and leaves the native Goal untouched', async () => {
    const fixture = await createCommittedWorktree()
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-complete-checks'),
      controllerSessionId: ControllerSessionId('controller-complete-checks'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const weakenedLint = CONFIG.checks[0]
    if (weakenedLint === undefined) throw new Error('fixture configuration is malformed')
    const binding = await controller.start(request({ sourceFingerprint: fixture.fingerprint }))

    const verdict = await controller.complete(binding, await completionRequest(fixture, binding, {
      checks: [
        executionFor(weakenedLint, 'passed', { arguments: ['run', 'lint', '--fix'] }),
        executionFor(CONFIG.checks[1]!),
      ],
    }))

    expect(verdict.kind).toBe('rejected')
    if (verdict.kind !== 'rejected' || verdict.stage !== 'required-checks') {
      throw new Error('expected a required-checks rejection')
    }
    expect(verdict.verdict.violations).toEqual([{
      reason: 'REQUIRED_CHECKS_COMMAND_MISMATCH',
      checkId: weakenedLint.checkId,
      configured: { executable: weakenedLint.executable, arguments: weakenedLint.arguments, cwd: weakenedLint.cwd },
      executed: [{ executable: weakenedLint.executable, arguments: ['run', 'lint', '--fix'], cwd: weakenedLint.cwd }],
    }])
    expect(goals.current).toMatchObject({ id: 'goal-1', revision: 2, phase: 'active' })
    expect(controller.admissionState).toBe('closed')
  })

  it('rejects at the review stage and leaves the native Goal untouched', async () => {
    const fixture = await createCommittedWorktree()
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-complete-review'),
      controllerSessionId: ControllerSessionId('controller-complete-review'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const binding = await controller.start(request({ sourceFingerprint: fixture.fingerprint }))
    const review = reviewEvent('changes_required', {
      binding: resultReference(binding),
      snapshotId: binding.snapshotId,
    })

    const verdict = await controller.complete(binding, await completionRequest(fixture, binding, { review }))

    expect(verdict.kind).toBe('rejected')
    if (verdict.kind !== 'rejected' || verdict.stage !== 'review') {
      throw new Error('expected a review rejection')
    }
    expect(verdict.reviewId).toBe(review.reviewId)
    expect(verdict.decision).toBe('changes_required')
    expect(verdict.findings).toEqual(review.findings)
    expect(goals.current).toMatchObject({ id: 'goal-1', revision: 2, phase: 'active' })
    expect(controller.admissionState).toBe('closed')
  })

  it('propagates a failed store resolution fail-loud before any native mutation', async () => {
    const fixture = await createCommittedWorktree()
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-complete-store'),
      controllerSessionId: ControllerSessionId('controller-complete-store'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const binding = await controller.start(request({ sourceFingerprint: fixture.fingerprint }))

    await expect(controller.complete(binding, await completionRequest(fixture, binding, {
      requiredChecksStore: new MemoryRequiredChecksConfigStore(),
    }))).rejects.toMatchObject({
      name: 'RequiredChecksError',
      code: 'REQUIRED_CHECKS_CONFIG_NOT_FOUND',
    })
    expect(trace.filter(entry => entry.startsWith('goal:complete'))).toEqual([])
    expect(goals.current).toMatchObject({ id: 'goal-1', revision: 2, phase: 'active' })
    expect(controller.admissionState).toBe('closed')
  })

  it('keeps admission open when the identity is unknown', async () => {
    const fixture = await createCommittedWorktree()
    const goals = fakeGoals([])
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-complete-unknown'),
      controllerSessionId: ControllerSessionId('controller-complete-unknown'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const binding = await controller.start(request({ sourceFingerprint: fixture.fingerprint }))

    await expect(controller.complete(
      { ...binding, goalId: GoalId('goal-missing') },
      await completionRequest(fixture, binding),
    )).rejects.toMatchObject({ code: 'GOAL_BINDING_NOT_FOUND' })
    expect(controller.admissionState).toBe('open')
  })

  it('rejects a native Goal that vanished before the completion', async () => {
    const fixture = await createCommittedWorktree()
    const goals = fakeGoals([])
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-complete-vanished'),
      controllerSessionId: ControllerSessionId('controller-complete-vanished'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const binding = await controller.start(request({ sourceFingerprint: fixture.fingerprint }))
    goals.current = undefined

    await expect(controller.complete(binding, await completionRequest(fixture, binding)))
      .rejects.toMatchObject({ code: 'GOAL_BINDING_IDENTITY_MISMATCH' })
    expect(controller.admissionState).toBe('closed')
  })

  it('refuses completion as real task failure when the log holds a fail-graded memory record', async () => {
    const fixture = await createCommittedWorktree()
    const goals = fakeGoals([])
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-complete-warning'),
      controllerSessionId: ControllerSessionId('controller-complete-warning'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const binding = await controller.start(request({ sourceFingerprint: fixture.fingerprint }))
    const before = goals.current

    // The required-memory task's graded record: the acceptance needed the
    // memory operation and it failed, so the verdict is a rejection with the
    // record's own evidence and the native Goal stays untouched — the task's
    // real outcome is failure, never a warned completion.
    const verdict = await controller.complete(binding, await completionRequest(fixture, binding, {
      taskWarnings: [{
        version: 1,
        taskId: binding.taskIds[0]!,
        warning: 'MEMORY_UNAVAILABLE',
        tool: 'memory_append',
        grade: 'fail',
      }],
    }))
    expect(verdict).toEqual({
      kind: 'rejected',
      stage: 'task-warning',
      taskId: binding.taskIds[0],
      warning: 'MEMORY_UNAVAILABLE',
      tool: 'memory_append',
      grade: 'fail',
    })
    expect(goals.current).toBe(before)
    expect(goals.current?.phase).not.toBe('complete')
    expect(controller.admissionState).toBe('closed')
  })

  it('completes an optional-memory task whose degraded record never graded fail', async () => {
    const fixture = await createCommittedWorktree()
    const goals = fakeGoals([])
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-complete-optional'),
      controllerSessionId: ControllerSessionId('controller-complete-optional'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const binding = await controller.start(request({ sourceFingerprint: fixture.fingerprint }))

    // The optional-memory path does not regress: a complete-with-warning
    // record is not failure evidence, and the admission admits.
    const verdict = await controller.complete(binding, await completionRequest(fixture, binding, {
      taskWarnings: [{
        version: 1,
        taskId: binding.taskIds[0]!,
        warning: 'MEMORY_UNAVAILABLE',
        tool: 'memory_append',
        grade: 'complete-with-warning',
      }],
    }))
    expect(verdict.kind).toBe('admitted')
    expect(goals.current?.phase).toBe('complete')
  })

  it('rejects a native Goal that now belongs to another identity', async () => {
    const fixture = await createCommittedWorktree()
    const goals = fakeGoals([])
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-complete-foreign'),
      controllerSessionId: ControllerSessionId('controller-complete-foreign'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const binding = await controller.start(request({ sourceFingerprint: fixture.fingerprint }))
    goals.current = { ...goals.current!, id: GoalId('goal-foreign') }

    await expect(controller.complete(binding, await completionRequest(fixture, binding)))
      .rejects.toMatchObject({ code: 'GOAL_BINDING_IDENTITY_MISMATCH' })
  })

  it('rejects a native Goal that fell behind the bound revision', async () => {
    const fixture = await createCommittedWorktree()
    const goals = fakeGoals([])
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-complete-behind'),
      controllerSessionId: ControllerSessionId('controller-complete-behind'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const binding = await controller.start(request({ sourceFingerprint: fixture.fingerprint }))
    goals.current = { ...goals.current!, revision: 1 }

    await expect(controller.complete(binding, await completionRequest(fixture, binding)))
      .rejects.toMatchObject({ code: 'GOAL_BINDING_IDENTITY_MISMATCH' })
  })

  it('rejects a Goal the native lifecycle already completed', async () => {
    const fixture = await createCommittedWorktree()
    const goals = fakeGoals([])
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-complete-done'),
      controllerSessionId: ControllerSessionId('controller-complete-done'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const binding = await controller.start(request({ sourceFingerprint: fixture.fingerprint }))
    goals.current = { ...goals.current!, phase: 'complete' }

    await expect(controller.complete(binding, await completionRequest(fixture, binding)))
      .rejects.toThrow('is already complete')
  })

  it('rejects review evidence attributed to another Goal before evaluating', async () => {
    const fixture = await createCommittedWorktree()
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-complete-attribution'),
      controllerSessionId: ControllerSessionId('controller-complete-attribution'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const binding = await controller.start(request({ sourceFingerprint: fixture.fingerprint }))
    // A real worktree evaluation would only ever return a verdict, so each
    // GoalBindingError below proves the attribution mismatch is enforced
    // before the predicates run.
    const completion = await completionRequest(fixture, binding)
    const foreignGoal = reviewEvent('pass', { binding: { ...completion.review.binding, goalId: GoalId('goal-admission') } })
    const foreignSession = reviewEvent('pass', {
      binding: { ...completion.review.binding, controllerSessionId: ControllerSessionId('controller-foreign') },
    })
    const foreignWorkspace = reviewEvent('pass', {
      binding: { ...completion.review.binding, workspaceId: WorkspaceId('workspace-foreign') },
    })

    await expect(controller.complete(binding, { ...completion, review: foreignGoal })).rejects.toThrow(
      'completion review evidence is attributed to Goal "goal-admission"',
    )
    await expect(controller.complete(binding, { ...completion, review: foreignSession })).rejects.toThrow(
      'is recorded under controller Session "controller-foreign"',
    )
    await expect(controller.complete(binding, { ...completion, review: foreignWorkspace })).rejects.toThrow(
      'is recorded for workspace "workspace-foreign"',
    )
    expect(trace.filter(entry => entry.startsWith('goal:complete'))).toEqual([])
    expect(goals.current).toMatchObject({ id: 'goal-1', revision: 2, phase: 'active' })
  })

  it('rejects a native completion that returned another identity without persisting it', async () => {
    const fixture = await createCommittedWorktree()
    const goals = fakeGoals([])
    const store = new MemoryGoalBindingStore()
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-complete-returned'),
      controllerSessionId: ControllerSessionId('controller-complete-returned'),
      goals,
      store,
    })
    const binding = await controller.start(request({ sourceFingerprint: fixture.fingerprint }))
    const foreignState: TraceGoal = {
      id: GoalId('goal-foreign'),
      revision: 3,
      phase: 'complete',
      activation: 'disarmed',
    }
    goals.complete = () => foreignState

    await expect(controller.complete(binding, await completionRequest(fixture, binding)))
      .rejects.toMatchObject({ code: 'GOAL_BINDING_IDENTITY_MISMATCH' })
    await expect(store.read(WorkspaceId('workspace-complete-returned'))).resolves.toMatchObject({ goalRevision: 2 })
    expect(controller.admissionState).toBe('closed')
  })
})

/** Build one completion request over a fresh store registration, with overrides. */
async function completionRequest(
  fixture: WorktreeFixture,
  binding: GoalBinding,
  overrides: Partial<CompleteGoalRequest> = {},
): Promise<CompleteGoalRequest> {
  const store = new MemoryRequiredChecksConfigStore()
  return {
    worktreePath: fixture.root,
    checks: CONFIG.checks.map(check => executionFor(check)),
    requiredChecksDigest: await store.save(CONFIG),
    requiredChecksStore: store,
    review: reviewEvent('pass', { binding: resultReference(binding), snapshotId: binding.snapshotId }),
    taskWarnings: [],
    ...overrides,
  }
}

describe('GoalBindingController final-merge completion contract', { timeout: 30_000 }, () => {
  // The final merge moves the controller worktree past the binding's initial
  // start fingerprint; every case runs the whole admission against a real git
  // worktree, so the budget stays above the runner default for that cost.

  /**
   * Start one two-task Goal whose controller worktree then receives the final
   * merge, and build the whole-Goal evidence contract the completion
   * admission consumes in the final-merge lane.
   */
  async function finalMergeFixture(workspaceId: string) {
    const fixture = await createCommittedWorktree()
    const initial = fixture.fingerprint
    // Simulate the final merge landing in the controller worktree: the tree
    // moves past the initial claim before completion is attempted.
    await writeFile(join(fixture.root, 'merged.ts'), 'export const merged = true\n')
    const merged = await computeSourceFingerprint({ worktreePath: fixture.root })
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const store = new MemoryGoalBindingStore()
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId(workspaceId),
      controllerSessionId: ControllerSessionId(workspaceId),
      goals,
      store,
    })
    const binding = await controller.start(request({
      taskIds: [TaskId('task-a'), TaskId('task-b')],
      sourceFingerprint: initial,
    }))
    const checksStore = new MemoryRequiredChecksConfigStore()
    const digest = await checksStore.save(CONFIG)
    const mergedBinding = {
      controllerSessionId: binding.controllerSessionId,
      goalId: binding.goalId,
      goalRevision: binding.goalRevision,
      taskIds: binding.taskIds,
      acceptanceHash: binding.acceptanceHash,
      workspaceId: binding.workspaceId,
      sourceFingerprint: merged.fingerprint,
      snapshotId: DevFrameSnapshotId('snapshot-final-merge'),
    }
    const verification = {
      version: 1 as const,
      verificationId: DevFrameVerificationId('verification-final-merge'),
      binding: mergedBinding,
      snapshotId: mergedBinding.snapshotId,
      status: 'passed' as const,
      requiredChecks: { config: CONFIG, digest },
      checks: CONFIG.checks.map(check => executionFor(check)),
    }
    const review = reviewEvent('pass', {
      reviewId: DevFrameReviewId('review-final-merge'),
      binding: mergedBinding,
      snapshotId: mergedBinding.snapshotId,
      reviewerSessionId: SessionId('final-reviewer'),
    })
    const contract = {
      targetPath: fixture.root,
      tasks: [
        { taskId: TaskId('task-a'), appliedHead: 'a'.repeat(40) },
        { taskId: TaskId('task-b'), appliedHead: 'b'.repeat(40) },
      ],
      verification, review,
      workerSessionIds: [SessionId('worker-a'), SessionId('worker-b')],
    }
    const completeRequest: CompleteGoalRequest = {
      worktreePath: fixture.root,
      checks: verification.checks,
      requiredChecksDigest: digest,
      requiredChecksStore: checksStore,
      review,
      taskWarnings: [],
      finalIntegration: contract,
    }
    return { fixture, initial, merged, trace, goals, store, controller, binding, contract, completeRequest }
  }

  it('completes at the merged fingerprint and leaves the stored initial claim untouched', async () => {
    const f = await finalMergeFixture('workspace-final-merge')
    const verdict = await f.controller.complete(f.binding, f.completeRequest)
    expect(verdict).toEqual({
      kind: 'admitted',
      fingerprint: f.merged.fingerprint,
      requiredChecksDigest: requiredChecksDigest(CONFIG),
    })
    expect(f.goals.current).toMatchObject({ id: 'goal-1', revision: 3, phase: 'complete', activation: 'disarmed' })
    // No silent rebind: the durable binding keeps the initial start claim.
    await expect(f.store.read(WorkspaceId('workspace-final-merge'))).resolves.toMatchObject({
      sourceFingerprint: f.initial,
      goalRevision: 3,
    })
  })

  it('refuses a bound task worker standing in as the final-merge reviewer', async () => {
    const f = await finalMergeFixture('workspace-final-merge-worker-review')
    const request: CompleteGoalRequest = { ...f.completeRequest, finalIntegration: {
      ...f.contract, review: { ...f.contract.review, reviewerSessionId: SessionId('worker-a') },
    } }
    const verdict = await f.controller.complete(f.binding, request)
    expect(verdict).toEqual({ kind: 'rejected', stage: 'final-integration', reason: 'reviewer-not-independent' })
    expect(f.goals.current).toMatchObject({ id: 'goal-1', revision: 2, phase: 'active' })
  })

  it('refuses delivery-bound evidence masquerading as the final-merge gate', async () => {
    const f = await finalMergeFixture('workspace-final-merge-delivery-bound')
    const request: CompleteGoalRequest = { ...f.completeRequest, finalIntegration: {
      ...f.contract,
      verification: { ...f.contract.verification, deliveryId: DevFrameDeliveryId('delivery-final') },
      review: { ...f.contract.review, deliveryId: DevFrameDeliveryId('delivery-final') },
    } }
    const verdict = await f.controller.complete(f.binding, request)
    expect(verdict).toEqual({ kind: 'rejected', stage: 'final-integration', reason: 'delivery-bound-evidence' })
    expect(f.goals.current).toMatchObject({ id: 'goal-1', revision: 2, phase: 'active' })
  })

  it('refuses a contract that does not cover exactly the bound tasks', async () => {
    const f = await finalMergeFixture('workspace-final-merge-coverage')
    const request: CompleteGoalRequest = { ...f.completeRequest, finalIntegration: {
      ...f.contract, tasks: [f.contract.tasks[0]!],
    } }
    const verdict = await f.controller.complete(f.binding, request)
    expect(verdict).toEqual({ kind: 'rejected', stage: 'final-integration', reason: 'coverage', taskId: TaskId('task-b') })
    expect(f.goals.current).toMatchObject({ id: 'goal-1', revision: 2, phase: 'active' })
  })

  it('refuses when the claimed merged fingerprint does not match the live tree', async () => {
    const f = await finalMergeFixture('workspace-final-merge-fp')
    const phantom = SourceFingerprint('dsh-source-fp-v1-phantom-merge')
    const phantomBinding = { ...f.contract.verification.binding, sourceFingerprint: phantom }
    const request: CompleteGoalRequest = { ...f.completeRequest, finalIntegration: {
      ...f.contract,
      verification: { ...f.contract.verification, binding: phantomBinding },
      review: { ...f.contract.review, binding: phantomBinding },
    } }
    const verdict = await f.controller.complete(f.binding, request)
    if (verdict.kind !== 'rejected' || verdict.stage !== 'source-fingerprint') {
      throw new Error('expected the merged-fingerprint claim to face the live recompute')
    }
    expect(verdict.mismatch.recordedFingerprint).toBe(phantom)
    expect(verdict.mismatch.computed.fingerprint).toBe(f.merged.fingerprint)
    expect(f.goals.current).toMatchObject({ id: 'goal-1', revision: 2, phase: 'active' })
  })

  it('refuses the plain lane on the moved tree instead of letting the initial claim pass the final state', async () => {
    const f = await finalMergeFixture('workspace-final-merge-plain')
    const plain: CompleteGoalRequest = {
      worktreePath: f.completeRequest.worktreePath,
      checks: f.completeRequest.checks,
      requiredChecksDigest: f.completeRequest.requiredChecksDigest,
      requiredChecksStore: f.completeRequest.requiredChecksStore,
      review: reviewEvent('pass', { binding: resultReference(f.binding), snapshotId: f.binding.snapshotId }),
      taskWarnings: [],
    }
    const verdict = await f.controller.complete(f.binding, plain)
    if (verdict.kind !== 'rejected' || verdict.stage !== 'source-fingerprint') {
      throw new Error('expected the initial fingerprint to fail against the merged tree')
    }
    expect(verdict.mismatch.recordedFingerprint).toBe(f.initial)
    expect(verdict.mismatch.computed.fingerprint).toBe(f.merged.fingerprint)
    expect(f.goals.current).toMatchObject({ id: 'goal-1', revision: 2, phase: 'active' })
  })

  it('refuses submitted completion evidence that is not the supplied final-merge evidence', async () => {
    const f = await finalMergeFixture('workspace-final-merge-evidence')
    const staleReview = reviewEvent('pass', { binding: resultReference(f.binding), snapshotId: f.binding.snapshotId })
    await expect(f.controller.complete(f.binding, { ...f.completeRequest, review: staleReview }))
      .rejects.toThrow('completion evidence must be the supplied final-merge evidence')
    expect(f.goals.current).toMatchObject({ id: 'goal-1', revision: 2, phase: 'active' })
    expect(f.controller.admissionState).toBe('closed')
  })
})

describe('GoalBindingController stop and abandon (AT1-10)', () => {
  it('records a human-authorized stop request with disarmed native continuation', async () => {
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const store = new MemoryGoalBindingStore()
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-stop'),
      controllerSessionId: ControllerSessionId('controller-stop'),
      goals,
      store,
    })
    const binding = await controller.start(request())

    const stopped = await controller.stop(
      { controllerSessionId: binding.controllerSessionId, goalId: binding.goalId },
      createHumanAuthorization('stop-confirm'),
    )

    expect(stopped.lifecycle).toBe('stop_requested')
    expect(stopped.goalRevision).toBe(binding.goalRevision)
    expect(goals.current).toMatchObject({ activation: 'disarmed', phase: 'active' })
    expect(controller.admissionState).toBe('closed')
    expect(() => controller.assertAdmitted(binding)).toThrow(
      expect.objectContaining({ code: 'GOAL_BINDING_ADMISSION_CLOSED' }),
    )
    expect(trace).toEqual([
      'goal:get',
      'goal:create:implement task',
      'goal:disarm',
      'goal:resume:goal-1:1',
      'goal:get',
      'goal:disarm',
    ])
    await expect(store.read(WorkspaceId('workspace-stop'))).resolves.toMatchObject({
      goalId: 'goal-1',
      lifecycle: 'stop_requested',
    })
  })

  it('refuses forged authorization, repeat stops, and complete goals without stopping', async () => {
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-stop-refusals'),
      controllerSessionId: ControllerSessionId('controller-stop-refusals'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const binding = await controller.start(request())
    expect(trace).toHaveLength(4)

    const forged = { kind: 'human', confirmationId: 'model-text' }
    await expect(controller.stop(
      { controllerSessionId: binding.controllerSessionId, goalId: binding.goalId },
      forged as never,
    )).rejects.toMatchObject({ code: 'GOAL_BINDING_AUTHORIZATION_REQUIRED' })
    expect(trace).toHaveLength(4)

    await controller.stop(
      { controllerSessionId: binding.controllerSessionId, goalId: binding.goalId },
      createHumanAuthorization('stop-confirm'),
    )
    expect(trace).toHaveLength(6)

    await expect(controller.stop(
      { controllerSessionId: binding.controllerSessionId, goalId: binding.goalId },
      createHumanAuthorization('stop-confirm-2'),
    )).rejects.toMatchObject({ code: 'GOAL_BINDING_INVALID_REQUEST' })
    expect(trace).toHaveLength(7)

    goals.current = { ...goals.current!, phase: 'complete' }
    await expect(controller.stop(
      { controllerSessionId: binding.controllerSessionId, goalId: binding.goalId },
      createHumanAuthorization('stop-confirm-3'),
    )).rejects.toMatchObject({ code: 'GOAL_BINDING_IDENTITY_MISMATCH' })
    expect(trace).toHaveLength(8)
  })

  it('clears the native Goal when abandoning an unfinished Goal and retains the stop-mark', async () => {
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const store = new MemoryGoalBindingStore()
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-abandon-running'),
      controllerSessionId: ControllerSessionId('controller-abandon-running'),
      goals,
      store,
    })
    const binding = await controller.start(request())

    const retained = await controller.abandon(
      { controllerSessionId: binding.controllerSessionId, goalId: binding.goalId },
      createHumanAuthorization('abandon-confirm'),
    )

    expect(retained.lifecycle).toBe('stop_requested')
    expect(goals.current).toBeUndefined()
    expect(controller.admissionState).toBe('closed')
    expect(trace).toEqual([
      'goal:get',
      'goal:create:implement task',
      'goal:disarm',
      'goal:resume:goal-1:1',
      'goal:get',
      'goal:disarm',
      'goal:clear:goal-1:2',
    ])
    await expect(store.read(WorkspaceId('workspace-abandon-running'))).resolves.toMatchObject({
      goalId: 'goal-1',
      lifecycle: 'stop_requested',
    })
  })

  it('abandons an already stopped Goal without another binding record', async () => {
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const store = new MemoryGoalBindingStore()
    await store.save({
      version: 1,
      workspaceId: WorkspaceId('workspace-abandon-stopped'),
      controllerSessionId: ControllerSessionId('controller-abandon-stopped'),
      goalId: GoalId('goal-1'),
      goalRevision: 2,
      taskIds: [TaskId('task-1')],
      acceptanceHash: AcceptanceHash('acceptance-a'),
      sourceFingerprint: SourceFingerprint('source-a'),
      snapshotId: DevFrameSnapshotId('snapshot-a'),
      confirmation: {
        id: ConfigurationConfirmationId('confirm-a'),
        acceptanceHash: AcceptanceHash('acceptance-a'),
      },
      lifecycle: 'stopped',
      budget: { maxAttempts: 3, consumedAttempts: 0 },
    })
    goals.current = {
      id: GoalId('goal-1'),
      revision: 2,
      phase: 'paused',
      activation: 'disarmed',
    }
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-abandon-stopped'),
      controllerSessionId: ControllerSessionId('controller-abandon-stopped'),
      goals,
      store,
    })

    const retained = await controller.abandon(
      { controllerSessionId: ControllerSessionId('controller-abandon-stopped'), goalId: GoalId('goal-1') },
      createHumanAuthorization('abandon-confirm'),
    )

    expect(retained.lifecycle).toBe('stopped')
    expect(goals.current).toBeUndefined()
    expect(trace).toEqual(['goal:get', 'goal:disarm', 'goal:clear:goal-1:2'])
    const loaded = await store.load(ControllerSessionId('controller-abandon-stopped'))
    expect(loaded[0]).toMatchObject({ goalId: 'goal-1', lifecycle: 'stopped' })
  })

  it('refuses abandon mid-stop and when the native port cannot clear', async () => {
    const trace: string[] = []
    const goals = fakeGoals(trace)
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-abandon-midstop'),
      controllerSessionId: ControllerSessionId('controller-abandon-midstop'),
      goals,
      store: new MemoryGoalBindingStore(),
    })
    const binding = await controller.start(request())
    await controller.stop(
      { controllerSessionId: binding.controllerSessionId, goalId: binding.goalId },
      createHumanAuthorization('stop-confirm'),
    )

    await expect(controller.abandon(
      { controllerSessionId: binding.controllerSessionId, goalId: binding.goalId },
      createHumanAuthorization('abandon-confirm'),
    )).rejects.toMatchObject({ code: 'GOAL_BINDING_INVALID_REQUEST' })
    expect(goals.current).not.toBeUndefined()
    expect(trace.some(entry => entry.startsWith('goal:clear'))).toBe(false)

    const base = fakeGoals([])
    const withoutClear: NativeGoalPort = {
      create: request => base.create(request),
      disarm: () => base.disarm(),
      get: () => base.get(),
      resume: ref => base.resume(ref),
      complete: ref => base.complete(ref),
    }
    const clearless = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-abandon-noport'),
      controllerSessionId: ControllerSessionId('controller-abandon-noport'),
      goals: withoutClear,
      store: new MemoryGoalBindingStore(),
    })
    const started = await clearless.start(request({}))

    await expect(clearless.abandon(
      { controllerSessionId: started.controllerSessionId, goalId: started.goalId },
      createHumanAuthorization('abandon-confirm'),
    )).rejects.toMatchObject({ code: 'GOAL_BINDING_INVALID_REQUEST' })
    expect(clearless.admissionState).toBe('closed')
    expect(() => clearless.assertAdmitted(started)).toThrow(
      expect.objectContaining({ code: 'GOAL_BINDING_ADMISSION_CLOSED' }),
    )
  })
})
