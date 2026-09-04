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
import { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SubagentService from '@deepseek-ai/dsh-subagent'
import * as SubagentSpawn from '@deepseek-ai/dsh-subagent-spawn-in-process'
import TeamService from '../src/index.ts'
import { MockAdapter } from '../../../core/agent-loop/tests/mock-adapter.ts'

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
  const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-team-child-options-'))
  roots.push(storageRoot)
  await ctx.plugin(JsonlSessionPersistence, { root: storageRoot })
  await ctx.plugin(AgentLoop, { agents: [] })
  await ctx.plugin(SubagentService)
  await ctx.plugin(SubagentSpawn, { providerName: 'spawn' })
  await ctx.plugin(TeamService)
  ctx.llm.registerAdapter(['mock'], new MockAdapter(['hang']))
  const lead = ctx.agentLoop.create(SessionId('child-options-lead'), { provider: 'mock', model: 'mock' })
  return { ctx, lead }
}

async function waitRunning(ctx: Context, id: SessionId): Promise<Agent> {
  return vi.waitFor(() => {
    const child = ctx.agents.get(id)
    expect(child?.status).toBe('running')
    return child!
  }, { timeout: 5_000 })
}

function resultText(result: Awaited<ReturnType<Context['tools']['execute']>>): string {
  return result.content.flatMap(block => block.type === 'text' ? [block.text] : []).join('')
}

describe('Team child composition options', () => {
  it('forwards persona and inherited tool restrictions through real child composition', async () => {
    const { ctx, lead } = await setup()
    for (const name of ['project_read', 'project_write']) {
      ctx.tools.register(defineContentToolFixture({
        name,
        description: name,
        parameters: {},
        async execute() {
          return [{ type: 'text' as const, text: `${name} ran` }]
        },
      }))
    }

    const started = await ctx.agentTeams.spawnTeammate(lead, {
      name: 'reviewer',
      description: 'read-only review',
      prompt: [{ type: 'text', text: 'review the project' }],
      context: 'fresh',
      provider: 'spawn',
      persona: 'You are a read-only reviewer.',
      toolFilter: { allow: ['project_read'] },
      signal: SIGNAL,
    })
    const child = await waitRunning(ctx, started.member.id)

    const assembly = await ctx.systemPrompt.assemble({ scope: child })
    expect(assembly.sections.find(section => section.name === 'deployment:persona')?.text)
      .toBe('You are a read-only reviewer.')
    expect(ctx.tools.schemas(child).map(schema => schema.name)).toEqual(['project_read'])

    const allowed = await ctx.tools.execute({
      callId: ToolCallId('child-options-read'),
      name: 'project_read',
      arguments: {},
      signal: SIGNAL,
      agent: child,
    })
    expect(allowed.isError).toBe(false)

    const denied = await ctx.tools.execute({
      callId: ToolCallId('child-options-write'),
      name: 'project_write',
      arguments: {},
      signal: SIGNAL,
      agent: child,
    })
    expect(denied.isError).toBe(true)
    expect(resultText(denied)).toBe('Error: unknown tool "project_write"')

    const stored = await ctx.sessionPersistence.inspect(child.id)
    const descriptor = stored.events.find(event => event.type === 'subagent/descriptor')
    expect(descriptor?.type === 'subagent/descriptor' && descriptor.data).toMatchObject({
      persona: 'You are a read-only reviewer.',
      toolFilter: { allow: ['project_read'] },
    })

    ctx.agentTeams.interrupt(lead, 'reviewer')
    await vi.waitFor(() => { expect(ctx.agents.get(child.id)).toBeUndefined() }, { timeout: 5_000 })
  })
})
