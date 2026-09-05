import { mkdir, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import type { ToolExecutionResult } from '@deepseek-ai/dsh-tools'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import { Session, SessionId, SESSION_FORMAT_VERSION } from '@deepseek-ai/dsh-session'
import type { SessionHeader } from '@deepseek-ai/dsh-session'
import Storage from '@deepseek-ai/dsh-storage'
import { DomainFacility } from '@deepseek-ai/dsh-storage-domain'
import WorkspaceRegistry from '@deepseek-ai/dsh-workspace'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { MemoryMediaPool, MemoryStorageBackend } from '../../../storage/storage-domain/tests/helpers/memory-backend.ts'
import { WorktreeRegistry, WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import type {
  Worktree,
  WorktreeCreateRequest,
  WorktreeReconcileOptions,
  WorktreeReconcileReport,
  WorktreeRemoveOptions,
  WorktreeStatus,
} from '@deepseek-ai/dsh-worktree-registry'
import * as toolWorktree from '../src/index.ts'

/**
 * An in-memory WorktreeRegistry standing in behind ctx.worktreeRegistry. It
 * records the requests the tools make and answers with canned observations;
 * the real registry's git mechanics are covered by the registry package.
 */
class FakeWorktreeRegistry extends WorktreeRegistry {
  requests: WorktreeCreateRequest[] = []
  removed: { id: WorktreeId; force: boolean }[] = []
  reconciles: WorktreeReconcileOptions[] = []
  statusScript: (id: WorktreeId) => WorktreeStatus = () => ({ directoryExists: true, branch: 'wt-a', clean: true })
  reconcileScript: (options: WorktreeReconcileOptions) => WorktreeReconcileReport = () => ({
    dangling: [],
    unregistered: [],
    removedRows: [],
    adoptedPaths: [],
  })

  private rows = new Map<WorktreeId, Worktree>()
  private counter = 0

  async create(request: WorktreeCreateRequest): Promise<Worktree> {
    this.requests.push(request)
    this.counter += 1
    const worktree: Worktree = {
      id: WorktreeId(`wt-${this.counter}`),
      workspaceId: request.workspaceId,
      path: request.path,
      branch: request.branch ?? 'wt-a',
      createdAt: '2026-09-09T00:00:00.000Z',
      updatedAt: '2026-09-09T00:00:00.000Z',
    }
    this.rows.set(worktree.id, worktree)
    return worktree
  }

  list(workspaceId: WorkspaceId): readonly Worktree[] {
    return [...this.rows.values()].filter(row => row.workspaceId === workspaceId)
  }

  async status(id: WorktreeId): Promise<WorktreeStatus> {
    return this.statusScript(id)
  }

  async remove(id: WorktreeId, options?: WorktreeRemoveOptions): Promise<void> {
    this.removed.push({ id, force: options?.force === true })
  }

  async reconcile(_workspaceId: WorkspaceId, options?: WorktreeReconcileOptions): Promise<WorktreeReconcileReport> {
    const resolved = options ?? {}
    this.reconciles.push(resolved)
    return this.reconcileScript(resolved)
  }
}

const contexts: Context[] = []
const roots: string[] = []

afterEach(async () => {
  await Promise.all(contexts.splice(0).map(ctx => ctx.fiber.dispose()))
  await Promise.all(roots.splice(0).map(root => rm(root, { recursive: true, force: true })))
})

interface Setup {
  ctx: Context
  registry: FakeWorktreeRegistry
  workspacePath: string
  execute: (name: string, args: unknown, sessionCwd?: string | null) => Promise<ToolExecutionResult>
}

function headerFor(id: SessionId, cwd: string | undefined): SessionHeader {
  return {
    version: SESSION_FORMAT_VERSION,
    id,
    createdAt: 0,
    isSeeded: false,
    ...cwd !== undefined ? { cwd } : {},
  }
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

async function setup(): Promise<Setup> {
  const root = await mkdtemp(join(tmpdir(), 'dsh-tool-worktree-'))
  roots.push(root)
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
  // Constructing a Service mounts it: the WorktreeRegistry constructor
  // registers the `worktreeRegistry` key on this context.
  const registry = new FakeWorktreeRegistry(ctx)
  await ctx.plugin(toolWorktree)

  // The caller's workspace and a second workspace the caller must not touch.
  const workspacePath = join(root, 'workspace')
  await mkdir(workspacePath)
  await mkdir(join(root, 'other'))
  await ctx.workspaceRegistry.create(workspacePath)
  await ctx.workspaceRegistry.create(join(root, 'other'))

  const execute = (name: string, args: unknown, sessionCwd?: string | null): Promise<ToolExecutionResult> => {
    // null omits the header cwd entirely; undefined means the caller's workspace.
    const cwd = sessionCwd === undefined ? workspacePath : sessionCwd === null ? undefined : sessionCwd
    const session = Session.create(SessionId('caller'), undefined, headerFor(SessionId('caller'), cwd))
    const agent = { id: session.id, options: {}, session } as never
    return ctx.tools.execute({
      signal: new AbortController().signal,
      callId: ToolCallId('call-1'),
      name,
      arguments: args,
      agent,
    })
  }
  return { ctx, registry, workspacePath, execute }
}

describe('worktree tool authorization', () => {
  it('rejects a call without a calling agent', async () => {
    const { ctx } = await setup()
    const pending = ctx.tools.execute({
      signal: new AbortController().signal,
      callId: ToolCallId('call-1'),
      name: 'worktree_list',
      arguments: {},
    })
    const result = await pending
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain('require a calling agent')
  })

  it('rejects a session whose header carries no cwd', async () => {
    const { execute } = await setup()
    const result = await execute('worktree_list', {}, null)
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain('carries no cwd')
  })

  it('rejects a session directory that is not a registered workspace', async () => {
    const { execute, workspacePath } = await setup()
    // The temp root exists but no workspace is registered over it.
    const result = await execute('worktree_list', {}, dirname(workspacePath))
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain('not a registered workspace')
  })

  it('treats another workspace worktree id as unknown and never reaches the registry', async () => {
    const { registry, execute } = await setup()
    const foreign = await registry.create({ workspaceId: 'other-ws' as never, path: 'somewhere' })

    const status = await execute('worktree_status', { id: foreign.id })
    const remove = await execute('worktree_remove', { id: foreign.id })

    expect(status.isError).toBe(true)
    expect(textOf(status)).toContain('not registered for this workspace')
    expect(remove.isError).toBe(true)
    expect(textOf(remove)).toContain('not registered for this workspace')
    expect(registry.removed).toEqual([])
  })
})

describe('worktree tool behavior', () => {
  it('creates a worktree with the workspace-relative target resolved and renders the result', async () => {
    const { registry, execute, workspacePath } = await setup()

    const result = await execute('worktree_create', { path: 'wt-a' })

    expect(registry.requests[0]?.workspaceId).toBeTypeOf('string')
    expect(registry.requests[0]?.path).toBe(join(workspacePath, 'wt-a'))
    expect(result.isError).toBe(false)
    expect(textOf(result)).toContain('Created worktree wt-1')
    expect(textOf(result)).toContain(join(workspacePath, 'wt-a'))
    expect(textOf(result)).toContain("branch 'wt-a'")
  })

  it('passes an absolute target and an explicit branch name through', async () => {
    const { registry, execute, workspacePath } = await setup()

    await execute('worktree_create', { path: join(workspacePath, 'abs'), branch: 'feature/x' })

    expect(registry.requests[0]?.path).toBe(join(workspacePath, 'abs'))
    expect(registry.requests[0]?.branch).toBe('feature/x')
  })

  it('rejects empty path and id parameters before the registry runs', async () => {
    const { registry, execute } = await setup()

    const create = await execute('worktree_create', { path: '   ' })
    const status = await execute('worktree_status', { id: '' })

    expect(create.isError).toBe(true)
    expect(textOf(create)).toContain('non-empty string')
    expect(status.isError).toBe(true)
    expect(textOf(status)).toContain('non-empty string')
    expect(registry.requests).toEqual([])
  })

  it('lists the caller workspace registrations', async () => {
    const { execute } = await setup()
    await execute('worktree_create', { path: 'wt-a' })
    await execute('worktree_create', { path: 'wt-b' })

    const result = await execute('worktree_list', {})

    expect(result.isError).toBe(false)
    expect(textOf(result)).toContain('2 worktree(s) registered')
    expect(textOf(result)).toContain('wt-1')
    expect(textOf(result)).toContain('wt-2')
  })

  it('reports status with branch and cleanliness and names the prune recovery for a missing directory', async () => {
    const { registry, execute } = await setup()
    const created = await execute('worktree_create', { path: 'wt-a' })
    const { id } = valueOf(created) as { id: string }

    const ok = await execute('worktree_status', { id })
    expect(textOf(ok)).toContain("branch 'wt-a'")
    expect(textOf(ok)).toContain('clean: yes')

    registry.statusScript = () => ({ directoryExists: false })
    const gone = await execute('worktree_status', { id })
    expect(textOf(gone)).toContain('no longer exists')
    expect(textOf(gone)).toContain('worktree_prune')
  })

  it('removes with force and renders the removed path', async () => {
    const { registry, execute } = await setup()
    const created = await execute('worktree_create', { path: 'wt-a' })
    const { id } = valueOf(created) as { id: string }

    const result = await execute('worktree_remove', { id, force: true })

    expect(result.isError).toBe(false)
    expect(registry.removed).toEqual([{ id, force: true }])
    expect(textOf(result)).toContain(`Removed worktree ${id}`)
  })

  it('maps the prune flags to reconcile options and projects the report', async () => {
    const { registry, execute } = await setup()
    registry.reconcileScript = () => ({
      dangling: [{ id: WorktreeId('wt-9'), path: 'gone', reason: 'directory-missing' }],
      unregistered: [{ path: 'stray', branch: 'stray-branch' }],
      removedRows: [WorktreeId('wt-9')],
      adoptedPaths: ['stray'],
    })

    const observed = await execute('worktree_prune', {})
    expect(registry.reconciles[0]).toEqual({})
    expect(textOf(observed)).toContain('directory-missing')
    expect(textOf(observed)).toContain("on branch 'stray-branch'")

    const applied = await execute('worktree_prune', { pruneDangling: true, adoptUnregistered: true })
    expect(registry.reconciles[1]).toEqual({ pruneRows: true, adoptUnregistered: true })
    expect(textOf(applied)).toContain('1 registration(s) dropped')
    expect(textOf(applied)).toContain('1 worktree(s) adopted')
  })

  it('renders agreement when reconcile reports no difference', async () => {
    const { execute } = await setup()

    const result = await execute('worktree_prune', {})

    expect(textOf(result)).toContain('Registry and git agree')
  })
})
