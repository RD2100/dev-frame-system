/**
 * The durable acknowledgment face over the real stack: real jsonl session
 * persistence (the durability bridge participates in the flush barrier),
 * real engine dispatch, and real child turns driven by a scripted adapter,
 * zero model calls. The proofs are the ones a memory ledger cannot give:
 * the ack is derived from the child's own durable log, `durable` is granted
 * only by a participating flush barrier, and the account survives a real
 * process restart through the reloaded log.
 * @module tests/durable-ack
 */

import { execFile } from 'node:child_process'
import { existsSync } from 'node:fs'
import { mkdir, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import { afterEach, describe, expect, it } from 'vitest'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import type { GenerateOptions, StreamChunk } from '@deepseek-ai/dsh-llm'
import { LlmAdapter } from '@deepseek-ai/dsh-llm'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { LlmResolvedModelInfo, MessageId } from '@deepseek-ai/dsh-llm'
import AgentHierarchy, { type AgentHierarchyConfigInput } from '@deepseek-ai/dsh-experimental-agent-hierarchy'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import { SessionId, SessionSeq } from '@deepseek-ai/dsh-session'
import type { SessionEvent } from '@deepseek-ai/dsh-session'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import SubprocessLocal from '@deepseek-ai/dsh-subprocess-local'
import WorkspaceRegistry, { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { defineContentToolFixture } from '@deepseek-ai/dsh-tools'
import GitWorktreeRegistry from '@deepseek-ai/dsh-worktree-registry'
import type { Worktree } from '@deepseek-ai/dsh-worktree-registry'
import { AgentDispatch, foldBriefingAck } from '../src/index.ts'
import type { DispatchAgentOptions } from '../src/index.ts'
import type { Agent } from '@deepseek-ai/dsh-agent'

/** One git invocation, failing loud with its stderr. */
function git(cwd: string, ...args: string[]): Promise<string> {
  return new Promise((resolvePromise, rejectPromise) => {
    execFile('git', args, { cwd, windowsHide: true }, (error, stdout, stderr) => {
      if (error !== null) {
        rejectPromise(new Error(`git ${args.join(' ')} failed: ${error.message} stderr=${stderr ?? ''}`))
      } else {
        resolvePromise(stdout)
      }
    })
  })
}

const rolesConfig: AgentHierarchyConfigInput = {
  roleToolPolicies: {
    controller: { inheritedTools: ['project_read'] },
    lead: { inheritedTools: ['project_read'] },
    worker: { inheritedTools: ['project_read'] },
  },
}

/** One streamed text answer, the adapter-side shape the loop assembles. */
function textResponse(text: string): StreamChunk[] {
  return [
    { type: 'block-start', index: 0, blockType: 'text' },
    ...Array.from(text, (char): StreamChunk => ({ type: 'text-delta', index: 0, text: char })),
    { type: 'block-end', index: 0, block: { type: 'text', text } },
    { type: 'usage', usage: { inputTokens: 10, outputTokens: text.length } },
    { type: 'finish', reason: { kind: 'stop' } },
  ]
}

/** Script entries: a chunk list answers, an error entry fails the call, `hang` pends until aborted. */
type ScriptEntry = StreamChunk[] | { readonly error: string } | 'hang'

/**
 * Scripted adapter: each model call consumes the next entry. Real turns run
 * through the real loop with no model behind them.
 */
class ScriptedAdapter extends LlmAdapter {
  requests: GenerateOptions[] = []

  constructor(private readonly script: ScriptEntry[]) {
    super()
  }

  override resolveModel(provider: string, model: string): Promise<LlmResolvedModelInfo> {
    return Promise.resolve({ provider, id: model, name: model })
  }

  async *stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    this.requests.push(options)
    const entry = this.script.shift()
    if (entry === undefined) throw new Error('ScriptedAdapter: script exhausted')
    if (entry !== 'hang' && 'error' in entry) throw new Error(entry.error)
    const chunks: StreamChunk[] = entry === 'hang'
      ? [{ type: 'block-start', index: 0, blockType: 'text' }]
      : entry
    for (const chunk of chunks) {
      if (options.signal?.aborted) throw new Error('aborted')
      yield chunk
    }
    if (entry === 'hang') {
      await new Promise<void>((_resolve, reject) => {
        if (options.signal?.aborted) { reject(new Error('aborted')); return }
        options.signal?.addEventListener('abort', () => { reject(new Error('aborted')) }, { once: true })
      })
    }
  }
}

const contexts: Context[] = []
const roots: string[] = []

afterEach(async () => {
  await Promise.all(contexts.splice(0).map(ctx => ctx.fiber.dispose()))
  await Promise.all(roots.splice(0).map(root => rm(root, { recursive: true, force: true })))
})

interface Harness {
  ctx: Context
  root: string
  repo: string
  workspaceId: WorkspaceId
  controller: Agent
  createWorktree: (name: string, branch: string) => Promise<Worktree>
  dispatch: (
    request: Parameters<AgentDispatch['createChildAgent']>[1],
    options?: Partial<DispatchAgentOptions>,
  ) => ReturnType<AgentDispatch['createChildAgent']>
}

/**
 * Boot the real composition with real jsonl persistence (the durability
 * bridge) and the scripted route, then register the repository workspace
 * and one live controller.
 */
async function harness(
  adapter: ScriptedAdapter,
  leadPluginScopes: AgentHierarchyConfigInput['leadPluginScopes'] = {},
  existingRoot?: string,
): Promise<Harness> {
  const root = existingRoot ?? await mkdtemp(join(tmpdir(), 'dsh-agent-dispatch-ack-'))
  if (existingRoot === undefined) roots.push(root)
  const ctx = new Context()
  contexts.push(ctx)
  try {
    await mountAgentLoopTestDependencies(ctx)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(AgentLoop, { agents: [] })
    await ctx.plugin(Storage)
    await ctx.plugin(StorageJson, { root })
    await ctx.plugin(StorageDomain, { backend: 'json' })
    await ctx.plugin(JsonlSessionPersistence, {
      root: join(root, 'sessions'),
      compression: 'none',
      writeBatchMaxDelayMs: 1,
    })
    await ctx.plugin(WorkspaceRegistry)
    await ctx.plugin(SubprocessLocal)
    await ctx.plugin(GitWorktreeRegistry)
    await ctx.plugin(AgentBindingRegistry)
    ctx.tools.register(defineContentToolFixture({
      name: 'project_read',
      description: 'agent-dispatch durable-ack probe project_read',
      parameters: {},
      async execute() {
        return []
      },
    }))
    await ctx.plugin(AgentHierarchy, { ...rolesConfig, leadPluginScopes })
    // The plugin's formal bootstrap is opt-in; the dispatch/ack faces run
    // without it, so no project controller is mounted.
    await ctx.plugin(AgentDispatch)
    ctx.llm.registerAdapter(['mock'], adapter)

    const repo = join(root, 'repo')
    if (!existsSync(repo)) {
      await mkdir(repo)
      await git(root, 'init', '-b', 'main', repo)
      await git(repo, 'config', 'user.email', 'agent-dispatch-ack@test.local')
      await git(repo, 'config', 'user.name', 'Agent Dispatch Ack Tests')
      await git(repo, 'commit', '--allow-empty', '-m', 'init')
      await ctx.workspaceRegistry.create(repo)
    }
    const workspace = ctx.workspaceRegistry.list().find(entry => entry.path === repo)
    if (workspace === undefined) throw new Error(`the restarted root did not restore the workspace at ${repo}`)

    const controller = (await ctx.agents.create({
      sessionId: SessionId('ack-controller'),
      meta: { cwd: repo },
    })).agent
    // A restarted root restores the controller's binding from durable
    // storage; binding again would refuse an existing record.
    if (ctx.agentBindings.find(SessionId('ack-controller')) === undefined) {
      await ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
    }

    return {
      ctx,
      root,
      repo,
      workspaceId: workspace.id,
      controller,
      createWorktree: async (name, branch) => await ctx.worktreeRegistry.create({
        workspaceId: workspace.id,
        path: join(root, name),
        branch,
      }),
      dispatch: (request, options) => ctx.agentDispatch.createChildAgent(controller, request, {
        workspaceId: workspace.id,
        agentOptions: { provider: 'mock', model: 'mock' },
        ...options,
      }),
    }
  } catch (error: unknown) {
    await ctx.fiber.dispose()
    contexts.splice(contexts.indexOf(ctx), 1)
    throw error
  }
}

/** Poll the task ack until the predicate holds; bounded, on observable state. */
async function waitForAck(
  ctx: Context,
  parent: Agent,
  taskId: TaskId,
  predicate: (state: string) => boolean,
): Promise<NonNullable<Awaited<ReturnType<AgentDispatch['taskAck']>>>> {
  const deadline = Date.now() + 10_000
  for (;;) {
    const ack = await ctx.agentDispatch.taskAck(parent, taskId)
    if (ack !== undefined && predicate(ack.state)) return ack
    if (Date.now() > deadline) throw new Error(`timed out waiting for ack state; last: ${JSON.stringify(ack)}`)
    await new Promise(resolve => setTimeout(resolve, 25))
  }
}

it('derives briefed, then terminal completed, from a real turn over real persistence', async () => {
  const h = await harness(new ScriptedAdapter([textResponse('task done')]))
  const tree = await h.createWorktree('wt-ack', 'feature/ack')
  const created = await h.dispatch({
    cwd: tree.path,
    role: 'lead',
    taskId: TaskId('ack-1'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }, { prompt: 'do the task' })

  // The delivery is in the child's log and the flush barrier participated:
  // the parent can trust the task was recorded durably. The wake race means
  // the claiming turn may already be open when the parent looks — both
  // pre-terminal states are honest here, the mid states have their own
  // deterministic proofs below.
  const briefed = await h.ctx.agentDispatch.taskAck(h.controller, TaskId('ack-1'))
  expect(briefed).toBeDefined()
  expect(['briefed', 'claimed']).toContain(briefed?.state)
  expect(briefed?.durable).toBe(true)
  expect(String(briefed?.briefingMessageId)).toBe('dispatch-briefing:ack-controller:ack-1')

  await waitForAck(h.ctx, h.controller, TaskId('ack-1'), state => state === 'terminal')
  const terminal = await h.ctx.agentDispatch.taskAck(h.controller, TaskId('ack-1'))
  expect(terminal).toMatchObject({
    state: 'terminal',
    durable: true,
    completed: true,
    turnEnd: { turn: 1, reason: { kind: 'completed' } },
  })

  // The identity's durable log carries exactly one delivery and one intake
  // of the briefing: reuse re-reads the same account and never re-tasks.
  const intake = created.agent.session.snapshotEvents()
    .filter(event => event.type === 'user/message')
    .filter(event => String(event.data.id) === String(terminal?.briefingMessageId))
  expect(intake).toHaveLength(1)
  const reused = await h.dispatch({
    cwd: tree.path,
    role: 'lead',
    taskId: TaskId('ack-1'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }, { sessionId: created.record.agentId })
  expect(reused.record.agentId).toBe(created.record.agentId)
  await expect(h.ctx.agentDispatch.taskAck(h.controller, TaskId('ack-1'))).resolves.toMatchObject({
    state: 'terminal',
    completed: true,
    durable: true,
  })
}, 20_000)

it('reports a failed turn as terminal without completing', async () => {
  const h = await harness(new ScriptedAdapter([{ error: 'scripted failure' }]))
  const tree = await h.createWorktree('wt-ack-error', 'feature/ack-error')
  await h.dispatch({
    cwd: tree.path,
    role: 'lead',
    taskId: TaskId('ack-err'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }, { prompt: 'this will fail' })
  await waitForAck(h.ctx, h.controller, TaskId('ack-err'), state => state === 'terminal')
  await expect(h.ctx.agentDispatch.taskAck(h.controller, TaskId('ack-err'))).resolves.toMatchObject({
    state: 'terminal',
    durable: true,
    completed: false,
    turnEnd: { turn: 1, reason: { kind: 'error' } },
  })
}, 20_000)

it('reports an open claiming turn as claimed', async () => {
  const h = await harness(new ScriptedAdapter(['hang']))
  const tree = await h.createWorktree('wt-ack-hang', 'feature/ack-hang')
  await h.dispatch({
    cwd: tree.path,
    role: 'lead',
    taskId: TaskId('ack-hang'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }, { prompt: 'hang the turn' })
  const ack = await waitForAck(h.ctx, h.controller, TaskId('ack-hang'), state => state === 'claimed')
  expect(ack.durable).toBe(true)
}, 20_000)

it('keeps the terminal account across a restart: unavailable, then terminal from the reloaded log', async () => {
  const first = await harness(new ScriptedAdapter([textResponse('survive the restart')]))
  const tree = await first.createWorktree('wt-ack-restart', 'feature/ack-restart')
  const created = await first.dispatch({
    cwd: tree.path,
    role: 'lead',
    taskId: TaskId('ack-restart'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }, { prompt: 'survive the restart' })
  await waitForAck(first.ctx, first.controller, TaskId('ack-restart'), state => state === 'terminal')
  await expect(first.ctx.agentDispatch.taskAck(first.controller, TaskId('ack-restart')))
    .resolves.toMatchObject({ state: 'terminal', completed: true, durable: true })
  const artifact = first.ctx.sessionPersistence.locate(created.agent.session.header)?.path
  expect(artifact).toBeDefined()
  await first.ctx.fiber.dispose()
  contexts.splice(contexts.indexOf(first.ctx), 1)
  // The root stays: the durable reservation, the workspace row, and the
  // child's jsonl log are exactly what the restart consumes.
  roots.splice(roots.indexOf(first.root), 1)
  roots.push(first.root)

  // Cold restart over the same root: the durable reservation returns, the
  // agent does not. The ack face says exactly that, and nothing more.
  const second = await harness(new ScriptedAdapter([]), {}, first.root)
  const restoredRow = second.ctx.worktreeRegistry.list(second.workspaceId)
    .find(row => row.path === tree.path)
  if (restoredRow === undefined) throw new Error('the restarted root did not restore the worktree row')
  await expect(second.ctx.agentDispatch.taskAck(second.controller, TaskId('ack-restart')))
    .resolves.toMatchObject({ state: 'unavailable', durable: false })

  // Recovery through the dispatch lane resumes the reloaded log: the
  // completed terminal account is re-derived from durable storage, not
  // from any in-process memory.
  const recovered = await second.ctx.agentDispatch.recoverChildAgent(second.controller, {
    cwd: restoredRow.path,
    role: 'lead',
    taskId: TaskId('ack-restart'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: restoredRow.id, worktreePath: restoredRow.path, branch: restoredRow.branch },
  }, {
    workspaceId: second.workspaceId,
    sessionId: created.record.agentId,
    agentOptions: { provider: 'mock', model: 'mock' },
  })
  await expect(second.ctx.agentDispatch.taskAck(second.controller, TaskId('ack-restart')))
    .resolves.toMatchObject({ state: 'terminal', completed: true, durable: true })
  expect(String(recovered.record.agentId)).toBe(String(created.record.agentId))
}, 20_000)

it('reports unbriefed when recovery republishes a missing log', async () => {
  const h = await harness(new ScriptedAdapter([]))
  const tree = await h.createWorktree('wt-ack-missing', 'feature/ack-missing')
  // No briefing: the reservation exists, the child log stays eventless, so
  // the recovery below exercises the typed missing-log republication.
  const created = await h.dispatch({
    cwd: tree.path,
    role: 'lead',
    taskId: TaskId('ack-missing'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  })
  const artifact = h.ctx.sessionPersistence.locate(created.agent.session.header)?.path
  await h.ctx.fiber.dispose()
  contexts.splice(contexts.indexOf(h.ctx), 1)
  roots.splice(roots.indexOf(h.root), 1)
  roots.push(h.root)
  if (artifact === undefined) throw new Error('the jsonl backend did not locate the child artifact')
  await rm(artifact, { force: true })

  const restarted = await harness(new ScriptedAdapter([]), {}, h.root)
  const restoredRow = restarted.ctx.worktreeRegistry.list(restarted.workspaceId)
    .find(row => row.path === tree.path)
  if (restoredRow === undefined) throw new Error('the restarted root did not restore the worktree row')
  const recovered = await restarted.ctx.agentDispatch.recoverChildAgent(restarted.controller, {
    cwd: restoredRow.path,
    role: 'lead',
    taskId: TaskId('ack-missing'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: restoredRow.id, worktreePath: restoredRow.path, branch: restoredRow.branch },
  }, {
    workspaceId: restarted.workspaceId,
    sessionId: created.record.agentId,
    agentOptions: { provider: 'mock', model: 'mock' },
  })
  // The engine republished under the reserved identity with an empty log:
  // no delivery splice exists, and the ack refuses to pretend otherwise.
  await expect(restarted.ctx.agentDispatch.taskAck(restarted.controller, TaskId('ack-missing')))
    .resolves.toMatchObject({ state: 'unbriefed', durable: true })
  expect(String(recovered.record.agentId)).toBe(String(created.record.agentId))
}, 20_000)

describe('foldBriefingAck', () => {
  const briefingId = brandString<MessageId>('dispatch-briefing:p:t')
  const delivery: SessionEvent[] = [
    { type: 'agent/inbox/spliced', seq: SessionSeq(1), time: 1, data: { target: 'next-turn', start: 0, inserted: [{ id: briefingId, role: 'user', content: [], source: { kind: 'plugin', plugin: 'agent-dispatch' } }] } },
  ]

  it('reports dropped when a cancellation removed the briefing unrun', () => {
    const events: SessionEvent[] = [
      ...delivery,
      { type: 'agent/inbox/spliced', seq: SessionSeq(2), time: 2, data: { target: 'next-turn', start: 0, removedCount: 1, inserted: [], outcome: 'canceled' } },
    ]
    expect(foldBriefingAck(events, String(briefingId))).toEqual({ state: 'dropped' })
  })

  it('reports unbriefed when the log holds no delivery', () => {
    expect(foldBriefingAck([], String(briefingId))).toEqual({ state: 'unbriefed' })
  })

  it('reports claimed while the claiming turn is still open', () => {
    const events: SessionEvent[] = [
      { type: 'turn/start', seq: SessionSeq(1), time: 1, data: { turn: 1 } },
      ...delivery,
      { type: 'agent/inbox/spliced', seq: SessionSeq(3), time: 3, data: { target: 'next-turn', start: 0, removedCount: 1, inserted: [] } },
    ]
    expect(foldBriefingAck(events, String(briefingId))).toEqual({ state: 'claimed' })
  })

  it('does not let a later turn close account for an earlier claim', () => {
    const events: SessionEvent[] = [
      { type: 'turn/start', seq: SessionSeq(1), time: 1, data: { turn: 1 } },
      ...delivery,
      { type: 'agent/inbox/spliced', seq: SessionSeq(3), time: 3, data: { target: 'next-turn', start: 0, removedCount: 1, inserted: [] } },
      { type: 'turn/start', seq: SessionSeq(4), time: 4, data: { turn: 2 } },
      { type: 'turn/end', seq: SessionSeq(5), time: 5, data: { turn: 2, reason: { kind: 'completed' } } },
    ]
    expect(foldBriefingAck(events, String(briefingId))).toEqual({ state: 'claimed' })
  })
})
