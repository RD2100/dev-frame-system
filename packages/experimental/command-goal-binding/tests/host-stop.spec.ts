import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import AgentRegistry, { Inbox } from '@deepseek-ai/dsh-agent'
import type { Agent } from '@deepseek-ai/dsh-agent'
import CommandRuntime from '@deepseek-ai/dsh-commands'
import GoalService from '@deepseek-ai/dsh-goal'
import SessionStore, { Session, SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import type { SubprocessHandle } from '@deepseek-ai/dsh-subprocess'
import { WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import type { StopProcess } from '@deepseek-ai/dsh-experimental-devframe'
import { WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import type { Worktree, WorktreeId, WorktreeRegistry } from '@deepseek-ai/dsh-worktree-registry'
import type { WorkspaceRegistry } from '@deepseek-ai/dsh-workspace'
import { apply, hostStopInventoryOf } from '../src/index.ts'
import { createHostStopTree, createHostWriterRelease, HostStopProcessInventory } from '../src/host-stop.ts'
import { GoalBindingComposition } from '../src/composition.ts'

const WORKSPACE_ID = WorkspaceId('ws-v14-host-stop')

const roots: string[] = []
const contexts: Context[] = []

afterEach(async () => {
  for (const ctx of contexts.splice(0).reverse()) await ctx.fiber.dispose()
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

/** A fresh canonical temp directory that outlives the test body. */
function tempRoot(): string {
  const root = mkdtempSync(join(tmpdir(), 'dsh-host-stop-'))
  roots.push(root)
  return root
}

/** Build a live idle agent accepted by the exact-identity goal service. */
function stubAgent(session: Session): Agent {
  const inbox = new Inbox(session, { inserted: () => {}, discarded: () => {}, claimed: () => {} })
  return {
    id: session.id,
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
}

interface TestFiber {
  readonly ctx: Context
  readonly agent: Agent
}

/** Mount the minimal standard-profile services on a fresh fiber. */
async function boot(options: { readonly cwd: string; readonly sessionId: string }): Promise<TestFiber> {
  const ctx = new Context()
  contexts.push(ctx)
  await ctx.plugin(SessionStore)
  await ctx.plugin(JsonlSessionPersistence, { root: tempRoot() })
  await ctx.plugin(CommandRuntime)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(GoalService)
  const session = ctx.sessions.create(SessionId(options.sessionId), { meta: { cwd: options.cwd } })
  const agent = stubAgent(session)
  ctx.agents.register(agent)
  return { ctx, agent }
}

describe('host stop tree', () => {
  it('returns the live agents of the configured worktree and excludes every other cwd', async () => {
    const worktree = tempRoot()
    const foreign = tempRoot()
    const { ctx, agent } = await boot({ cwd: worktree, sessionId: 'host-stop-root' })
    const child = ctx.sessions.create(SessionId('host-stop-child'), {
      meta: { cwd: worktree, parentSession: agent.session.id },
    })
    ctx.agents.register(stubAgent(child))
    ctx.agents.register(stubAgent(ctx.sessions.create(SessionId('host-stop-stranger'), {
      meta: { cwd: foreign, parentSession: agent.session.id },
    })))
    const cwdless = ctx.sessions.create(SessionId('host-stop-cwdless'))
    ctx.agents.register(stubAgent(cwdless))

    const tree = createHostStopTree(ctx.agents, { workspaceRoot: worktree })

    expect(tree().map(entry => entry.id).sort()).toEqual(
      [agent.id, child.id].map(String).sort(),
    )
  })

  it('re-reads the live registry on every call so a stopped agent leaves the tree', async () => {
    const worktree = tempRoot()
    const { ctx, agent } = await boot({ cwd: worktree, sessionId: 'host-stop-live' })
    const tree = createHostStopTree(ctx.agents, { workspaceRoot: worktree })
    expect(tree()).toHaveLength(1)

    const disposer = ctx.agents.register(stubAgent(ctx.sessions.create(SessionId('host-stop-leaving'), { meta: { cwd: worktree } })))
    expect(tree()).toHaveLength(2)
    disposer()
    expect(tree()).toHaveLength(1)
    expect(String(agent.id)).toBeTruthy()
  })
})

describe('host stop process inventory', () => {
  it('captures, replaces by identity, forgets, and lists in capture order', () => {
    const inventory = new HostStopProcessInventory()
    const handle = { terminate: () => {} } as unknown as SubprocessHandle
    const first: StopProcess = { ownerSession: SessionId('inv-owner'), label: 'probe', operationId: 'op-1', handle }
    const reconciled: StopProcess = { ownerSession: SessionId('inv-owner'), label: 'probe', operationId: 'op-2' }
    inventory.capture(first)
    inventory.capture(reconciled)
    expect(inventory.list()).toEqual([first, reconciled])

    const refreshed: StopProcess = { ownerSession: SessionId('inv-owner'), label: 'probe', operationId: 'op-1', handle }
    inventory.capture(refreshed)
    expect(inventory.list()).toEqual([refreshed, reconciled])

    inventory.forget({ ownerSession: SessionId('inv-owner'), label: 'probe', operationId: 'op-1' })
    expect(inventory.list()).toEqual([reconciled])
  })
})

describe('host writer release', () => {
  interface FakeRegistry {
    readonly registry: WorktreeRegistry
    readonly workspaces: WorkspaceRegistry
    readonly released: Array<{ readonly id: WorktreeId; readonly holder: WorktreeLockHolder }>
    bindRow(holder: WorktreeLockHolder | undefined): void
    rejectUnbindWith(error: Error): void
  }

  /** A worktree registry standing in for the durable rows the adapter reads. */
  function fakeRegistries(worktreePath: string): FakeRegistry {
    const worktreeId = 'wt-1' as WorktreeId
    const mutableRow = {
      id: worktreeId,
      workspaceId: WORKSPACE_ID,
      path: worktreePath,
      branch: 'main',
      createdAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-01T00:00:00.000Z',
      lockedBy: undefined as WorktreeLockHolder | undefined,
    }
    const row = mutableRow as Worktree
    const released: FakeRegistry['released'] = []
    let unbindError: Error | undefined
    const registry = {
      list: (workspaceId: typeof WORKSPACE_ID) => (workspaceId === WORKSPACE_ID ? [row] : []),
      unbind: async (id: WorktreeId, holder: WorktreeLockHolder) => {
        if (unbindError !== undefined) throw unbindError
        released.push({ id, holder })
        mutableRow.lockedBy = undefined
        return row
      },
    } as unknown as WorktreeRegistry
    const workspaces = {
      list: () => [{ id: WORKSPACE_ID, path: worktreePath }],
    } as unknown as WorkspaceRegistry
    return {
      registry,
      workspaces,
      released,
      bindRow: holder => { mutableRow.lockedBy = holder },
      rejectUnbindWith: error => { unbindError = error },
    }
  }

  async function releaseFixture(): Promise<{
    readonly ctx: Context
    readonly tree: () => readonly Agent[]
    readonly fake: FakeRegistry
    readonly worktree: string
    readonly warnings: string[]
  }> {
    const worktree = tempRoot()
    const { ctx } = await boot({ cwd: worktree, sessionId: 'release-root' })
    return {
      ctx,
      tree: createHostStopTree(ctx.agents, { workspaceRoot: worktree }),
      fake: fakeRegistries(worktree),
      worktree,
      warnings: [],
    }
  }

  it('releases the binding of a live tree session with the exact holder', async () => {
    const { ctx, tree, fake, warnings } = await releaseFixture()
    fake.bindRow(WorktreeLockHolder(String(ctx.agents.list()[0]!.session.id)))

    const release = createHostWriterRelease(
      { agents: ctx.agents, workspaceRegistry: fake.workspaces, worktreeRegistry: fake.registry, log: message => { warnings.push(message) } },
      { workspaceRoot: fake.workspaces.list()[0]!.path, tree },
    )
    release()

    expect(fake.released).toHaveLength(1)
    expect(String(fake.released[0]!.holder)).toBe(String(ctx.agents.list()[0]!.session.id))
    expect(warnings).toHaveLength(0)
  })

  it('treats an unbound worktree as an already-completed release', async () => {
    const { tree, fake, warnings } = await releaseFixture()
    fake.bindRow(undefined)
    const release = createHostWriterRelease(
      { agents: { ctx: new Context() } as unknown as AgentRegistry, workspaceRegistry: fake.workspaces, worktreeRegistry: fake.registry, log: message => { warnings.push(message) } },
      { workspaceRoot: fake.workspaces.list()[0]!.path, tree },
    )
    expect(() => release()).not.toThrow()
    expect(fake.released).toHaveLength(0)
  })

  it('refuses and retains the writer when the holder is not a live tree session', async () => {
    const { tree, fake, warnings } = await releaseFixture()
    fake.bindRow(WorktreeLockHolder('foreign-session'))
    const release = createHostWriterRelease(
      { agents: { ctx: new Context() } as unknown as AgentRegistry, workspaceRegistry: fake.workspaces, worktreeRegistry: fake.registry, log: message => { warnings.push(message) } },
      { workspaceRoot: fake.workspaces.list()[0]!.path, tree },
    )
    expect(() => release()).toThrow('not a live project tree session')
    expect(fake.released).toHaveLength(0)
  })

  it('refuses when the configured worktree has no registered row', async () => {
    const { tree, fake, warnings } = await releaseFixture()
    const release = createHostWriterRelease(
      { agents: { ctx: new Context() } as unknown as AgentRegistry, workspaceRegistry: fake.workspaces, worktreeRegistry: fake.registry, log: message => { warnings.push(message) } },
      { workspaceRoot: `${fake.workspaces.list()[0]!.path}-missing`, tree },
    )
    expect(() => release()).toThrow('registered workspace')
  })

  it('keeps the writer bound and reports loudly when the registry unbind rejects', async () => {
    const { ctx, tree, fake, warnings } = await releaseFixture()
    fake.bindRow(WorktreeLockHolder(String(ctx.agents.list()[0]!.session.id)))
    fake.rejectUnbindWith(new Error('durable write failed'))
    const release = createHostWriterRelease(
      { agents: ctx.agents, workspaceRegistry: fake.workspaces, worktreeRegistry: fake.registry, log: message => { warnings.push(message) } },
      { workspaceRoot: fake.workspaces.list()[0]!.path, tree },
    )

    release()
    await new Promise(resolve => setImmediate(resolve))

    expect(warnings).toHaveLength(1)
    expect(warnings[0]).toContain('durable write failed')
    expect(fake.released).toHaveLength(0)
  })
})

describe('apply face wiring', () => {
  function compositionConfig(workspaceRoot: string | undefined) {
    const storageRoot = tempRoot()
    return {
      workspaceId: WORKSPACE_ID,
      requiredChecksPath: join(storageRoot, 'required-checks.json'),
      checks: {
        version: 1 as const,
        checks: [{ checkId: 'probe-pass', executable: 'node', arguments: ['-e', 'process.exit(0)'], cwd: storageRoot }],
      },
      taskIds: ['task-v14-host-stop'],
      maxAttempts: 3,
      stopChain: true,
      ...(workspaceRoot === undefined ? {} : { workspaceRoot }),
    }
  }

  it('mounts the real tree and process faces and the reachable inventory on the fiber', async () => {
    const worktree = tempRoot()
    const { ctx, agent } = await boot({ cwd: worktree, sessionId: 'apply-face-root' })
    const composition = apply(ctx, compositionConfig(worktree))

    expect(composition).toBeInstanceOf(GoalBindingComposition)
    const stores = composition as unknown as {
      stopTree?: () => readonly Agent[]
      stopProcesses?: () => readonly StopProcess[]
      stopReleaseWriter?: unknown
    }
    expect(stores.stopTree).toBeTypeOf('function')
    expect(stores.stopTree!().map(entry => entry.id)).toEqual([agent.id])
    expect(stores.stopReleaseWriter).toBeUndefined()

    const inventory = hostStopInventoryOf(ctx)
    expect(inventory).toBeInstanceOf(HostStopProcessInventory)
    const handle = { terminate: () => {} } as unknown as SubprocessHandle
    inventory!.capture({ ownerSession: agent.id, label: 'probe', handle })
    expect(stores.stopProcesses!()).toEqual([{ ownerSession: agent.id, label: 'probe', handle }])
  })

  it('keeps the tree unwired without a configured worktree so the chain fails closed', async () => {
    const { ctx } = await boot({ cwd: tempRoot(), sessionId: 'apply-face-noroot' })
    const composition = apply(ctx, compositionConfig(undefined))
    const stores = composition as unknown as { stopTree?: unknown; stopProcesses?: unknown }
    expect(stores.stopTree).toBeUndefined()
    expect(stores.stopProcesses).toBeTypeOf('function')
  })
})
