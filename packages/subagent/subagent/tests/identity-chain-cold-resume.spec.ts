/**
 * Identity chain across a process restart: a parent spawns a continuable
 * child through the real service path, the child session persists, the whole
 * context is torn down, and a fresh context over the same persistence root
 * enumerates the same child identity and cold-resumes it without minting a
 * new one. This is the end-to-end anchor for the identity the delegation
 * surface exposes as the SessionID.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import { SessionId } from '@deepseek-ai/dsh-session'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import { queueHostSubagentPrompt } from '@deepseek-ai/dsh-subagent/internal'
import * as SubagentSpawn from '@deepseek-ai/dsh-subagent-spawn-in-process'
import { MockAdapter, textResponse } from '../../../core/agent-loop/tests/mock-adapter.ts'
import SubagentRuntime from '../src/index.ts'
import { TestSessionQuery } from './test-session-query.ts'

type Script = ConstructorParameters<typeof MockAdapter>[0]

const contexts: Context[] = []
const roots: string[] = []
afterEach(async () => {
  for (const ctx of contexts.splice(0).reverse()) await ctx.fiber.dispose()
  for (const root of roots.splice(0)) {
    rmSync(root, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 })
  }
})

/** Boot one full continuable stack over its own JSONL root. */
async function bootStack(script: Script, root: string, options: { spawn?: boolean } = {}) {
  const ctx = new Context()
  contexts.push(ctx)
  await mountAgentLoopTestDependencies(ctx)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(JsonlSessionPersistence, { root })
  await ctx.plugin(AgentLoop, { agents: [] })
  await ctx.plugin(TestSessionQuery)
  await ctx.plugin(SubagentRuntime)
  if (options.spawn === true) await ctx.plugin(SubagentSpawn, { providerName: 'spawn' })
  ctx.llm.registerAdapter(['mock'], new MockAdapter(script))
  return ctx
}

/** Keep the top-level test parent out of the scripted model corpus. */
function parkParent(ctx: Context, parent: Agent): void {
  ctx.on('agent/pre-step', async ({ agent: subject }, next) => {
    if (subject !== parent) return next()
    return { kind: 'reject' as const }
  })
}

/** Wait until a child's Activation is gone, i.e. its handle finished disposal. */
async function waitNoActivation(ctx: Context, childId: SessionId): Promise<void> {
  await vi.waitFor(() => {
    expect(ctx.agents.get(childId)).toBeUndefined()
  }, { timeout: 15_000 })
}

describe('subagent identity chain across a restart', () => {
  it('keeps the spawned child session id and lineage stable from spawn through cold resume to listing', { timeout: 30_000 }, async () => {
    // Lifecycle 1: the parent spawns a continuable child through the real
    // service path; the child settles and its session persists.
    const root = mkdtempSync(join(tmpdir(), 'dsh-subagent-identity-chain-'))
    roots.push(root)
    const ctx1 = await bootStack([textResponse('child done')], root, { spawn: true })
    const parent1 = ctx1.agentLoop.create(SessionId('parent'), { provider: 'mock', model: 'mock' })
    parkParent(ctx1, parent1)

    const started = await ctx1.subagents.startContinuable({
      provider: 'spawn',
      label: 'chain child',
      request: { prompt: [{ type: 'text', text: 'chain task' }], parent: parent1 },
      signal: new AbortController().signal,
    })
    await waitNoActivation(ctx1, started.childId)

    // The identity handed back is the durable child session: its persisted
    // header carries the full lineage and recursion budget.
    const persisted = await ctx1.sessionPersistence.load(started.childId)
    expect(persisted.meta.id).toBe(started.childId)
    expect(persisted.meta.parentSession).toBe(SessionId('parent'))
    expect(persisted.meta.origin).toBe('subagent')
    expect(persisted.meta.delegationDepth).toBe(1)
    const liveListing = await ctx1.subagents.listChildren(parent1.id)
    expect(liveListing).toEqual([{
      kind: 'child', id: started.childId, label: 'chain child', mode: 'continuable',
      activity: 'inactive', hasChildren: false,
    }])
    await ctx1.sessions.flush(parent1.session)
    await ctx1.fiber.dispose()
    // The restart already tore this context down; afterEach must not dispose
    // it a second time.
    contexts.splice(contexts.indexOf(ctx1), 1)

    // Lifecycle 2: a fresh context over the same root — the restart shape.
    // The spawn provider stays unregistered: cold resume must not need it.
    const ctx2 = await bootStack([textResponse('after restart')], root)
    const resumedChildren: Agent[] = []
    ctx2.on('agent/created', ({ agent }) => {
      if (agent.session.header.id === started.childId) resumedChildren.push(agent)
    })
    const { agent: parent2 } = await ctx2.agents.resume({
      resumeSessionId: SessionId('parent'),
      agentOptions: { provider: 'mock', model: 'mock' },
    })
    parkParent(ctx2, parent2)
    expect(parent2.session.header.id).toBe(SessionId('parent'))

    // Cold-resume the child through the sanctioned host delivery path.
    await queueHostSubagentPrompt(
      ctx2.subagents,
      parent2,
      started.childId,
      [{ type: 'text', text: 'continue after restart' }],
      { kind: 'user' },
      new AbortController().signal,
    )
    expect(resumedChildren).toHaveLength(1)
    const child2 = resumedChildren[0]!
    expect(child2.session.header.id).toBe(started.childId)
    expect(child2.session.header.parentSession).toBe(SessionId('parent'))
    expect(child2.session.header.origin).toBe('subagent')
    expect(child2.session.header.delegationDepth).toBe(1)
    await waitNoActivation(ctx2, started.childId)

    // The listing still enumerates the same child under the same parent with
    // the same durable identity it had before the restart.
    await expect(ctx2.subagents.listChildren(parent2.id)).resolves.toEqual([{
      kind: 'child', id: started.childId, label: 'chain child', mode: 'continuable',
      activity: 'inactive', hasChildren: false,
    }])
    await expect(ctx2.subagents.listDescendants(parent2.id)).resolves.toEqual([{
      kind: 'child', id: started.childId, label: 'chain child', mode: 'continuable',
      activity: 'inactive', hasChildren: false, parentId: parent2.id, depth: 1,
    }])
  })
})
