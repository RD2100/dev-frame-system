import { describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import AgentRegistry, { Inbox } from '@deepseek-ai/dsh-agent'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { GoalId } from '@deepseek-ai/dsh-goal'
import GoalService from '@deepseek-ai/dsh-goal'
import SessionStore, { Session, SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import { AcceptanceHash, DevFrameSnapshotId, SourceFingerprint, WorkspaceId } from '../src/shared/types.ts'
import {
  ControllerSessionId,
  GoalBindingController,
  GoalBindingError,
  MemoryGoalBindingStore,
  TaskId,
  createHumanAuthorization,
} from '../src/controller/goal-binding.ts'
import type {
  GoalBinding,
  GoalResultBinding,
  GoalBindingStore,
  NativeGoalPort,
  NativeGoalState,
} from '../src/controller/goal-binding.ts'

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
  } as Agent
}

/** Mount the native Goal service behind the controller's narrow port. */
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
    port: {
      create: request => ctx.goals.create(agent, request),
      disarm: () => ctx.goals.disarm(agent),
      get: () => ctx.goals.get(agent),
      resume: ref => ctx.goals.resume(agent, ref),
    },
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

function resultReference(binding: GoalBinding): GoalResultBinding {
  return {
    controllerSessionId: binding.controllerSessionId,
    goalId: binding.goalId,
    goalRevision: binding.goalRevision,
    taskIds: binding.taskIds,
    acceptanceHash: binding.acceptanceHash,
    workspaceId: binding.workspaceId,
    sourceFingerprint: binding.sourceFingerprint,
    snapshotId: binding.snapshotId,
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
})

describe('GoalBindingError', () => {
  it('keeps a stable name and code', () => {
    const error = new GoalBindingError('closed', 'GOAL_BINDING_ADMISSION_CLOSED')
    expect(error).toBeInstanceOf(Error)
    expect(error.name).toBe('GoalBindingError')
    expect(error.code).toBe('GOAL_BINDING_ADMISSION_CLOSED')
  })
})
