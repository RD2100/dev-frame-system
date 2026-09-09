/** Real Loader composition for the host-controlled Worker commit tool: authority, host scope, quiescence, and the delivery seam. */

import { execFile } from 'node:child_process'
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { promisify } from 'node:util'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Include from '@deepseek-ai/cordis-plugin-include'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import LlmRuntime, { LlmAdapter, ToolCallId } from '@deepseek-ai/dsh-llm'
import type { GenerateOptions, StreamChunk } from '@deepseek-ai/dsh-llm'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import LocalJobRegistry from '@deepseek-ai/dsh-jobs-local'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import WorkspaceRegistry from '@deepseek-ai/dsh-workspace'
import SubprocessLocal from '@deepseek-ai/dsh-subprocess-local'
import GitWorktreeRegistry from '@deepseek-ai/dsh-worktree-registry'
import { WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { computeSourceFingerprint, FileRequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe'
import { AcceptanceHash, ConfigurationConfirmationId, DevFrameSnapshotId, WorkspaceId as GoalWorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { ControllerSessionId, TaskId as GoalTaskId } from '@deepseek-ai/dsh-experimental-devframe/controller'
import { devFrameProjectionDefinition } from '@deepseek-ai/dsh-experimental-devframe/src/projection.ts'
import { GoalId } from '@deepseek-ai/dsh-goal'
import AgentHierarchy from '@deepseek-ai/dsh-experimental-agent-hierarchy'
import * as agentDispatch from '@deepseek-ai/dsh-experimental-agent-dispatch'
import ProjectController from '../src/index.ts'
import * as taskConsumer from '../src/task-consumer.ts'
import * as deliveryConsumer from '../src/delivery-consumer.ts'
import { normalizeCommitPaths, registerProjectCommitTool } from '../src/commit-consumer.ts'

const cleanups: (() => Promise<void>)[] = []

afterEach(async () => {
  for (const cleanup of cleanups.splice(0).reverse()) await cleanup()
})

/** Any model request during these tests is a defect: the tools run directly against real Agents. */
class SilentAdapter extends LlmAdapter {
  override async resolveModel(provider: string, model: string) { return { provider, id: model, name: model } }

  async * stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    throw new Error(`Unexpected model request ${String(options.sessionId)}`)
  }
}

const artifactName = 'worker-a-artifact.txt'

async function load(options: { readonly jobs?: boolean } = {}) {
  const root = await mkdtemp(join(tmpdir(), 'dsh-project-commit-loader-'))
  cleanups.push(() => rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 }))
  const ctx = new Context()
  cleanups.push(() => ctx.fiber.dispose())
  const requiredChecksPath = join(root, 'approved-checks.json')
  const store = new FileRequiredChecksConfigStore({ path: requiredChecksPath })
  const digest = await store.save({ version: 1, checks: [
    { checkId: 'artifact', executable: process.execPath, cwd: join(root, 'worker-a'),
      arguments: ['--input-type=module', '-e',
        'import { readFileSync } from \'node:fs\'; import { strict as assert } from \'node:assert\'; '
          + `assert.equal(readFileSync('${artifactName}', 'utf8'), 'implemented\\n')`] },
  ] })
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
    ['@deepseek-ai/dsh-experimental-project-controller/task-consumer', taskConsumer],
    ['@deepseek-ai/dsh-experimental-project-controller/delivery-consumer', deliveryConsumer],
  ])
  if (options.jobs !== false) modules.set('@deepseek-ai/dsh-jobs-local', LocalJobRegistry)
  const settings: Record<string, unknown> = {
    '@deepseek-ai/dsh-agent-loop': { agents: [] },
    '@deepseek-ai/dsh-session-persistence-jsonl': { root: join(root, 'sessions'), compression: 'none', writeBatchMaxDelayMs: 1 },
    '@deepseek-ai/dsh-storage-json': { root: join(root, 'storage') },
    '@deepseek-ai/dsh-storage-domain': { backend: 'json' },
    '@deepseek-ai/dsh-experimental-agent-hierarchy': {
      roleToolPolicies: {
        controller: { inheritedTools: ['project_task', 'agent_dispatch'] },
        lead: { inheritedTools: ['project_task', 'agent_dispatch'] },
        worker: { inheritedTools: ['project_commit', 'project_deliver'] },
      },
      leadPluginScopes: { lead: ['plugin-a'] },
    },
    '@deepseek-ai/dsh-experimental-project-controller/delivery-consumer': {
      requiredChecksPath, requiredChecksByTask: { 'task-a': String(digest) }, gitExecutable: 'git',
      gitTimeoutMs: 15_000, gitMaxOutputBytes: 1024 * 1024, checkTimeoutMs: 15_000, checkMaxOutputBytes: 1024 * 1024,
      commitPathsByTask: { 'task-a': [artifactName, 'second-artifact.txt', 'output', 'link/inner.txt'],
        'task-b': ['worker-b-artifact.txt'] },
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

function execute(ctx: Context, agent: Agent, args: object) {
  return ctx.tools.execute({ signal: new AbortController().signal, callId: ToolCallId('commit-harness'),
    name: 'project_task', arguments: args, agent })
}

type Fixture = Awaited<ReturnType<typeof setup>>

async function tool(f: Fixture, agent: Agent, name: string, args: object) {
  return await f.ctx.tools.execute({ signal: new AbortController().signal, callId: ToolCallId('commit-tool'),
    name, arguments: args, agent })
}

async function setup(options: { readonly jobs?: boolean } = {}) {
  const { ctx, root } = await load(options)
  const exec = promisify(execFile)
  const repo = join(root, 'repo')
  await mkdir(repo)
  await writeFile(join(root, 'empty-config'), '')
  await mkdir(join(root, 'empty-template'))
  const git = async (cwd: string, ...args: string[]) => (await exec('git', ['-C', cwd, ...args], {
    windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024,
    env: { ...Object.fromEntries(Object.entries(process.env)
      .filter(([key]) => !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key))),
    GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: join(root, 'empty-config') },
  })).stdout.trim()
  await git(repo, 'init', '--template=' + join(root, 'empty-template'), '-b', 'main')
  await git(repo, 'config', 'user.name', 'Commit Loader')
  await git(repo, 'config', 'user.email', 'commit@example.invalid')
  await git(repo, 'config', 'commit.gpgsign', 'false')
  await git(repo, 'config', 'core.hooksPath', join(root, 'no-hooks'))
  await git(repo, 'config', 'core.attributesFile', join(root, 'empty-config'))
  await git(repo, 'config', 'core.autocrlf', 'false')
  await git(repo, 'commit', '--allow-empty', '-m', 'initial')
  const workspace = await ctx.workspaceRegistry.create(repo)
  const trees = await Promise.all(['target', 'lead', 'worker-a', 'worker-b'].map(async branch =>
    await ctx.worktreeRegistry.create({ workspaceId: workspace.id, path: join(root, branch), branch })))
  const controller = (await ctx.agents.create({ sessionId: SessionId('controller'), meta: { cwd: trees[0]!.path } })).agent
  await ctx.agentBindings.bind({ agentId: controller.id, role: 'controller',
    worktree: { worktreeId: trees[0]!.id, worktreePath: trees[0]!.path } })
  await ctx.worktreeRegistry.bind(trees[0]!.id, WorktreeLockHolder(controller.id))
  ctx.effect(() => ctx.sessionProjections.register(devFrameProjectionDefinition))
  const acceptanceHash = AcceptanceHash('task-acceptance')
  controller.session.append('devframe/goal-binding', {
    version: 1, controllerSessionId: ControllerSessionId(controller.id), workspaceId: GoalWorkspaceId(workspace.id),
    goalId: GoalId('task-goal'), goalRevision: 1, taskIds: ['task-a', 'task-b'].map(GoalTaskId),
    acceptanceHash, sourceFingerprint: (await computeSourceFingerprint({ worktreePath: trees[0]!.path })).fingerprint,
    snapshotId: DevFrameSnapshotId('task-snapshot'),
    confirmation: { id: ConfigurationConfirmationId('task-confirmation'), acceptanceHash },
    lifecycle: 'admission_open', budget: { maxAttempts: 10, consumedAttempts: 0 },
  })
  await ctx.sessions.flush(controller.session)
  ctx.projectController.startProject()
  for (const taskId of ['task-a', 'task-b']) {
    const planned = await execute(ctx, controller, { action: 'plan', taskId, title: taskId, pluginId: 'plugin-a' })
    expect(planned.isError, JSON.stringify(planned)).not.toBe(true)
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
  ctx.llm.registerAdapter(['test'], new SilentAdapter())
  const policy = { inheritedTools: [], denyScopedTools: [] }
  controller.session.append('devframe/role-policy', {
    version: 1, controllerSessionId: controller.id, workspaceId: GoalWorkspaceId(workspace.id), policyVersion: 'commit-policy',
    config: { controller: policy, worker: policy, reviewer: policy },
    assignments: [{ role: 'controller', sessionId: controller.id }, { role: 'lead', sessionId: lead.id }],
  })
  await ctx.sessions.flush(controller.session)
  for (const taskId of ['task-a', 'task-b']) {
    const started = await execute(ctx, controller, { action: 'start', taskId })
    expect(started.isError, JSON.stringify(started)).not.toBe(true)
  }
  return { ctx, root, repo, git, trees, controller, lead, workerA, workerB }
}

/** Start one owned, unsettled background job; the caller settles it through the returned gate. */
function startFixtureJob(f: Fixture, owner: Agent, options: { readonly settleOnCancel?: boolean } = {}) {
  const gate = Promise.withResolvers<{ status: 'completed' | 'killed'; detail?: string }>()
  f.ctx.jobs.attachController('commit-harness')
  const id = f.ctx.jobs.start({
    kind: 'bash', label: 'fixture background writer', owner,
    run: () => ({ cancel: () => { if (options.settleOnCancel !== false) gate.resolve({ status: 'killed' }) },
      done: gate.promise }),
  })
  return { id, settle: () => { gate.resolve({ status: 'completed' }) } }
}

describe('project commit consumer through the real Loader', () => {
  it('bounds the commit path grammar before any authority resolution', () => {
    expect(() => normalizeCommitPaths([])).toThrow('at least one commit path')
    expect(() => normalizeCommitPaths(Array.from({ length: 65 }, (_, i) => `path-${i}.txt`)))
      .toThrow('at most 64 commit paths')
    expect(() => normalizeCommitPaths([''])).toThrow('between 1 and 256 characters')
    expect(() => normalizeCommitPaths(['a'.repeat(257)])).toThrow('between 1 and 256 characters')
    expect(() => normalizeCommitPaths(['a\0b'])).toThrow('relative path inside the Worker worktree')
    expect(normalizeCommitPaths(['b.txt', 'a.txt', 'b.txt'])).toEqual(['b.txt', 'a.txt'])
  })

  it('fails loud at registration when the host commit Service is missing', () => {
    const registered: unknown[] = []
    expect(() => {
      registerProjectCommitTool({
        tools: { register: (definition: unknown) => { registered.push(definition); return () => undefined } } as unknown as Context['tools'],
        registry: {} as never,
        resolveWorker: () => { throw new Error('unused') },
        serial: async <T>(_key: string, run: () => Promise<T>): Promise<T> => await run(),
        gitEnvironment: () => ({}),
        commitPathsByTask: new Map(),
        jobs: () => undefined,
        resolveOwnerHead: () => ({ ownerPath: 'unused', branch: 'main' }),
        config: { gitExecutable: 'git', gitTimeoutMs: 1000, gitMaxOutputBytes: 1024 },
      })
    }).toThrow('worktree-registry host commit Service')
    expect(registered).toEqual([])
  })

  it('refuses to prove quiescence without a background job registry instead of assuming quiet', async () => {
    const f = await setup({ jobs: false })
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    const result = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
    expect(result.isError).toBe(true)
    expect(JSON.stringify(result)).toContain('requires the background job registry')
    expect((await f.git(worktree, 'rev-parse', 'HEAD')).trim())
      .toBe((await f.git(f.repo, 'rev-parse', 'HEAD')).trim())
  })

  it('commits exactly the requested artifacts, keeps the writer lock, and reports the new head', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    const anchorBefore = (await f.git(f.repo, 'rev-parse', 'HEAD')).trim()
    const untrimmed = await tool(f, f.workerA, 'project_commit', { taskId: ' task-a', paths: [artifactName] })
    expect(untrimmed.isError).toBe(true)
    expect(JSON.stringify(untrimmed)).toContain('Task id must be trimmed')
    await writeFile(join(worktree, artifactName), 'implemented\n')
    const result = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
    expect(result.isError, JSON.stringify(result)).not.toBe(true)
    const head = (await f.git(worktree, 'rev-parse', 'HEAD')).trim()
    expect(head).not.toBe(anchorBefore)
    expect((await f.git(worktree, 'status', '--porcelain=v1', '--untracked-files=all')).trim()).toBe('')
    expect((await f.git(worktree, 'diff-tree', '--no-commit-id', '--name-only', '-r', head)).trim()).toBe(artifactName)
    expect((await f.git(worktree, 'log', '-1', '--format=%s', head)).trim()).toBe('Commit task task-a (goal task-goal)')
    expect(f.ctx.worktreeRegistry.list(f.trees[0]!.workspaceId).find(tree => tree.id === f.trees[2]!.id)?.lockedBy)
      .toBe(f.workerA.id)
    expect((await f.git(f.repo, 'rev-parse', 'HEAD')).trim()).toBe(anchorBefore)
  })

  it('derives authority from the real binding and never consults forged identity arguments', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    // The parameter root is open by design; authority fields are inert because
    // the operation derives every identity from the real binding.
    const result = await tool(f, f.workerA, 'project_commit', {
      taskId: 'task-a', paths: [artifactName],
      holder: 'forged-holder', worktreeId: 'forged-worktree', expectedHead: '0'.repeat(40),
    })
    expect(result.isError, JSON.stringify(result)).not.toBe(true)
    expect(f.ctx.worktreeRegistry.list(f.trees[0]!.workspaceId).find(tree => tree.id === f.trees[2]!.id)?.lockedBy)
      .toBe(f.workerA.id)
    expect((await f.git(worktree, 'status', '--porcelain=v1')).trim()).toBe('')
  })

  it('refuses a worker that is not the assigned owner of the task', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    const headBefore = (await f.git(worktree, 'rev-parse', 'HEAD')).trim()
    const result = await tool(f, f.workerB, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
    expect(result.isError).toBe(true)
    expect(JSON.stringify(result)).toContain('assigned Worker')
    expect((await f.git(worktree, 'status', '--porcelain=v1')).trim()).toContain(artifactName)
    expect((await f.git(worktree, 'diff', '--cached', '--name-only')).trim()).toBe('')
    expect((await f.git(worktree, 'rev-parse', 'HEAD')).trim()).toBe(headBefore)
  })

  it('refuses a task that has not reached the developing state', async () => {
    const f = await setup()
    await f.ctx.projectController.block(TaskId('task-b'), {
      blockedReason: 'harness pause', nextAction: 'resume after the fixture check', wakeCondition: 'operator input',
    })
    const result = await tool(f, f.workerB, 'project_commit', { taskId: 'task-b', paths: ['worker-b-artifact.txt'] })
    expect(result.isError).toBe(true)
    expect(JSON.stringify(result)).toContain('requires a developing task')
  })

  it('refuses a registered scope path that names a directory', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await mkdir(join(worktree, 'output'))
    const result = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: ['output'] })
    expect(result.isError).toBe(true)
    expect(JSON.stringify(result)).toContain('must name files, not directories')
  })

  it('refuses an in-scope file reachable only through a link escaping the worktree', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    const target = join(f.root, 'outside-target')
    await mkdir(target)
    await writeFile(join(target, 'inner.txt'), 'escape\n')
    if (process.platform === 'win32') await symlink(target, join(worktree, 'link'), 'junction')
    else await symlink(target, join(worktree, 'link'))
    const result = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: ['link/inner.txt'] })
    expect(result.isError).toBe(true)
    expect(JSON.stringify(result)).toContain('must stay inside the Worker worktree')
  })

  it('refuses escaping, absolute, and in-scope missing paths without staging anything', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    const headBefore = (await f.git(worktree, 'rev-parse', 'HEAD')).trim()
    for (const [paths, message] of [
      [['../outside.txt'], 'relative path inside'],
      [['sub/../' + artifactName], 'relative path inside'],
      [['.git/config'], 'relative path inside'],
      [['C:/outside.txt'], 'relative path inside'],
      [[join(worktree, artifactName)], 'relative path inside'],
      [['second-artifact.txt'], 'does not exist in the Worker worktree'],
    ] as const) {
      const result = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [...paths] })
      expect(result.isError, JSON.stringify(result)).toBe(true)
      expect(JSON.stringify(result)).toContain(message)
    }
    expect((await f.git(worktree, 'diff', '--cached', '--name-only')).trim()).toBe('')
    expect((await f.git(worktree, 'rev-parse', 'HEAD')).trim()).toBe(headBefore)
  })

  it('refuses paths outside the host-registered commit scope and preserves them', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    await writeFile(join(worktree, 'unregistered-artifact.txt'), 'not authorized\n')
    const headBefore = (await f.git(worktree, 'rev-parse', 'HEAD')).trim()
    const result = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: ['unregistered-artifact.txt'] })
    expect(result.isError).toBe(true)
    expect(JSON.stringify(result)).toContain('outside the host-registered commit path scope')
    expect(await readFile(join(worktree, 'unregistered-artifact.txt'), 'utf8')).toBe('not authorized\n')
    expect((await f.git(worktree, 'diff', '--cached', '--name-only')).trim()).toBe('')
    expect((await f.git(worktree, 'rev-parse', 'HEAD')).trim()).toBe(headBefore)
  })

  it('commits only the authorized scope and reports remaining changes as unverified', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    await writeFile(join(worktree, 'unrelated.txt'), 'keep me\n')
    const result = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
    expect(result.isError, JSON.stringify(result)).not.toBe(true)
    const head = (await f.git(worktree, 'rev-parse', 'HEAD')).trim()
    expect((await f.git(worktree, 'diff-tree', '--no-commit-id', '--name-only', '-r', head)).trim()).toBe(artifactName)
    expect(await readFile(join(worktree, 'unrelated.txt'), 'utf8')).toBe('keep me\n')
    expect(JSON.stringify(result)).toContain('pending changes remain and their ownership is unverified')
  })

  it('commits the registered scope in rounds and reports a clean tree at the end', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    await writeFile(join(worktree, 'second-artifact.txt'), 'continued\n')
    const first = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
    expect(first.isError, JSON.stringify(first)).not.toBe(true)
    expect(JSON.stringify(first)).toContain('pending changes remain and their ownership is unverified')
    const second = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: ['second-artifact.txt'] })
    expect(second.isError, JSON.stringify(second)).not.toBe(true)
    expect(JSON.stringify(second)).toContain('worktree clean')
    expect((await f.git(worktree, 'status', '--porcelain=v1', '--untracked-files=all')).trim()).toBe('')
  })

  it('passes the single observed HEAD through the Service request and refuses a stale HEAD', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    const original = f.ctx.worktreeRegistry.commit.bind(f.ctx.worktreeRegistry)
    Reflect.set(f.ctx.worktreeRegistry, 'commit', async (request: unknown, signal: AbortSignal | undefined) => {
      await f.git(worktree, 'commit', '--allow-empty', '-m', 'interfering commit')
      return await original(request as Parameters<typeof original>[0], signal)
    })
    try {
      const result = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
      expect(result.isError).toBe(true)
      expect(JSON.stringify(result)).toContain('expected HEAD')
    } finally {
      Reflect.deleteProperty(f.ctx.worktreeRegistry, 'commit')
    }
    expect((await f.git(worktree, 'diff', '--cached', '--name-only')).trim()).toBe('')
  })

  it('refuses a Worker checkout whose .git pointer is redirected to another registered worktree', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    const otherWorktree = f.workerB.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    const pointer = await readFile(join(otherWorktree, '.git'), 'utf8')
    // Git marks this file hidden on Windows; reopening it avoids CREATE_ALWAYS's hidden-file refusal.
    await writeFile(join(worktree, '.git'), pointer, { flag: 'r+' })
    const otherHeadBefore = (await f.git(otherWorktree, 'rev-parse', 'HEAD')).trim()
    const result = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
    expect(result.isError).toBe(true)
    expect(JSON.stringify(result)).toContain('does not belong')
    expect((await f.git(otherWorktree, 'rev-parse', 'HEAD')).trim()).toBe(otherHeadBefore)
    expect((await f.git(otherWorktree, 'diff', '--cached', '--name-only')).trim()).toBe('')
  })

  it('refuses a job that reached the stopping state and commits only after it settles', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    const job = startFixtureJob(f, f.workerA, { settleOnCancel: false })
    try {
      f.ctx.jobs.kill(job.id, f.workerA)
      const refused = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
      expect(refused.isError).toBe(true)
      expect(JSON.stringify(refused)).toContain('non-terminal background job')
      expect((await f.git(worktree, 'diff', '--cached', '--name-only')).trim()).toBe('')
    } finally {
      job.settle()
    }
    const result = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
    expect(result.isError, JSON.stringify(result)).not.toBe(true)
    expect(JSON.stringify(result)).toContain('worktree clean')
  })

  it('refuses when the authority signature changes between awaits', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    const original = f.ctx.worktreeRegistry.list.bind(f.ctx.worktreeRegistry)
    let calls = 0
    Reflect.set(f.ctx.worktreeRegistry, 'list', (workspaceId: Parameters<typeof original>[0]) => {
      const rows = original(workspaceId)
      calls += 1
      // The fourth resolve re-reads the rows after the HEAD observation; a
      // changed row digest must refuse the commit there.
      if (calls === 5) {
        return rows.map(row => row.id === f.trees[2]!.id ? { ...row, branch: 'mutated-branch' } : row)
      }
      return rows
    })
    try {
      const result = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
      expect(result.isError).toBe(true)
      expect(JSON.stringify(result)).toContain('Commit authority changed')
    } finally {
      Reflect.deleteProperty(f.ctx.worktreeRegistry, 'list')
    }
    expect((await f.git(worktree, 'diff', '--cached', '--name-only')).trim()).toBe('')
  })

  it('refuses when the registered worktree row disappears before the owner observation', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    const original = f.ctx.worktreeRegistry.list.bind(f.ctx.worktreeRegistry)
    let calls = 0
    Reflect.set(f.ctx.worktreeRegistry, 'list', (workspaceId: Parameters<typeof original>[0]) => {
      calls += 1
      // The fourth call is the owner-workspace row resolution for the HEAD
      // observation; a vanished row refuses instead of observing unanchored.
      return calls === 4 ? [] : original(workspaceId)
    })
    try {
      const result = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
      expect(result.isError).toBe(true)
      expect(JSON.stringify(result)).toContain('registered Worker worktree row')
    } finally {
      Reflect.deleteProperty(f.ctx.worktreeRegistry, 'list')
    }
  })

  it('refuses while a non-terminal background job of the caller exists and commits after it settles', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    const job = startFixtureJob(f, f.workerA)
    try {
      const refused = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
      expect(refused.isError).toBe(true)
      expect(JSON.stringify(refused)).toContain('non-terminal background job')
      expect((await f.git(worktree, 'diff', '--cached', '--name-only')).trim()).toBe('')
      job.settle()
      const result = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
      expect(result.isError, JSON.stringify(result)).not.toBe(true)
      expect(JSON.stringify(result)).toContain('worktree clean')
    } finally {
      job.settle()
    }
  })

  it('rechecks job quiescence after the HEAD observation and refuses a job that appears there', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    const original = f.ctx.jobs.list.bind(f.ctx.jobs)
    const gate = Promise.withResolvers<{ status: 'completed' | 'killed'; detail?: string }>()
    f.ctx.jobs.attachController('commit-harness')
    let seen = false
    Reflect.set(f.ctx.jobs, 'list', (caller?: Agent) => {
      const snapshots = original(caller)
      if (!seen) {
        seen = true
        f.ctx.jobs.start({ kind: 'bash', label: 'late background writer', owner: f.workerA,
          run: () => ({ cancel: () => { gate.resolve({ status: 'killed' }) }, done: gate.promise }) })
      }
      return snapshots
    })
    try {
      const result = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
      expect(result.isError).toBe(true)
      expect(JSON.stringify(result)).toContain('non-terminal background job')
      expect((await f.git(worktree, 'diff', '--cached', '--name-only')).trim()).toBe('')
    } finally {
      gate.resolve({ status: 'completed' })
      Reflect.deleteProperty(f.ctx.jobs, 'list')
    }
  })

  it('uses the model-provided single-line message when given and refuses others', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    const rejected = await tool(f, f.workerA, 'project_commit', {
      taskId: 'task-a', paths: [artifactName], message: 'line one\nline two',
    })
    expect(rejected.isError).toBe(true)
    expect(JSON.stringify(rejected)).toContain('plain single-line text')
    const emptied = await tool(f, f.workerA, 'project_commit', {
      taskId: 'task-a', paths: [artifactName], message: '   ',
    })
    expect(emptied.isError).toBe(true)
    expect(JSON.stringify(emptied)).toContain('must not be empty when provided')
    const oversized = await tool(f, f.workerA, 'project_commit', {
      taskId: 'task-a', paths: [artifactName], message: 'x'.repeat(513),
    })
    expect(oversized.isError).toBe(true)
    expect(JSON.stringify(oversized)).toContain('at most 512 characters')
    const result = await tool(f, f.workerA, 'project_commit', {
      taskId: 'task-a', paths: [artifactName], message: 'Implement the fixture export',
    })
    expect(result.isError, JSON.stringify(result)).not.toBe(true)
    expect((await f.git(worktree, 'log', '-1', '--format=%s')).trim()).toBe('Implement the fixture export')
  })

  it('hands a clean committed worktree to the standard delivery', async () => {
    const f = await setup()
    const worktree = f.workerA.session.header.cwd!
    await writeFile(join(worktree, artifactName), 'implemented\n')
    const committed = await tool(f, f.workerA, 'project_commit', { taskId: 'task-a', paths: [artifactName] })
    expect(committed.isError, JSON.stringify(committed)).not.toBe(true)
    const delivered = await tool(f, f.workerA, 'project_deliver', { taskId: 'task-a' })
    expect(delivered.isError, JSON.stringify(delivered)).not.toBe(true)
    expect(f.ctx.projectController.find(TaskId('task-a'))?.state).toBe('reviewing')
    const state = f.ctx.sessionProjections.stateOf(f.controller.session, 'devframe')!
    expect(state.deliveries).toHaveLength(1)
    expect(state.deliveries[0]!.sourceCommit).toBe((await f.git(worktree, 'rev-parse', 'HEAD')).trim())
    expect(state.verifications).toHaveLength(1)
    expect(state.verifications[0]!.status).toBe('passed')
  })
})
