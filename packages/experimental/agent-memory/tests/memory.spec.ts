/** MVP behavior: persistence, scope, lifecycle, conflicts, deletion, budget, and traces. */
import { describe, expect, it } from 'vitest'
import { AgentMemoryError } from '../src/index.ts'
import { harness } from './helpers.ts'

describe('agent memory persistence and retrieval', () => {
  it('restores episodes and semantic facts across a cold restart', async () => {
    const first = await harness()
    const fact = await first.ctx.agentMemory.upsertFact({
      scope: { workspaceId: 'ws-alpha', projectId: 'harness' }, subject: 'DSH', predicate: 'storage', object: 'JSON',
      statement: 'DSH uses JSON storage for this test composition.', source: { type: 'source_code', ref: 'test:composition' }, confidence: 0.9,
    })
    const episode = await first.ctx.agentMemory.recordEpisode({ scope: { workspaceId: 'ws-alpha', projectId: 'harness' }, taskType: 'storage', summary: 'Configured JSON storage', result: 'success' })
    const root = first.root
    await first.dispose({ keepRoot: true })

    const second = await harness(root)
    try {
      const context = await second.ctx.agentMemory.retrieveContext({ query: 'storage JSON', scope: { workspaceId: 'ws-alpha', projectId: 'harness' } })
      expect(context.items.map(item => item.id)).toEqual(expect.arrayContaining([fact.id, episode.id]))
      expect(context.traceId).toMatch(/^trace_/u)
      expect(second.ctx.agentMemory.inspectTrace(context.traceId)?.injected).toContain(fact.id)
    } finally {
      await second.dispose()
    }
  })

  it('rejects another workspace and never leaks records across scope', async () => {
    const h = await harness()
    try {
      await expect(h.ctx.agentMemory.upsertFact({ scope: { workspaceId: 'ws-beta' }, subject: 'x', predicate: 'y', object: 'z', statement: 'z', source: { type: 'agent_inference', ref: 'test' } })).rejects.toMatchObject({ code: 'MEMORY_SCOPE_FORBIDDEN' })
      await h.ctx.agentMemory.upsertFact({ scope: { workspaceId: 'ws-alpha', projectId: 'alpha' }, subject: 'private', predicate: 'value', object: 'alpha', statement: 'alpha private value', source: { type: 'source_code', ref: 'test' } })
      const context = await h.ctx.agentMemory.retrieveContext({ query: 'private alpha', scope: { workspaceId: 'ws-alpha', projectId: 'other' } })
      expect(context.items).toHaveLength(0)
    } finally {
      await h.dispose()
    }
  })
})

describe('semantic lifecycle and forgetting', () => {
  it('supersedes weaker facts, marks equal conflicts, and deduplicates', async () => {
    const h = await harness()
    try {
      const weak = await h.ctx.agentMemory.upsertFact({ scope: { workspaceId: 'ws-alpha' }, subject: 'API', predicate: 'timeout', object: '30s', statement: 'API timeout is 30s.', source: { type: 'agent_inference', ref: 'old' } })
      const strong = await h.ctx.agentMemory.upsertFact({ scope: { workspaceId: 'ws-alpha' }, subject: 'API', predicate: 'timeout', object: '60s', statement: 'API timeout is 60s.', source: { type: 'source_code', ref: 'config.ts' } })
      expect(strong.status).toBe('active')
      expect((await h.ctx.agentMemory.retrieveContext({ query: 'API timeout', scope: { workspaceId: 'ws-alpha' } })).items.map(item => item.id)).toEqual([strong.id])
      const duplicate = await h.ctx.agentMemory.upsertFact({ scope: { workspaceId: 'ws-alpha' }, subject: 'API', predicate: 'timeout', object: '60s', statement: 'API timeout is 60s.', source: { type: 'source_code', ref: 'config.ts' } })
      expect(duplicate.id).toBe(strong.id)
      expect(weak.id).not.toBe(strong.id)

      await h.ctx.agentMemory.upsertFact({ scope: { workspaceId: 'ws-alpha', projectId: 'conflict' }, subject: 'mode', predicate: 'default', object: 'a', statement: 'mode defaults to a', source: { type: 'test_result', ref: 'a' } })
      const b = await h.ctx.agentMemory.upsertFact({ scope: { workspaceId: 'ws-alpha', projectId: 'conflict' }, subject: 'mode', predicate: 'default', object: 'b', statement: 'mode defaults to b', source: { type: 'test_result', ref: 'b' } })
      expect(b.status).toBe('conflicted')
      expect((await h.ctx.agentMemory.retrieveContext({ query: 'mode default', scope: { workspaceId: 'ws-alpha', projectId: 'conflict' } })).items).toHaveLength(0)
    } finally {
      await h.dispose()
    }
  })

  it('forgets a record immediately and rejects credential-like text', async () => {
    const h = await harness()
    try {
      const row = await h.ctx.agentMemory.recordEpisode({ scope: { workspaceId: 'ws-alpha' }, taskType: 'forget', summary: 'temporary fact' })
      expect(await h.ctx.agentMemory.forget(row.id)).toBe(true)
      expect((await h.ctx.agentMemory.retrieveContext({ query: 'temporary fact', scope: { workspaceId: 'ws-alpha' } })).items).toHaveLength(0)
      await expect(h.ctx.agentMemory.recordEpisode({ scope: { workspaceId: 'ws-alpha' }, taskType: 'secret', summary: 'api key = abc' })).rejects.toBeInstanceOf(AgentMemoryError)
    } finally {
      await h.dispose()
    }
  })
})

describe('context budget and graceful degradation', () => {
  it('keeps rendered context within its byte budget and exposes truncation', async () => {
    const h = await harness()
    try {
      await h.ctx.agentMemory.recordEpisode({ scope: { workspaceId: 'ws-alpha' }, taskType: 'budget', summary: 'first long memory item' })
      await h.ctx.agentMemory.recordEpisode({ scope: { workspaceId: 'ws-alpha' }, taskType: 'budget', summary: 'second long memory item' })
      const context = await h.ctx.agentMemory.retrieveContext({ query: 'budget memory', scope: { workspaceId: 'ws-alpha' }, budgetBytes: 35 })
      expect(Buffer.byteLength(context.items.map(item => item.text).join(''), 'utf8')).toBeLessThanOrEqual(35)
      expect(context.truncated).toBe(true)
    } finally {
      await h.dispose()
    }
  })

  it('mounts without storage and keeps the host loadable', async () => {
    const h = await harness()
    await h.dispose()
    // A second direct context omits storage entirely; service activation is
    // intentionally best effort and reports a stable unavailable code.
    const { Context } = await import('@deepseek-ai/cordis')
    const ToolRuntime = (await import('@deepseek-ai/dsh-tools')).default
    const SystemPrompt = (await import('@deepseek-ai/dsh-system-prompt')).default
    const ctx = new Context()
    try {
      await ctx.plugin(SystemPrompt)
      await ctx.plugin(ToolRuntime)
      const { default: Service } = await import('../src/index.ts')
      await ctx.plugin(Service, { workspaceId: 'ws-alpha', autoRetrieve: false })
      await expect(ctx.agentMemory.recordEpisode({ scope: { workspaceId: 'ws-alpha' }, taskType: 'offline', summary: 'should fail explicitly' })).rejects.toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
    } finally {
      await ctx.fiber.dispose()
    }
  })
})
