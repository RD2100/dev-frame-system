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
import { afterEach, expect, it } from 'vitest'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import type { UserMessage } from '@deepseek-ai/dsh-llm'
import AgentHierarchy, { type AgentHierarchyConfigInput } from '@deepseek-ai/dsh-experimental-agent-hierarchy'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import SubprocessLocal from '@deepseek-ai/dsh-subprocess-local'
import WorkspaceRegistry, { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { defineContentToolFixture } from '@deepseek-ai/dsh-tools'
import {
  GitWorktreeRegistry,
  WorktreeId,
  WorktreeLockHolder,
} from '@deepseek-ai/dsh-worktree-registry'
import type { Worktree } from '@deepseek-ai/dsh-worktree-registry'
import { AgentDispatch, AgentDispatchError, type DispatchAgentOptions } from '../src/index.ts'

/** One git invocation, failing loud with its stderr. */
function git(cwd: string, ...args: string[]): Promise<string> {
  return new Promise((resolvePromise, rejectPromise) => {
    execFile('git', args, { cwd, windowsHide: true }, (error, stdout, stderr) => {
      if (error !== null) {
        rejectPromise(new Error(`git ${args.join(' ')} failed: ${error.message} stderr=${String(stderr ?? '')}`))
      } else {
        resolvePromise(String(stdout))
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
  dispose: () => Promise<void>
}

/** Boot the real composition: agent loop, storage, both registries, engine, dispatch entry. */
async function harness(leadPluginScopes: AgentHierarchyConfigInput['leadPluginScopes']): Promise<Harness> {
  const root = await mkdtemp(join(tmpdir(), 'dsh-agent-dispatch-'))
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
    await ctx.plugin(AgentDispatch)
    const repo = join(root, 'repo')
    await mkdir(repo)
    await git(root, 'init', '-b', 'main', repo)
    await git(repo, 'config', 'user.email', 'agent-dispatch@test.local')
    await git(repo, 'config', 'user.name', 'Agent Dispatch Tests')
    await git(repo, 'commit', '--allow-empty', '-m', 'init')
    const workspace = await ctx.workspaceRegistry.create(repo)
    return {
      ctx,
      root,
      workspaceId: workspace.id,
      createWorktree: async (name, branch) => await ctx.worktreeRegistry.create({
        workspaceId: workspace.id,
        path: join(root, name),
        branch,
      }),
      dispatch: (parent, request, options) => ctx.agentDispatch.createChildAgent(parent, request, {
        workspaceId: workspace.id,
        ...options,
      }),
      dispose: async () => {
        await ctx.fiber.dispose()
        await rm(root, { recursive: true, force: true })
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
