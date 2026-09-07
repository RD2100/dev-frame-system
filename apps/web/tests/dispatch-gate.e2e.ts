// The model-driven full-chain dispatch gate over the real web composition
// (组合验收 C-line face). The flow is B1's proven one: workspaceRegistry.create
// → worktreeRegistry.create trees → a bound controller →
// agentDispatch.createChildAgent for the lead and then the worker, every
// dispatch asserted against its durable binding record, the worktree's
// single-writer lock, and the child's own session facts, and the four entry
// denials observed as classified AgentDispatchError codes. Controller and
// lead make no model calls (the B1 shape); the worker rounds are the
// model-driven face — a replayed turn on the keyless lane and, behind
// DSH_DISPATCH_GATE=real, one real round on the scenario's approved gateway
// route with a pwsh artifact check.
//
// Admission boundary (总控 relay of the external read-only verification): this
// gate covers the dispatch chain only. The product admission gate's real
// coverage is the controller submitted/admission state machine — submit only
// checks `reviewing`, requestMainTreeMerge only checks
// controller/submitted/admission, and integrate consumes an in-memory marker
// without executing Git — while the merge-request consumer across
// packages/apps is tests-only and lead review plus source-fingerprint reads
// are not wired into that flow. This scenario therefore asserts no admission
// or merge fact, and its evidence must never present a scripted merge as an
// admission-gate pass.
import { execFile } from 'node:child_process'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { AgentDispatch } from '@deepseek-ai/dsh-experimental-agent-dispatch'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { SessionId, type SessionEvent } from '@deepseek-ai/dsh-session'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { WorktreeId, WorktreeLockHolder, type Worktree } from '@deepseek-ai/dsh-worktree-registry'
import { launchWebScaffold, type WebScaffold } from './scaffold.ts'

const OVERLAY = fileURLToPath(new URL('./dispatch-gate.overlay.yml', import.meta.url))
// The rows the overlay inserts name these packages; no carrier layer depends
// on them yet, so each package dir rides the scaffold's overlay-package
// mechanism (self-linked, peer closure supplying the injected services).
const OVERLAY_PACKAGE_DIRS = [
  fileURLToPath(new URL('../../../packages/experimental/agent-dispatch', import.meta.url)),
  fileURLToPath(new URL('../../../packages/experimental/agent-hierarchy', import.meta.url)),
  fileURLToPath(new URL('../../../packages/experimental/session-identity', import.meta.url)),
]

// The real gate round rides the win32 lane's approved gateway account; the
// key comes from the runner's environment, the credential never lands in this
// file, and the isolated harness home holds the provider profile. One real
// round per 总控 notification — limited attempts.
const WIN32_ROUTE = 'huoshan-1'
const WIN32_MODEL = 'deepseek-v4-flash-ga-260731'
const WIN32_BASE_URL = 'https://ark.cn-beijing.volces.com/api/coding/v3'
const WIN32_API_KEY_ENV = 'HUOSHAN_1_API_KEY'
const REAL_GATE = process.env.DSH_DISPATCH_GATE === 'real' && process.platform === 'win32'
// The stub round's worker route is the scaffold's own replay pair.
const STUB_ROUTE = 'deepseek-official'
const STUB_MODEL = 'deepseek-v4-flash'

const WORKER_REPLY = 'DISPATCH_GATE_WORKER_OK'
const REAL_PROMPT = 'Use the pwsh tool once to create dispatch-gate-worker.txt in your current working directory '
  + `containing exactly ${WORKER_REPLY}. Verify the file, then reply with the single word ${WORKER_REPLY} and stop. `
  + 'Do not create agents or modify other files.'
const STUB_PROMPT = `Reply with exactly ${WORKER_REPLY} and stop.`

/** One registered worktree's identity fields. */
type Tree = Pick<Worktree, 'id' | 'path' | 'branch'>
/** One published dispatch: the live child plus its durable binding record. */
type DispatchResult = Awaited<ReturnType<AgentDispatch['createChildAgent']>>

/** One git invocation, failing loud with its stderr. */
function git(cwd: string, ...args: string[]): Promise<string> {
  return new Promise((resolvePromise, rejectPromise) => {
    execFile('git', args, { cwd, windowsHide: true }, (error, stdout, stderr) => {
      if (error !== null) {
        rejectPromise(new Error(`git ${args.join(' ')} failed: ${error.message} stderr=${stderr}`))
      } else {
        resolvePromise(stdout)
      }
    })
  })
}

describe('web e2e: model-driven dispatch gate', () => {
  let scaffold: WebScaffold | undefined
  let tempRoot: string | undefined
  let workspaceId: WorkspaceId | undefined
  let controllerTreePath: string
  let leadAgent: Agent | undefined
  const eventsBySession = new Map<string, SessionEvent[]>()

  afterAll(async () => {
    const failures: unknown[] = []
    await scaffold?.close().catch((error: unknown) => failures.push(error))
    scaffold = undefined
    if (tempRoot !== undefined) await rm(tempRoot, { recursive: true, force: true }).catch((error: unknown) => failures.push(error))
    tempRoot = undefined
    if (failures.length === 1) throw failures[0]
    if (failures.length > 1) throw new AggregateError(failures, 'dispatch-gate teardown failed')
  })

  beforeAll(async () => {
    tempRoot = await mkdtemp(join(tmpdir(), 'dsh-web-dispatch-gate-'))
    const repo = join(tempRoot, 'repo')
    await mkdir(repo)
    await git(repo, 'init', '-b', 'gate-main')
    await git(repo, 'config', 'user.email', 'dispatch-gate@example.invalid')
    await git(repo, 'config', 'user.name', 'Dispatch Gate')
    await writeFile(join(repo, 'README.md'), 'dispatch gate repo\n')
    await git(repo, 'add', '.')
    await git(repo, 'commit', '-m', 'gate root')

    // The stub worker's model call replays from this authored one-call script;
    // the temp placement keeps it out of the pinned corpus and leaves
    // compareReplaySession at its off default.
    const workerScriptDir = join(tempRoot, 'worker-script')
    await mkdir(workerScriptDir)
    const workerFixture = join(workerScriptDir, 'session.jsonl')
    await writeFile(workerFixture, [
      JSON.stringify({ type: 'session', version: 0, id: 'dispatch-gate-worker-script', createdAt: 0, cwd: '.', agentPreset: 'standard' }),
      JSON.stringify({ type: 'assistant/chunk', data: { turn: 1, step: 1, chunk: { type: 'block-start', index: 0, blockType: 'text' } } }),
      JSON.stringify({ type: 'assistant/chunk', data: { turn: 1, step: 1, chunk: { type: 'block-end', index: 0, block: { type: 'text', text: WORKER_REPLY } } } }),
      JSON.stringify({ type: 'assistant/chunk', data: { turn: 1, step: 1, chunk: { type: 'usage', usage: { inputTokens: 12, outputTokens: 4 } } } }),
      JSON.stringify({ type: 'assistant/chunk', data: { turn: 1, step: 1, chunk: { type: 'finish', reason: { kind: 'stop' } } } }),
    ].join('\n') + '\n')

    scaffold = await launchWebScaffold({
      extraOverlayPath: OVERLAY,
      extraOverlayPackageDirs: OVERLAY_PACKAGE_DIRS,
      replayFixture: workerFixture,
    })
    if (REAL_GATE) {
      if (process.env[WIN32_API_KEY_ENV] === undefined || process.env[WIN32_API_KEY_ENV]?.length === 0) {
        throw new Error(`dispatch-gate real round needs ${WIN32_API_KEY_ENV} (env or repo-root .env)`)
      }
      await scaffold.ctx.settings.update('llm-pi-ai', {
        providers: {
          [WIN32_ROUTE]: {
            displayName: 'Huoshan',
            api: 'openai-completions',
            baseURL: WIN32_BASE_URL,
            apiKeyEnv: WIN32_API_KEY_ENV,
            models: [{ id: WIN32_MODEL, name: 'DeepSeek-V4-Flash-GA' }],
          },
        },
      })
    }
    scaffold.ctx.on('session/event', (session, event: SessionEvent) => {
      const list = eventsBySession.get(session.id) ?? []
      list.push(event)
      eventsBySession.set(session.id, list)
    })

    const ctx = scaffold.ctx
    const workspace = await ctx.workspaceRegistry.create(repo)
    workspaceId = workspace.id
    const controllerTree = await ctx.worktreeRegistry.create({
      workspaceId,
      path: join(tempRoot, 'wt-controller'),
      branch: 'gate/controller',
    })
    controllerTreePath = controllerTree.path
    const controller = (await ctx.agents.create({
      sessionId: SessionId('dispatch-gate-controller'),
      meta: { cwd: controllerTree.path },
      setup: async (childCtx) => { await ctx.agentPresets.mount(childCtx) },
    })).agent
    await ctx.worktreeRegistry.bind(controllerTree.id, WorktreeLockHolder(controller.id))
    await ctx.agentBindings.bind({
      agentId: controller.id,
      role: 'controller',
      worktree: { worktreeId: controllerTree.id, worktreePath: controllerTree.path, branch: controllerTree.branch },
    })

    const leadTree = await ctx.worktreeRegistry.create({
      workspaceId,
      path: join(tempRoot, 'wt-lead'),
      branch: 'gate/lead',
    })
    const leadResult = await ctx.agentDispatch.createChildAgent(controller, {
      cwd: leadTree.path,
      role: 'lead',
      taskId: TaskId('gate-lead'),
      pluginId: PluginId('dispatch-gate'),
      worktree: { worktreeId: leadTree.id, worktreePath: leadTree.path, branch: leadTree.branch },
    }, { workspaceId, sessionId: SessionId('dispatch-gate-lead') })
    const leadRow = ctx.worktreeRegistry.list(workspaceId).find(row => row.id === leadTree.id)
    expect(leadRow?.lockedBy).toBe(leadResult.agent.id)
    expect(leadResult.record.parentSessionId).toBe(controller.id)
    expect(leadResult.record.role).toBe('lead')
    expect(leadResult.record.pluginId).toBe(PluginId('dispatch-gate'))
    expect(leadResult.record.taskId).toBe(TaskId('gate-lead'))
    expect(leadResult.agent.session.header.cwd).toBe(leadTree.path)
    // The real-roster preset join A2 verified only as the rosterless no-op.
    expect(ctx.agentPresets.composedPreset(leadResult.agent.ctx)).toBe('standard')
    leadAgent = leadResult.agent
  }, 240_000)

  function lead(): Agent {
    if (leadAgent === undefined) throw new Error('dispatch-gate: the beforeAll chain did not publish the lead')
    return leadAgent
  }

  function eventsOf(agent: Agent): SessionEvent[] {
    return eventsBySession.get(agent.id) ?? []
  }

  function replyText(agent: Agent): string {
    return eventsOf(agent).flatMap((event) => {
      if (event.type !== 'assistant/chunk') return []
      const chunk = event.data.chunk
      return chunk.type === 'block-end' && chunk.block.type === 'text' ? [chunk.block.text] : []
    }).join('')
  }

  function lastTurnEnd(agent: Agent): Extract<SessionEvent, { type: 'turn/end' }> | undefined {
    const ends = eventsOf(agent).filter((event): event is Extract<SessionEvent, { type: 'turn/end' }> => event.type === 'turn/end')
    return ends[ends.length - 1]
  }

  function expectDispatched(result: DispatchResult, tree: Tree, parent: Agent, role: 'lead' | 'worker', taskId: string): void {
    const ctx = scaffold!.ctx
    const row = ctx.worktreeRegistry.list(workspaceId!).find(entry => entry.id === tree.id)
    expect(row?.lockedBy).toBe(result.agent.id)
    expect(result.record.parentSessionId).toBe(parent.id)
    expect(result.record.role).toBe(role)
    expect(result.record.taskId).toBe(TaskId(taskId))
    expect(result.agent.session.header.cwd).toBe(tree.path)
    expect(ctx.agentBindings.find(result.agent.id)?.role).toBe(role)
  }

  /** One dispatch request naming a registered tree exactly as the registry row does. */
  function workerRequest(tree: Tree) {
    return {
      cwd: tree.path,
      role: 'worker' as const,
      taskId: TaskId('gate-probe'),
      pluginId: PluginId('dispatch-gate'),
      worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
    }
  }

  it('dispatches a worker through the real composition and drives its model round', async () => {
    const workerTree = await scaffold!.ctx.worktreeRegistry.create({
      workspaceId: workspaceId!,
      path: join(tempRoot!, 'wt-worker'),
      branch: 'gate/worker',
    })
    const workerResult = await scaffold!.ctx.agentDispatch.createChildAgent(lead(), {
      cwd: workerTree.path,
      role: 'worker',
      taskId: TaskId('gate-worker'),
      pluginId: PluginId('dispatch-gate'),
      worktree: { worktreeId: workerTree.id, worktreePath: workerTree.path, branch: workerTree.branch },
    }, {
      workspaceId: workspaceId!,
      agentOptions: { provider: STUB_ROUTE, model: STUB_MODEL },
      prompt: STUB_PROMPT,
    })
    expectDispatched(workerResult, workerTree, lead(), 'worker', 'gate-worker')
    await workerResult.agent.whenIdle()
    expect(lastTurnEnd(workerResult.agent)?.data.reason).toEqual({ kind: 'completed' })
    expect(replyText(workerResult.agent)).toContain(WORKER_REPLY)
  }, 120_000)

  it('classifies the four entry denials over the real composition', async () => {
    const ctx = scaffold!.ctx
    const dispatch = (parent: Agent, request: Parameters<AgentDispatch['createChildAgent']>[1]) =>
      ctx.agentDispatch.createChildAgent(parent, request, { workspaceId: workspaceId! })

    await expect(dispatch(lead(), workerRequest({
      id: WorktreeId('gate-no-such-worktree'),
      path: join(tempRoot!, 'wt-ghost'),
      branch: 'gate/ghost',
    }))).rejects.toMatchObject({ code: 'DISPATCH_WORKTREE_UNREGISTERED' })

    const workerTree = ctx.worktreeRegistry.list(workspaceId!).find(row => row.branch === 'gate/worker')
    await expect(dispatch(lead(), {
      ...workerRequest(workerTree!),
      worktree: { worktreeId: workerTree!.id, worktreePath: join(tempRoot!, 'wt-wrong'), branch: workerTree!.branch },
    })).rejects.toMatchObject({ code: 'DISPATCH_WORKTREE_MISMATCH' })

    const strayTree = await ctx.worktreeRegistry.create({
      workspaceId: workspaceId!,
      path: join(tempRoot!, 'wt-stray'),
      branch: 'gate/stray',
    })
    const stray = (await ctx.agents.create({
      sessionId: SessionId('dispatch-gate-stray'),
      meta: { cwd: controllerTreePath },
    })).agent
    await expect(dispatch(stray, workerRequest(strayTree))).rejects.toMatchObject({ code: 'DISPATCH_PARENT_UNBOUND' })

    const rogueTree = await ctx.worktreeRegistry.create({
      workspaceId: workspaceId!,
      path: join(tempRoot!, 'wt-rogue'),
      branch: 'gate/rogue',
    })
    const rogue = (await ctx.agents.create({
      sessionId: SessionId('dispatch-gate-rogue'),
      meta: { cwd: controllerTreePath },
    })).agent
    await ctx.worktreeRegistry.bind(rogueTree.id, WorktreeLockHolder(rogue.id))
    await ctx.agentBindings.bind({
      agentId: rogue.id,
      role: 'worker',
      worktree: { worktreeId: rogueTree.id, worktreePath: rogueTree.path, branch: rogueTree.branch },
    })
    const rogueTarget = await ctx.worktreeRegistry.create({
      workspaceId: workspaceId!,
      path: join(tempRoot!, 'wt-rogue-target'),
      branch: 'gate/rogue-target',
    })
    await expect(dispatch(rogue, workerRequest(rogueTarget))).rejects.toMatchObject({ code: 'DISPATCH_HIERARCHY_DENIED' })
  }, 120_000)

  it.skipIf(!REAL_GATE)('drives one real model round through the chain on the approved gateway route', async () => {
    const realTree = await scaffold!.ctx.worktreeRegistry.create({
      workspaceId: workspaceId!,
      path: join(tempRoot!, 'wt-worker-real'),
      branch: 'gate/worker-real',
    })
    const realResult = await scaffold!.ctx.agentDispatch.createChildAgent(lead(), {
      cwd: realTree.path,
      role: 'worker',
      taskId: TaskId('gate-worker-real'),
      pluginId: PluginId('dispatch-gate'),
      worktree: { worktreeId: realTree.id, worktreePath: realTree.path, branch: realTree.branch },
    }, {
      workspaceId: workspaceId!,
      agentOptions: { provider: WIN32_ROUTE, model: WIN32_MODEL },
      prompt: REAL_PROMPT,
    })
    expectDispatched(realResult, realTree, lead(), 'worker', 'gate-worker-real')
    await realResult.agent.whenIdle()
    expect(lastTurnEnd(realResult.agent)?.data.reason).toEqual({ kind: 'completed' })
    expect(replyText(realResult.agent)).toContain(WORKER_REPLY)
    const artifact = await readFile(join(realTree.path, 'dispatch-gate-worker.txt'), 'utf8')
    expect(artifact.trim()).toBe(WORKER_REPLY)
  }, 300_000)
})
