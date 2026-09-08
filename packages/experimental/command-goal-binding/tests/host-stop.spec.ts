import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import AgentRegistry, { Inbox } from '@deepseek-ai/dsh-agent'
import type { Agent } from '@deepseek-ai/dsh-agent'
import CommandRuntime from '@deepseek-ai/dsh-commands'
import type { CommandExecution } from '@deepseek-ai/dsh-commands'
import GoalService from '@deepseek-ai/dsh-goal'
import LocalJobRegistry from '@deepseek-ai/dsh-jobs-local'
import type { JobHooks, JobOutcome } from '@deepseek-ai/dsh-jobs'
import SessionStore, { Session, SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import { WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import type { WorktreeRegistry } from '@deepseek-ai/dsh-worktree-registry'
import type { WorkspaceRegistry } from '@deepseek-ai/dsh-workspace'
import { WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type { GoalBinding } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type { DevFrameRequiredChecksConfig } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { createCommittedWorktree, drainWorktreeFixtures } from '../../devframe/tests/completion-fixtures.ts'
import { apply } from '../src/index.ts'
import { createHostStopTree, createHostWriterAcquire, createHostWriterRelease } from '../src/host-stop.ts'
import { resolveCommandGoalBindingConfig } from '../src/config.ts'
import { GoalBindingComposition } from '../src/composition.ts'
import {
  renderStopChainStoppedText,
} from '../src/command.ts'

const WORKSPACE_ID = WorkspaceId('ws-v14-host-stop')

const roots: string[] = []
const contexts: Context[] = []

afterEach(async () => {
  for (const ctx of contexts.splice(0).reverse()) await ctx.fiber.dispose()
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
  await drainWorktreeFixtures()
})

/** A fresh canonical temp directory that outlives the test body. */
function tempRoot(): string {
  const root = mkdtempSync(join(tmpdir(), 'dsh-host-stop-'))
  roots.push(root)
  return root
}

/** The approved checklist /devframe-start executes for real on one worktree. */
function startChecks(root: string): DevFrameRequiredChecksConfig {
  return {
    version: 1,
    checks: [{
      checkId: 'probe-pass',
      executable: 'node',
      arguments: ['-e', 'process.exit(0)'],
      cwd: root,
    }],
  }
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

interface TestComposition {
  readonly ctx: Context
  readonly agent: Agent
  readonly session: Session
  readonly composition: GoalBindingComposition
}

interface BootOptions {
  readonly checks: DevFrameRequiredChecksConfig
  readonly workspaceRoot: string
  readonly storageRoot: string
  readonly sessionId: SessionId
  readonly restore?: boolean
  readonly stopGraceMs?: number
  readonly mountJobs?: boolean
  /** Explicit host stop adapters; absent faces stay absent and fail closed. */
  readonly stopAdapters?: {
    readonly tree?: (root: Agent) => readonly Agent[]
    readonly processes?: () => readonly { readonly ownerSession: SessionId; readonly label: string }[]
    readonly releaseWriter?: (root: Agent) => void | Promise<void>
  }
}

/** Boot the real composition with the standard-profile services mounted. */
async function boot(options: BootOptions): Promise<TestComposition> {
  const ctx = new Context()
  contexts.push(ctx)
  await ctx.plugin(SessionStore)
  await ctx.plugin(JsonlSessionPersistence, { root: options.storageRoot })
  await ctx.plugin(CommandRuntime)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(GoalService)
  if (options.mountJobs === true) {
    await ctx.plugin(LocalJobRegistry)
    ctx.effect(function* () { yield ctx.jobs.attachController('host-stop-spec') }, 'host-stop-spec-jobs')
  }
  const resolved = resolveCommandGoalBindingConfig({
    workspaceId: WORKSPACE_ID,
    requiredChecksPath: join(options.storageRoot, 'required-checks.json'),
    checks: options.checks,
    taskIds: ['task-v14-host-stop'],
    maxAttempts: 3,
    workspaceRoot: options.workspaceRoot,
    stopChain: true,
    ...(options.stopGraceMs === undefined ? {} : { stopGraceMs: options.stopGraceMs }),
  })
  const composition = new GoalBindingComposition(ctx, resolved, {
    stop: options.stopAdapters === undefined ? {} : {
      ...(options.stopAdapters.tree === undefined ? {} : { tree: options.stopAdapters.tree }),
      ...(options.stopAdapters.processes === undefined ? {} : { processes: options.stopAdapters.processes }),
      ...(options.stopAdapters.releaseWriter === undefined ? {} : { releaseWriter: options.stopAdapters.releaseWriter }),
    },
  })
  let session: Session
  if (options.restore === true) {
    const preparation = await ctx.sessionPersistence.prepare(options.sessionId)
    session = preparation.session
    ctx.effect(function* () {
      yield ctx.sessions.enter(session)
      ctx.sessions.announce(session)
    }, 'host-stop-spec-restore')
    preparation[Symbol.dispose]()
  } else {
    session = ctx.sessions.create(options.sessionId)
  }
  const agent = stubAgent(session)
  ctx.agents.register(agent)
  return { ctx, agent, session, composition }
}

/** Execute one slash command through the same registry boundary as a UI adapter. */
async function execute(test: TestComposition, line: string): Promise<CommandExecution> {
  const execution = await test.ctx.commands.execute(test.agent, line, [], new AbortController().signal)
  if (execution === undefined) throw new Error('expected command was not registered')
  return execution
}

/** Every logged goal-binding event payload, in log order. */
function goalBindingEvents(test: TestComposition): GoalBinding[] {
  return test.session.snapshotEvents()
    .filter(candidate => candidate.type === 'devframe/goal-binding')
    .map(candidate => (candidate as { readonly data: GoalBinding }).data)
}

/** The lifecycle sequence the goal's binding records fold through. */
function lifecycleSequence(test: TestComposition): string[] {
  return goalBindingEvents(test).map(binding => binding.lifecycle)
}

/** Start one real owned job whose cancel settles after `settleMs`. */
function startSlowCancelJob(test: TestComposition, owner: Agent, settleMs: number): { cancelled: () => boolean } {
  let cancelRequested = false
  let settleJob: (outcome: JobOutcome) => void = () => {}
  const done = new Promise<JobOutcome>((resolve) => { settleJob = resolve })
  test.ctx.jobs.start({
    kind: 'bash',
    label: `slow-cancel-${Math.random().toString(36).slice(2)}`,
    owner,
    run: (): JobHooks => ({
      cancel: () => {
        cancelRequested = true
        void delay(settleMs).then(() => { settleJob({ status: 'killed', detail: 'project stop' }) })
      },
      done,
    }),
  })
  return { cancelled: () => cancelRequested }
}

describe('host stop tree', () => {
  it('resolves the tree by dispatch lineage: descendants on independent worktrees belong', async () => {
    const worktree = tempRoot()
    const independent = tempRoot()
    const { ctx, agent } = await boot({ checks: startChecks(worktree), workspaceRoot: worktree, storageRoot: tempRoot(), sessionId: SessionId('tree-root') })
    const lead = stubAgent(ctx.sessions.create(SessionId('tree-lead'), { meta: { cwd: worktree, parentSession: agent.session.id } }))
    ctx.agents.register(lead)
    // The counterexample case: an explicit-bound worker whose own cwd is an
    // independent worktree — lineage, not cwd equality, owns membership.
    const worker = stubAgent(ctx.sessions.create(SessionId('tree-worker'), { meta: { cwd: independent, parentSession: lead.session.id } }))
    ctx.agents.register(worker)
    // A session of the same repository with no lineage binding: never drained.
    ctx.agents.register(stubAgent(ctx.sessions.create(SessionId('tree-stranger'), { meta: { cwd: worktree } })))
    // A foreign root of an unrelated project: its lineage never reaches ours.
    ctx.agents.register(stubAgent(ctx.sessions.create(SessionId('tree-foreign'), { meta: { cwd: independent } })))

    const tree = createHostStopTree(ctx.agents)

    expect(tree(agent).map(entry => String(entry.id)).sort()).toEqual(
      [agent, lead, worker].map(entry => String(entry.id)).sort(),
    )
  })

  it('bounds the lineage walk so a corrupt parent cycle cannot hang the drain', async () => {
    const worktree = tempRoot()
    const { ctx, agent } = await boot({ checks: startChecks(worktree), workspaceRoot: worktree, storageRoot: tempRoot(), sessionId: SessionId('tree-cycle-root') })
    const cyclic = stubAgent(ctx.sessions.create(SessionId('tree-cycle-a'), { meta: { cwd: worktree, parentSession: SessionId('tree-cycle-b') } }))
    const cyclicParent = stubAgent(ctx.sessions.create(SessionId('tree-cycle-b'), { meta: { cwd: worktree, parentSession: cyclic.session.id } }))
    ctx.agents.register(cyclic)
    ctx.agents.register(cyclicParent)

    const tree = createHostStopTree(ctx.agents)

    expect(tree(agent).map(entry => String(entry.id))).toEqual([String(agent.id)])
  })

  it('excludes a lineage that leaves the live registry and re-reads liveness per call', async () => {
    const worktree = tempRoot()
    const { ctx, agent } = await boot({ checks: startChecks(worktree), workspaceRoot: worktree, storageRoot: tempRoot(), sessionId: SessionId('tree-live-root') })
    const tree = createHostStopTree(ctx.agents)
    expect(tree(agent).map(entry => String(entry.id))).toEqual([String(agent.id)])

    const child = stubAgent(ctx.sessions.create(SessionId('tree-live-child'), { meta: { cwd: worktree, parentSession: agent.session.id } }))
    const disposer = ctx.agents.register(child)
    expect(tree(agent).map(entry => String(entry.id)).sort()).toEqual([String(agent.id), String(child.id)].sort())
    disposer()
    expect(tree(agent).map(entry => String(entry.id))).toEqual([String(agent.id)])
  })
})

describe('host writer release', () => {
  interface FakeRegistry {
    readonly registry: WorktreeRegistry
    readonly workspaces: WorkspaceRegistry
    readonly released: Array<{ readonly id: string; readonly holder: string }>
    readonly bound: Array<{ readonly id: string; readonly holder: string }>
    bindRow(holder: WorktreeLockHolder | undefined): void
    rejectUnbindWith(error: Error): void
  }

  /** A worktree registry standing in for the durable rows the adapter reads. */
  function fakeRegistries(worktreePath: string, extraWorkspacePath?: string): FakeRegistry {
    const mutableRow = {
      id: 'wt-1',
      workspaceId: WORKSPACE_ID,
      path: worktreePath,
      branch: 'main',
      createdAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-01T00:00:00.000Z',
      lockedBy: undefined as WorktreeLockHolder | undefined,
    }
    const released: FakeRegistry['released'] = []
    const bound: FakeRegistry['bound'] = []
    let unbindError: Error | undefined
    const registry = {
      list: (workspaceId: typeof WORKSPACE_ID) => (workspaceId === WORKSPACE_ID ? [mutableRow] : []),
      unbind: async (id: string, holder: WorktreeLockHolder) => {
        if (unbindError !== undefined) throw unbindError
        released.push({ id, holder: String(holder) })
        mutableRow.lockedBy = undefined
        return mutableRow
      },
      // The registry contract: an unbound row or the same holder re-binds; a
      // foreign holder is refused without displacement.
      bind: async (id: string, holder: WorktreeLockHolder) => {
        if (mutableRow.lockedBy !== undefined && mutableRow.lockedBy !== holder) {
          throw new Error('already-locked')
        }
        bound.push({ id, holder: String(holder) })
        mutableRow.lockedBy = holder
        return mutableRow
      },
    }
    const workspaces = {
      list: () => [
        { id: WORKSPACE_ID, path: worktreePath },
        ...(extraWorkspacePath === undefined ? [] : [{ id: WorkspaceId('ws-v14-host-stop-extra'), path: extraWorkspacePath }]),
      ],
    } as unknown as WorkspaceRegistry
    return {
      registry: registry as unknown as WorktreeRegistry,
      workspaces,
      released,
      bound,
      bindRow: (holder) => { mutableRow.lockedBy = holder },
      rejectUnbindWith: (error) => { unbindError = error },
    }
  }

  it('awaits the registry release and settles only when the binding is provably cleared', async () => {
    const worktree = tempRoot()
    const { ctx, agent } = await boot({ checks: startChecks(worktree), workspaceRoot: worktree, storageRoot: tempRoot(), sessionId: SessionId('release-root') })
    const tree = createHostStopTree(ctx.agents)
    const fake = fakeRegistries(worktree)
    fake.bindRow(WorktreeLockHolder(String(agent.session.id)))

    const release = createHostWriterRelease(
      { workspaceRegistry: fake.workspaces, worktreeRegistry: fake.registry },
      { workspaceRoot: worktree, tree },
    )
    await release(agent)

    expect(fake.released).toHaveLength(1)
    expect(fake.released[0]!.holder).toBe(String(agent.session.id))
  })

  it('propagates a rejected unbind so the chain reports the writer as retained', async () => {
    const worktree = tempRoot()
    const { ctx, agent } = await boot({ checks: startChecks(worktree), workspaceRoot: worktree, storageRoot: tempRoot(), sessionId: SessionId('release-reject') })
    const tree = createHostStopTree(ctx.agents)
    const fake = fakeRegistries(worktree)
    fake.bindRow(WorktreeLockHolder(String(agent.session.id)))
    fake.rejectUnbindWith(new Error('durable write failed'))

    const release = createHostWriterRelease(
      { workspaceRegistry: fake.workspaces, worktreeRegistry: fake.registry },
      { workspaceRoot: worktree, tree },
    )

    await expect(release(agent)).rejects.toThrow('durable write failed')
    expect(fake.released).toHaveLength(0)
  })

  it('refuses a foreign holder and treats an unbound row as already released', async () => {
    const worktree = tempRoot()
    const { ctx, agent } = await boot({ checks: startChecks(worktree), workspaceRoot: worktree, storageRoot: tempRoot(), sessionId: SessionId('release-foreign') })
    const tree = createHostStopTree(ctx.agents)
    const fake = fakeRegistries(worktree)
    fake.bindRow(WorktreeLockHolder('foreign-session'))

    const release = createHostWriterRelease(
      { workspaceRegistry: fake.workspaces, worktreeRegistry: fake.registry },
      { workspaceRoot: worktree, tree },
    )
    await expect(release(agent)).rejects.toThrow('not a live project tree session')

    fake.bindRow(undefined)
    await expect(release(agent)).resolves.toBeUndefined()
    expect(fake.released).toHaveLength(0)
  })

  it('re-takes the binding on resume and stays idempotent for the same writer', async () => {
    const worktree = tempRoot()
    const { ctx, agent } = await boot({ checks: startChecks(worktree), workspaceRoot: worktree, storageRoot: tempRoot(), sessionId: SessionId('acquire-root') })
    const fake = fakeRegistries(worktree)

    const acquire = createHostWriterAcquire(
      { agents: ctx.agents, workspaceRegistry: fake.workspaces, worktreeRegistry: fake.registry },
      { workspaceRoot: worktree },
    )
    await acquire(agent)
    expect(fake.bound).toHaveLength(1)
    expect(fake.bound[0]!.holder).toBe(String(agent.session.id))

    // The confirmed-stop recovery path may re-enter over the writer's own binding.
    fake.bindRow(WorktreeLockHolder(String(agent.session.id)))
    await acquire(agent)
    expect(fake.bound).toHaveLength(2)
  })

  it('refuses a foreign-held binding without displacing the writer', async () => {
    const worktree = tempRoot()
    const { ctx, agent } = await boot({ checks: startChecks(worktree), workspaceRoot: worktree, storageRoot: tempRoot(), sessionId: SessionId('acquire-foreign') })
    const fake = fakeRegistries(worktree)
    fake.bindRow(WorktreeLockHolder('foreign-session'))

    const acquire = createHostWriterAcquire(
      { agents: ctx.agents, workspaceRegistry: fake.workspaces, worktreeRegistry: fake.registry },
      { workspaceRoot: worktree },
    )
    await expect(acquire(agent)).rejects.toThrow('already-locked')
    expect(fake.bound).toHaveLength(0)
    expect(fake.released).toHaveLength(0)
  })

  it('refuses a receiving root that is not live and a worktree outside its registered row', async () => {
    const worktree = tempRoot()
    const rowlessRoot = tempRoot()
    const { ctx, agent } = await boot({ checks: startChecks(worktree), workspaceRoot: worktree, storageRoot: tempRoot(), sessionId: SessionId('acquire-gate') })
    const fake = fakeRegistries(worktree, rowlessRoot)
    const acquire = createHostWriterAcquire(
      { agents: ctx.agents, workspaceRegistry: fake.workspaces, worktreeRegistry: fake.registry },
      { workspaceRoot: worktree },
    )

    const ghost = stubAgent(ctx.sessions.create(SessionId('acquire-ghost'), {}))
    await expect(acquire(ghost)).rejects.toThrow('not a live agent')
    expect(fake.bound).toHaveLength(0)

    // The extra workspace is registered but owns no row at that path.
    const rowless = createHostWriterAcquire(
      { agents: ctx.agents, workspaceRegistry: fake.workspaces, worktreeRegistry: fake.registry },
      { workspaceRoot: rowlessRoot },
    )
    await expect(rowless(agent)).rejects.toThrow('no registered worktree row')
    expect(fake.bound).toHaveLength(0)
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

  it('mounts the lineage tree face and no fabricated process inventory', async () => {
    const worktree = tempRoot()
    const storageRoot = tempRoot()
    const ctx = new Context()
    contexts.push(ctx)
    await ctx.plugin(SessionStore)
    await ctx.plugin(JsonlSessionPersistence, { root: storageRoot })
    await ctx.plugin(CommandRuntime)
    await ctx.plugin(AgentRegistry)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(GoalService)
    const session = ctx.sessions.create(SessionId('apply-root'))
    const agent = stubAgent(session)
    ctx.agents.register(agent)
    const composition = apply(ctx, compositionConfig(worktree))

    expect(composition).toBeInstanceOf(GoalBindingComposition)
    const stores = composition as unknown as {
      stopTree?: (root: Agent) => readonly Agent[]
      stopProcesses?: unknown
      stopReleaseWriter?: unknown
    }
    expect(stores.stopTree).toBeTypeOf('function')
    expect(stores.stopTree!(agent).map(entry => String(entry.id))).toEqual([String(agent.id)])
    // The process inventory is never fabricated: an unprovable inventory must
    // fail closed, so the apply face mounts no face at all.
    expect(stores.stopProcesses).toBeUndefined()
    // The worktree registries are not mounted on this bare fiber.
    expect(stores.stopReleaseWriter).toBeUndefined()
  })

  it('keeps the tree unwired without an agent registry so the chain fails closed', async () => {
    const ctx = new Context()
    contexts.push(ctx)
    await ctx.plugin(SessionStore)
    await ctx.plugin(JsonlSessionPersistence, { root: tempRoot() })
    await ctx.plugin(CommandRuntime)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(GoalService)
    const composition = apply(ctx, compositionConfig(tempRoot()))
    const stores = composition as unknown as { stopTree?: unknown; stopProcesses?: unknown }
    expect(stores.stopTree).toBeUndefined()
    expect(stores.stopProcesses).toBeUndefined()
  })
})

describe('stop chain over the real host adapters', () => {
  it('drains an independent-worktree descendant and releases the writer', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = tempRoot()
    const independent = tempRoot()
    const sessionId = SessionId('chain-independent-root')
    const childSessionId = SessionId('chain-independent-worker')
    // The face evaluates when the chain runs, after the boot hands back the
    // registry the real face walks.
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      mountJobs: true,
      stopAdapters: {
        tree: root => treeFace(root),
        // The host asserts its captured-process inventory explicitly.
        processes: () => [],
        releaseWriter: () => {},
      },
    })
    const treeFace = createHostStopTree(first.ctx.agents)
    // The counterexample's positive case: an explicit-bound worker whose own
    // cwd is an independent worktree — the lineage tree face includes it and
    // the chain drains its owned job.
    const childSession = first.ctx.sessions.create(childSessionId, { meta: { cwd: independent, parentSession: first.agent.session.id } })
    const child = stubAgent(childSession)
    first.ctx.agents.register(child)
    const childJob = startSlowCancelJob(first, child, 150)

    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')
    const stopped = await execute(first, '/devframe-stop')
    if (stopped.result.kind !== 'success') {
      throw new Error(`expected a success result: ${stopped.result.text}`)
    }
    expect(stopped.result.text).toBe(renderStopChainStoppedText())
    expect(childJob.cancelled()).toBe(true)
    expect(lifecycleSequence(first).at(-1)).toBe('stopped')
  })

  it('refuses quiescence by name when no process inventory face is mounted', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = tempRoot()
    const sessionId = SessionId('chain-no-inventory-root')
    let releaseCalls = 0
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      mountJobs: true,
      stopAdapters: {
        tree: () => (self === undefined ? [] : [self.agent]),
        releaseWriter: () => { releaseCalls += 1 },
      },
    })
    const self = first
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')

    // No mounted inventory face means the chain has no provable process
    // inventory: the refusal must be named and the release must never run —
    // emptiness is never read as quiescence.
    const stopped = await execute(first, '/devframe-stop')
    expect(stopped.result.kind).toBe('error')
    if (stopped.result.kind === 'error') {
      expect(stopped.result.text).toContain('processes:inventory: operation_failed')
      expect(stopped.result.text).toContain('The writer remains held')
    }
    expect(releaseCalls).toBe(0)
    expect(lifecycleSequence(first).at(-1)).toBe('needs_attention')
  })

  it('keeps the writer held when the release stays pending past the grace bound', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = tempRoot()
    const sessionId = SessionId('chain-pending-root')
    let settleRelease: () => void = () => {}
    const releaseGate = new Promise<void>((resolve) => { settleRelease = resolve })
    let releaseCalls = 0
    // The face evaluates when the chain runs, after the boot hands back the
    // root the fixture tree returns.
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      stopGraceMs: 300,
      mountJobs: true,
      stopAdapters: {
        tree: () => (self === undefined ? [] : [self.agent]),
        processes: () => [],
        releaseWriter: () => {
          releaseCalls += 1
          return releaseGate
        },
      },
    })
    const self = first
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')

    const stopped = await execute(first, '/devframe-stop')
    expect(stopped.result.kind).toBe('error')
    if (stopped.result.kind === 'error') {
      expect(stopped.result.text).toContain('writer:release: timeout')
      expect(stopped.result.text).toContain('The writer remains held')
    }
    expect(releaseCalls).toBe(1)
    expect(lifecycleSequence(first).at(-1)).toBe('needs_attention')

    // The pending release settles late; the repeat stop re-enters and the
    // now-settled release lands the stopped terminal.
    settleRelease()
    const rerun = await execute(first, '/devframe-stop')
    expect(rerun.result.kind).toBe('success')
    if (rerun.result.kind === 'success') expect(rerun.result.text).toBe(renderStopChainStoppedText())
    expect(releaseCalls).toBe(2)
    expect(lifecycleSequence(first).at(-1)).toBe('stopped')
    const stored = await first.composition.bindingStore.load(ControllerSessionId(first.agent.id))
    expect(stored.at(-1)?.lifecycle).toBe('stopped')
  })

  it('reports a rejected release as needs_attention and converges on the rerun', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = tempRoot()
    const sessionId = SessionId('chain-reject-root')
    let rejections = 1
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      mountJobs: true,
      stopAdapters: {
        tree: () => (self === undefined ? [] : [self.agent]),
        processes: () => [],
        releaseWriter: () => {
          if (rejections > 0) {
            rejections -= 1
            throw new Error('durable write failed')
          }
        },
      },
    })
    const self = first
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')

    const stopped = await execute(first, '/devframe-stop')
    expect(stopped.result.kind).toBe('error')
    if (stopped.result.kind === 'error') {
      // The release rejection must be named; a contended flush may add its own
      // bounded issue, so the assertion names the release rather than the whole
      // resource list.
      expect(stopped.result.text).toContain('writer:release: operation_failed')
      expect(stopped.result.text).toContain('The writer remains held')
    }
    expect(lifecycleSequence(first).at(-1)).toBe('needs_attention')

    const rerun = await execute(first, '/devframe-stop')
    expect(rerun.result.kind).toBe('success')
    if (rerun.result.kind === 'success') expect(rerun.result.text).toBe(renderStopChainStoppedText())
    expect(lifecycleSequence(first).at(-1)).toBe('stopped')
  })

  it('re-enters only the release after a cold restart left the log quiescence-confirmed', async () => {
    const fixture = await createCommittedWorktree()
    const storageRoot = tempRoot()
    const sessionId = SessionId('chain-restart-root')
    const first = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      mountJobs: true,
      stopAdapters: {
        processes: () => [],
        releaseWriter: () => {},
      },
    })
    expect((await execute(first, '/devframe-start fix the billing bug')).result.kind).toBe('success')
    // Simulate the crash state exactly: the drain confirmed quiescence
    // durably, then the process died before the release and the terminal
    // bookkeeping. The repeat stop must NOT be refused.
    const started = goalBindingEvents(first)[0]
    if (started === undefined) throw new Error('started binding is missing')
    first.session.append('devframe/goal-binding', { ...started, lifecycle: 'stop_requested' })
    first.session.append('devframe/goal-binding', { ...started, lifecycle: 'quiescence_confirmed' })
    await first.ctx.sessions.flush(first.session)
    contexts.splice(contexts.indexOf(first.ctx), 1)
    await first.ctx.fiber.dispose()

    const releaseOrder: string[] = []
    const second = await boot({
      checks: startChecks(fixture.root),
      workspaceRoot: fixture.root,
      storageRoot,
      sessionId,
      restore: true,
      mountJobs: true,
      stopAdapters: {
        tree: () => (secondSelf === undefined ? [] : [secondSelf.agent]),
        processes: () => [],
        releaseWriter: () => { releaseOrder.push('releaseWriter') },
      },
    })
    const secondSelf = second
    const stopped = await execute(second, '/devframe-stop')
    expect(stopped.result.kind).toBe('success')
    if (stopped.result.kind === 'success') expect(stopped.result.text).toBe(renderStopChainStoppedText())
    expect(releaseOrder).toEqual(['releaseWriter'])
    expect(lifecycleSequence(second).at(-1)).toBe('stopped')
    const stored = await second.composition.bindingStore.load(ControllerSessionId(second.agent.id))
    expect(stored.at(-1)?.lifecycle).toBe('stopped')
  })
})
