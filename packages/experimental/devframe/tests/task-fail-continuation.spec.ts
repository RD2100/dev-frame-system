/** The fail-grade → disarm consumption: a graded fail stops automatic continuation. */

import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import type { Agent, AgentRegistry } from '@deepseek-ai/dsh-agent'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import type { Session } from '@deepseek-ai/dsh-session'
import type { GoalService } from '@deepseek-ai/dsh-goal'
import { TaskId } from '../src/controller/goal-binding.ts'
import { taskFailDisarm } from '../src/index.ts'

const CONTEXTS: Context[] = []

afterEach(async () => {
  for (const ctx of CONTEXTS.splice(0).reverse()) await ctx.fiber.dispose()
})

/** One fake goal the native port reports. */
interface FakeGoal {
  readonly id: string
  readonly revision: number
  readonly phase: 'active' | 'paused' | 'complete'
  readonly activation: 'armed' | 'disarmed'
}

/** The native goal port double: readable state, recorded disarms, optional refusal. */
function stubGoals(goals: Map<Agent, FakeGoal>, refuse: boolean = false): {
  service: GoalService
  disarmed: Agent[]
} {
  const disarmed: Agent[] = []
  const service = {
    get: (agent: Agent) => goals.get(agent),
    disarm: (agent: Agent) => {
      if (refuse) throw new Error('goal port refused')
      disarmed.push(agent)
    },
  } as unknown as GoalService
  return { service, disarmed }
}

/** The agent registry double keyed by the local identity coincidence. */
function stubAgents(agents: Map<string, Agent>): AgentRegistry {
  return { get: (id: string) => agents.get(id) } as unknown as AgentRegistry
}

function makeAgent(id: string): Agent {
  return { id } as unknown as Agent
}

async function boot(options: {
  agents?: Map<string, Agent>
  goals?: Map<Agent, FakeGoal>
  refuse?: boolean
} = {}): Promise<{ ctx: Context; session: Session; agent: Agent; disarmed: Agent[] }> {
  const agentMap = options.agents ?? new Map<string, Agent>()
  const goalMap = options.goals ?? new Map<Agent, FakeGoal>()
  const { service, disarmed } = stubGoals(goalMap, options.refuse ?? false)
  const ctx = new Context()
  CONTEXTS.push(ctx)
  await ctx.plugin(SessionStore)
  await ctx.plugin(function provideStubAgents(inner: Context) { inner.provide('agents', stubAgents(agentMap)) })
  await ctx.plugin(function provideStubGoals(inner: Context) { inner.provide('goals', service) })
  await ctx.plugin(taskFailDisarm)
  const session = ctx.sessions.create(SessionId('session-driver'), { meta: { createdAt: 0 } })
  return { ctx, session, agent: makeAgent('session-driver'), disarmed }
}

function appendWarning(session: Session, grade: 'fail' | 'complete-with-warning'): void {
  session.append('devframe/task-warning', {
    version: 1,
    taskId: TaskId('task-1'),
    warning: 'MEMORY_UNAVAILABLE',
    tool: 'memory_append',
    grade,
  })
}

describe('task-fail continuation consumption', () => {
  it('disarms an armed active goal when a fail-graded warning lands', async () => {
    const agent = makeAgent('session-driver')
    const { session, disarmed } = await boot({
      agents: new Map([['session-driver', agent]]),
      goals: new Map([[agent, { id: 'goal-1', revision: 1, phase: 'active', activation: 'armed' }]]),
    })

    appendWarning(session, 'fail')

    expect(disarmed).toEqual([agent])
    expect(session.snapshotEvents().some(event => event.type === 'devframe/task-warning')).toBe(true)
  })

  it('leaves a complete-with-warning task armed', async () => {
    const agent = makeAgent('session-driver')
    const { session, disarmed } = await boot({
      agents: new Map([['session-driver', agent]]),
      goals: new Map([[agent, { id: 'goal-1', revision: 1, phase: 'active', activation: 'armed' }]]),
    })

    appendWarning(session, 'complete-with-warning')

    expect(disarmed).toEqual([])
  })

  it('skips goals that are not armed and active', async () => {
    const agent = makeAgent('session-driver')
    const { session, disarmed } = await boot({
      agents: new Map([['session-driver', agent]]),
      goals: new Map([
        [agent, { id: 'goal-1', revision: 2, phase: 'active', activation: 'disarmed' }],
      ]),
    })

    appendWarning(session, 'fail')

    expect(disarmed).toEqual([])
  })

  it('skips a session without a live agent', async () => {
    const { session, disarmed } = await boot()

    appendWarning(session, 'fail')

    expect(disarmed).toEqual([])
  })

  it('contains a refusing goal port without losing the graded record', async () => {
    const agent = makeAgent('session-driver')
    const { session, disarmed } = await boot({
      agents: new Map([['session-driver', agent]]),
      goals: new Map([[agent, { id: 'goal-1', revision: 1, phase: 'active', activation: 'armed' }]]),
      refuse: true,
    })

    expect(() =>{  appendWarning(session, 'fail') }).not.toThrow()
    expect(disarmed).toEqual([])
    expect(session.snapshotEvents().some(event =>
      event.type === 'devframe/task-warning' && event.data.grade === 'fail')).toBe(true)
  })

  it('stops consuming after disposal', async () => {
    const agent = makeAgent('session-driver')
    const { ctx, session, disarmed } = await boot({
      agents: new Map([['session-driver', agent]]),
      goals: new Map([[agent, { id: 'goal-1', revision: 1, phase: 'active', activation: 'armed' }]]),
    })
    await ctx.fiber.dispose()
    CONTEXTS.length = 0

    appendWarning(session, 'fail')

    expect(disarmed).toEqual([])
  })
})
