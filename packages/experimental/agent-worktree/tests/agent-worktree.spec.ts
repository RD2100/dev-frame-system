import { existsSync } from 'node:fs'
import { rm } from 'node:fs/promises'
import { join } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import type { ToolExecutionResult } from '@deepseek-ai/dsh-tools'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import { Session, SessionId, SESSION_FORMAT_VERSION } from '@deepseek-ai/dsh-session'
import type { SessionHeader } from '@deepseek-ai/dsh-session'
import Storage from '@deepseek-ai/dsh-storage'
import { DomainFacility } from '@deepseek-ai/dsh-storage-domain'
import { MemoryMediaPool, MemoryStorageBackend } from '../../../storage/storage-domain/tests/helpers/memory-backend.ts'
import WorkspaceRegistry from '@deepseek-ai/dsh-workspace'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import GitWorktreeRegistry from '@deepseek-ai/dsh-worktree-registry'
import SubprocessLocal from '@deepseek-ai/dsh-subprocess-local'
import { git, gitStyle, harness } from '../../../workflow/worktree-registry/tests/helpers.ts'
import * as agentWorktree from '../src/index.ts'
import { TOOL_NAMES } from '../src/index.ts'

const contexts: Context[] = []
const roots: string[] = []

afterEach(async () => {
  await Promise.all(contexts.splice(0).map(ctx => ctx.fiber.dispose()))
  await Promise.all(roots.splice(0).map(root => rm(root, { recursive: true, force: true })))
})

interface Setup {
  ctx: Context
  root: string
  workspaceId: WorkspaceId
  createRepoWorkspace: Awaited<ReturnType<typeof harness>>['createRepoWorkspace']
  /** The plugin fiber mounted by setup; disposing it unmounts the whole seam. */
  pluginFiber: Awaited<ReturnType<Context['plugin']>>
  execute: (name: string, args: unknown, sessionId: string) => Promise<ToolExecutionResult>
}

function headerFor(id: SessionId, cwd: string): SessionHeader {
  return { version: SESSION_FORMAT_VERSION, id, createdAt: 0, isSeeded: false, cwd }
}

/** The model-facing text of one result. */
function textOf(result: ToolExecutionResult): string {
  return (result.content[0] as { text: string }).text
}

/** The canonical value of a successful result. */
function valueOf(result: ToolExecutionResult): Record<string, unknown> {
  if (result.isError) throw new Error(`expected success, got: ${textOf(result)}`)
  return result.value as Record<string, unknown>
}

/**
 * Boot the registry harness (real git over the subprocess seam), then mount
 * the system prompt, the real tool runtime, and the agent-worktree plugin —
 * every tool execution below runs through the real dispatcher against the
 * real GitWorktreeRegistry.
 */
async function setup(): Promise<Setup> {
  const prepared = await harness()
  contexts.push(prepared.ctx)
  roots.push(prepared.root)
  await prepared.ctx.plugin(SystemPrompt)
  await prepared.ctx.plugin(ToolRuntime)
  const pluginFiber = await prepared.ctx.plugin(agentWorktree)

  // The caller sessions run inside the registered repository workspace.
  const { workspaceId, repo } = await prepared.createRepoWorkspace('workspace')

  const execute = (name: string, args: unknown, sessionId: string): Promise<ToolExecutionResult> => {
    const session = Session.create(SessionId(sessionId), undefined, headerFor(SessionId(sessionId), repo))
    const agent = { id: session.id, options: {}, session } as never
    return prepared.ctx.tools.execute({
      signal: new AbortController().signal,
      callId: ToolCallId(`call-${sessionId}-${name}`),
      name,
      arguments: args,
      agent,
    })
  }
  return {
    ctx: prepared.ctx,
    root: prepared.root,
    workspaceId,
    createRepoWorkspace: prepared.createRepoWorkspace,
    pluginFiber,
    execute,
  }
}

describe('agent worktree tool schemas', () => {
  it('registers the three stable model-facing names with model-oriented parameters', async () => {
    const { ctx } = await setup()

    const definitions = TOOL_NAMES.map(toolName => ctx.tools.get(toolName))
    expect(definitions.every(definition => definition !== undefined)).toBe(true)
    expect(definitions.every(definition => definition!.description.length > 40)).toBe(true)
    const parametersOf = (toolName: string) =>
      ctx.tools.get(toolName)!.parameters as unknown as { properties: Record<string, unknown>; required?: string[] }
    expect(Object.keys(parametersOf('worktree_create').properties)).toEqual(['path', 'branch'])
    expect(parametersOf('worktree_create').required).toEqual(['path'])
    expect(Object.keys(parametersOf('worktree_status').properties)).toEqual(['id'])
    expect(Object.keys(parametersOf('worktree_remove').properties)).toEqual(['id', 'force'])
  })
})

describe('agent worktree tool behavior over real git', () => {
  it('creates a worktree bound to the calling session and registers it with git', async () => {
    const { ctx, root, workspaceId, execute } = await setup()

    const result = await execute('worktree_create', { path: 'wt-a', branch: 'agent/one' }, 'sess-a')
    const value = valueOf(result) as { id: string; path: string; branch: string }

    expect(result.isError).toBe(false)
    expect(value.branch).toBe('agent/one')
    expect(value.path).toBe(join(root, 'workspace', 'wt-a'))
    const rows = ctx.worktreeRegistry.list(workspaceId)
    expect(rows).toHaveLength(1)
    expect(String(rows[0]?.lockedBy)).toBe('sess-a')
    expect(rows[0]?.lockedAt).toBeTypeOf('string')
    expect(gitStyle(await git(join(root, 'workspace'), 'worktree', 'list', '--porcelain')))
      .toContain(gitStyle(value.path))
    expect(textOf(result)).toContain('bound to this session as its single writer')
  })

  it('reports the binding from each session perspective', async () => {
    const { execute } = await setup()
    const created = await execute('worktree_create', { path: 'wt-a' }, 'sess-a')
    const { id } = valueOf(created) as { id: string }

    const own = valueOf(await execute('worktree_status', { id }, 'sess-a'))
    expect(own).toMatchObject({ directoryExists: true, locked: true, lockedByThisSession: true, clean: true })
    const other = valueOf(await execute('worktree_status', { id }, 'sess-b'))
    expect(other).toMatchObject({ directoryExists: true, locked: true, lockedByThisSession: false })
    expect(textOf(await execute('worktree_status', { id }, 'sess-b'))).toContain('bound to another session')
  })

  it('refuses removal by another session and removes for the holding session', async () => {
    const { execute } = await setup()
    const created = await execute('worktree_create', { path: 'wt-a' }, 'sess-a')
    const { id, path } = valueOf(created) as { id: string; path: string }

    const refused = await execute('worktree_remove', { id, force: true }, 'sess-b')
    expect(refused.isError).toBe(true)
    expect(textOf(refused)).toContain('bound to writer')
    expect(existsSync(path)).toBe(true)

    const removed = await execute('worktree_remove', { id }, 'sess-a')
    expect(removed.isError).toBe(false)
    expect((valueOf(removed) as { path: string }).path).toBe(path)
    expect(existsSync(path)).toBe(false)
  })

  it('removes an unbound worktree that any authorized session may remove', async () => {
    const { ctx, root, workspaceId, execute } = await setup()
    const unbound = await ctx.worktreeRegistry.create({ workspaceId, path: join(root, 'unbound-wt') })

    const removed = await execute('worktree_remove', { id: unbound.id }, 'sess-b')

    expect(removed.isError).toBe(false)
    expect(ctx.worktreeRegistry.list(workspaceId)).toEqual([])
  })

  it('reports a foreign-workspace id like an unknown one and leaves the worktree alone', async () => {
    const { ctx, root, createRepoWorkspace, execute } = await setup()
    const other = await createRepoWorkspace('other-repo')
    const foreign = await ctx.worktreeRegistry.create({
      workspaceId: other.workspaceId,
      path: join(root, 'other-wt'),
    })

    const status = await execute('worktree_status', { id: foreign.id }, 'sess-a')
    const remove = await execute('worktree_remove', { id: foreign.id }, 'sess-a')

    expect(status.isError).toBe(true)
    expect(textOf(status)).toContain('not registered for this workspace')
    expect(remove.isError).toBe(true)
    expect(existsSync(foreign.path)).toBe(true)
  })
})

describe('agent worktree plugin lifecycle', () => {
  it('contributes nothing while the worktree registry is missing and activates when it arrives', async () => {
    const pool = new MemoryMediaPool()
    const ctx = new Context()
    contexts.push(ctx)
    await ctx.plugin(Storage)
    ctx.storage.backend.register('memory', new MemoryStorageBackend(pool))
    const facility = new DomainFacility(ctx, { backend: 'memory', routes: {} })
    ctx.storage.mount('domain', facility)
    ctx.provide('storageDomain', facility)
    ctx.provide('sessionPersistence', {
      list: async () => [],
      load: () => { throw new Error('event bodies must not be loaded') },
      inspect: () => { throw new Error('event bodies must not be inspected') },
    } as never)
    await ctx.plugin(WorkspaceRegistry)
    await ctx.plugin(SystemPrompt)
    await ctx.plugin(ToolRuntime)

    // The declared registry injection holds the plugin fiber pending: no
    // tools, no service — the seam stays unavailable, never silently degraded.
    const fiber = await ctx.plugin(agentWorktree)
    expect(ctx.tools.get('worktree_create')).toBeUndefined()
    expect(ctx.tools.get('worktree_status')).toBeUndefined()
    expect(ctx.tools.get('worktree_remove')).toBeUndefined()

    // The registry arrives (with its own subprocess dependency) and the same
    // fiber activates with its tools.
    await ctx.plugin(SubprocessLocal)
    await ctx.plugin(GitWorktreeRegistry)
    await vi.waitFor(() => { expect(ctx.tools.get('worktree_create')).toBeDefined() })
    await fiber.dispose()
    expect(ctx.tools.get('worktree_create')).toBeUndefined()
  })

  it('unregisters the tools with the plugin fiber and reinstalls them on reload (HMR safety)', async () => {
    const { ctx, pluginFiber, execute } = await setup()
    expect(ctx.tools.get('worktree_create')).toBeDefined()

    await pluginFiber.dispose()
    expect(ctx.tools.get('worktree_create')).toBeUndefined()
    expect(ctx.tools.get('worktree_status')).toBeUndefined()
    expect(ctx.tools.get('worktree_remove')).toBeUndefined()

    await ctx.plugin(agentWorktree)
    expect(ctx.tools.get('worktree_create')).toBeDefined()
    const result = await execute('worktree_status', { id: 'no-such-id' }, 'sess-a')
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain('not registered for this workspace')
  })
})
