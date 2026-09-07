/** Real task admission over Loader, hierarchy dispatch, durable state, and concurrent Agent model requests. */

import { execFile } from 'node:child_process'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { promisify } from 'node:util'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Include from '@deepseek-ai/cordis-plugin-include'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import LlmRuntime, { LlmAdapter, ToolCallId, createUserMessage } from '@deepseek-ai/dsh-llm'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import WorkspaceRegistry from '@deepseek-ai/dsh-workspace'
import SubprocessLocal from '@deepseek-ai/dsh-subprocess-local'
import GitWorktreeRegistry from '@deepseek-ai/dsh-worktree-registry'
import { WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import { PluginId, TaskId, type TaskRecord } from '@deepseek-ai/dsh-experimental-project-contracts'
import { devFrameProjectionDefinition } from '@deepseek-ai/dsh-experimental-devframe/src/projection.ts'
import { DevFrameSessionJournal } from '@deepseek-ai/dsh-experimental-devframe/src/session-journal.ts'
import ProjectController from '../src/index.ts'
import * as consumer from '../src/task-consumer.ts'
import * as deliveryConsumer from '../src/delivery-consumer.ts'
import * as integrationConsumer from '../src/consumer.ts'
import AgentHierarchy from '@deepseek-ai/dsh-experimental-agent-hierarchy'
import * as agentDispatch from '@deepseek-ai/dsh-experimental-agent-dispatch'
import type { GenerateOptions, StreamChunk } from '@deepseek-ai/dsh-llm'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { AcceptanceHash, ConfigurationConfirmationId, DevFrameSnapshotId, WorkspaceId as GoalWorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { ControllerSessionId, TaskId as GoalTaskId } from '@deepseek-ai/dsh-experimental-devframe/controller'
import { computeSourceFingerprint, FileRequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe'
import { applyWorkload, DeliveryAdapter, workloadGit } from './task-delivery-fixture.ts'

const cleanups: (() => Promise<void>)[] = []

afterEach(async () => {
  for (const cleanup of cleanups.splice(0).reverse()) await cleanup()
})

async function load(delivery = false, mutateDuringCheck = false) {
  const root = await mkdtemp(join(tmpdir(), 'dsh-project-integration-loader-'))
  cleanups.push(() => rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 }))
  const ctx = new Context()
  cleanups.push(() => ctx.fiber.dispose())
  const modules = new Map<string, unknown>([
    ['@deepseek-ai/dsh-llm', LlmRuntime],
    ['@deepseek-ai/dsh-session', SessionStore],
    ['@deepseek-ai/dsh-session-persistence-jsonl', JsonlSessionPersistence],
    ['@deepseek-ai/dsh-system-prompt', SystemPrompt],
    ['@deepseek-ai/dsh-tools', ToolRuntime],
    ['@deepseek-ai/dsh-agent', AgentRegistry],
    ['@deepseek-ai/dsh-agent-loop', AgentLoop],
    ['@deepseek-ai/dsh-session-projection', SessionProjectionRegistry],
    ['@deepseek-ai/dsh-storage', Storage],
    ['@deepseek-ai/dsh-storage-json', StorageJson],
    ['@deepseek-ai/dsh-storage-domain', StorageDomain],
    ['@deepseek-ai/dsh-experimental-session-identity', AgentBindingRegistry],
    ['@deepseek-ai/dsh-workspace', WorkspaceRegistry],
    ['@deepseek-ai/dsh-subprocess-local', SubprocessLocal],
    ['@deepseek-ai/dsh-worktree-registry', GitWorktreeRegistry],
    ['@deepseek-ai/dsh-experimental-agent-hierarchy', AgentHierarchy],
    ['@deepseek-ai/dsh-experimental-agent-dispatch', agentDispatch],
    ['@deepseek-ai/dsh-experimental-project-controller', ProjectController],
    ['@deepseek-ai/dsh-experimental-project-controller/task-consumer', consumer],
  ])
  const settings: Record<string, unknown> = {
    '@deepseek-ai/dsh-agent-loop': { agents: [] },
    '@deepseek-ai/dsh-session-persistence-jsonl': { root: join(root, 'sessions'), compression: 'none', writeBatchMaxDelayMs: 1 },
    '@deepseek-ai/dsh-storage-json': { root: join(root, 'storage') },
    '@deepseek-ai/dsh-storage-domain': { backend: 'json' },
    '@deepseek-ai/dsh-experimental-agent-hierarchy': {
      roleToolPolicies: {
        controller: { inheritedTools: ['project_task', 'agent_dispatch'] },
        lead: { inheritedTools: ['project_task', 'agent_dispatch'] },
        worker: { inheritedTools: ['project_task'] },
      },
      leadPluginScopes: { lead: ['plugin-a'] },
    },
  }
  if (delivery) {
    const requiredChecksPath = join(root, 'approved-checks.json')
    const store = new FileRequiredChecksConfigStore({ path: requiredChecksPath })
    const requiredChecksByTask: Record<string, string> = {}
    for (const suffix of ['a', 'b']) {
      const script = mutateDuringCheck
        ? `import { writeFileSync } from 'node:fs'; writeFileSync('worker-${suffix}.txt', 'changed during checks')`
        : `import { readFileSync } from 'node:fs'; import { strict as assert } from 'node:assert'; assert.equal(readFileSync('worker-${suffix}.txt', 'utf8'), 'implemented\\n')`
      const digest = await store.save({ version: 1, checks: [
        { checkId: 'workload', executable: process.execPath, arguments: ['--input-type=module', '-e', script], cwd: join(root, 'worker-' + suffix) },
        { checkId: 'diff-check', executable: 'git', arguments: ['diff', '--check'], cwd: join(root, 'worker-' + suffix) },
      ] })
      requiredChecksByTask['task-' + suffix] = digest
    }
    modules.set('@deepseek-ai/dsh-experimental-project-controller/delivery-consumer', deliveryConsumer)
    modules.set('@deepseek-ai/dsh-experimental-project-controller/consumer', integrationConsumer)
    modules.set('fixture-workload', { name: 'fixture-workload', inject: ['tools', 'agentBindings'], apply: applyWorkload })
    const processSettings = { requiredChecksPath, gitExecutable: 'git', gitTimeoutMs: 15_000, gitMaxOutputBytes: 1024 * 1024 }
    settings['@deepseek-ai/dsh-experimental-project-controller/delivery-consumer'] = {
      ...processSettings, requiredChecksByTask, checkTimeoutMs: 15_000, checkMaxOutputBytes: 1024 * 1024,
    }
    settings['@deepseek-ai/dsh-experimental-project-controller/consumer'] = processSettings
    settings['@deepseek-ai/dsh-experimental-agent-hierarchy'] = {
      roleToolPolicies: {
        controller: { inheritedTools: ['project_task', 'agent_dispatch', 'project_integrate'] },
        lead: { inheritedTools: ['project_review', 'agent_dispatch'] },
        worker: { inheritedTools: ['fixture_commit', 'project_deliver'] },
      }, leadPluginScopes: { lead: ['plugin-a'] },
    }
  }
  const configPath = join(root, 'cordis.yml')
  await writeFile(configPath, JSON.stringify([...modules.keys()].map(name => ({ name, config: settings[name] }))))
  ctx.baseUrl = pathToFileURL(root).href + '/'
  await ctx.plugin(Loader)
  ctx.loader.builtins.include = Include
  ctx.loader.internal = {
    version: 'v2',
    async import(specifier: string) {
      if (!modules.has(specifier)) throw new Error(`Unexpected Loader import ${specifier}`)
      return modules.get(specifier)
    },
  } as unknown as NonNullable<typeof ctx.loader.internal>
  await ctx.loader.create({ name: 'cordis:include', config: { path: pathToFileURL(configPath).href } })
  await ctx.loader.await()
  expect([...ctx.loader.entries()].filter(entry => entry.fiber === undefined && !entry.disabled)
    .map(entry => entry.options.name)).toEqual([])
  return { ctx, root }
}

function execute(ctx: Context, agent: Agent, args: object) {
  return ctx.tools.execute({ signal: new AbortController().signal, callId: ToolCallId('task-call'),
    name: 'project_task', arguments: args, agent })
}

/** Only the external model boundary is scripted; the barrier requires both real Worker requests. */
class WorkerAdapter extends LlmAdapter {
  readonly entered: string[] = []
  readonly completed: string[] = []
  active = 0
  maxActive = 0
  private readonly both = Promise.withResolvers<undefined>()

  override async resolveModel(provider: string, model: string) {
    return { provider, id: model, name: model }
  }

  async * stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    const id = String(options.sessionId)
    if (!['worker-a', 'worker-b'].includes(id)) throw new Error(`Unexpected model caller ${id}`)
    this.entered.push(id)
    this.active++
    this.maxActive = Math.max(this.maxActive, this.active)
    if (this.entered.length === 2) this.both.resolve(undefined)
    const aborted = Promise.withResolvers<never>()
    const abort = () => { aborted.reject(new Error('Worker request cancelled')) }
    options.signal?.addEventListener('abort', abort, { once: true })
    try {
      if (options.signal?.aborted) abort()
      await Promise.race([this.both.promise, aborted.promise])
      yield { type: 'block-start', index: 0, blockType: 'text' }
      yield { type: 'text-delta', index: 0, text: 'Work started' }
      yield { type: 'block-end', index: 0, block: { type: 'text', text: 'Work started' } }
      yield { type: 'finish', reason: { kind: 'stop' } }
    } finally {
      options.signal?.removeEventListener('abort', abort)
      this.active--
      this.completed.push(id)
    }
  }
}

async function setup(planTasks = false, delivery = false, mutateDuringCheck = false) {
  const { ctx, root } = await load(delivery, mutateDuringCheck)
  const exec = promisify(execFile)
  const repo = join(root, 'repo')
  await mkdir(repo)
  await writeFile(join(root, 'empty-config'), '')
  await mkdir(join(root, 'empty-template'))
  const git = async (...args: string[]) => (await exec('git', ['-C', repo, ...args], {
    windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024,
    env: { ...Object.fromEntries(Object.entries(process.env)
      .filter(([key]) => !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key))),
    GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: join(root, 'empty-config') },
  })).stdout.trim()
  await git('init', '--template=' + join(root, 'empty-template'), '-b', 'main')
  await git('config', 'user.name', 'Task Loader')
  await git('config', 'user.email', 'task@example.invalid')
  await git('config', 'commit.gpgsign', 'false')
  await git('config', 'core.hooksPath', join(root, 'no-hooks'))
  await git('config', 'core.attributesFile', join(root, 'empty-config'))
  await git('config', 'core.autocrlf', 'false')
  await git('commit', '--allow-empty', '-m', 'initial')
  const workspace = await ctx.workspaceRegistry.create(repo)
  const trees = await Promise.all(['target', 'lead', 'worker-a', 'worker-b'].map(async branch =>
    await ctx.worktreeRegistry.create({ workspaceId: workspace.id, path: join(root, branch), branch })))
  const target = trees[0]!
  const controller = (await ctx.agents.create({ sessionId: SessionId('controller'), meta: { cwd: target.path } })).agent
  await ctx.agentBindings.bind({ agentId: controller.id, role: 'controller',
    worktree: { worktreeId: target.id, worktreePath: target.path } })
  await ctx.worktreeRegistry.bind(target.id, WorktreeLockHolder(controller.id))
  ctx.effect(() => ctx.sessionProjections.register(devFrameProjectionDefinition))
  const acceptanceHash = AcceptanceHash('task-acceptance')
  controller.session.append('devframe/goal-binding', {
    version: 1, controllerSessionId: ControllerSessionId(controller.id), workspaceId: GoalWorkspaceId(workspace.id),
    goalId: GoalId('task-goal'), goalRevision: 1, taskIds: ['task-a', 'task-b'].map(GoalTaskId),
    acceptanceHash, sourceFingerprint: (await computeSourceFingerprint({ worktreePath: target.path })).fingerprint,
    snapshotId: DevFrameSnapshotId('task-snapshot'),
    confirmation: { id: ConfigurationConfirmationId('task-confirmation'), acceptanceHash },
    lifecycle: 'admission_open', budget: { maxAttempts: 10, consumedAttempts: 0 },
  })
  await ctx.sessions.flush(controller.session)
  ctx.projectController.startProject()
  if (planTasks) {
    for (const taskId of ['task-a', 'task-b']) {
      const planned = await execute(ctx, controller, { action: 'plan', taskId, title: taskId, pluginId: 'plugin-a' })
      expect(planned.isError, JSON.stringify(planned)).not.toBe(true)
    }
  }
  const dispatch = async (parent: Agent, role: 'lead' | 'worker', taskId: string, index: number) => {
    const tree = trees[index]!
    const result = await ctx.agentDispatch.createChildAgent(parent, {
      role, taskId: TaskId(taskId), pluginId: PluginId('plugin-a'), cwd: tree.path,
      worktree: { worktreeId: tree.id, worktreePath: tree.path, branch: tree.branch },
    }, { workspaceId: workspace.id, sessionId: SessionId(tree.branch), agentOptions: { provider: 'test', model: 'test' } })
    return result.agent
  }
  const lead = await dispatch(controller, 'lead', 'coordination', 1)
  const workerA = await dispatch(lead, 'worker', 'task-a', 2)
  const workerB = await dispatch(lead, 'worker', 'task-b', 3)
  const adapter = new WorkerAdapter()
  if (!delivery) ctx.llm.registerAdapter(['test'], adapter)
  return { ctx, root, controller, lead, workerA, workerB, adapter, trees }
}

async function deliverySetup(mutateDuringCheck = false) {
  const f = await setup(true, true, mutateDuringCheck)
  const adapter = new DeliveryAdapter()
  f.ctx.llm.registerAdapter(['test'], adapter)
  const policy = { inheritedTools: [], denyScopedTools: [] }
  f.controller.session.append('devframe/role-policy', {
    version: 1, controllerSessionId: f.controller.id, workspaceId: GoalWorkspaceId(f.trees[0]!.workspaceId), policyVersion: 'delivery-policy',
    config: { controller: policy, worker: policy, reviewer: policy },
    assignments: [{ role: 'controller', sessionId: f.controller.id }, { role: 'lead', sessionId: f.lead.id }],
  })
  await f.ctx.sessions.flush(f.controller.session)
  const tool = async (agent: Agent, name: string, args: object) => await f.ctx.tools.execute({
    signal: new AbortController().signal, callId: ToolCallId('delivery-call'), name, arguments: args, agent,
  })
  const start = async (briefing: boolean) => {
    for (const taskId of ['task-a', 'task-b']) {
      const result = await execute(f.ctx, f.controller, { action: 'start', taskId, ...(briefing ? { briefing: 'Implement and deliver' } : {}) })
      expect(result.isError, JSON.stringify(result)).not.toBe(true)
    }
    if (briefing) await Promise.all([f.workerA.whenIdle(), f.workerB.whenIdle()])
  }
  const turn = async (agent: Agent, calls: Parameters<DeliveryAdapter['enqueue']>[1]) => {
    const before = agent.session.snapshotEvents().length
    adapter.enqueue(String(agent.id), calls)
    agent.followup(createUserMessage({ content: [{ type: 'text', text: 'Execute the next authorized task stage' }],
      source: { kind: 'plugin', plugin: 'delivery-fixture' } }))
    await agent.whenIdle()
    expect(JSON.stringify(agent.session.snapshotEvents().slice(before).filter(event => event.type === 'tool/result')))
      .not.toContain('"isError":true')
  }
  return { ...f, adapter, tool, start, turn }
}

describe('project task consumer through the real Loader', () => {
  // Delivery cases run four linked worktrees, real checks, and multiple model/tool turns.
  describe('delivery lifecycle', () => {
    it('executes overlapping Worker commits, approved checks, lead model review, and controller integration', async () => {
      const f = await deliverySetup()
      await f.start(true)
      expect(f.adapter.maxActive).toBe(2)
      expect(f.ctx.projectController.list().map(task => task.state), JSON.stringify({
        results: [f.workerA, f.workerB].flatMap(worker => worker.session.snapshotEvents().filter(event => event.type === 'tool/result')),
        verifications: f.ctx.sessionProjections.stateOf(f.controller.session, 'devframe')?.verifications,
      })).toEqual(['reviewing', 'reviewing'])
      const state = f.ctx.sessionProjections.stateOf(f.controller.session, 'devframe')!
      expect(state.failure).toBeNull()
      expect(state.deliveries).toHaveLength(2)
      expect(state.verifications).toHaveLength(2)
      expect(state.reviews).toHaveLength(0)
      for (const delivery of state.deliveries) {
        expect(delivery.sourceCommit).toBe(await workloadGit(delivery.worktreePath, 'rev-parse', 'HEAD'))
        const verification = state.verifications.find(item => item.deliveryId === delivery.deliveryId)!
        expect(verification.status).toBe('passed')
        expect(verification.checks.map(check => check.exitCode)).toEqual([0, 0])
        expect(delivery.binding.sourceFingerprint).not.toBe(delivery.sourceFingerprint)
      }
      for (const [taskId, worker] of [['task-a', f.workerA], ['task-b', f.workerB]] as const) {
        if (taskId === 'task-b') {
          await f.turn(worker, [
            { name: 'fixture_commit', arguments: { action: 'rebase' } },
            { name: 'project_deliver', arguments: { taskId } },
          ])
        }
        await f.turn(f.lead, [{ name: 'project_review', arguments: { taskId, decision: 'pass', findings: [] } }])
        expect(f.ctx.projectController.find(TaskId(taskId))?.state,
          JSON.stringify(f.lead.session.snapshotEvents().slice(-12))).toBe('submitted')
        const result = await f.tool(f.controller, 'project_integrate', { action: 'integrate', taskId })
        expect(result.isError, JSON.stringify(result)).not.toBe(true)
        expect(f.ctx.projectController.find(TaskId(taskId))?.state).toBe('integrated')
        expect(await workloadGit(f.trees[0]!.path, 'rev-parse', 'HEAD'))
          .toBe(await workloadGit(worker.session.header.cwd!, 'rev-parse', 'HEAD'))
      }
      expect(await workloadGit(f.trees[0]!.path, 'ls-tree', '--name-only', 'HEAD')).toBe('worker-a.txt\nworker-b.txt')
      for (const taskId of ['task-a', 'task-b']) {
        expect(f.ctx.storageDomain.get('project_tasks')!.table('tasks').get(taskId)).toMatchObject({ state: 'integrated' })
      }
      expect(f.lead.session.snapshotEvents().filter(event => event.type === 'tool/call' && event.data.name === 'project_review'))
        .toHaveLength(2)
    })

    it('does not record a passing verification when an approved check changes the source', async () => {
      const f = await deliverySetup(true)
      await f.start(true)
      const state = f.ctx.sessionProjections.stateOf(f.controller.session, 'devframe')!
      expect(state.deliveries).toHaveLength(2)
      expect(state.verifications).toEqual([])
      expect(state.reviews).toEqual([])
      expect(f.ctx.projectController.list().map(task => task.state)).toEqual(['developing', 'developing'])
      for (const worker of [f.workerA, f.workerB]) {
        expect(await workloadGit(worker.session.header.cwd!, 'status', '--porcelain')).toContain('M worker-')
      }
    })

    it('refuses another task append after its shared controller journal flush failed', async () => {
      const f = await deliverySetup()
      await f.start(false)
      for (const worker of [f.workerA, f.workerB]) {
        expect((await f.tool(worker, 'fixture_commit', { action: 'write' })).isError).not.toBe(true)
      }
      const original = f.ctx.sessions.flush.bind(f.ctx.sessions)
      const spy = vi.spyOn(f.ctx.sessions, 'flush').mockImplementation(async (session) => {
        if (session.id === f.controller.id) throw new Error('controller journal unavailable')
        return await original(session)
      })
      try {
        expect((await f.tool(f.workerA, 'project_deliver', { taskId: 'task-a' })).isError).toBe(true)
        const before = f.controller.session.snapshotEvents().length
        spy.mockRestore()
        expect((await f.tool(f.workerB, 'project_deliver', { taskId: 'task-b' })).isError).toBe(true)
        expect(f.controller.session.snapshotEvents()).toHaveLength(before)
        const state = f.ctx.sessionProjections.stateOf(f.controller.session, 'devframe')!
        expect(state.verifications).toEqual([])
        expect(state.deliveries.filter(item => String(item.taskId) === 'task-b')).toEqual([])
      } finally { spy.mockRestore() }
    })

    it('rechecks Worker ownership after waiting behind another task journal flush', async () => {
      const f = await deliverySetup()
      await f.start(false)
      for (const worker of [f.workerA, f.workerB]) {
        expect((await f.tool(worker, 'fixture_commit', { action: 'write' })).isError).not.toBe(true)
      }
      const blocked = Promise.withResolvers<undefined>()
      const release = Promise.withResolvers<undefined>()
      const queued = Promise.withResolvers<undefined>()
      const originalFlush = f.ctx.sessions.flush.bind(f.ctx.sessions)
      const flushSpy = vi.spyOn(f.ctx.sessions, 'flush').mockImplementation(async (session) => {
        if (session.id === f.controller.id) { blocked.resolve(undefined); await release.promise }
        return await originalFlush(session)
      })
      // Observe queue entry while delegating every append and persistence operation to the real journal.
      const append = Reflect.get(DevFrameSessionJournal.prototype, 'append')
      const appendSpy = vi.spyOn(DevFrameSessionJournal.prototype, 'append').mockImplementation(function (this: DevFrameSessionJournal, ...args) {
        const pending = append.apply(this, args)
        if (args[1] === 'devframe/task-delivery' && 'taskId' in args[2] && String(args[2].taskId) === 'task-b') {
          queued.resolve(undefined)
        }
        return pending
      })
      const first = f.tool(f.workerA, 'project_deliver', { taskId: 'task-a' })
      let second: ReturnType<typeof f.tool> | undefined
      try {
        await blocked.promise
        second = f.tool(f.workerB, 'project_deliver', { taskId: 'task-b' })
        await queued.promise
        await f.ctx.worktreeRegistry.unbind(f.trees[3]!.id, WorktreeLockHolder(f.workerB.id))
        release.resolve(undefined)
        const firstResult = await first
        expect(firstResult.isError, JSON.stringify(firstResult)).not.toBe(true)
        expect((await second).isError).toBe(true)
        const state = f.ctx.sessionProjections.stateOf(f.controller.session, 'devframe')!
        expect(state.deliveries.map(item => String(item.taskId))).toEqual(['task-a'])
        expect(state.verifications).toHaveLength(1)
        expect(f.ctx.projectController.find(TaskId('task-b'))?.state).toBe('developing')
      } finally {
        release.resolve(undefined)
        await Promise.allSettled([first, ...(second === undefined ? [] : [second])])
        appendSpy.mockRestore()
        flushSpy.mockRestore()
      }
    })

    it('recovers the task board after a durable negative review without recording another decision', async () => {
      const f = await deliverySetup()
      await f.start(true)
      const table = f.ctx.storageDomain.get('project_tasks')!.table('tasks')
      const spy = vi.spyOn(table, 'put').mockRejectedValueOnce(new Error('board write interrupted'))
      const args = { taskId: 'task-a', decision: 'changes_required', findings: [{ id: 'fix', severity: 'blocking', message: 'Correct the output' }] }
      let reviewResult: Awaited<ReturnType<typeof f.tool>> | undefined
      try {
        reviewResult = await f.tool(f.lead, 'project_review', args)
        expect(reviewResult.isError, JSON.stringify(reviewResult)).toBe(true)
      }
      finally { spy.mockRestore() }
      expect(f.ctx.projectController.find(TaskId('task-a'))?.state, JSON.stringify({
        reviewResult,
        results: f.workerA.session.snapshotEvents().filter(event => event.type === 'tool/result'),
        verifications: f.ctx.sessionProjections.stateOf(f.controller.session, 'devframe')?.verifications,
      })).toBe('reviewing')
      expect((await f.tool(f.lead, 'project_review', args)).isError).not.toBe(true)
      expect(f.ctx.projectController.find(TaskId('task-a'))?.state).toBe('developing')
      const state = f.ctx.sessionProjections.stateOf(f.controller.session, 'devframe')!
      expect(state.reviews).toHaveLength(1)
      expect(state.reviews[0]?.decision).toBe('changes_required')
      expect((await f.tool(f.workerA, 'project_deliver', { taskId: 'task-a' })).isError).toBe(true)
      expect(state.deliveries).toHaveLength(2)
    })
  })

  it.each(['plan', 'start'] as const)('refuses %s after a durable stop request closes admission', async (action) => {
    const { ctx, controller, adapter } = await setup(action === 'start')
    const goal = ctx.sessionProjections.stateOf(controller.session, 'devframe')!.bindings.at(-1)!
    const binding = {
      controllerSessionId: goal.controllerSessionId, workspaceId: goal.workspaceId,
      goalId: goal.goalId, goalRevision: goal.goalRevision, taskIds: goal.taskIds,
      acceptanceHash: goal.acceptanceHash, sourceFingerprint: goal.sourceFingerprint, snapshotId: goal.snapshotId,
    }
    controller.session.append('devframe/lifecycle', {
      version: 1, binding, state: 'stop_requested', remaining: [],
    })
    await ctx.sessions.flush(controller.session)
    expect(ctx.sessionProjections.stateOf(controller.session, 'devframe')?.failure).toBeNull()
    const result = await execute(ctx, controller, action === 'plan'
      ? { action, taskId: 'task-a', title: 'A', pluginId: 'plugin-a' }
      : { action, taskId: 'task-a', briefing: 'Must not start' })
    expect(result.isError).toBe(true)
    expect(ctx.projectController.find(TaskId('task-a'))?.state).toBe(action === 'plan' ? undefined : 'planned')
    expect(adapter.entered).toEqual([])
  })

  it('plans and starts two independently locked Workers whose model requests overlap', async () => {
    const { ctx, controller, lead, workerA, workerB, adapter, trees } = await setup(true)
    expect(ctx.tools.get('project_task')).toBeDefined()
    expect(ctx.projectController.list().map(task => task.state)).toEqual(['planned', 'planned'])
    expect(adapter.entered).toEqual([])
    const started = await Promise.all(['task-a', 'task-b'].map(async taskId =>
      await execute(ctx, controller, { action: 'start', taskId, briefing: `Begin ${taskId}` })))
    for (const result of started) expect(result.isError, JSON.stringify(result)).not.toBe(true)
    await Promise.all([workerA.whenIdle(), workerB.whenIdle()])
    expect(adapter.entered.sort()).toEqual(['worker-a', 'worker-b'])
    expect(adapter.completed).toHaveLength(2)
    expect(adapter.maxActive).toBe(2)
    expect(ctx.projectController.list().map(task => task.state)).toEqual(['developing', 'developing'])
    for (const worker of [workerA, workerB]) {
      expect(ctx.agentBindings.find(worker.id)?.parentSessionId).toBe(lead.id)
      expect(worker.session.snapshotEvents().filter(event => event.type === 'request/context')).toHaveLength(1)
      const binding = ctx.agentBindings.find(worker.id)!
      expect(ctx.worktreeRegistry.list(trees[0]!.workspaceId).find(tree => tree.id === binding.worktreeId)?.lockedBy)
        .toBe(worker.id)
    }
    expect(new Set(trees.map(tree => tree.path)).size).toBe(4)
    const countBefore = workerA.session.snapshotEvents().length
    const repeated = await execute(ctx, controller, { action: 'start', taskId: 'task-a', briefing: 'Do not duplicate' })
    expect(repeated.isError).toBe(true)
    expect(workerA.session.snapshotEvents()).toHaveLength(countBefore)
    expect(adapter.entered).toHaveLength(2)
    expect(controller.session.snapshotEvents().some(event => event.type === 'devframe/verification' || event.type === 'devframe/review')).toBe(false)
  })

  it('refuses non-root callers, tasks outside the Goal, and a mismatched Worker scope', async () => {
    const { ctx, controller, lead, workerA, adapter } = await setup()
    for (const caller of [lead, workerA]) {
      expect((await execute(ctx, caller, { action: 'plan', taskId: 'task-a', title: 'A', pluginId: 'plugin-a' })).isError).toBe(true)
    }
    expect((await execute(ctx, controller, { action: 'plan', taskId: 'outside', title: 'Outside', pluginId: 'plugin-a' })).isError).toBe(true)
    expect(ctx.projectController.list()).toEqual([])
    expect((await execute(ctx, controller, { action: 'plan', taskId: 'task-a', title: 'A', pluginId: 'wrong-plugin' })).isError).not.toBe(true)
    expect((await execute(ctx, controller, { action: 'start', taskId: 'task-a', briefing: 'Do not start' })).isError).toBe(true)
    expect(ctx.projectController.find(TaskId('task-a'))?.state).toBe('planned')
    expect(adapter.entered).toEqual([])
  })

  it.each(['plan', 'assign', 'develop'] as const)('rechecks authority at the queued %s write boundary', async (stage) => {
    const { ctx, controller, workerA, adapter, trees } = await setup()
    if (stage !== 'plan') {
      expect((await execute(ctx, controller, { action: 'plan', taskId: 'task-a', title: 'A', pluginId: 'plugin-a' })).isError).not.toBe(true)
    }
    if (stage === 'develop') await ctx.projectController.assign(TaskId('task-a'), workerA.id)

    // These scheduling wrappers delegate every write and queued operation to
    // the real owner; they neither manufacture state nor replace authorization.
    const table = Reflect.get(ctx.projectController, 'table') as { put(key: TaskId, value: TaskRecord): Promise<void> }
    const put = table.put.bind(table)
    const blocked = Promise.withResolvers<undefined>()
    const release = Promise.withResolvers<undefined>()
    table.put = async (key, value) => {
      if (key === TaskId('task-b')) {
        blocked.resolve(undefined)
        await release.promise
      }
      await put(key, value)
    }
    const enqueue = Reflect.get(ctx.projectController, 'enqueue') as (operation: () => Promise<unknown>) => Promise<unknown>
    const queued = Promise.withResolvers<undefined>()
    const blocker = execute(ctx, controller, { action: 'plan', taskId: 'task-b', title: 'B', pluginId: 'plugin-a' })
    let pending: ReturnType<typeof execute> | undefined
    try {
      await blocked.promise
      Reflect.set(ctx.projectController, 'enqueue', (operation: () => Promise<unknown>) => {
        const result = enqueue.call(ctx.projectController, operation)
        queued.resolve(undefined)
        return result
      })
      pending = execute(ctx, controller, stage === 'plan'
        ? { action: 'plan', taskId: 'task-a', title: 'A', pluginId: 'plugin-a' }
        : { action: 'start', taskId: 'task-a', briefing: 'Must not run' })
      await queued.promise
      const revoked = stage === 'plan' ? trees[0]! : trees[2]!
      await ctx.worktreeRegistry.unbind(revoked.id, WorktreeLockHolder(stage === 'plan' ? controller.id : workerA.id))
      release.resolve(undefined)
      expect((await blocker).isError).not.toBe(true)
      expect((await pending).isError).toBe(true)
      expect(ctx.projectController.find(TaskId('task-a'))?.state)
        .toBe(stage === 'plan' ? undefined : stage === 'assign' ? 'planned' : 'assigned')
      expect(adapter.entered).toEqual([])
      expect(workerA.session.snapshotEvents().some(event => event.type === 'agent/inbox/spliced')).toBe(false)
    } finally {
      release.resolve(undefined)
      await Promise.allSettled([blocker, ...(pending === undefined ? [] : [pending])])
      table.put = put
      Reflect.set(ctx.projectController, 'enqueue', enqueue)
    }
  })
})
