import { afterEach, describe, expect, it } from 'vitest'
import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { Context } from '@deepseek-ai/cordis'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import GoalService from '@deepseek-ai/dsh-goal'
import { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SubagentService from '@deepseek-ai/dsh-subagent'
import TeamService from '../src/index.ts'
import * as toolTeam from '../../tool-agent-team/src/index.ts'

const roots: string[] = []
let callNumber = 0

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

async function setup() {
  const ctx = new Context()
  await mountAgentLoopTestDependencies(ctx)
  await ctx.plugin(SessionProjectionRegistry)
  const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-devframe-composition-'))
  roots.push(storageRoot)
  await ctx.plugin(JsonlSessionPersistence, { root: storageRoot })
  await ctx.plugin(AgentLoop, { agents: [] })
  await ctx.plugin(SubagentService)
  await ctx.plugin(GoalService)
  await ctx.plugin(TeamService)
  await ctx.plugin(toolTeam)
  const lead = ctx.agentLoop.create(SessionId('devframe-composition-lead'), {})
  return { ctx, lead, storageRoot }
}

async function execute(ctx: Context, agent: ReturnType<Awaited<ReturnType<typeof setup>>['ctx']['agentLoop']['create']>, name: string, args: unknown) {
  return ctx.tools.execute({
    callId: ToolCallId(`devframe-composition-${++callNumber}`),
    name,
    arguments: args,
    agent,
    signal: new AbortController().signal,
  })
}

function text(result: Awaited<ReturnType<typeof execute>>): string {
  return result.content.flatMap(block => block.type === 'text' ? [block.text] : []).join('')
}

describe('DevFrame native composition baseline', () => {
  it('dispatches a Team task through the real scoped tool and persists it', async () => {
    const { ctx, lead } = await setup()

    const created = await execute(ctx, lead, 'team_task_create', {
      subject: 'composition probe',
      description: 'persist one native Team task',
      blocked_by: [],
      write_scopes: ['src'],
    })

    expect(created.isError).toBe(false)
    const task = JSON.parse(text(created)) as { id: string; revision: number; status: string }
    expect(task).toMatchObject({ revision: 1, status: 'pending' })

    const listed = await execute(ctx, lead, 'team_task_get', { task_id: task.id })
    expect(listed.isError).toBe(false)
    expect(JSON.parse(text(listed))).toMatchObject({ id: task.id, revision: 1, status: 'pending' })

    await ctx.sessions.flush(lead.session)
    const stored = await ctx.sessionPersistence.inspect(lead.id)
    expect(stored.events.some(event => event.type === 'team/task'
      && event.data.task.id === task.id
      && event.data.task.revision === 1)).toBe(true)
  })

  it('disarms before persistence and resumes the same Goal identity', async () => {
    const { ctx, lead } = await setup()

    const created = ctx.goals.create(lead, { objective: 'run one bound composition task' })
    expect(created.activation).toBe('armed')
    const disarmed = ctx.goals.disarm(lead)
    expect(disarmed).toMatchObject({ id: created.id, revision: created.revision, activation: 'disarmed' })

    await ctx.sessions.flush(lead.session)
    const persistedBeforeResume = await ctx.sessionPersistence.inspect(lead.id)
    expect(persistedBeforeResume.events.filter(event => event.type === 'goal/change')).toHaveLength(1)

    const resumed = ctx.goals.resume(lead, { id: created.id, revision: created.revision })
    expect(resumed).toMatchObject({ id: created.id, revision: created.revision + 1, activation: 'armed' })
    await ctx.sessions.flush(lead.session)
    const persistedAfterResume = await ctx.sessionPersistence.inspect(lead.id)
    expect(persistedAfterResume.events.filter(event => event.type === 'goal/change')).toHaveLength(2)
    expect(ctx.goals.get(lead)).toMatchObject({ id: created.id, revision: resumed.revision })
  })
})
