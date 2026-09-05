/**
 * Plugin wiring behavior: boot provides the service and registers the three
 * memory tools, dispatch enforces the declared schemas, and the host-owned
 * append policy keeps `confirmed` unreachable from the model surface.
 */

import { afterEach, describe, expect, it } from 'vitest'
import { mkdirSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import { Session, SessionId } from '@deepseek-ai/dsh-session'
import { defineTool } from '@deepseek-ai/dsh-tools'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import * as projectMemory from '../src/index.ts'
import { NoteId } from '../src/ids.ts'
import type { Config } from '../src/index.ts'

const ROOTS: string[] = []
const CONTEXTS: Context[] = []

afterEach(async () => {
  for (const ctx of CONTEXTS.splice(0).reverse()) await ctx.fiber.dispose()
  while (ROOTS.length > 0) {
    const root = ROOTS.pop()
    if (root !== undefined) rmSync(root, { recursive: true, force: true })
  }
})

/** Create one throwaway Vault root with the memory subtree pre-created. */
function makeVault(): string {
  const root = mkdtempSync(join(tmpdir(), 'pm-plugin-'))
  ROOTS.push(root)
  mkdirSync(join(root, 'devframe-memory'), { recursive: true })
  return root
}

/** Boot a minimal context with the memory plugin mounted. */
async function boot(config: Config): Promise<Context> {
  const ctx = new Context()
  CONTEXTS.push(ctx)
  await ctx.plugin(SystemPrompt)
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(projectMemory, config)
  return ctx
}

/**
 * One structural stand-in for a dispatching agent: the append tool needs only
 * the live session whose log receives the receipt.
 */
function stubAgent(sessionId: string): Agent {
  return { session: Session.create(SessionId(sessionId)) } as unknown as Agent
}

/** Dispatch one tool call through the live registry pipeline. */
async function dispatch(ctx: Context, name: string, args: unknown, callNumber: number, agent?: Agent) {
  return await ctx.tools.execute({
    callId: ToolCallId(`pm-plugin-${callNumber}`),
    name,
    arguments: args,
    signal: new AbortController().signal,
    ...(agent === undefined ? {} : { agent }),
  })
}

describe('project-memory plugin boot', () => {
  it('provides the service and reserves all three tool names globally', async () => {
    const ctx = await boot({
      workspaceId: 'ws-alpha',
      vaultRoot: makeVault(),
      writeEnabled: true,
      userScopeEnabled: true,
    })
    expect(ctx.projectMemory).toBeInstanceOf(projectMemory.ProjectMemoryService)
    // A valid definition reusing a registered name is rejected by the registry.
    const duplicate = defineTool({
      name: 'memory_search',
      description: 'probe definition used to prove the memory tools are registered',
      parameters: {},
      output: { schema: { type: 'json' }, render: () => [] },
      async execute() { return null },
    })
    expect(() => ctx.tools.register(duplicate)).toThrow(/already registered/u)
  })

  it('fails loud at load when appends are enabled without a Vault root', async () => {
    await expect(boot({ workspaceId: 'ws-alpha', writeEnabled: true }))
      .rejects.toThrow(/writeEnabled requires an explicit vaultRoot/u)
  })

  it('fails loud at load when the workspace identity is missing', async () => {
    // The loader schema owns requiredness: the ValidationError fires before apply.
    await expect(boot({})).rejects.toThrow(/workspaceId/u)
  })

  it('validates the loader schema: wrong types and missing workspaceId are rejected', () => {
    expect(() => projectMemory.Config({ workspaceId: 42 })).toThrow()
    expect(() => projectMemory.Config({})).toThrow()
    const resolved = projectMemory.Config({ workspaceId: 'ws-alpha' })
    expect(resolved).toEqual({ workspaceId: 'ws-alpha', writeEnabled: false, userScopeEnabled: false })
  })
})

describe('memory tool dispatch', () => {
  it('appends, searches, and reads end-to-end through the registry', async () => {
    const ctx = await boot({
      workspaceId: 'ws-alpha',
      vaultRoot: makeVault(),
      writeEnabled: true,
    })
    const agent = stubAgent('pm-e2e-agent')
    const append = await dispatch(ctx, 'memory_append', {
      scope: 'project',
      source_ref: 'session-alpha#event-1',
      kind: 'fact',
      body: 'The deploy script lives in scripts/deploy.ps1.',
    }, 1, agent)
    expect(append.isError).toBe(false)
    if (append.isError) return
    expect(append.value).toMatchObject({ status: 'created' })

    const search = await dispatch(ctx, 'memory_search', {
      scope: 'project',
      query: 'deploy script',
    }, 2)
    expect(search.isError).toBe(false)
    if (search.isError) return
    const searchValue = search.value as { hits: Array<{ noteId: string; freshness: string }>; coverageComplete: boolean }
    expect(searchValue.hits).toHaveLength(1)
    expect(searchValue.coverageComplete).toBe(true)
    expect(searchValue.hits[0]?.freshness).toBe('current')

    const read = await dispatch(ctx, 'memory_read', {
      scope: 'project',
      note_id: searchValue.hits[0]?.noteId,
    }, 3)
    expect(read.isError).toBe(false)
    if (read.isError) return
    const readValue = read.value as { status: string; note?: { body: string; status: string } }
    expect(readValue.status).toBe('found')
    expect(readValue.note?.body).toBe('The deploy script lives in scripts/deploy.ps1.')
    expect(readValue.note?.status).toBe('observed')
  })

  it('keeps append idempotency and conflict reporting intact through the tool surface', async () => {
    const ctx = await boot({
      workspaceId: 'ws-alpha',
      vaultRoot: makeVault(),
      writeEnabled: true,
    })
    const agent = stubAgent('pm-idempotent-agent')
    const request = {
      scope: 'project',
      source_ref: 'session-alpha#event-2',
      kind: 'lesson',
      body: 'Always run the typecheck before committing.',
    }
    const first = await dispatch(ctx, 'memory_append', request, 4, agent)
    const retry = await dispatch(ctx, 'memory_append', request, 5, agent)
    expect(first.isError).toBe(false)
    expect(retry.isError).toBe(false)
    if (first.isError || retry.isError) return
    expect(first.value).toMatchObject({ status: 'created' })
    expect(retry.value).toMatchObject({ status: 'already_exists' })

    const conflict = await dispatch(ctx, 'memory_append', { ...request, body: 'A different lesson.' }, 6, agent)
    expect(conflict.isError).toBe(false)
    if (conflict.isError) return
    expect(conflict.value).toMatchObject({ status: 'memory_conflict' })
  })

  it('records tool appends as observations: confirmed status stays unreachable', async () => {
    const ctx = await boot({
      workspaceId: 'ws-alpha',
      vaultRoot: makeVault(),
      writeEnabled: true,
      userScopeEnabled: true,
    })
    const agent = stubAgent('pm-observe-agent')
    const append = await dispatch(ctx, 'memory_append', {
      scope: 'user',
      source_ref: 'session-alpha#event-3',
      kind: 'preference',
      body: 'The user prefers concise summaries.',
    }, 7, agent)
    expect(append.isError).toBe(false)
    if (append.isError) return
    const created = append.value as { status: string; noteId: string }
    expect(created.status).toBe('created')

    const read = await dispatch(ctx, 'memory_read', { scope: 'user', note_id: created.noteId }, 8)
    expect(read.isError).toBe(false)
    if (read.isError) return
    const readValue = read.value as { note?: { status: string } }
    expect(readValue.note?.status).toBe('observed')
  })

  it('rejects malformed tool arguments with schema violations', async () => {
    const ctx = await boot({ workspaceId: 'ws-alpha', vaultRoot: makeVault() })
    const result = await dispatch(ctx, 'memory_search', { scope: 'everywhere', query: 'x' }, 9)
    expect(result.isError).toBe(true)
    if (!result.isError) return
    expect(JSON.stringify(result.error)).toContain('scope')
  })

  it('reports an unconfigured Vault as an honest tool failure, not a crash', async () => {
    const ctx = await boot({ workspaceId: 'ws-alpha' })
    const result = await dispatch(ctx, 'memory_search', { scope: 'project', query: 'anything' }, 10)
    expect(result.isError).toBe(true)
    if (!result.isError) return
    expect(JSON.stringify(result.error)).toContain('not configured')
  })

  it('commits the receipt into the calling session log before the tool result is created', async () => {
    const ctx = await boot({
      workspaceId: 'ws-alpha',
      vaultRoot: makeVault(),
      writeEnabled: true,
    })
    const agent = stubAgent('pm-receipt-agent')
    const append = await dispatch(ctx, 'memory_append', {
      scope: 'project',
      source_ref: 'session-alpha#event-4',
      kind: 'fact',
      body: 'The receipt must reach the session log.',
    }, 11, agent)
    expect(append.isError).toBe(false)
    if (append.isError) return
    const created = append.value as { status: string; noteId: string }
    expect(created.status).toBe('created')

    const event = agent.session.snapshotEvents().findLast(item => item.type === 'memory/receipt')
    expect(event).toBeDefined()
    expect(event?.data).toMatchObject({ noteId: created.noteId })

    // Cold recovery: a replayed log rehydrates a fresh receipt index.
    const recovered = Session.create(SessionId('pm-receipt-agent-2'), agent.session.snapshotEvents())
    const freshIndex = projectMemory.createMemoryReceiptStore()
    await projectMemory.rehydrateMemoryReceipts(freshIndex, recovered)
    const receipt = await freshIndex.read(NoteId(created.noteId))
    expect(receipt).toBeDefined()
    expect(receipt?.relativePath).toContain('devframe-memory/projects/ws-alpha/')
  })

  it('refuses an append without a calling agent: the receipt could not reach a session log', async () => {
    const ctx = await boot({
      workspaceId: 'ws-alpha',
      vaultRoot: makeVault(),
      writeEnabled: true,
    })
    const result = await dispatch(ctx, 'memory_append', {
      scope: 'project',
      source_ref: 'session-alpha#event-5',
      kind: 'fact',
      body: 'No agent, no durable receipt.',
    }, 12)
    expect(result.isError).toBe(true)
    if (!result.isError) return
    expect(JSON.stringify(result.error)).toContain('calling agent')
  })
})
