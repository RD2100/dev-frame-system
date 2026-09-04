import { describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import AgentRegistry, { agentEvents, Inbox } from '@deepseek-ai/dsh-agent'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { createUserMessage, HarnessError } from '@deepseek-ai/dsh-llm'
import SessionStore, { Session, SessionId, type UserMessage } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import GoalService, {
  GoalError,
  GoalId,
  decodeGoalChange,
  foldGoal,
} from '@deepseek-ai/dsh-goal'
import type { GoalChangeMeta, GoalReceiptChangeMeta, GoalRef, GoalSnapshotChangeMeta } from '@deepseek-ai/dsh-goal'

interface StubAgent {
  agent: Agent
  session: Session
}

/** Number the next balanced test-fixture turn. */
function nextTurn(session: Session): number {
  return session.snapshotEvents().reduce((max, event) => event.type === 'turn/start' ? Math.max(max, event.data.turn) : max, 0) + 1
}

/** Mirror the public Agent.inject contract for domain tests. */
function appendInjection(session: Session, input: UserMessage): void {
  new Inbox(session, { inserted: () => {}, discarded: () => {}, claimed: () => {} }).append('next-step', input)
}

/** Build a registry-compatible agent around one concrete session. */
function stubAgentForSession(session: Session): StubAgent {
  const id = session.id
  const inbox = new Inbox(session, { inserted: () => {}, discarded: () => {}, claimed: () => {} })
  const agent: Agent = {
    id,
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
  return {
    agent,
    session,
  }
}

/** Build a registry-compatible agent around a fresh session. */
function stubAgent(rawId: string, seed?: readonly import('@deepseek-ai/dsh-session').SessionEvent[]): StubAgent {
  return stubAgentForSession(Session.create(SessionId(rawId), seed))
}

async function harness(config: { defaultMaxGoalRounds?: number } = {}) {
  const ctx = new Context()
  await ctx.plugin(SessionStore)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(GoalService, config)
  const stub = stubAgentForSession(ctx.sessions.create(SessionId(`goal-test-${Math.random()}`)))
  ctx.agents.register(stub.agent)
  return { ctx, ...stub }
}

/** Append one admitted goal round as a balanced user-message turn. */
function appendRound(session: Session, ref: GoalRef, round: number): void {
  const source = { kind: 'goal', goalId: ref.id, revision: ref.revision, round } as const
  const turn = nextTurn(session)
  session.append('turn/start', { turn })
  session.append('user/message', createUserMessage({
    content: [{ type: 'text', text: `round ${round}` }], source,
  }), { surfaceOp: 'append' })
  session.append('turn/end', { turn, reason: { kind: 'completed' } })
}

describe('GoalService creation and replay', () => {
  it('does not activate without the required projection registry', async () => {
    const ctx = new Context()
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(GoalService)
    expect(ctx.get('goals')).toBeUndefined()
  })

  it('applies the configured default and writes one durable goal change', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(1_700_000_000_000)
    const { ctx, agent, session } = await harness({ defaultMaxGoalRounds: 17 })
    const seen: string[] = []
    ctx.on('goal/changed', ({ change }) => { seen.push(change.operation) })

    const goal = ctx.goals.create(agent, { objective: '  finish the feature  ' })

    expect(goal).toMatchObject({
      objective: 'finish the feature',
      phase: 'active',
      revision: 1,
      maxGoalRounds: 17,
      roundsStarted: 0,
      createdAt: 1_700_000_000_000,
      updatedAt: 1_700_000_000_000,
      activation: 'armed',
    })
    expect(goal.id).toMatch(/^goal-/)
    expect(seen).toEqual(['create'])
    expect(session.snapshotEvents().map(event => event.type)).toEqual(['goal/change'])
    const context = session.snapshotEvents()[0]
    expect(context?.type).toBe('goal/change')
    if (context?.type !== 'goal/change') throw new Error('expected durable goal change')
    const change = decodeGoalChange(context.data)
    if (change === undefined) throw new Error('expected decoded goal change')
    expect(change).toMatchObject({ operation: 'create', goal: { id: goal.id } })
    expect(agent.inbox.nextStep).toEqual([])
    expect(session.deriveMessages()).toEqual([])
    expect(foldGoal(session.snapshotEvents())).toMatchObject({ goal: { id: goal.id }, roundsStarted: 0 })
    vi.useRealTimers()
  })

  it('uses 256 rounds by default and validates create input inside create', async () => {
    const { ctx, agent } = await harness()
    expect(() => ctx.goals.create(agent, { objective: '   ' })).toThrow(expect.objectContaining({
      code: 'GOAL_INVALID_OBJECTIVE',
    }))
    expect(() => ctx.goals.create(agent, { objective: 'x', maxGoalRounds: 0 })).toThrow(expect.objectContaining({
      code: 'GOAL_INVALID_MAX_ROUNDS',
    }))
    expect(() => ctx.goals.create(agent, { objective: 'x', maxGoalRounds: 1.5 })).toThrow(GoalError)
    expect(() => ctx.goals.create(agent, { objective: 'x', maxGoalRounds: 1.5 })).toThrow(HarnessError)
    expect(() => ctx.goals.create(agent, {
      objective: 'x', maxGoalRounds: Number.MAX_SAFE_INTEGER + 1,
    })).toThrow(GoalError)
    expect(ctx.goals.create(agent, { objective: 'x' }).maxGoalRounds).toBe(256)
  })

  it('also resolves the default when constructed directly without Cordis config normalization', async () => {
    const ctx = new Context()
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(SessionProjectionRegistry)
    const stub = stubAgent('goal-direct-construction')
    ctx.agents.register(stub.agent)
    const goals = new GoalService(ctx)
    await new Promise(resolve => setImmediate(resolve))
    expect(goals.create(stub.agent, { objective: 'direct' })).toMatchObject({
      objective: 'direct', maxGoalRounds: 256,
    })
  })

  it('rejects invalid direct configuration', async () => {
    const ctx = new Context()
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(SessionProjectionRegistry)
    await expect(ctx.plugin(GoalService, { defaultMaxGoalRounds: -1 })).rejects.toThrow(expect.objectContaining({
      code: 'GOAL_INVALID_MAX_ROUNDS',
    }))
  })

  it('restores a seeded goal and rounds with activation disarmed', async () => {
    const first = await harness()
    const created = first.ctx.goals.create(first.agent, { objective: 'seed me', maxGoalRounds: 9 })
    appendRound(first.session, created, 1)
    appendRound(first.session, created, 2)

    const ctx = new Context()
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(GoalService)
    const resumed = stubAgent('seeded-goal', first.session.snapshotEvents())
    ctx.agents.register(resumed.agent)
    expect(ctx.goals.get(resumed.agent)).toMatchObject({
      id: created.id,
      roundsStarted: 2,
      activation: 'disarmed',
    })
  })

  it('inherits the completed-turn goal prefix through SessionStore.fork with child activation disarmed', async () => {
    const ctx = new Context()
    await ctx.plugin(SessionStore)
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(GoalService)
    const parent = stubAgentForSession(ctx.sessions.create(SessionId('goal-fork-parent')))
    ctx.agents.register(parent.agent)
    const goal = ctx.goals.create(parent.agent, { objective: 'inherit through fork', maxGoalRounds: 5 })
    appendRound(parent.session, goal, 1)

    const child = stubAgentForSession(ctx.sessions.fork(parent.session))
    ctx.agents.register(child.agent)
    expect(ctx.goals.get(child.agent)).toMatchObject({
      id: goal.id,
      objective: goal.objective,
      roundsStarted: 1,
      activation: 'disarmed',
    })
    expect(child.session.header.parentSession).toBe(parent.session.id)
    expect(child.session.header.isSeeded).toBe(true)
    expect(child.session.inheritedEventCount).toBe(parent.session.seq)
  })

  it('disarms live activation on every session-start edge', async () => {
    const { ctx, agent, session } = await harness()
    let goal = ctx.goals.create(agent, { objective: 'stay stopped after resume' })
    expect(goal.activation).toBe('armed')
    agentEvents(ctx, agent).emit('agent/session-start', { source: 'resume' })
    expect(ctx.goals.get(agent)?.activation).toBe('disarmed')
    goal = ctx.goals.resume(agent, goal)
    expect(goal).toMatchObject({ phase: 'active', activation: 'armed', revision: 2 })
    expect(() => foldGoal(session.snapshotEvents())).not.toThrow()
  })

  it('lets a lifecycle owner disarm without writing a durable revision', async () => {
    const { ctx, agent, session } = await harness()
    const goal = ctx.goals.create(agent, { objective: 'survive driver reload' })
    const before = session.snapshotEvents().length
    expect(ctx.goals.disarm(agent)).toMatchObject({
      id: goal.id,
      revision: goal.revision,
      phase: 'active',
      activation: 'disarmed',
    })
    expect(session.snapshotEvents()).toHaveLength(before)
    expect(ctx.goals.resume(agent, goal)).toMatchObject({ revision: 2, activation: 'armed' })
  })

  it('removes the service and projection with the providing fiber', async () => {
    const ctx = new Context()
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(SessionProjectionRegistry)
    const fiber = await ctx.plugin(GoalService)
    const first = ctx.goals
    const stub = stubAgent('goal-hmr')
    ctx.agents.register(stub.agent)
    const goal = ctx.goals.create(stub.agent, { objective: 'survive service reload' })

    await fiber.dispose()
    expect(ctx.get('goals')).toBeUndefined()
    expect(ctx.sessionProjections.stateOf(stub.session, 'goal')).toBeUndefined()
    expect(() => first.get(stub.agent)).toThrow('goal projection is not registered')

    await ctx.plugin(GoalService)
    expect(ctx.goals).not.toBe(first)
    expect(ctx.goals.get(stub.agent)).toMatchObject({ id: goal.id, activation: 'disarmed' })
  })

  it('requires the exact live registry instance for reads and mutations', async () => {
    const { ctx, agent } = await harness()
    // A same-id agent backed by a different session object — the live-instance
    // check must reject it even though the ids match.
    const impostor = stubAgentForSession(Session.create(agent.id)).agent
    expect(() => ctx.goals.get(impostor)).toThrow(expect.objectContaining({ code: 'GOAL_AGENT_NOT_LIVE' }))
    expect(() => ctx.goals.create(impostor, { objective: 'no' })).toThrow(expect.objectContaining({
      code: 'GOAL_AGENT_NOT_LIVE',
    }))
  })

})

describe('GoalService mutations', () => {
  it('adapts Remote creation and reuses business methods for later mutations', async () => {
    const { ctx, agent } = await harness()
    const created = ctx.goals.remoteExportCreate(agent, { objective: 'remote lifecycle' })
    const edited = ctx.goals.edit(agent, created.ref, { objective: 'edited remotely' })
    const paused = ctx.goals.pause(agent, edited)
    const resumed = ctx.goals.resume(agent, paused)
    const completed = ctx.goals.complete(agent, resumed)
    const cleared = ctx.goals.clear(agent, completed)

    expect(edited).toMatchObject({ objective: 'edited remotely', revision: 2 })
    expect(paused).toMatchObject({ phase: 'paused', revision: 3 })
    expect(resumed).toMatchObject({ phase: 'active', revision: 4 })
    expect(completed).toMatchObject({ phase: 'complete', revision: 5 })
    expect(cleared).toEqual({ id: created.ref.id, revision: 6 })
  })

  it('edits with compare-and-set revisions and rejects empty edits', async () => {
    const { ctx, agent } = await harness()
    const created = ctx.goals.create(agent, { objective: 'old', maxGoalRounds: 4 })
    expect(() => ctx.goals.edit(agent, created, {})).toThrow(expect.objectContaining({ code: 'GOAL_INVALID_EDIT' }))
    const objective = ctx.goals.edit(agent, created, { objective: ' new ' })
    expect(objective).toMatchObject({ objective: 'new', maxGoalRounds: 4, revision: 2, activation: 'armed' })
    expect(() => ctx.goals.edit(agent, created, { maxGoalRounds: 8 })).toThrow(expect.objectContaining({
      code: 'GOAL_STALE_REVISION',
    }))
    const cap = ctx.goals.edit(agent, objective, { maxGoalRounds: 8 })
    expect(cap).toMatchObject({ objective: 'new', maxGoalRounds: 8, revision: 3 })
    expect(() => ctx.goals.edit(agent, cap, { objective: ' ' })).toThrow(expect.objectContaining({
      code: 'GOAL_INVALID_OBJECTIVE',
    }))
  })

  it('supports pause, resume, block, and completion transitions', async () => {
    const { ctx, agent } = await harness()
    let goal = ctx.goals.create(agent, { objective: 'lifecycle' })
    goal = ctx.goals.pause(agent, goal)
    expect(goal).toMatchObject({ phase: 'paused', activation: 'disarmed', revision: 2 })
    goal = ctx.goals.resume(agent, goal)
    expect(goal).toMatchObject({ phase: 'active', activation: 'armed', revision: 3 })
    goal = ctx.goals.block(agent, goal, { code: 'needs-input', message: 'A choice is required.' })
    expect(goal).toMatchObject({
      phase: 'blocked',
      blockedReason: { code: 'needs-input', message: 'A choice is required.' },
      activation: 'disarmed',
    })
    goal = ctx.goals.resume(agent, goal)
    goal = ctx.goals.pause(agent, goal)
    goal = ctx.goals.complete(agent, goal)
    expect(goal).toMatchObject({ phase: 'complete', activation: 'disarmed' })
    expect(() => ctx.goals.resume(agent, goal)).toThrow(expect.objectContaining({ code: 'GOAL_INVALID_TRANSITION' }))
  })

  it('allows completion from every stopped phase and replacement only after completion', async () => {
    const phases = ['paused', 'blocked'] as const
    for (const phase of phases) {
      const { ctx, agent } = await harness()
      let goal = ctx.goals.create(agent, { objective: phase })
      goal = phase === 'paused'
        ? ctx.goals.pause(agent, goal)
        : ctx.goals.block(agent, goal, { code: 'test-blocker', message: 'Blocked for the test.' })
      const complete = ctx.goals.complete(agent, goal)
      const replacement = ctx.goals.create(agent, { objective: `after ${phase}` })
      expect(complete.phase).toBe('complete')
      expect(replacement.id).not.toBe(complete.id)
      expect(replacement.revision).toBe(1)
    }
  })

  it('rejects replacement and invalid phase transitions while a resumable goal exists', async () => {
    const { ctx, agent } = await harness()
    const goal = ctx.goals.create(agent, { objective: 'still active' })
    expect(() => ctx.goals.create(agent, { objective: 'replacement' })).toThrow(expect.objectContaining({
      code: 'GOAL_ALREADY_EXISTS',
    }))
    expect(() => ctx.goals.resume(agent, goal)).toThrow(expect.objectContaining({ code: 'GOAL_INVALID_TRANSITION' }))
    const paused = ctx.goals.pause(agent, goal)
    expect(() => ctx.goals.pause(agent, paused)).toThrow(expect.objectContaining({ code: 'GOAL_INVALID_TRANSITION' }))
    expect(() => ctx.goals.block(agent, paused, {
      code: 'test-blocker', message: 'Blocked for the test.',
    })).toThrow(expect.objectContaining({
      code: 'GOAL_INVALID_TRANSITION',
    }))
  })

  it('records canonical blocker reasons and enforces the round cap on resume', async () => {
    const { ctx, agent, session } = await harness()
    let goal = ctx.goals.create(agent, { objective: 'bounded', maxGoalRounds: 2 })
    for (const reason of [null, [], { code: 1, message: 'invalid code' }, { code: 'round-limit', message: 1 }]) {
      expect(() => ctx.goals.block(agent, goal, reason as never)).toThrow(expect.objectContaining({
        code: 'GOAL_INVALID_BLOCK_REASON',
      }))
    }
    expect(() => ctx.goals.block(agent, goal, {
      code: 'Not Canonical', message: 'invalid code',
    })).toThrow(expect.objectContaining({ code: 'GOAL_INVALID_BLOCK_REASON' }))
    expect(() => ctx.goals.block(agent, goal, {
      code: 'round-limit', message: '   ',
    })).toThrow(expect.objectContaining({ code: 'GOAL_INVALID_BLOCK_REASON' }))
    appendRound(session, goal, 1)
    expect(ctx.goals.get(agent)?.roundsStarted).toBe(1)
    appendRound(session, goal, 2)
    goal = ctx.goals.block(agent, goal, { code: 'round-limit', message: '  Goal round limit reached.  ' })
    expect(goal).toMatchObject({
      phase: 'blocked',
      blockedReason: { code: 'round-limit', message: 'Goal round limit reached.' },
      roundsStarted: 2,
      activation: 'disarmed',
    })
    expect(() => ctx.goals.resume(agent, goal)).toThrow(expect.objectContaining({ code: 'GOAL_INVALID_TRANSITION' }))
    goal = ctx.goals.edit(agent, goal, { maxGoalRounds: 3 })
    expect(goal.blockedReason).toEqual({ code: 'round-limit', message: 'Goal round limit reached.' })
    goal = ctx.goals.resume(agent, goal)
    expect(goal).toMatchObject({ phase: 'active', maxGoalRounds: 3, activation: 'armed' })
    expect(goal.blockedReason).toBeUndefined()
    appendRound(session, goal, 3)
    goal = ctx.goals.block(agent, goal, { code: 'round-limit', message: 'Goal round limit reached.' })
    expect(ctx.goals.complete(agent, goal).phase).toBe('complete')
  })

  it('clears through a revisioned tombstone and permits a fresh goal', async () => {
    const { ctx, agent, session } = await harness()
    const goal = ctx.goals.create(agent, { objective: 'temporary' })
    const tombstone = ctx.goals.clear(agent, goal)
    expect(tombstone).toEqual({ id: goal.id, revision: 2 })
    expect(ctx.goals.get(agent)).toBeUndefined()
    expect(foldGoal(session.snapshotEvents())).toEqual({ roundsStarted: 0, lastRef: tombstone })
    expect(() => ctx.goals.clear(agent, goal)).toThrow(expect.objectContaining({ code: 'GOAL_NOT_FOUND' }))
    const next = ctx.goals.create(agent, { objective: 'fresh' })
    expect(next.id).not.toBe(goal.id)
  })

  it('keeps per-goal mutation timestamps monotonic when the wall clock moves backward', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(100)
    const { ctx, agent, session } = await harness()
    let goal = ctx.goals.create(agent, { objective: 'monotonic time' })
    vi.setSystemTime(90)
    goal = ctx.goals.pause(agent, goal)
    expect(goal.updatedAt).toBe(100)
    vi.setSystemTime(80)
    ctx.goals.clear(agent, goal)
    const clear = session.snapshotEvents()
      .filter(event => event.type === 'goal/change')
      .map(event => event.type === 'goal/change' ? decodeGoalChange(event.data) : undefined)
      .at(-1)
    expect(clear).toMatchObject({ operation: 'clear', clearedAt: 100 })
    expect(() => foldGoal(session.snapshotEvents())).not.toThrow()
    vi.useRealTimers()
  })

  it('contains goal notification failures and preserves later listeners', async () => {
    const { ctx, agent } = await harness()
    const warn = vi.spyOn(ctx.logger, 'warn').mockImplementation(() => {})
    const seen: string[] = []
    ctx.on('goal/changed', () => { throw new Error('broken observer') })
    ctx.on('goal/changed', ({ change }) => { seen.push(change.operation) })
    expect(ctx.goals.create(agent, { objective: 'notify' }).phase).toBe('active')
    expect(seen).toEqual(['create'])
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('broken observer'))
  })

  it('commits consecutive revisions through durable goal events', async () => {
    const { ctx, agent, session } = await harness()
    let goal = ctx.goals.create(agent, { objective: 'deferred', maxGoalRounds: 5 })
    goal = ctx.goals.edit(agent, goal, { objective: 'deferred edit' })
    goal = ctx.goals.pause(agent, goal)
    expect(goal).toMatchObject({ revision: 3, phase: 'paused', activation: 'disarmed' })
    expect(session.snapshotEvents().map(event => event.type)).toEqual([
      'goal/change', 'goal/change', 'goal/change',
    ])
    expect(ctx.goals.get(agent)).toMatchObject({ revision: 3, phase: 'paused' })
    expect(foldGoal(session.snapshotEvents())).toMatchObject({ goal: { revision: 3, phase: 'paused' } })
  })

  it('publishes a mutation consistently to a reentrant session observer', async () => {
    const ctx = new Context()
    await ctx.plugin(SessionStore)
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(GoalService)
    const stub = stubAgentForSession(ctx.sessions.create(SessionId('goal-reentrant-observer')))
    ctx.agents.register(stub.agent)
    let observed: ReturnType<GoalService['get']>
    ctx.on('session/event', (session, event) => {
      if (session === stub.session && event.type === 'goal/change') observed = ctx.goals.get(stub.agent)
    })

    const created = ctx.goals.create(stub.agent, { objective: 'publish once' })

    expect(observed).toEqual(created)
    expect(ctx.goals.get(stub.agent)).toEqual(created)
    expect(foldGoal(stub.session.snapshotEvents())).toMatchObject({ goal: { id: created.id, revision: 1 } })
  })

  it('does not delegate goal persistence to agent injection', async () => {
    const ctx = new Context()
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(GoalService)
    const stub = stubAgent('goal-independent-injection')
    stub.agent.inject = () => { throw new Error('injection must not be called') }
    ctx.agents.register(stub.agent)

    expect(ctx.goals.create(stub.agent, { objective: 'persist directly' })).toMatchObject({
      objective: 'persist directly',
      revision: 1,
    })
    expect(stub.agent.inbox.nextStep).toEqual([])
    expect(stub.session.snapshotEvents().map(event => event.type)).toEqual(['goal/change'])
  })

  it('observes an external goal change and disarms local activation', async () => {
    const { ctx, agent, session } = await harness()
    const created = ctx.goals.create(agent, { objective: 'before external edit', maxGoalRounds: 4 })
    expect(created.activation).toBe('armed')
    const change: GoalSnapshotChangeMeta = {
      kind: 'goal/change',
      version: 1,
      operation: 'edit',
      goal: {
        id: created.id,
        revision: created.revision + 1,
        objective: 'observe external append',
        phase: 'active',
        maxGoalRounds: 4,
      },
      roundsStarted: created.roundsStarted,
      createdAt: created.createdAt,
      updatedAt: created.updatedAt,
    }
    session.append('goal/change', change)

    expect(ctx.goals.get(agent)).toMatchObject({
      id: change.goal.id,
      objective: change.goal.objective,
      activation: 'disarmed',
    })
  })

})

describe('GoalService completion receipts', () => {
  const EVIDENCE = [
    {
      kind: 'test-run',
      summary: 'vitest packages/goal: all green',
      at: 1_700_000_000_500,
      ref: 'packages/goal/goal/tests/goal.spec.ts',
    },
    { kind: 'typecheck', summary: 'tsc -b tsconfig.host.json: clean', at: 1_700_000_000_600 },
  ]

  /** A session whose goal is complete at revision 2. */
  async function completedHarness() {
    const bench = await harness()
    const created = bench.ctx.goals.create(bench.agent, { objective: 'receipt me', maxGoalRounds: 4 })
    const completed = bench.ctx.goals.complete(bench.agent, created)
    return { ...bench, created, completed }
  }

  it('commits a receipt event, keeps the revision, and notifies with operation receipt', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(1_700_000_000_000)
    try {
      const { ctx, agent, session, completed } = await completedHarness()
      // completedHarness() already committed create and complete; this listener
      // observes only the receipt notification.
      const seen: string[] = []
      ctx.on('goal/changed', ({ change }) => { seen.push(change.operation) })

      const receipt = ctx.goals.recordReceipt(agent, completed, EVIDENCE)

      expect(receipt).toMatchObject({
        ref: { id: completed.id, revision: completed.revision },
        recordedAt: 1_700_000_000_000,
      })
      expect(receipt.evidence).toEqual(EVIDENCE)
      expect(seen).toEqual(['receipt'])
      const changes = session.snapshotEvents().filter(event => event.type === 'goal/change')
      expect(changes).toHaveLength(3)
      const change = decodeGoalChange(changes[2]!.data)
      if (change === undefined || change.operation !== 'receipt') throw new Error('expected a receipt change')
      expect(change.ref).toEqual({ id: completed.id, revision: 2 })
      expect(change.evidence).toEqual(EVIDENCE)
      expect(ctx.goals.get(agent)).toMatchObject({
        phase: 'complete',
        revision: completed.revision,
        activation: 'disarmed',
      })
      expect(foldGoal(session.snapshotEvents())).toMatchObject({
        goal: { id: completed.id, revision: 2, phase: 'complete' },
        roundsStarted: 0,
      })
    } finally {
      vi.useRealTimers()
    }
  })

  it('enforces compare-and-set refs and the complete phase before recording', async () => {
    const { ctx, agent, created, completed } = await completedHarness()
    expect(() => ctx.goals.recordReceipt(agent, created, EVIDENCE)).toThrow(expect.objectContaining({
      code: 'GOAL_STALE_REVISION',
    }))
    expect(() => ctx.goals.recordReceipt(agent, {
      id: GoalId('goal-other'), revision: completed.revision,
    }, EVIDENCE)).toThrow(expect.objectContaining({ code: 'GOAL_STALE_REVISION' }))

    const fresh = await harness()
    const active = fresh.ctx.goals.create(fresh.agent, { objective: 'still active' })
    expect(() => fresh.ctx.goals.recordReceipt(fresh.agent, active, EVIDENCE)).toThrow(expect.objectContaining({
      code: 'GOAL_INVALID_TRANSITION',
    }))
    const paused = fresh.ctx.goals.pause(fresh.agent, active)
    expect(() => fresh.ctx.goals.recordReceipt(fresh.agent, paused, EVIDENCE)).toThrow(expect.objectContaining({
      code: 'GOAL_INVALID_TRANSITION',
    }))

    const cleared = await completedHarness()
    cleared.ctx.goals.clear(cleared.agent, cleared.completed)
    expect(() => cleared.ctx.goals.recordReceipt(cleared.agent, cleared.completed, EVIDENCE)).toThrow(
      expect.objectContaining({ code: 'GOAL_NOT_FOUND' }),
    )
  })

  it('validates evidence entries, normalizes summaries and refs, and appends only valid receipts', async () => {
    const { ctx, agent, session, completed } = await completedHarness()
    expect(() => ctx.goals.recordReceipt(agent, completed, [])).toThrow(expect.objectContaining({
      code: 'GOAL_INVALID_EVIDENCE',
    }))
    const invalid: unknown[] = [
      null,
      [],
      { kind: 'Test-Run', summary: 'ok', at: 1 },
      { kind: 'test run', summary: 'ok', at: 1 },
      { kind: 'test-run', summary: '   ', at: 1 },
      { kind: 'test-run', summary: 'ok', at: -1 },
      { kind: 'test-run', summary: 'ok', at: 1.5 },
      { kind: 'test-run', summary: 'ok', at: 1, ref: '   ' },
    ]
    for (const entry of invalid) {
      expect(() => ctx.goals.recordReceipt(agent, completed, [entry as never])).toThrow(expect.objectContaining({
        code: 'GOAL_INVALID_EVIDENCE',
      }))
    }
    expect(session.snapshotEvents().filter(event => event.type === 'goal/change')).toHaveLength(2)

    const receipt = ctx.goals.recordReceipt(agent, completed, [{
      kind: 'log', summary: '  padded summary  ', at: 3, ref: '  logs/run.txt  ',
    }])
    expect(receipt.evidence).toEqual([{ kind: 'log', summary: 'padded summary', at: 3, ref: 'logs/run.txt' }])
    expect(session.snapshotEvents().filter(event => event.type === 'goal/change')).toHaveLength(3)
  })

  it('allows repeated receipts for one revision and replays them without state change', async () => {
    const { ctx, agent, session, completed } = await completedHarness()
    ctx.goals.recordReceipt(agent, completed, [{ kind: 'test-run', summary: 'first', at: 10 }])
    ctx.goals.recordReceipt(agent, completed, [{ kind: 'log', summary: 'second', at: 11, ref: 'logs/a.txt' }])
    expect(session.snapshotEvents().filter(event => event.type === 'goal/change')).toHaveLength(4)
    expect(() => foldGoal(session.snapshotEvents())).not.toThrow()
    expect(foldGoal(session.snapshotEvents())).toMatchObject({
      goal: { id: completed.id, revision: 2, phase: 'complete' },
      roundsStarted: 0,
      lastRef: { id: completed.id, revision: 2 },
    })
  })

  it('keeps receipts compatible with goal replacement after completion', async () => {
    const { ctx, agent, session, completed } = await completedHarness()
    ctx.goals.recordReceipt(agent, completed, [{ kind: 'test-run', summary: 'verified', at: 5 }])
    const replacement = ctx.goals.create(agent, { objective: 'next objective' })
    expect(replacement.revision).toBe(1)
    expect(() => foldGoal(session.snapshotEvents())).not.toThrow()
    expect(foldGoal(session.snapshotEvents())).toMatchObject({ goal: { id: replacement.id, revision: 1 } })
    expect(() => ctx.goals.recordReceipt(agent, completed, EVIDENCE)).toThrow(expect.objectContaining({
      code: 'GOAL_STALE_REVISION',
    }))
  })

})

describe('goal replay validation', () => {
  function snapshotChange(overrides: Partial<GoalSnapshotChangeMeta> = {}): GoalSnapshotChangeMeta {
    return {
      kind: 'goal/change',
      version: 1,
      operation: 'create',
      goal: {
        id: GoalId('goal-validation'),
        revision: 1,
        objective: 'validate',
        phase: 'active',
        maxGoalRounds: 2,
      },
      roundsStarted: 0,
      createdAt: 10,
      updatedAt: 10,
      ...overrides,
    }
  }

  function appendChange(session: Session, change: GoalChangeMeta): void {
    session.append('goal/change', change)
  }

  function oneChange(change: GoalChangeMeta) {
    const session = Session.create(SessionId(`validation-${Math.random()}`))
    appendChange(session, change)
    return session.snapshotEvents()
  }

  function mutation(
    current: GoalSnapshotChangeMeta,
    operation: Exclude<GoalSnapshotChangeMeta['operation'], 'create'>,
    phase: GoalSnapshotChangeMeta['goal']['phase'],
    overrides: Partial<GoalSnapshotChangeMeta> = {},
  ): GoalSnapshotChangeMeta {
    return {
      ...current,
      operation,
      goal: {
        id: current.goal.id,
        revision: current.goal.revision + 1,
        objective: current.goal.objective,
        phase,
        ...phase === 'blocked'
          ? { blockedReason: { code: 'test-blocker', message: 'Blocked for replay validation.' } }
          : {},
        maxGoalRounds: current.goal.maxGoalRounds,
      },
      updatedAt: current.updatedAt + 1,
      ...overrides,
    }
  }

  function receiptChange(
    current: GoalSnapshotChangeMeta,
    overrides: Partial<GoalReceiptChangeMeta> = {},
  ): GoalReceiptChangeMeta {
    return {
      kind: 'goal/change',
      version: 1,
      operation: 'receipt',
      ref: { id: current.goal.id, revision: current.goal.revision },
      evidence: [{ kind: 'test-run', summary: 'all green', at: current.updatedAt + 1 }],
      recordedAt: current.updatedAt + 1,
      ...overrides,
    }
  }

  it('keeps durable goal state independent from inbox changes', () => {
    const change = snapshotChange()
    const session = Session.create(SessionId('inbox-independent-change'))
    appendChange(session, change)
    expect(foldGoal(session.snapshotEvents())).toMatchObject({ goal: { id: change.goal.id, revision: 1 } })
    const message = createUserMessage({
      content: [{ type: 'text', text: 'unrelated pending context' }],
      source: { kind: 'plugin', plugin: 'test' },
    })
    const inbox = new Inbox(session, { inserted: () => {}, discarded: () => {}, claimed: () => {} })
    inbox.append('next-step', message)
    expect(inbox.remove(message.id)).toBe(true)
    expect(foldGoal(session.snapshotEvents())).toMatchObject({ goal: { id: change.goal.id, revision: 1 } })
  })

  function foldPair(first: GoalSnapshotChangeMeta, second: GoalChangeMeta): ReturnType<typeof foldGoal> {
    const session = Session.create(SessionId(`validation-pair-${Math.random()}`))
    appendChange(session, first)
    appendChange(session, second)
    return foldGoal(session.snapshotEvents())
  }

  function changeSequence(...changes: GoalChangeMeta[]): ReturnType<typeof foldGoal> {
    const session = Session.create(SessionId(`validation-seq-${Math.random()}`))
    for (const change of changes) appendChange(session, change)
    return foldGoal(session.snapshotEvents())
  }

  it('ignores unrelated metadata and non-goal round sources', () => {
    expect(decodeGoalChange(undefined)).toBeUndefined()
    expect(decodeGoalChange({ kind: 'other' })).toBeUndefined()
    const session = Session.create(SessionId('unrelated'))
    appendInjection(session, createUserMessage({
      content: [{ type: 'text', text: 'other' }],
      source: { kind: 'plugin', plugin: 'test' },
    }))
    expect(foldGoal(session.snapshotEvents())).toEqual({ roundsStarted: 0 })
    const source = { kind: 'plugin', plugin: 'ordinary-user-message' } as const
    const turn = nextTurn(session)
    session.append('turn/start', { turn })
    session.append('user/message', createUserMessage({
      content: [{ type: 'text', text: 'ordinary' }], source,
    }), { surfaceOp: 'append' })
    session.append('turn/end', { turn, reason: { kind: 'completed' } })
    expect(foldGoal(session.snapshotEvents())).toEqual({ roundsStarted: 0 })
  })

  it('rejects rounds attributed to another goal', () => {
    const change = snapshotChange()
    const session = Session.create(SessionId('other-goal-round'), oneChange(change))
    appendRound(session, { id: GoalId('goal-other'), revision: 1 }, 1)
    expect(() => foldGoal(session.snapshotEvents())).toThrow('not the next admitted round')
  })

  it('rejects unsupported versions, operations, and extra top-level fields', () => {
    expect(() => decodeGoalChange({ ...snapshotChange(), version: 2 })).toThrow('unsupported goal change version')
    expect(() => decodeGoalChange({ ...snapshotChange(), operation: 'explode' })).toThrow('operation is invalid')
    expect(() => decodeGoalChange({ ...snapshotChange(), extra: true })).toThrow('snapshot change must have exactly')
    expect(() => decodeGoalChange({
      kind: 'goal/change', version: 1, operation: 'clear', cleared: { id: 'x', revision: 2 }, clearedAt: 1, extra: true,
    })).toThrow('clear change must have exactly')
  })

  it('rejects invalid create and missing-current mutation sequences', () => {
    const base = snapshotChange()
    const invalidCreates: GoalSnapshotChangeMeta[] = [
      { ...base, goal: { ...base.goal, revision: 2 } },
      { ...base, goal: { ...base.goal, phase: 'paused' } },
      { ...base, roundsStarted: 1 },
    ]
    for (const change of invalidCreates) expect(() => foldGoal(oneChange(change))).toThrow('goal create requires')

    const edit = mutation(base, 'edit', 'active')
    expect(() => foldGoal(oneChange(edit))).toThrow('requires a current goal')
    const clear: GoalChangeMeta = {
      kind: 'goal/change', version: 1, operation: 'clear', cleared: { id: base.goal.id, revision: 2 }, clearedAt: 12,
    }
    expect(() => foldGoal(oneChange(clear))).toThrow('clear requires a current goal')

    const secondCreate = snapshotChange({
      goal: { ...base.goal, id: GoalId('goal-second') },
      createdAt: 20,
      updatedAt: 20,
    })
    expect(() => foldPair(base, secondCreate)).toThrow('goal create requires')
  })

  it('rejects stale identity, counters, timestamps, and definition changes', () => {
    const base = snapshotChange()
    const invalid: GoalSnapshotChangeMeta[] = [
      mutation(base, 'edit', 'active', { goal: { ...base.goal, id: GoalId('goal-wrong'), revision: 2 } }),
      mutation(base, 'edit', 'active', { goal: { ...base.goal, revision: 3 } }),
      mutation(base, 'edit', 'active', { createdAt: 11 }),
      mutation(base, 'edit', 'active', { updatedAt: 9 }),
      mutation(base, 'edit', 'active', { roundsStarted: 1 }),
      mutation(base, 'pause', 'paused', {
        goal: { ...base.goal, revision: 2, phase: 'paused', objective: 'changed illegally' },
      }),
      mutation(base, 'pause', 'paused', {
        goal: { ...base.goal, revision: 2, phase: 'paused', maxGoalRounds: 3 },
      }),
    ]
    for (const change of invalid) expect(() => foldPair(base, change)).toThrow()
  })

  it('rejects invalid replayed lifecycle phase transitions', () => {
    const base = snapshotChange()
    const invalid: GoalSnapshotChangeMeta[] = [
      mutation(base, 'edit', 'paused'),
      mutation(base, 'pause', 'active'),
      mutation(base, 'resume', 'paused'),
      mutation(base, 'complete', 'active'),
      mutation(base, 'block', 'active'),
    ]
    for (const change of invalid) expect(() => foldPair(base, change)).toThrow()

    const paused = mutation(base, 'pause', 'paused')
    const exhausted = mutation(paused, 'resume', 'active', {
      roundsStarted: 2,
      goal: { ...paused.goal, revision: 3, phase: 'active', maxGoalRounds: 2 },
    })
    const session = Session.create(SessionId('exhausted-resume'))
    appendChange(session, base)
    appendRound(session, base.goal, 1)
    appendRound(session, base.goal, 2)
    appendChange(session, { ...paused, roundsStarted: 2 })
    appendChange(session, exhausted)
    expect(() => foldGoal(session.snapshotEvents())).toThrow('exhausted round budget')
  })

  it('rejects invalid clear continuity and goal id reuse', () => {
    const base = snapshotChange()
    const staleClear: GoalChangeMeta = {
      kind: 'goal/change', version: 1, operation: 'clear', cleared: { id: base.goal.id, revision: 3 }, clearedAt: 11,
    }
    expect(() => foldPair(base, staleClear)).toThrow('advance the current goal')
    const earlyClear: GoalChangeMeta = {
      kind: 'goal/change', version: 1, operation: 'clear', cleared: { id: base.goal.id, revision: 2 }, clearedAt: 9,
    }
    expect(() => foldPair(base, earlyClear)).toThrow('timestamp cannot precede')

    const complete = mutation(base, 'complete', 'complete')
    const sameCurrentId = snapshotChange({
      goal: { ...base.goal, revision: 1 },
      createdAt: 20,
      updatedAt: 20,
    })
    const completedSession = Session.create(SessionId('reuse-complete'))
    appendChange(completedSession, base)
    appendChange(completedSession, complete)
    appendChange(completedSession, sameCurrentId)
    expect(() => foldGoal(completedSession.snapshotEvents())).toThrow('fresh active revision-one')

    const second = snapshotChange({
      goal: { ...base.goal, id: GoalId('goal-second') },
      createdAt: 20,
      updatedAt: 20,
    })
    const secondComplete = mutation(second, 'complete', 'complete')
    const nonAdjacentReuse = Session.create(SessionId('reuse-non-adjacent'))
    appendChange(nonAdjacentReuse, base)
    appendChange(nonAdjacentReuse, complete)
    appendChange(nonAdjacentReuse, second)
    appendChange(nonAdjacentReuse, secondComplete)
    appendChange(nonAdjacentReuse, { ...sameCurrentId, createdAt: 30, updatedAt: 30 })
    expect(() => foldGoal(nonAdjacentReuse.snapshotEvents())).toThrow('fresh active revision-one')

    const clear: GoalChangeMeta = {
      kind: 'goal/change', version: 1, operation: 'clear', cleared: { id: base.goal.id, revision: 2 }, clearedAt: 11,
    }
    const clearedSession = Session.create(SessionId('reuse-clear'))
    appendChange(clearedSession, base)
    appendChange(clearedSession, clear)
    appendChange(clearedSession, sameCurrentId)
    expect(() => foldGoal(clearedSession.snapshotEvents())).toThrow('fresh active revision-one')
  })

  it('rejects non-positive goal round sources', () => {
    const session = Session.create(SessionId('goal-source-without-meta'))
    const source = { kind: 'goal', goalId: GoalId('goal-missing-meta'), revision: 1, round: 0 } as const
    const turn = nextTurn(session)
    session.append('turn/start', { turn })
    session.append('user/message', createUserMessage({
      content: [{ type: 'text', text: 'missing' }], source,
    }), { surfaceOp: 'append' })
    session.append('turn/end', { turn, reason: { kind: 'completed' } })
    expect(() => foldGoal(session.snapshotEvents())).toThrow('goal message source is invalid')
  })

  it('rejects malformed snapshots, refs, counters, and timestamps', () => {
    const base = snapshotChange()
    const badSnapshots: unknown[] = [
      null,
      { ...base.goal, extra: true },
      { ...base.goal, id: '' },
      { ...base.goal, objective: ' ' },
      { ...base.goal, objective: ' padded ' },
      { ...base.goal, phase: 'unknown' },
      { ...base.goal, blockedReason: { code: 'unexpected', message: 'Only blocked goals have reasons.' } },
      { ...base.goal, phase: 'blocked' },
      { ...base.goal, phase: 'blocked', blockedReason: null },
      { ...base.goal, phase: 'blocked', blockedReason: { code: 'test-blocker', message: 'Valid.', extra: true } },
      { ...base.goal, phase: 'blocked', blockedReason: { code: 'NOT_CANONICAL', message: 'Bad code.' } },
      { ...base.goal, phase: 'blocked', blockedReason: { code: 'test-blocker', message: ' padded ' } },
      { ...base.goal, revision: 0 },
      { ...base.goal, maxGoalRounds: -1 },
    ]
    for (const goal of badSnapshots) expect(() => decodeGoalChange({ ...base, goal })).toThrow()
    expect(() => decodeGoalChange({ ...base, roundsStarted: -1 })).toThrow('roundsStarted')
    expect(() => decodeGoalChange({ ...base, createdAt: -1 })).toThrow('createdAt')
    expect(() => decodeGoalChange({ ...base, updatedAt: 9 })).toThrow('cannot precede')
    expect(() => decodeGoalChange({
      kind: 'goal/change', version: 1, operation: 'clear', cleared: null, clearedAt: 1,
    })).toThrow('tombstone')
    expect(() => decodeGoalChange({
      kind: 'goal/change', version: 1, operation: 'clear', cleared: { id: '', revision: 1 }, clearedAt: 1,
    })).toThrow('non-empty')
    expect(() => decodeGoalChange({
      kind: 'goal/change', version: 1, operation: 'clear', cleared: { id: 'x', revision: 0 }, clearedAt: 1,
    })).toThrow('positive safe integer')
  })

  it('folds a clear tombstone after a snapshot', () => {
    const change = snapshotChange()
    const session = Session.create(SessionId('fold-clear'), oneChange(change))
    const clear: GoalChangeMeta = {
      kind: 'goal/change',
      version: 1,
      operation: 'clear',
      cleared: { id: change.goal.id, revision: 2 },
      clearedAt: 20,
    }
    appendChange(session, clear)
    expect(foldGoal(session.snapshotEvents())).toEqual({
      roundsStarted: 0,
      lastRef: { id: change.goal.id, revision: 2 },
    })
  })

  it('folds a receipt after a complete snapshot without changing fold state', () => {
    const base = snapshotChange()
    const complete = mutation(base, 'complete', 'complete')
    const receipt = receiptChange(complete)
    expect(changeSequence(base, complete, receipt)).toEqual(changeSequence(base, complete))
    const second = receiptChange(complete, {
      evidence: [{ kind: 'log', summary: 'second receipt', at: complete.updatedAt + 2, ref: 'logs/b.txt' }],
      recordedAt: complete.updatedAt + 2,
    })
    expect(changeSequence(base, complete, second)).toEqual(changeSequence(base, complete))
    expect(changeSequence(base, complete)).toEqual({
      goal: complete.goal,
      roundsStarted: 0,
      createdAt: complete.createdAt,
      updatedAt: complete.updatedAt,
      lastRef: { id: complete.goal.id, revision: 2 },
    })
  })

  it('rejects malformed receipt payloads', () => {
    const base = snapshotChange()
    const receipt = receiptChange(base)
    expect(() => decodeGoalChange({ ...receipt, extra: true })).toThrow('receipt change must have exactly')
    expect(() => decodeGoalChange({ ...receipt, evidence: [] })).toThrow('evidence must be a non-empty array')
    expect(() => decodeGoalChange({ ...receipt, evidence: 'all green' })).toThrow('non-empty array')
    expect(() => decodeGoalChange({
      ...receipt, evidence: [{ kind: 'test-run', summary: 'all green', at: 11, extra: true }],
    })).toThrow('exactly kind, summary, at, and optional ref fields')
    expect(() => decodeGoalChange({
      ...receipt, evidence: [{ kind: 'Test-Run', summary: 'all green', at: 11 }],
    })).toThrow('kind must be lower-kebab-case')
    expect(() => decodeGoalChange({
      ...receipt, evidence: [{ kind: 'test-run', summary: ' padded ', at: 11 }],
    })).toThrow('summary must be non-empty and normalized')
    expect(() => decodeGoalChange({
      ...receipt, evidence: [{ kind: 'test-run', summary: 'all green', at: -1 }],
    })).toThrow('evidence at')
    expect(() => decodeGoalChange({
      ...receipt, evidence: [{ kind: 'test-run', summary: 'all green', at: 11, ref: ' padded ' }],
    })).toThrow('ref must be a non-empty normalized string')
    expect(() => decodeGoalChange({ ...receipt, ref: null })).toThrow('receipt ref must have exactly')
    expect(() => decodeGoalChange({ ...receipt, ref: { id: base.goal.id, revision: 0 } })).toThrow(
      'positive safe integer',
    )
    expect(() => decodeGoalChange({ ...receipt, recordedAt: -1 })).toThrow('recordedAt')
  })

  it('rejects receipts without a current complete goal at the exact revision', () => {
    const base = snapshotChange()
    const receipt = receiptChange(base)
    expect(() => foldGoal(oneChange(receipt))).toThrow('goal receipt requires a current goal')

    const otherGoal = receiptChange(base, { ref: { id: GoalId('goal-other'), revision: 1 } })
    expect(() => foldPair(base, otherGoal)).toThrow('must reference the current revision')

    const staleRevision = receiptChange(base, { ref: { id: base.goal.id, revision: 2 } })
    expect(() => foldPair(base, staleRevision)).toThrow('must reference the current revision')

    const activeGoal = receiptChange(base)
    expect(() => foldPair(base, activeGoal)).toThrow('requires a complete goal')

    const complete = mutation(base, 'complete', 'complete')
    const early = receiptChange(complete, { recordedAt: complete.updatedAt - 1, evidence: [{
      kind: 'test-run', summary: 'all green', at: complete.updatedAt - 1,
    }] })
    expect(() => changeSequence(base, complete, early)).toThrow('timestamp cannot precede the current goal update')

    const clear: GoalChangeMeta = {
      kind: 'goal/change', version: 1, operation: 'clear', cleared: { id: base.goal.id, revision: 3 }, clearedAt: 12,
    }
    const completeThenClear = Session.create(SessionId('receipt-after-clear'))
    appendChange(completeThenClear, base)
    appendChange(completeThenClear, complete)
    appendChange(completeThenClear, clear)
    appendChange(completeThenClear, receiptChange(complete))
    expect(() => foldGoal(completeThenClear.snapshotEvents())).toThrow('goal receipt requires a current goal')
  })
})
