import { describe, expect, it } from 'vitest'
import type { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { SessionId } from '@deepseek-ai/dsh-session'
import {
  installRolePolicy,
  type DevFrameRole,
} from '../src/permissions/index.ts'

interface FakeExecution {
  readonly agent?: Agent
  readonly name: string
}

interface FakeContextParts {
  readonly context: Context
  readonly agents: Map<SessionId, Agent>
  readonly guards: Array<(execution: Readonly<FakeExecution>) => string | undefined>
  readonly restrictions: Array<{ readonly allow?: readonly string[]; readonly deny?: readonly string[] }>
  readonly releasedRestrictions: number[]
  readonly effectCleanups: Array<() => void>
  readonly disposedListeners: Array<(payload: { agent: Agent }) => void>
}

function fakeContext(): FakeContextParts {
  const agents = new Map<SessionId, Agent>()
  const guards: FakeContextParts['guards'] = []
  const restrictions: FakeContextParts['restrictions'] = []
  const releasedRestrictions: number[] = []
  const effectCleanups: Array<() => void> = []
  const disposedListeners: Array<(payload: { agent: Agent }) => void> = []
  const tools = {
    restrict(filter: { readonly allow?: readonly string[]; readonly deny?: readonly string[] }): () => void {
      restrictions.push(filter)
      const index = restrictions.length - 1
      return () => { releasedRestrictions.push(index) }
    },
    guard(check: (execution: Readonly<FakeExecution>) => string | undefined): () => void {
      guards.push(check)
      return () => { guards.splice(guards.indexOf(check), 1) }
    },
  }
  const context = {
    get(name: string): unknown {
      if (name === 'tools') return tools
      if (name === 'agents') return { get: (id: SessionId) => agents.get(id) }
      return undefined
    },
    on(_event: string, listener: (payload: { agent: Agent }) => void): () => void {
      disposedListeners.push(listener)
      return () => {
        const index = disposedListeners.indexOf(listener)
        if (index >= 0) disposedListeners.splice(index, 1)
      }
    },
    effect(setup: () => () => void): () => void {
      const cleanup = setup()
      effectCleanups.push(cleanup)
      return cleanup
    },
  } as unknown as Context
  return { context, agents, guards, restrictions, releasedRestrictions, effectCleanups, disposedListeners }
}

function fakeAgent(id: string, context: Context): Agent {
  return { id: SessionId(id), ctx: context } as Agent
}

function config() {
  return {
    controller: { inheritedTools: ['project_read'] },
    worker: { inheritedTools: ['project_read', 'project_write'], denyScopedTools: ['worker_local'] },
    reviewer: { inheritedTools: ['project_read'] },
  } satisfies Record<DevFrameRole, { inheritedTools: readonly string[]; denyScopedTools?: readonly string[] }>
}

describe('DevFrame role policy', () => {
  it('fails explicitly when native tools are not mounted', () => {
    const context = { get: () => undefined } as unknown as Context
    expect(() => installRolePolicy(context, config())).toThrow(expect.objectContaining({
      code: 'ROLE_TOOLS_UNAVAILABLE',
    }))
  })

  it('applies exact identities, restrictions, monotonic denials, and disposal', () => {
    const fake = fakeContext()
    const lead = fakeAgent('permission-lead', fake.context)
    const worker = fakeAgent('permission-worker', fake.context)
    const reviewer = fakeAgent('permission-reviewer', fake.context)
    const stale = fakeAgent('permission-lead', fake.context)
    fake.agents.set(lead.id, lead)
    fake.agents.set(worker.id, worker)
    fake.agents.set(reviewer.id, reviewer)
    const policy = installRolePolicy(fake.context, config())
    const guard = fake.guards[0]!

    expect(policy.roleOf(lead)).toBeUndefined()
    expect(guard({ name: 'project_read' })).toBe('DevFrame role policy requires an exact live Agent')
    expect(guard({ name: 'project_read', agent: stale })).toContain('has no role')
    expect(() => { policy.assign(stale, 'controller') }).toThrow(expect.objectContaining({ code: 'ROLE_IDENTITY_CONFLICT' }))

    policy.assign(lead, 'controller')
    expect(policy.roleOf(lead)).toBe('controller')
    expect(fake.restrictions).toEqual([{ allow: ['project_read'] }])
    expect(guard({ name: 'project_read', agent: lead })).toBeUndefined()
    expect(() => { policy.assign(lead, 'controller') }).toThrow(expect.objectContaining({ code: 'ROLE_ALREADY_ASSIGNED' }))
    expect(() => { policy.assign(lead, 'worker') }).toThrow(expect.objectContaining({ code: 'ROLE_IDENTITY_CONFLICT' }))
    expect(policy.roleOf(stale)).toBeUndefined()

    policy.assign(worker, 'worker')
    policy.assign(reviewer, 'reviewer')
    expect(fake.restrictions).toEqual([
      { allow: ['project_read'] },
      { allow: ['project_read', 'project_write'] },
      { allow: ['project_read'] },
    ])
    expect(guard({ name: 'worker_local', agent: worker })).toContain('worker')
    expect(guard({ name: 'team_task_update', agent: reviewer })).toContain('reviewer')
    expect(guard({ name: 'project_read', agent: reviewer })).toBeUndefined()

    fake.disposedListeners[0]!({ agent: worker })
    expect(policy.roleOf(worker)).toBeUndefined()
    fake.disposedListeners[0]!({ agent: stale })
    fake.disposedListeners[0]!({ agent: lead })
    expect(policy.roleOf(lead)).toBeUndefined()

    policy.dispose()
    policy.dispose()
    expect(fake.guards).toHaveLength(0)
    expect(fake.effectCleanups).toHaveLength(1)
    expect(fake.releasedRestrictions).toEqual([1, 0, 2])
    expect(() => { policy.assign(reviewer, 'reviewer') }).toThrow(expect.objectContaining({ code: 'ROLE_TOOLS_UNAVAILABLE' }))
    fake.effectCleanups[0]!()
  })
})
