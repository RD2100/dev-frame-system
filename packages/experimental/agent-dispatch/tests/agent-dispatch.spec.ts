/**
 * The daily dispatch entry over the real engine: every creation runs through
 * `ctx.agentDispatch.createChildAgent` with a real registered git worktree,
 * the real binding registry, and the real hierarchy service — denials are
 * observed as classified {@link AgentDispatchError}s, and the happy path is
 * observed in the registry rows, the durable bindings, and the child's own
 * inbox.
 * @module tests/agent-dispatch
 */

import { execFile } from 'node:child_process'
import { mkdir, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import { afterEach, expect, it, vi } from 'vitest'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import type { UserMessage } from '@deepseek-ai/dsh-llm'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentHierarchy, { type AgentHierarchyConfigInput } from '@deepseek-ai/dsh-experimental-agent-hierarchy'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import { SessionId, type Session } from '@deepseek-ai/dsh-session'
import { SessionPersistenceNotFoundError } from '@deepseek-ai/dsh-session-persistence'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import SubprocessLocal from '@deepseek-ai/dsh-subprocess-local'
import WorkspaceRegistry, { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { defineContentToolFixture } from '@deepseek-ai/dsh-tools'
import { LlmAdapter, type GenerateOptions, type StreamChunk } from '@deepseek-ai/dsh-llm'
import {
  GitWorktreeRegistry,
  WorktreeId,
  WorktreeLockHolder,
} from '@deepseek-ai/dsh-worktree-registry'
import type { Worktree } from '@deepseek-ai/dsh-worktree-registry'
import { AgentDispatch, AgentDispatchError, type DispatchAgentOptions } from '../src/index.ts'
import { watchChildSettlement, type DispatchSettledMessageSource } from '../src/index.ts'

/** A never-exhausting adapter: every model call returns the same short reply. */
class TextAdapter extends LlmAdapter {
  async * stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    if (options.signal?.aborted) throw new Error('aborted')
    const text = 'ok'
    yield { type: 'block-start', index: 0, blockType: 'text' }
    yield { type: 'text-delta', index: 0, text }
    yield { type: 'block-end', index: 0, block: { type: 'text', text } }
    yield { type: 'usage', usage: { inputTokens: 1, outputTokens: 1 } }
    yield { type: 'finish', reason: { kind: 'stop' } }
  }
}

/** A failing adapter: the model stream always throws, so the turn ends with the structured error reason. */
class FailingAdapter extends LlmAdapter {
  async * stream(): AsyncIterable<StreamChunk> {
    throw new Error('child model failure')
  }
}

/** Poll until the probe returns a truthy value or the budget expires. */
async function until(probe: () => unknown, budgetMs = 5_000): Promise<void> {
  const deadline = Date.now() + budgetMs
  for (;;) {
    if (probe()) return
    if (Date.now() > deadline) throw new Error('probe did not settle within its budget')
    await new Promise(resolve => setTimeout(resolve, 25))
  }
}

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

interface Harness {
  ctx: Context
  root: string
  workspaceId: WorkspaceId
  createWorktree: (name: string, branch: string) => Promise<Worktree>
  dispatch: (
    parent: Parameters<AgentDispatch['createChildAgent']>[0],
    request: Parameters<AgentDispatch['createChildAgent']>[1],
    options?: Partial<DispatchAgentOptions>,
  ) => ReturnType<AgentDispatch['createChildAgent']>
  dispose: (options?: { readonly keepRoot?: boolean }) => Promise<void>
}

interface HarnessOptions {
  /** Existing storage root to reuse (restart specs pass the previous root). */
  readonly root?: string
  /** Skip the repo/workspace seed when restarting over a root that already has one. */
  readonly seed?: boolean
}

/** Boot the real composition: agent loop, storage, both registries, engine, dispatch entry. */
async function harness(
  leadPluginScopes: AgentHierarchyConfigInput['leadPluginScopes'],
  options: HarnessOptions = {},
): Promise<Harness> {
  const root = options.root ?? await mkdtemp(join(tmpdir(), 'dsh-agent-dispatch-'))
  const ctx = new Context()
  try {
    await mountAgentLoopTestDependencies(ctx)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(AgentLoop, { agents: [] })
    await ctx.plugin(Storage)
    await ctx.plugin(StorageJson, { root })
    await ctx.plugin(StorageDomain, { backend: 'json' })
    ctx.provide('sessionPersistence', {
      list: async () => [],
      load: () => { throw new Error('event bodies must not be loaded') },
      inspect: () => { throw new Error('event bodies must not be inspected') },
    } as never)
    await ctx.plugin(WorkspaceRegistry)
    await ctx.plugin(SubprocessLocal)
    await ctx.plugin(GitWorktreeRegistry)
    await ctx.plugin(AgentBindingRegistry)
    // The role policies name this tool; the engine's restrict() install
    // validates every configured name against the global surface.
    ctx.tools.register(defineContentToolFixture({
      name: 'project_read',
      description: 'agent-dispatch probe project_read',
      parameters: {},
      async execute() {
        return []
      },
    }))
    await ctx.plugin(AgentHierarchy, { ...rolesConfig, leadPluginScopes: leadPluginScopes ?? {} })
    // The plugin's formal bootstrap is opt-in; these dispatch-face suites
    // run without it, so no project controller is mounted.
    await ctx.plugin(AgentDispatch)
    let workspaceId: WorkspaceId
    if (options.seed !== false) {
      const repo = join(root, 'repo')
      await mkdir(repo)
      await git(root, 'init', '-b', 'main', repo)
      await git(repo, 'config', 'user.email', 'agent-dispatch@test.local')
      await git(repo, 'config', 'user.name', 'Agent Dispatch Tests')
      await git(repo, 'commit', '--allow-empty', '-m', 'init')
      workspaceId = (await ctx.workspaceRegistry.create(repo)).id
    } else {
      const restored = ctx.workspaceRegistry.list()
      if (restored.length !== 1) {
        throw new Error(`expected the restarted root to restore exactly one workspace, got ${restored.length}`)
      }
      workspaceId = restored[0]!.id
    }
    return {
      ctx,
      root,
      workspaceId,
      createWorktree: async (name, branch) => await ctx.worktreeRegistry.create({
        workspaceId,
        path: join(root, name),
        branch,
      }),
      dispatch: (parent, request, options) => ctx.agentDispatch.createChildAgent(parent, request, {
        workspaceId,
        ...options,
      }),
      dispose: async (disposeOptions) => {
        await ctx.fiber.dispose()
        if (disposeOptions?.keepRoot !== true) await rm(root, { recursive: true, force: true })
      },
    }
  } catch (error: unknown) {
    await ctx.fiber.dispose()
    await rm(root, { recursive: true, force: true })
    throw error
  }
}

/** Assert the promise refuses with the classified dispatch error and return it. */
async function dispatchError(run: () => Promise<unknown>): Promise<AgentDispatchError> {
  try {
    await run()
  } catch (error: unknown) {
    if (error instanceof AgentDispatchError) return error
    throw error
  }
  throw new Error('expected the dispatch to be refused with an AgentDispatchError')
}

const activeHarnesses: Harness[] = []

afterEach(async () => {
  await Promise.all(activeHarnesses.splice(0).map(h => h.dispose()))
})

it('dispatches a lead and then a worker inside a second approved plugin scope, with the registry lock and the prompt delivered after publication', async () => {
  const h = await harness({ 'dispatch-lead': ['plugin-a', 'plugin-b'] })
  activeHarnesses.push(h)
  const controller = (await h.ctx.agents.create({
    sessionId: SessionId('dispatch-controller'),
    meta: { cwd: join(h.root, 'repo') },
  })).agent
  await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const leadTree = await h.createWorktree('wt-lead', 'feature/lead')
  const lead = await h.dispatch(controller, {
    cwd: leadTree.path,
    role: 'lead',
    taskId: TaskId('lead-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: leadTree.id, worktreePath: leadTree.path, branch: leadTree.branch },
  }, { sessionId: SessionId('dispatch-lead') })
  expect(lead.record).toMatchObject({
    agentId: 'dispatch-lead',
    role: 'lead',
    pluginId: 'plugin-a',
    taskId: 'lead-task',
    worktreeId: leadTree.id,
    worktreePath: leadTree.path,
    parentSessionId: controller.id,
  })
  const leadRow = h.ctx.worktreeRegistry.list(h.workspaceId).find(entry => entry.id === leadTree.id)
  expect(String(leadRow?.lockedBy)).toBe('dispatch-lead')

  // The lead's own binding scope is plugin-a; approving plugin-b for the
  // worker is exactly what the retired narrow comparison rejected.
  const workerTree = await h.createWorktree('wt-worker', 'feature/worker')
  const inserted: UserMessage[] = []
  const worker = await h.dispatch(lead.agent, {
    cwd: workerTree.path,
    role: 'worker',
    taskId: TaskId('worker-task'),
    pluginId: PluginId('plugin-b'),
    worktree: { worktreeId: workerTree.id, worktreePath: workerTree.path, branch: workerTree.branch },
  }, {
    sessionId: SessionId('dispatch-worker'),
    prompt: 'worker briefing: build the widget',
    setup: (childCtx) => {
      childCtx.agent?.ctx.on('agent/inbox/inserted', ({ message }) => { inserted.push(message) })
    },
  })
  expect(worker.record).toMatchObject({
    agentId: 'dispatch-worker',
    role: 'worker',
    pluginId: 'plugin-b',
    taskId: 'worker-task',
    worktreeId: workerTree.id,
    worktreePath: workerTree.path,
    parentSessionId: lead.agent.id,
  })
  const workerRow = h.ctx.worktreeRegistry.list(h.workspaceId).find(entry => entry.id === workerTree.id)
  expect(String(workerRow?.lockedBy)).toBe('dispatch-worker')
  expect(inserted).toHaveLength(1)
  expect(JSON.stringify(inserted[0]?.content)).toContain('worker briefing: build the widget')
  expect(h.ctx.agentBindings.list()).toHaveLength(3)
})

it('rejects unregistered ids, foreign workspaces, vanished directories, and git-broken worktrees with classified failures', async () => {
  const h = await harness({})
  activeHarnesses.push(h)
  const controller = (await h.ctx.agents.create({
    sessionId: SessionId('proof-controller'),
    meta: { cwd: join(h.root, 'repo') },
  })).agent
  await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const request = (worktreeId: WorktreeId, worktreePath: string, branch?: string) => ({
    cwd: worktreePath,
    role: 'lead' as const,
    taskId: TaskId(`task-${String(worktreeId)}`),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId, worktreePath, ...(branch === undefined ? {} : { branch }) },
  })

  const unregistered = await dispatchError(() => h.dispatch(controller,
    request(WorktreeId('never-registered'), join(h.root, 'ghost'))))
  expect(unregistered.code).toBe('DISPATCH_WORKTREE_UNREGISTERED')

  const realTree = await h.createWorktree('wt-real', 'feature/real')
  const foreignWorkspace = await dispatchError(() => h.ctx.agentDispatch.createChildAgent(controller,
    request(realTree.id, realTree.path, 'feature/real'),
    { workspaceId: WorkspaceId('no-such-workspace') }))
  expect(foreignWorkspace.code).toBe('DISPATCH_WORKTREE_UNREGISTERED')

  const vanished = await h.createWorktree('wt-vanished', 'feature/vanished')
  await rm(vanished.path, { recursive: true, force: true })
  const gone = await dispatchError(() => h.dispatch(controller, request(vanished.id, vanished.path)))
  expect(gone.code).toBe('DISPATCH_WORKTREE_MISMATCH')
  expect(gone.message).toContain('no longer exists')

  const wrongPath = await dispatchError(() => h.dispatch(controller,
    request(realTree.id, join(h.root, 'elsewhere'), 'feature/real')))
  expect(wrongPath.code).toBe('DISPATCH_WORKTREE_MISMATCH')
  expect(wrongPath.message).toContain('is registered at')

  const wrongBranch = await dispatchError(() => h.dispatch(controller,
    request(realTree.id, realTree.path, 'feature/wrong')))
  expect(wrongBranch.code).toBe('DISPATCH_WORKTREE_MISMATCH')
  expect(wrongBranch.message).toContain('is on branch')

  // A linked worktree's .git is a file pointing into the repo; deleting it
  // breaks the git observations the registry runs. The row still proves
  // registration, so the failure classifies as a live mismatch whose cause
  // carries git's evidence.
  const broken = await h.createWorktree('wt-broken', 'feature/broken')
  await rm(join(broken.path, '.git'), { force: true })
  const brokenObservation = await dispatchError(() => h.dispatch(controller, request(broken.id, broken.path)))
  expect(brokenObservation.code).toBe('DISPATCH_WORKTREE_MISMATCH')
  expect(String(brokenObservation.cause)).toMatch(/git/i)
})

it('rejects foreign single-writer bindings, unbound parents, worker dispatchers, and unapproved lead scopes', async () => {
  const h = await harness({})
  activeHarnesses.push(h)
  const controller = (await h.ctx.agents.create({
    sessionId: SessionId('denial-controller'),
    meta: { cwd: join(h.root, 'repo') },
  })).agent
  await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const leadRequest = (tree: Worktree, taskId: string) => ({
    cwd: tree.path,
    role: 'lead' as const,
    taskId: TaskId(taskId),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  })

  const occupiedTree = await h.createWorktree('wt-occupied', 'feature/occupied')
  await h.ctx.worktreeRegistry.bind(occupiedTree.id, WorktreeLockHolder('someone-else'))
  const occupied = await dispatchError(() => h.dispatch(controller, leadRequest(occupiedTree, 'occupied-task'), {
    sessionId: SessionId('other-child'),
  }))
  expect(occupied.code).toBe('DISPATCH_WORKTREE_MISMATCH')
  expect(occupied.message).toContain('bound to writer')

  const unbound = (await h.ctx.agents.create({
    sessionId: SessionId('no-binding'),
    meta: { cwd: join(h.root, 'repo') },
  })).agent
  const leadTree = await h.createWorktree('wt-lead', 'feature/lead')
  const noBinding = await dispatchError(() => h.dispatch(unbound, leadRequest(leadTree, 'lead-task')))
  expect(noBinding.code).toBe('DISPATCH_PARENT_UNBOUND')

  // An unlisted lead is approved for nothing: its own dispatch succeeds
  // (controller→lead needs no approved set), but its worker dispatch denies.
  const lead = await h.dispatch(controller, leadRequest(leadTree, 'lead-task'), {
    sessionId: SessionId('unlisted-lead'),
  })
  expect(lead.record.role).toBe('lead')
  const workerTree = await h.createWorktree('wt-worker', 'feature/worker')
  const unapproved = await dispatchError(() => h.dispatch(lead.agent, {
    cwd: workerTree.path,
    role: 'worker',
    taskId: TaskId('worker-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: workerTree.id, worktreePath: workerTree.path, branch: workerTree.branch },
  }))
  expect(unapproved.code).toBe('DISPATCH_HIERARCHY_DENIED')
  expect(unapproved.message).toContain('approved set')

  const workerTree2 = await h.createWorktree('wt-worker-2', 'feature/worker-2')
  const worker = (await h.ctx.agents.create({
    sessionId: SessionId('plain-worker'),
    meta: { cwd: join(h.root, 'repo') },
  })).agent
  await h.ctx.agentBindings.bind({ agentId: worker.id, role: 'worker' })
  const fromWorker = await dispatchError(() => h.dispatch(worker, {
    cwd: workerTree2.path,
    role: 'worker',
    taskId: TaskId('worker-2-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: workerTree2.id, worktreePath: workerTree2.path, branch: workerTree2.branch },
  }))
  expect(fromWorker.code).toBe('DISPATCH_HIERARCHY_DENIED')
})

it('reuses the returned identity without re-delivering the prompt, guides blind retries to it, and passes the engine recovery refusal through', async () => {
  const h = await harness({ 'dispatch-lead': ['plugin-a', 'plugin-b'] })
  activeHarnesses.push(h)
  const controller = (await h.ctx.agents.create({
    sessionId: SessionId('retry-controller'),
    meta: { cwd: join(h.root, 'repo') },
  })).agent
  await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const tree = await h.createWorktree('wt-retry', 'feature/retry')
  const request = {
    cwd: tree.path,
    role: 'lead' as const,
    taskId: TaskId('retry-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }
  const first = await h.dispatch(controller, request, { sessionId: SessionId('retry-lead') })
  expect(first.record.agentId).toBe('retry-lead')

  const identity = h.ctx.agentDispatch.findDispatchedChild(controller, TaskId('retry-task'))
  expect(identity?.record.agentId).toBe('retry-lead')
  expect(identity?.live).toBe(true)
  expect(h.ctx.agentDispatch.findDispatchedChild(controller, TaskId('other-task'))).toBeUndefined()

  // A blind same-task retry learns the returned identity instead of a
  // misleading worktree mismatch.
  const blind = await dispatchError(() => h.dispatch(controller, request))
  expect(blind.code).toBe('DISPATCH_IDENTITY_EXISTS')
  expect(blind.message).toContain('retry-lead')

  // Passing the returned id back reuses the engine's own dedupe answer; the
  // prompt must not be re-delivered to the already-running child.
  const inserted: UserMessage[] = []
  first.agent.ctx.on('agent/inbox/inserted', ({ message }) => { inserted.push(message) })
  const retry = await h.dispatch(controller, request, {
    sessionId: SessionId('retry-lead'),
    prompt: 're-briefing that must never arrive',
  })
  expect(retry.agent.id).toBe('retry-lead')
  expect(inserted).toHaveLength(0)

  // Cold restart over the same root: the identity stays durable but is no
  // longer live, and the engine's own recovery refusal passes through the
  // adapter unchanged — no wrap, no replacement child.
  await h.dispose({ keepRoot: true })
  activeHarnesses.splice(activeHarnesses.indexOf(h), 1)
  const restarted = await harness({ 'dispatch-lead': ['plugin-a', 'plugin-b'] }, { root: h.root, seed: false })
  activeHarnesses.push(restarted)
  expect(restarted.ctx.agentBindings.find(SessionId('retry-lead'))?.taskId).toBe('retry-task')
  const controller2 = (await restarted.ctx.agents.create({
    sessionId: SessionId('retry-controller'),
    meta: { cwd: join(restarted.root, 'repo') },
  })).agent
  const restored = restarted.ctx.agentDispatch.findDispatchedChild(controller2, TaskId('retry-task'))
  expect(restored?.record.agentId).toBe('retry-lead')
  expect(restored?.live).toBe(false)
  let recoveryError: unknown
  try {
    await restarted.dispatch(controller2, request, { sessionId: SessionId('retry-lead') })
  } catch (error: unknown) {
    recoveryError = error
  }
  expect(recoveryError).toBeInstanceOf(Error)
  expect(recoveryError).not.toBeInstanceOf(AgentDispatchError)
  expect((recoveryError as Error).message).toMatch(/requires session recovery/)
})

it('routes reserved-identity recovery through the engine lane and passes corruption through unchanged', async () => {
  const h = await harness({ 'dispatch-lead': ['plugin-a', 'plugin-b'] })
  activeHarnesses.push(h)
  const controller = (await h.ctx.agents.create({
    sessionId: SessionId('recovery-controller'),
    meta: { cwd: join(h.root, 'repo') },
  })).agent
  await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const tree = await h.createWorktree('wt-recover', 'feature/recover')
  const request = {
    cwd: tree.path,
    role: 'lead' as const,
    taskId: TaskId('recover-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }
  await h.dispatch(controller, request, { sessionId: SessionId('recover-lead') })
  // Cold restart over the same root: the reservation stays durable and the
  // child is no longer live — the state recovery exists for.
  await h.dispose({ keepRoot: true })
  activeHarnesses.splice(activeHarnesses.indexOf(h), 1)
  const restarted = await harness({ 'dispatch-lead': ['plugin-a', 'plugin-b'] }, { root: h.root, seed: false })
  activeHarnesses.push(restarted)
  const controller2 = (await restarted.ctx.agents.create({
    sessionId: SessionId('recovery-controller'),
    meta: { cwd: join(restarted.root, 'repo') },
  })).agent
  const reservation = restarted.ctx.agentDispatch.findDispatchedChild(controller2, TaskId('recover-task'))
  expect(reservation?.record.agentId).toBe('recover-lead')
  expect(reservation?.live).toBe(false)
  // Drop the restored single-writer lock so the later recovery must re-take
  // it through the recomposed assembly — a stale lock would prove nothing.
  await restarted.ctx.worktreeRegistry.unbind(tree.id, WorktreeLockHolder('recover-lead'))
  expect(restarted.ctx.worktreeRegistry.list(restarted.workspaceId).map(row => String(row.lockedBy)))
    .not.toContain('recover-lead')

  // A corrupted log is not a missing one: while the child is still not live,
  // the same error instance surfaces unwrapped and no replacement child
  // appears — the engine refuses at resume without touching the lock.
  const corrupt = new Error('corrupt log')
  const corruptResume = vi.spyOn(restarted.ctx.agents, 'resume').mockRejectedValue(corrupt)
  try {
    let corruptReason: unknown
    try {
      await restarted.ctx.agentDispatch.recoverChildAgent(controller2, request, {
        sessionId: SessionId('recover-lead'),
        workspaceId: restarted.workspaceId,
      })
    } catch (caught) {
      corruptReason = caught
    }
    expect(corruptResume.mock.calls).toHaveLength(1)
    expect(corruptReason).toBe(corrupt)
    expect(restarted.ctx.agentDispatch.findDispatchedChild(controller2, TaskId('recover-task'))?.live).toBe(false)
    expect(restarted.ctx.worktreeRegistry.list(restarted.workspaceId).map(row => String(row.lockedBy)))
      .not.toContain('recover-lead')
  } finally {
    corruptResume.mockRestore()
  }

  // The typed missing-log result is the one engine outcome that republishes
  // under the reserved identity; the recomposed assembly re-takes the lock.
  const resume = vi.spyOn(restarted.ctx.agents, 'resume')
    .mockRejectedValue(new SessionPersistenceNotFoundError(SessionId('recover-lead')))
  try {
    const recovered = await restarted.ctx.agentDispatch.recoverChildAgent(controller2, request, {
      sessionId: SessionId('recover-lead'),
      workspaceId: restarted.workspaceId,
    })
    expect(recovered.agent.id).toBe('recover-lead')
    expect(recovered.record.taskId).toBe('recover-task')
    expect(restarted.ctx.agentBindings.list()).toHaveLength(2)
    expect(restarted.ctx.worktreeRegistry.list(restarted.workspaceId).map(row => String(row.lockedBy)))
      .toContain('recover-lead')
  } finally {
    resume.mockRestore()
  }

  // Recovery without a reservation is the engine's own refusal, unwrapped.
  await expect(restarted.ctx.agentDispatch.recoverChildAgent(controller2, { ...request, taskId: TaskId('ghost-task') }, {
    sessionId: SessionId('recover-lead'),
    workspaceId: restarted.workspaceId,
  })).rejects.toThrow('existing child reservation')

  // A live child answers through the same entry without re-running anything.
  const liveTree = await restarted.ctx.worktreeRegistry.create({
    workspaceId: restarted.workspaceId,
    path: join(restarted.root, 'wt-live'),
    branch: 'feature/live',
  })
  const live = await restarted.dispatch(controller2, {
    cwd: liveTree.path,
    role: 'lead' as const,
    taskId: TaskId('live-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: liveTree.id, worktreePath: liveTree.path, branch: liveTree.branch },
  }, { sessionId: SessionId('live-lead') })
  const again = await restarted.ctx.agentDispatch.recoverChildAgent(controller2, {
    cwd: liveTree.path,
    role: 'lead' as const,
    taskId: TaskId('live-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: liveTree.id, worktreePath: liveTree.path, branch: liveTree.branch },
  }, {
    sessionId: SessionId('live-lead'),
    workspaceId: restarted.workspaceId,
  })
  expect(again.agent.id).toBe(live.agent.id)
})

it('delivers a concurrent same-task pair exactly one prompt under the per-task gate', async () => {
  const h = await harness({ 'dispatch-lead': ['plugin-a', 'plugin-b'] })
  activeHarnesses.push(h)
  const controller = (await h.ctx.agents.create({
    sessionId: SessionId('parallel-controller'),
    meta: { cwd: join(h.root, 'repo') },
  })).agent
  await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const tree = await h.createWorktree('wt-parallel', 'feature/parallel')
  const request = {
    cwd: tree.path,
    role: 'lead' as const,
    taskId: TaskId('parallel-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }
  const inserted: UserMessage[] = []
  const briefing = 'the one briefing'
  const listenerSetup = (childCtx: Parameters<NonNullable<DispatchAgentOptions['setup']>>[0]): void => {
    childCtx.agent?.ctx.on('agent/inbox/inserted', ({ message }) => { inserted.push(message) })
  }
  // Both callers enter together, both carry a briefing, neither has seen the
  // other. The gate decides once: the first span creates and delivers, the
  // second re-reads the durable identity and reuses without re-briefing.
  const [first, second] = await Promise.all([
    h.dispatch(controller, request, {
      sessionId: SessionId('parallel-lead'),
      prompt: briefing,
      setup: listenerSetup,
    }),
    h.dispatch(controller, request, {
      sessionId: SessionId('parallel-lead'),
      prompt: briefing,
    }),
  ])
  expect(first.agent.id).toBe('parallel-lead')
  expect(second.agent.id).toBe('parallel-lead')
  expect(first.record.agentId).toBe('parallel-lead')
  expect(second.record.agentId).toBe('parallel-lead')
  expect(inserted).toHaveLength(1)
  expect(JSON.stringify(inserted[0])).toContain(briefing)
  expect(h.ctx.agentBindings.list().filter(record => record.taskId === 'parallel-task')).toHaveLength(1)
})

it('delivers a durable settlement notice to the parent when a dispatched child finishes a real turn', async () => {
  const h = await harness({ 'dispatch-lead': ['plugin-a'] })
  activeHarnesses.push(h)
  // The mock route turns the briefing into a real completed child turn, and
  // the flush participant stands in for the durability backend the notice's
  // checkpoint rides.
  h.ctx.llm.registerAdapter(['mock'], new TextAdapter())
  ctxOnSessionFlush(h.ctx)
  const controller = (await h.ctx.agents.create({
    sessionId: SessionId('settle-controller'),
    meta: { cwd: join(h.root, 'repo') },
    agentOptions: { provider: 'mock', model: 'mock' },
  })).agent
  await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const tree = await h.createWorktree('wt-settle', 'feature/settle')
  await h.dispatch(controller, {
    cwd: tree.path,
    role: 'lead',
    taskId: TaskId('settle-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }, { sessionId: SessionId('settle-lead'), prompt: 'child briefing: do the work', agentOptions: { provider: 'mock', model: 'mock' } })

  // The child's own log holds the completed turn the notice accounts for.
  const child = h.ctx.agents.get(SessionId('settle-lead'))
  expect(child).toBeDefined()
  await until(() => child!.session.snapshotEvents().some(event =>
    event.type === 'turn/end'
    && (event.data as { reason?: { kind?: string } }).reason?.kind === 'completed'))

  // The parent learns about the settlement on its own inbox, under the
  // dispatch runtime's own typed account — matched by source kind, sender,
  // and the settled turn's identity, not by text coincidence.
  const parentNotices = (): DispatchSettledMessageSource[] => [
    ...controller.session.snapshotEvents()
      .filter(event => event.type === 'user/message')
      .map(event => (event.data as { source?: DispatchSettledMessageSource }).source),
    ...controller.inbox.nextTurn.map(message => message.source),
  ].filter((source): source is DispatchSettledMessageSource =>
    source?.kind === 'dispatch-settled' && source.senderSessionId === 'settle-lead')
  await until(() => parentNotices().length >= 1)
  await new Promise(resolve => setTimeout(resolve, 300))
  expect(parentNotices()).toHaveLength(1)
  expect(parentNotices()[0]!.kind).toBe('dispatch-settled')
  expect(parentNotices()[0]!.taskId).toBe('settle-task')
  expect(parentNotices()[0]!.turnIdentity).toMatch(/^\d+:1$/)
})

it('delivers exactly one notice per settled turn across duplicate watches', async () => {
  const h = await harness({ 'dispatch-lead': ['plugin-a'] })
  activeHarnesses.push(h)
  h.ctx.llm.registerAdapter(['mock'], new TextAdapter())
  ctxOnSessionFlush(h.ctx)
  const controller = (await h.ctx.agents.create({
    sessionId: SessionId('dup-controller'),
    meta: { cwd: join(h.root, 'repo') },
    agentOptions: { provider: 'mock', model: 'mock' },
  })).agent
  await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const tree = await h.createWorktree('wt-dup', 'feature/dup')
  const child = await h.dispatch(controller, {
    cwd: tree.path,
    role: 'lead',
    taskId: TaskId('dup-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }, { sessionId: SessionId('dup-lead'), prompt: 'child briefing: do the work', agentOptions: { provider: 'mock', model: 'mock' } })
  // A re-mounted watch — a duplicate dispatch or a cold recovery remount —
  // must dedupe on the parent's own durable facts, not on per-watch memory.
  watchChildSettlement(h.ctx, h.ctx.sessions, controller, child.agent, TaskId('dup-task'))

  const parentNotices = (): DispatchSettledMessageSource[] => [
    ...controller.session.snapshotEvents()
      .filter(event => event.type === 'user/message')
      .map(event => (event.data as { source?: DispatchSettledMessageSource }).source),
    ...controller.inbox.nextTurn.map(message => message.source),
  ].filter((source): source is DispatchSettledMessageSource =>
    source?.kind === 'dispatch-settled' && source.senderSessionId === 'dup-lead')
  await until(() => parentNotices().length >= 1)
  await new Promise(resolve => setTimeout(resolve, 400))
  expect(parentNotices()).toHaveLength(1)
  expect(parentNotices()[0]!.turnIdentity).toMatch(/^\d+:1$/)
})

it('wakes the parent again after a cold recovery remounts the settlement watch', async () => {
  // Phase 1: a real child turn settles and its notice reaches the parent.
  const h = await harness({ 'dispatch-lead': ['plugin-a'] })
  activeHarnesses.push(h)
  h.ctx.llm.registerAdapter(['mock'], new TextAdapter())
  ctxOnSessionFlush(h.ctx)
  const controller = (await h.ctx.agents.create({
    sessionId: SessionId('recover-wake-controller'),
    meta: { cwd: join(h.root, 'repo') },
    agentOptions: { provider: 'mock', model: 'mock' },
  })).agent
  await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const tree = await h.createWorktree('wt-recover-wake', 'feature/recover-wake')
  const request = {
    cwd: tree.path,
    role: 'lead' as const,
    taskId: TaskId('recover-wake-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }
  await h.dispatch(controller, request, {
    sessionId: SessionId('recover-wake-lead'),
    prompt: 'child briefing: do the work',
    agentOptions: { provider: 'mock', model: 'mock' },
  })
  const noticesOf = (parent: Agent): DispatchSettledMessageSource[] => [
    ...parent.session.snapshotEvents()
      .filter(event => event.type === 'user/message')
      .map(event => (event.data as { source?: DispatchSettledMessageSource }).source),
    ...parent.inbox.nextTurn.map(message => message.source),
  ].filter((source): source is DispatchSettledMessageSource =>
    source?.kind === 'dispatch-settled' && source.senderSessionId === 'recover-wake-lead')
  await until(() => noticesOf(controller).length >= 1)
  await new Promise(resolve => setTimeout(resolve, 300))
  expect(noticesOf(controller)).toHaveLength(1)

  // Phase 2: cold restart over the same root. The reservation survives, the
  // child is republished under the reserved identity as a NEW live agent,
  // and the settlement watch remounts on it.
  await h.dispose({ keepRoot: true })
  activeHarnesses.splice(activeHarnesses.indexOf(h), 1)
  const restarted = await harness({ 'dispatch-lead': ['plugin-a'] }, { root: h.root, seed: false })
  activeHarnesses.push(restarted)
  restarted.ctx.llm.registerAdapter(['mock'], new TextAdapter())
  ctxOnSessionFlush(restarted.ctx)
  const controller2 = (await restarted.ctx.agents.create({
    sessionId: SessionId('recover-wake-controller'),
    meta: { cwd: join(restarted.root, 'repo') },
    agentOptions: { provider: 'mock', model: 'mock' },
  })).agent
  // Drop the restored single-writer lock so the recovery re-takes it.
  await restarted.ctx.worktreeRegistry.unbind(tree.id, WorktreeLockHolder('recover-wake-lead'))
  const resume = vi.spyOn(restarted.ctx.agents, 'resume')
    .mockRejectedValue(new SessionPersistenceNotFoundError(SessionId('recover-wake-lead')))
  let recoveredAgent: Agent | undefined
  try {
    const recovered = await restarted.ctx.agentDispatch.recoverChildAgent(controller2, request, {
      sessionId: SessionId('recover-wake-lead'),
      workspaceId: restarted.workspaceId,
      agentOptions: { provider: 'mock', model: 'mock' },
    })
    recoveredAgent = recovered.agent
  } finally {
    resume.mockRestore()
  }
  expect(recoveredAgent.id).toBe('recover-wake-lead')
  // A recovered-but-idle child owes no notice: the fresh controller session
  // starts empty and recovery replays no stale settlement.
  await new Promise(resolve => setTimeout(resolve, 300))
  expect(noticesOf(controller2)).toHaveLength(0)

  // The recovered child's next real turn opens the parent's next turn with
  // a settlement notice — the wake survives the restart.
  await restarted.dispatch(controller2, request, {
    sessionId: SessionId('recover-wake-lead'),
    followupPrompt: 'recovered: continue the work.',
  })
  const child2 = restarted.ctx.agents.get(SessionId('recover-wake-lead'))
  await until(() => child2!.session.snapshotEvents().some(event =>
    event.type === 'turn/end'
    && (event.data as { reason?: { kind?: string } }).reason?.kind === 'completed'))
  await until(() => noticesOf(controller2).length >= 1)
  await new Promise(resolve => setTimeout(resolve, 300))
  expect(noticesOf(controller2)).toHaveLength(1)
  expect(noticesOf(controller2)[0]!.turnIdentity).toMatch(/^\d+:1$/)
})

it('keeps settlement claims scoped to the live child, so two isolated contexts with identical ids both wake', async () => {
  // Two independent contexts reuse the same session ids and, after their
  // first turns, the same log seqs. A string-keyed cross-host lock would
  // let one context's claim swallow the other's notice; the claim is
  // scoped to the exact live child instead, so both parents wake.
  const harnesses: Harness[] = []
  for (let index = 0; index < 2; index++) {
    const h = await harness({ 'dispatch-lead': ['plugin-a'] })
    activeHarnesses.push(h)
    harnesses.push(h)
    h.ctx.llm.registerAdapter(['mock'], new TextAdapter())
    ctxOnSessionFlush(h.ctx)
    const controller = (await h.ctx.agents.create({
      sessionId: SessionId('iso-controller'),
      meta: { cwd: join(h.root, 'repo') },
      agentOptions: { provider: 'mock', model: 'mock' },
    })).agent
    await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
    const tree = await h.createWorktree('wt-iso', 'feature/iso')
    await h.dispatch(controller, {
      cwd: tree.path,
      role: 'lead',
      taskId: TaskId('iso-task'),
      pluginId: PluginId('plugin-a'),
      worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
    }, { sessionId: SessionId('iso-lead'), prompt: 'child briefing: do the work', agentOptions: { provider: 'mock', model: 'mock' } })
  }
  expect(harnesses).toHaveLength(2)
  for (const h of harnesses) {
    const controller = h.ctx.agents.get(SessionId('iso-controller'))!
    const notices = (): DispatchSettledMessageSource[] => [
      ...controller.session.snapshotEvents()
        .filter(event => event.type === 'user/message')
        .map(event => (event.data as { source?: DispatchSettledMessageSource }).source),
      ...controller.inbox.nextTurn.map(message => message.source),
    ].filter((source): source is DispatchSettledMessageSource =>
      source?.kind === 'dispatch-settled' && source.senderSessionId === 'iso-lead')
    await until(() => notices().length >= 1)
    expect(notices()).toHaveLength(1)
  }
})

it('withholds the settlement notice when the turn end never flushes durably', async () => {
  const h = await harness({ 'dispatch-lead': ['plugin-a'] })
  activeHarnesses.push(h)
  // No flush participant: sessions.flush() answers false, so the notice's
  // durability warrant fails and the parent stays unwoken.
  h.ctx.llm.registerAdapter(['mock'], new TextAdapter())
  const controller = (await h.ctx.agents.create({
    sessionId: SessionId('quiet-controller'),
    meta: { cwd: join(h.root, 'repo') },
    agentOptions: { provider: 'mock', model: 'mock' },
  })).agent
  await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const tree = await h.createWorktree('wt-quiet', 'feature/quiet')
  await h.dispatch(controller, {
    cwd: tree.path,
    role: 'lead',
    taskId: TaskId('quiet-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }, { sessionId: SessionId('quiet-lead'), prompt: 'child briefing: do the work', agentOptions: { provider: 'mock', model: 'mock' } })

  const child = h.ctx.agents.get(SessionId('quiet-lead'))
  await until(() => child!.session.snapshotEvents().some(event =>
    event.type === 'turn/end'
    && (event.data as { reason?: { kind?: string } }).reason?.kind === 'completed'))
  await new Promise(resolve => setTimeout(resolve, 300))
  expect(controller.session.snapshotEvents().some(event =>
    event.type === 'user/message'
    && (event.data as { source?: DispatchSettledMessageSource }).source?.kind === 'dispatch-settled')).toBe(false)
})

it('does not deliver the settlement notice when the watch\'s host is disposed during the flush window', async () => {
  const h = await harness({ 'dispatch-lead': ['plugin-a'] })
  activeHarnesses.push(h)
  h.ctx.llm.registerAdapter(['mock'], new TextAdapter())
  ctxOnSessionFlush(h.ctx)
  const controller = (await h.ctx.agents.create({
    sessionId: SessionId('dispose-controller'),
    meta: { cwd: join(h.root, 'repo') },
    agentOptions: { provider: 'mock', model: 'mock' },
  })).agent
  await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const tree = await h.createWorktree('wt-dispose', 'feature/dispose')
  // Park the settlement watch inside its flush window: the barrier resolves
  // only after the host context has been disposed, so the post-flush code
  // runs against a revoked context — the exact race that used to escape as an
  // unhandled rejection.
  const barrier = Promise.withResolvers<boolean>()
  let flushEntered = false
  const sessions = h.ctx.sessions as unknown as { flush: (session: unknown) => Promise<boolean> }
  sessions.flush = async () => {
    flushEntered = true
    // Resolving `true` (not consulting the real backend) drives the watch past
    // the durability verdict straight into the post-flush delivery gate.
    return await barrier.promise
  }
  await h.dispatch(controller, {
    cwd: tree.path,
    role: 'lead',
    taskId: TaskId('dispose-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }, { sessionId: SessionId('dispose-lead'), prompt: 'child briefing: do the work', agentOptions: { provider: 'mock', model: 'mock' } })

  const child = h.ctx.agents.get(SessionId('dispose-lead'))
  await until(() => child!.session.snapshotEvents().some(event =>
    event.type === 'turn/end'
    && (event.data as { reason?: { kind?: string } }).reason?.kind === 'completed'))
  await until(() => flushEntered)

  await h.dispose()
  activeHarnesses.splice(activeHarnesses.indexOf(h), 1)
  barrier.resolve(true)

  // Give the parked continuation every chance to run and to reject: a
  // regression here surfaces as an unhandled rejection that fails this run.
  await new Promise(resolve => setTimeout(resolve, 300))
  expect(controller.session.snapshotEvents().some(event =>
    event.type === 'user/message'
    && (event.data as { source?: DispatchSettledMessageSource }).source?.kind === 'dispatch-settled')).toBe(false)
})

it('wakes the parent on a failed child turn too — any terminal turn/end settles', async () => {
  const h = await harness({ 'dispatch-lead': ['plugin-a'] })
  activeHarnesses.push(h)
  // The child's model stream always fails: the turn still ends (reason kind
  // error), and that terminal record settles — a failure-ended turn must
  // wake the parent or a failing chain would stall without any event.
  h.ctx.llm.registerAdapter(['mock'], new FailingAdapter())
  ctxOnSessionFlush(h.ctx)
  const controller = (await h.ctx.agents.create({
    sessionId: SessionId('failed-wake-controller'),
    meta: { cwd: join(h.root, 'repo') },
    agentOptions: { provider: 'mock', model: 'mock' },
  })).agent
  await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const tree = await h.createWorktree('wt-failed-wake', 'feature/failed-wake')
  await h.dispatch(controller, {
    cwd: tree.path,
    role: 'lead',
    taskId: TaskId('failed-wake-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }, { sessionId: SessionId('failed-wake-lead'), prompt: 'child briefing: do the work', agentOptions: { provider: 'mock', model: 'mock' } })

  const child = h.ctx.agents.get(SessionId('failed-wake-lead'))
  await until(() => child!.session.snapshotEvents().some(event =>
    event.type === 'turn/end'
    && (event.data as { reason?: { kind?: string } }).reason?.kind === 'error'))
  const parentNotices = (): DispatchSettledMessageSource[] => [
    ...controller.session.snapshotEvents()
      .filter(event => event.type === 'user/message')
      .map(event => (event.data as { source?: DispatchSettledMessageSource }).source),
    ...controller.inbox.nextTurn.map(message => message.source),
  ].filter((source): source is DispatchSettledMessageSource =>
    source?.kind === 'dispatch-settled' && source.senderSessionId === 'failed-wake-lead')
  await until(() => parentNotices().length >= 1)
  await new Promise(resolve => setTimeout(resolve, 300))
  expect(parentNotices()).toHaveLength(1)
  expect(parentNotices()[0]!.turnIdentity).toMatch(/^\d+:1$/)
})

it('delivers an explicit followup to an existing child without re-creating, and a fresh creation ignores one', async () => {
  const h = await harness({ 'dispatch-lead': ['plugin-a'] })
  activeHarnesses.push(h)
  const controller = (await h.ctx.agents.create({
    sessionId: SessionId('followup-controller'),
    meta: { cwd: join(h.root, 'repo') },
  })).agent
  await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const tree = await h.createWorktree('wt-followup', 'feature/followup')
  const request = {
    cwd: tree.path,
    role: 'lead' as const,
    taskId: TaskId('followup-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }
  await h.dispatch(controller, request, { sessionId: SessionId('followup-lead') })
  expect(h.ctx.agentBindings.list().filter(record => record.taskId === 'followup-task')).toHaveLength(1)

  const followupCount = (): number => h.ctx.agents.get(SessionId('followup-lead'))!
    .session.snapshotEvents()
    .filter(event => event.type === 'agent/inbox/spliced')
    .flatMap(event => (event.data as { inserted?: Array<{ id?: string }> }).inserted ?? [])
    .filter(message => typeof message.id === 'string' && message.id.startsWith('dispatch-followup:'))
    .length

  await h.dispatch(controller, request, {
    sessionId: SessionId('followup-lead'),
    followupPrompt: 'followup: review the delivered work now.',
  })
  expect(followupCount()).toBe(1)
  expect(h.ctx.agentBindings.list().filter(record => record.taskId === 'followup-task')).toHaveLength(1)

  // A second explicit followup is a second delivery: every followup is a
  // distinct instruction, not an idempotent re-brief.
  await h.dispatch(controller, request, {
    sessionId: SessionId('followup-lead'),
    followupPrompt: 'followup: also check the ledger.',
  })
  expect(followupCount()).toBe(2)

  // A fresh creation never queues a followup: the field applies only to an
  // existing child.
  const freshTree = await h.createWorktree('wt-fresh', 'feature/fresh')
  await h.dispatch(controller, {
    cwd: freshTree.path,
    role: 'lead',
    taskId: TaskId('fresh-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: freshTree.id, worktreePath: freshTree.path, branch: freshTree.branch },
  }, { sessionId: SessionId('fresh-lead'), followupPrompt: 'followup: ignored on a fresh creation' })
  expect(h.ctx.agents.get(SessionId('fresh-lead'))!.session.snapshotEvents()
    .filter(event => event.type === 'agent/inbox/spliced')
    .flatMap(event => (event.data as { inserted?: Array<{ id?: string }> }).inserted ?? [])
    .filter(message => typeof message.id === 'string' && message.id.startsWith('dispatch-followup:')))
    .toHaveLength(0)
})

it('rechecks the live parent after the flush window and never delivers to a disposed parent', async () => {
  const h = await harness({ 'dispatch-lead': ['plugin-a'] })
  activeHarnesses.push(h)
  h.ctx.llm.registerAdapter(['mock'], new TextAdapter())
  // The flush blocks once the child's real turn has ended — the watch's
  // delivery window — while earlier checkpoints pass through untouched.
  let releaseFlush: () => void = () => {}
  let flushEntered = false
  const childSessionRef: { session?: Session } = {}
  h.ctx.on('session/flush', (session: Session) => {
    if (session !== childSessionRef.session) return
    const ended = session.snapshotEvents().some(event =>
      event.type === 'turn/end'
      && (event.data as { reason?: { kind?: string } }).reason?.kind === 'completed')
    if (!ended) return
    flushEntered = true
    return new Promise<void>((resolve) => { releaseFlush = resolve })
  })
  const parentHandle = await h.ctx.agents.create({
    sessionId: SessionId('window-controller'),
    meta: { cwd: join(h.root, 'repo') },
    agentOptions: { provider: 'mock', model: 'mock' },
  })
  const controller = parentHandle.agent
  await h.ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const tree = await h.createWorktree('wt-window', 'feature/window')
  await h.dispatch(controller, {
    cwd: tree.path,
    role: 'lead',
    taskId: TaskId('window-task'),
    pluginId: PluginId('plugin-a'),
    worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
  }, { sessionId: SessionId('window-lead'), prompt: 'child briefing: do the work', agentOptions: { provider: 'mock', model: 'mock' } })

  const child = h.ctx.agents.get(SessionId('window-lead'))
  childSessionRef.session = child!.session
  await until(() => child!.session.snapshotEvents().some(event =>
    event.type === 'turn/end'
    && (event.data as { reason?: { kind?: string } }).reason?.kind === 'completed'))
  await until(() => flushEntered)
  const followupSpy = vi.spyOn(controller, 'followup')

  // The parent leaves the registry inside the flush window; the watch must
  // re-check the same live parent after the flush and skip the delivery.
  await parentHandle.dispose()
  releaseFlush()
  await new Promise(resolve => setTimeout(resolve, 200))
  expect(followupSpy).not.toHaveBeenCalled()
})

/** Register a no-op session/flush participant so flushes answer durable. */
function ctxOnSessionFlush(ctx: Context): void {
  ctx.on('session/flush', () => {})
}
