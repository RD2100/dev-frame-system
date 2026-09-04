import { afterEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import { defineContentToolFixture } from '@deepseek-ai/dsh-tools'
import type { ToolExecutionResult } from '@deepseek-ai/dsh-tools'
import { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SubagentService from '@deepseek-ai/dsh-subagent'
import * as SubagentFork from '@deepseek-ai/dsh-subagent-fork-in-process'
import * as SubagentSpawn from '@deepseek-ai/dsh-subagent-spawn-in-process'
import { MockAdapter } from '../../../core/agent-loop/tests/mock-adapter.ts'
import TeamService from '../src/index.ts'
import { TestSessionQuery } from './test-session-query.ts'

const SIGNAL = new AbortController().signal
const roots: string[] = []
const contexts: Context[] = []

afterEach(async () => {
  for (const ctx of contexts.splice(0).reverse()) await ctx.fiber.dispose()
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

async function setup() {
  const ctx = new Context()
  contexts.push(ctx)
  await mountAgentLoopTestDependencies(ctx)
  await ctx.plugin(SessionProjectionRegistry)
  const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-team-cold-role-'))
  roots.push(storageRoot)
  await ctx.plugin(JsonlSessionPersistence, { root: storageRoot })
  await ctx.plugin(TestSessionQuery)
  await ctx.plugin(AgentLoop, { agents: [] })
  await ctx.plugin(SubagentService)
  await ctx.plugin(SubagentSpawn, { providerName: 'spawn' })
  await ctx.plugin(SubagentFork, { providerName: 'fork' })
  await ctx.plugin(TeamService)
  ctx.llm.registerAdapter(['mock'], new MockAdapter(['hang', 'hang']))
  const lead = ctx.agentLoop.create(SessionId('cold-role-lead'), { provider: 'mock', model: 'mock' })
  return { ctx, lead }
}

async function waitRunning(ctx: Context, id: SessionId): Promise<Agent> {
  return vi.waitFor(() => {
    const agent = ctx.agents.get(id)
    expect(agent?.status).toBe('running')
    return agent!
  }, { timeout: 5_000 })
}

async function waitNoAgent(ctx: Context, id: SessionId): Promise<void> {
  await vi.waitFor(() => { expect(ctx.agents.get(id)).toBeUndefined() }, { timeout: 5_000 })
}

function resultText(result: ToolExecutionResult): string {
  return result.content.flatMap(block => block.type === 'text' ? [block.text] : []).join('')
}

describe('Team role composition recovery', () => {
  it('reinstalls a persisted reviewer restriction after cold resume', async () => {
    const { ctx, lead } = await setup()
    let bodyCalls = 0
    ctx.tools.register(defineContentToolFixture({
      name: 'project_read',
      description: 'read the approved project scope',
      parameters: {},
      async execute() {
        return [{ type: 'text' as const, text: 'read ran' }]
      },
    }))
    ctx.tools.register(defineContentToolFixture({
      name: 'project_write',
      description: 'write the approved project scope',
      parameters: {},
      async execute() {
        bodyCalls += 1
        return [{ type: 'text' as const, text: 'write ran' }]
      },
    }))

    const started = await ctx.agentTeams.spawnTeammate(lead, {
      name: 'reviewer',
      description: 'read-only review',
      prompt: [{ type: 'text', text: 'review the project' }],
      context: 'fresh',
      provider: 'spawn',
      persona: 'You are the read-only reviewer.',
      toolFilter: { allow: ['project_read'] },
      signal: SIGNAL,
    })
    const child = await waitRunning(ctx, started.member.id)
    expect(ctx.tools.schemas(child).map(schema => schema.name)).toEqual(['project_read'])

    const initialDenied = await ctx.tools.execute({
      callId: ToolCallId('cold-role-initial'),
      name: 'project_write',
      arguments: {},
      signal: SIGNAL,
      agent: child,
    })
    expect(initialDenied.isError).toBe(true)
    expect(resultText(initialDenied)).toBe('Error: unknown tool "project_write"')
    expect(bodyCalls).toBe(0)

    const stored = await ctx.sessionPersistence.inspect(started.member.id)
    const descriptor = stored.events.find(event => event.type === 'subagent/descriptor')
    expect(descriptor?.type === 'subagent/descriptor' && descriptor.data).toMatchObject({
      persona: 'You are the read-only reviewer.',
      toolFilter: { allow: ['project_read'] },
    })

    ctx.agentTeams.interrupt(lead, 'reviewer')
    await waitNoAgent(ctx, started.member.id)

    const resumed = await ctx.agentTeams.sendMessage(lead, {
      target: 'reviewer',
      content: [{ type: 'text', text: 'review the next snapshot' }],
      delivery: 'wakeup',
      signal: SIGNAL,
    })
    expect(['accepted', 'queued']).toContain(resumed.status)
    const coldChild = await waitRunning(ctx, started.member.id)
    expect(coldChild).not.toBe(child)
    expect(ctx.tools.schemas(coldChild).map(schema => schema.name)).toEqual(['project_read'])
    const resumedSession = await ctx.sessionPersistence.inspect(started.member.id)
    expect(resumedSession.events.some(event => event.type === 'user/message'
      && event.data.source.kind === 'team-message'
      && event.data.content.some(block => block.type === 'text' && block.text === 'review the next snapshot')))
      .toBe(true)

    const resumedDenied = await ctx.tools.execute({
      callId: ToolCallId('cold-role-resumed'),
      name: 'project_write',
      arguments: {},
      signal: SIGNAL,
      agent: coldChild,
    })
    expect(resumedDenied.isError).toBe(true)
    expect(resultText(resumedDenied)).toBe('Error: unknown tool "project_write"')
    expect(bodyCalls).toBe(0)

    ctx.agentTeams.interrupt(lead, 'reviewer')
    await waitNoAgent(ctx, started.member.id)
  })
})
