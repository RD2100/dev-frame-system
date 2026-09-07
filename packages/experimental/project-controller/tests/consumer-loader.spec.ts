/** Real Loader namespace and tool-runtime authorization for project integration, without model requests. */

import { execFile } from 'node:child_process'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { promisify } from 'node:util'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Include from '@deepseek-ai/cordis-plugin-include'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import LlmRuntime, { ToolCallId } from '@deepseek-ai/dsh-llm'
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
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { FileRequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe'
import { devFrameProjectionDefinition } from '@deepseek-ai/dsh-experimental-devframe/src/projection.ts'
import ProjectController from '../src/index.ts'
import * as consumer from '../src/consumer.ts'
import { appendIntegrationEvidence } from './integration-harness.ts'

const cleanups: (() => Promise<void>)[] = []

afterEach(async () => {
  for (const cleanup of cleanups.splice(0).reverse()) await cleanup()
})

async function load() {
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
    ['@deepseek-ai/dsh-experimental-project-controller', ProjectController],
    ['@deepseek-ai/dsh-experimental-project-controller/consumer', consumer],
  ])
  const settings: Record<string, unknown> = {
    '@deepseek-ai/dsh-agent-loop': { agents: [] },
    '@deepseek-ai/dsh-session-persistence-jsonl': { root: join(root, 'sessions'), compression: 'none', writeBatchMaxDelayMs: 1 },
    '@deepseek-ai/dsh-storage-json': { root: join(root, 'storage') },
    '@deepseek-ai/dsh-storage-domain': { backend: 'json' },
    '@deepseek-ai/dsh-experimental-project-controller/consumer': {
      requiredChecksPath: join(root, 'checks.json'), gitExecutable: 'git',
      gitTimeoutMs: 15_000, gitMaxOutputBytes: 1024 * 1024,
    },
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

function execute(ctx: Context, args: unknown, agent?: Agent) {
  return ctx.tools.execute({
    signal: new AbortController().signal, callId: ToolCallId('integration-call'),
    name: 'project_integrate', arguments: args, ...(agent === undefined ? {} : { agent }),
  })
}

async function submittedTask() {
  const { ctx, root } = await load()
  const exec = promisify(execFile)
  const git = async (cwd: string, ...args: string[]) => (await exec('git', ['-C', cwd, ...args], {
    windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024,
    env: Object.fromEntries(Object.entries(process.env)
      .filter(([key]) => !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key))),
  })).stdout.trim()
  const repo = join(root, 'repo')
  await mkdir(repo)
  await git(repo, 'init', '-b', 'main')
  await git(repo, 'config', 'user.name', 'Integration Consumer Test')
  await git(repo, 'config', 'user.email', 'integration@example.invalid')
  await git(repo, 'config', 'commit.gpgsign', 'false')
  await git(repo, 'config', 'core.autocrlf', 'false')
  await git(repo, 'config', 'core.hooksPath', join(root, 'no-hooks'))
  await writeFile(join(repo, 'feature.txt'), 'base\n')
  await git(repo, 'add', 'feature.txt')
  await git(repo, 'commit', '-m', 'base')
  const workspace = await ctx.workspaceRegistry.create(repo)
  const target = await ctx.worktreeRegistry.create({ workspaceId: workspace.id, path: join(root, 'target'), branch: 'target' })
  const leadTree = await ctx.worktreeRegistry.create({ workspaceId: workspace.id, path: join(root, 'lead'), branch: 'lead' })
  const source = await ctx.worktreeRegistry.create({ workspaceId: workspace.id, path: join(root, 'source'), branch: 'source' })
  await writeFile(join(source.path, 'feature.txt'), 'reviewed\n')
  await writeFile(join(source.path, 'new-only.txt'), 'reviewed new file\n')
  await git(source.path, 'add', 'feature.txt', 'new-only.txt')
  await git(source.path, 'commit', '-m', 'feature')
  const taskId = TaskId('task-admission')
  const pluginId = PluginId('p-test')
  const controller = (await ctx.agents.create({ sessionId: SessionId('controller'), meta: { cwd: target.path } })).agent
  const lead = (await ctx.agents.create({ sessionId: SessionId('lead'), meta: { cwd: leadTree.path } })).agent
  const worker = (await ctx.agents.create({ sessionId: SessionId('worker'), meta: { cwd: source.path } })).agent
  await ctx.agentBindings.bind({ agentId: controller.id, role: 'controller', worktree: { worktreeId: target.id, worktreePath: target.path } })
  await ctx.agentBindings.bind({ agentId: lead.id, parentSessionId: controller.id, role: 'lead', pluginId,
    worktree: { worktreeId: leadTree.id, worktreePath: leadTree.path } })
  await ctx.agentBindings.bind({ agentId: worker.id, parentSessionId: lead.id, role: 'worker', pluginId, taskId,
    worktree: { worktreeId: source.id, worktreePath: source.path } })
  for (const [tree, agent] of [[target, controller], [leadTree, lead], [source, worker]] as const) {
    await ctx.worktreeRegistry.bind(tree.id, WorktreeLockHolder(String(agent.id)))
  }
  ctx.effect(() => ctx.sessionProjections.register(devFrameProjectionDefinition))
  const evidence = await appendIntegrationEvidence(
    { ctx, root, dispose: async () => {} }, controller.session, lead.session, taskId, source.path, workspace.id,
  )
  await new FileRequiredChecksConfigStore({ path: join(root, 'checks.json') }).save(evidence.verification.requiredChecks.config)
  ctx.projectController.startProject()
  await ctx.projectController.createTask({ taskId, pluginId, title: 'Integrate reviewed source' })
  await ctx.projectController.assign(taskId, worker.id)
  await ctx.projectController.startDevelopment(taskId)
  await ctx.projectController.beginReview(taskId)
  await ctx.projectController.submit(taskId)
  return { ctx, root, controller, worker, taskId, target, source, git, evidence }
}

describe('project integration through Loader', () => {
  it('mounts the consumer namespace without replacing the controller service', async () => {
    expect('default' in consumer).toBe(false)
    const { ctx } = await load()
    const controller = ctx.projectController
    expect(controller).toBeInstanceOf(ProjectController)
    expect(ctx.tools.get('project_integrate')).toBeDefined()
    expect([...ctx.loader.entries()].filter(entry => entry.options.name === '@deepseek-ai/dsh-experimental-project-controller')).toHaveLength(1)
    const parameters = ctx.tools.get('project_integrate')!.parameters as {
      properties: Record<string, unknown>
      required: string[]
    }
    expect(Object.keys(parameters.properties)).toEqual(['taskId', 'action'])
    expect(parameters.required).toEqual(['taskId', 'action'])
  })

  it('refuses a call without the actual live caller', async () => {
    const { ctx } = await load()
    const result = await execute(ctx, { taskId: 'task', action: 'integrate' })
    expect(result.isError).toBe(true)
    expect(JSON.stringify(result.content)).toContain('actual live calling agent')
    expect(ctx.projectController.list()).toEqual([])
  })

  it('refuses a live Worker even when model arguments claim another caller', async () => {
    const { ctx, root } = await load()
    const worker = (await ctx.agents.create({ sessionId: SessionId('worker'), meta: { cwd: root } })).agent
    await ctx.agentBindings.bind({ agentId: worker.id, role: 'worker' })
    const result = await execute(ctx, { taskId: 'task', action: 'integrate', callerSessionId: 'controller' }, worker)
    expect(result.isError).toBe(true)
    expect(JSON.stringify(result.content)).not.toContain('applied')
    const ordinary = await execute(ctx, { taskId: 'task', action: 'integrate' }, worker)
    expect(ordinary.isError).toBe(true)
    expect(JSON.stringify(ordinary.content)).toContain('registered root controller')
    expect(ctx.projectController.list()).toEqual([])
  })

  it('integrates the registered reviewed source through the real tool and reconciles without another merge', { timeout: 60_000 }, async () => {
    const { ctx, controller, taskId, source, target, git } = await submittedTask()
    const result = await execute(ctx, { taskId, action: 'integrate' }, controller)
    expect(result.isError, JSON.stringify(result.content)).not.toBe(true)
    expect(result.value).toEqual({ taskId, state: 'integrated', observation: 'applied' })
    expect(await git(target.path, 'rev-parse', 'HEAD')).toBe(await git(source.path, 'rev-parse', 'HEAD'))
    expect(await readFile(join(target.path, 'feature.txt'), 'utf8')).toBe('reviewed\n')
    const reconciled = await execute(ctx, { taskId, action: 'reconcile' }, controller)
    expect(reconciled.isError, JSON.stringify(reconciled.content)).not.toBe(true)
    expect(reconciled.value).toEqual({ taskId, state: 'integrated', observation: 'applied' })
  })

  it('refuses an unlocked target without changing its HEAD or task', { timeout: 60_000 }, async () => {
    const { ctx, controller, taskId, target, git } = await submittedTask()
    const before = await git(target.path, 'rev-parse', 'HEAD')
    await ctx.worktreeRegistry.unbind(target.id, WorktreeLockHolder(String(controller.id)))
    const result = await execute(ctx, { taskId, action: 'integrate' }, controller)
    expect(result.isError).toBe(true)
    expect(JSON.stringify(result.content)).toContain('single-writer lock')
    expect(await git(target.path, 'rev-parse', 'HEAD')).toBe(before)
    expect(ctx.projectController.find(taskId)!.state).toBe('submitted')
  })

  it('does not borrow old review evidence after the Worker commits more code', { timeout: 60_000 }, async () => {
    const { ctx, controller, taskId, source, target, git } = await submittedTask()
    const before = await git(target.path, 'rev-parse', 'HEAD')
    await writeFile(join(source.path, 'feature.txt'), 'unreviewed\n')
    await git(source.path, 'add', 'feature.txt')
    await git(source.path, 'commit', '-m', 'unreviewed')
    const result = await execute(ctx, { taskId, action: 'integrate' }, controller)
    expect(result.isError).toBe(true)
    expect(await git(target.path, 'rev-parse', 'HEAD')).toBe(before)
    expect(ctx.projectController.find(taskId)!.state).toBe('submitted')
  })

  it('reconciles an ignored-file collision and retries only after an explicit retry action', { timeout: 60_000 }, async () => {
    const { ctx, controller, taskId, target, source, git } = await submittedTask()
    const before = await git(target.path, 'rev-parse', 'HEAD')
    const exclude = await git(target.path, 'rev-parse', '--path-format=absolute', '--git-path', 'info/exclude')
    await writeFile(exclude, 'new-only.txt\n')
    await writeFile(join(target.path, 'new-only.txt'), 'local user file\n')
    const failed = await execute(ctx, { taskId, action: 'integrate' }, controller)
    expect(failed.isError).toBe(true)
    expect(await readFile(join(target.path, 'new-only.txt'), 'utf8')).toBe('local user file\n')
    const reconciled = await execute(ctx, { taskId, action: 'reconcile' }, controller)
    expect(reconciled.isError, JSON.stringify(reconciled.content)).not.toBe(true)
    expect(reconciled.value).toEqual({ taskId, state: 'submitted', observation: 'unchanged' })
    await rm(join(target.path, 'new-only.txt'))
    const ordinary = await execute(ctx, { taskId, action: 'integrate' }, controller)
    expect(ordinary.isError).toBe(true)
    expect(await git(target.path, 'rev-parse', 'HEAD')).toBe(before)
    const retried = await execute(ctx, { taskId, action: 'retry' }, controller)
    expect(retried.isError, JSON.stringify(retried.content)).not.toBe(true)
    expect(retried.value).toEqual({ taskId, state: 'integrated', observation: 'applied' })
    expect(await git(target.path, 'rev-parse', 'HEAD')).toBe(await git(source.path, 'rev-parse', 'HEAD'))
  })
})
