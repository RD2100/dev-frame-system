/**
 * The package through a REAL Loader composition: a cordis.yml with the full
 * stack (model route shelf, session, storage, both registries, engine,
 * dispatch) is booted by the actual Loader, so the mount face under test is
 * the one the shipped profiles will use — the function-plugin namespace.
 * The assertions are the ones the direct-service suites cannot see: with the
 * namespace as the unwrapped entry, `agent_dispatch` registers and the
 * dispatch tool is visible and executable on the controller and lead faces
 * and invisible on the worker face.
 * @module tests/loader-composition
 */

import { execFile } from 'node:child_process'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Include from '@deepseek-ai/cordis-plugin-include'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import type { ToolExecutionResult } from '@deepseek-ai/dsh-tools'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import { SessionId } from '@deepseek-ai/dsh-session'
import { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import LlmRuntime from '@deepseek-ai/dsh-llm'
import SessionStore from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import AgentHierarchy from '@deepseek-ai/dsh-experimental-agent-hierarchy'
import WorkspaceRegistry from '@deepseek-ai/dsh-workspace'
import SubprocessLocal from '@deepseek-ai/dsh-subprocess-local'
import GitWorktreeRegistry from '@deepseek-ai/dsh-worktree-registry'
import * as agentDispatch from '../src/index.ts'
import type { Agent } from '@deepseek-ai/dsh-agent'

let root: string | undefined
const contexts: Context[] = []

afterEach(async () => {
  await Promise.all(contexts.splice(0).map(ctx => ctx.fiber.dispose()))
  if (root !== undefined) await rm(root, { recursive: true, force: true })
  root = undefined
})

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

/** Write the cordis.yml under test: the full stack plus this package's namespace mount face. */
async function writeCompositionConfig(options?: { bootstrap?: boolean }): Promise<string> {
  const dispatchConfig: string[] = options?.bootstrap === true
    ? [
        '  config:',
        '    bootstrap: true',
        `    checksLedgerPath: ${JSON.stringify(join(root as string, 'checks-ledger.json'))}`,
      ]
    : []
  const configPath = join(root as string, 'cordis.yml')
  await writeFile(configPath, [
    "- name: '@deepseek-ai/dsh-llm'",
    "- name: '@deepseek-ai/dsh-session'",
    "- name: '@deepseek-ai/dsh-session-persistence-jsonl'",
    '  config:',
    `    root: ${JSON.stringify(join(root as string, 'sessions'))}`,
    '    compression: none',
    '    writeBatchMaxDelayMs: 1',
    "- name: '@deepseek-ai/dsh-system-prompt'",
    "- name: '@deepseek-ai/dsh-tools'",
    "- name: '@deepseek-ai/dsh-agent'",
    "- name: '@deepseek-ai/dsh-agent-loop'",
    '  config:',
    '    agents: []',
    "- name: '@deepseek-ai/dsh-session-projection'",
    "- name: '@deepseek-ai/dsh-storage'",
    "- name: '@deepseek-ai/dsh-storage-json'",
    '  config:',
    `    root: ${JSON.stringify(join(root as string, 'storage'))}`,
    "- name: '@deepseek-ai/dsh-storage-domain'",
    '  config:',
    '    backend: json',
    "- name: '@deepseek-ai/dsh-experimental-session-identity'",
    "- name: '@deepseek-ai/dsh-experimental-agent-hierarchy'",
    '  config:',
    '    roleToolPolicies:',
    '      controller:',
    '        inheritedTools: [agent_dispatch]',
    '      lead:',
    '        inheritedTools: [agent_dispatch]',
    '      worker:',
    '        inheritedTools: []',
    '    leadPluginScopes:',
    '      dispatch-lead: [plugin-a]',
    "- name: '@deepseek-ai/dsh-workspace'",
    "- name: '@deepseek-ai/dsh-subprocess-local'",
    "- name: '@deepseek-ai/dsh-worktree-registry'",
    "- name: '@deepseek-ai/dsh-experimental-agent-dispatch'",
    ...dispatchConfig,
    '',
  ].join('\n'))
  return configPath
}

async function loadComposition(configPath: string, prepare?: (ctx: Context) => void): Promise<Context> {
  const ctx = new Context()
  contexts.push(ctx)
  ctx.baseUrl = pathToFileURL(root as string).href + '/'
  await ctx.plugin(Loader)
  ctx.loader.builtins.include = Include
  // Providers the composition needs before any plugin applies: an opt-in
  // bootstrap mount resolves its authorities at construction time.
  prepare?.(ctx)
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
    ['@deepseek-ai/dsh-experimental-agent-hierarchy', AgentHierarchy],
    ['@deepseek-ai/dsh-workspace', WorkspaceRegistry],
    ['@deepseek-ai/dsh-subprocess-local', SubprocessLocal],
    ['@deepseek-ai/dsh-worktree-registry', GitWorktreeRegistry],
    ['@deepseek-ai/dsh-experimental-agent-dispatch', agentDispatch],
  ])
  ctx.loader.internal = {
    version: 'v2',
    async import(specifier: string) {
      if (!modules.has(specifier)) throw new Error(`unexpected Loader import: ${specifier}`)
      return modules.get(specifier)
    },
  } as unknown as NonNullable<typeof ctx.loader.internal>
  await ctx.loader.create({
    name: 'cordis:include',
    config: { path: pathToFileURL(configPath).href },
  })
  await ctx.loader.await()
  const unloaded = [...ctx.loader.entries()]
    .filter(entry => entry.fiber === undefined && !entry.disabled)
    .map(entry => entry.options.name)
  expect(unloaded).toEqual([])
  return ctx
}

/** The model-facing text of one result. */
function textOf(result: ToolExecutionResult): string {
  return (result.content[0] as { text: string }).text
}

/** Execute one tool call as an exact live registry agent. */
function execute(ctx: Context, name: string, args: unknown, agent: Agent): Promise<ToolExecutionResult> {
  return ctx.tools.execute({
    signal: new AbortController().signal,
    callId: ToolCallId(`call-${String(agent.id)}-${name}`),
    name,
    arguments: args,
    agent,
  })
}

describe('agent dispatch through a real Loader composition', () => {
  it('registers the tool on the namespace face and shows it per role policy', async () => {
    root = await mkdtemp(join(tmpdir(), 'dsh-agent-dispatch-loader-'))
    const repo = join(root, 'repo')
    await mkdir(repo)
    await git(root, 'init', '-b', 'main', repo)
    await git(repo, 'config', 'user.email', 'agent-dispatch-loader@test.local')
    await git(repo, 'config', 'user.name', 'Agent Dispatch Loader Tests')
    await git(repo, 'commit', '--allow-empty', '-m', 'init')
    const configPath = await writeCompositionConfig()

    const ctx = await loadComposition(configPath)

    // The namespace is the unwrapped entry: the service mounts AND the
    // consumer's apply ran. With a default-exported service at the root,
    // the Loader mounts the service, apply never runs, and this assertion
    // fails — the exact formal-wiring defect this suite pins.
    expect(ctx.agentDispatch).toBeDefined()
    expect(ctx.tools.get('agent_dispatch')).toBeDefined()

    const workspace = await ctx.workspaceRegistry.create(repo)
    const tree = await ctx.worktreeRegistry.create({
      workspaceId: workspace.id,
      path: join(root, 'wt-lead'),
      branch: 'feature/lead',
    })

    const controller = (await ctx.agents.create({
      sessionId: SessionId('loader-controller'),
      meta: { cwd: repo },
    })).agent
    await ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })

    const lead = await execute(ctx, 'agent_dispatch', {
      role: 'lead',
      taskId: 'task-1',
      pluginId: 'plugin-a',
      worktreeId: String(tree.id),
      childId: 'dispatch-lead',
      prompt: 'build it',
    }, controller)
    expect(lead.isError, `lead dispatch failed: ${textOf(lead)}`).toBe(false)
    expect(String((lead.value as { childId: string }).childId)).toBe('dispatch-lead')
    const row = ctx.worktreeRegistry.list(workspace.id).find(entry => String(entry.id) === String(tree.id))
    expect(String(row?.lockedBy)).toBe('dispatch-lead')

    const leadAgent = ctx.agents.get(SessionId('dispatch-lead'))
    expect(leadAgent).toBeDefined()
    const workerTree = await ctx.worktreeRegistry.create({
      workspaceId: workspace.id,
      path: join(root, 'wt-worker'),
      branch: 'feature/worker',
    })
    const worker = await execute(ctx, 'agent_dispatch', {
      role: 'worker',
      taskId: 'task-2',
      pluginId: 'plugin-a',
      worktreeId: String(workerTree.id),
    }, leadAgent!)
    expect(worker.isError, `worker dispatch failed: ${textOf(worker)}`).toBe(false)

    // The worker role policy names no tools: restrict() makes the dispatch
    // tool unknown on the worker face before any policy could run.
    const workerAgent = (await ctx.agents.create({
      sessionId: SessionId('loader-worker'),
      meta: { cwd: repo },
    })).agent
    await ctx.agentBindings.bind({ agentId: workerAgent.id, role: 'worker' })
    const denied = await execute(ctx, 'agent_dispatch', {
      role: 'worker',
      taskId: 'task-3',
      pluginId: 'plugin-a',
      worktreeId: String(workerTree.id),
    }, workerAgent)
    expect(denied.isError).toBe(true)
    expect(textOf(denied)).toContain('unknown tool')
  })

  it('loads dispatch-only without a project controller, and mounts the bootstrap only on opt-in', async () => {
    root = await mkdtemp(join(tmpdir(), 'dsh-agent-dispatch-loader-optin-'))
    const repo = join(root, 'repo')
    await mkdir(repo)
    await git(root, 'init', '-b', 'main', repo)
    await git(repo, 'config', 'user.email', 'agent-dispatch-loader@test.local')
    await git(repo, 'config', 'user.name', 'Agent Dispatch Loader Tests')
    await git(repo, 'commit', '--allow-empty', '-m', 'init')

    // Dispatch-only deployment: no project controller service exists, and
    // the plugin must still load and register the dispatch tool.
    const dispatchOnly = await loadComposition(await writeCompositionConfig())
    expect(dispatchOnly.agentDispatch).toBeDefined()
    expect(dispatchOnly.tools.get('agent_dispatch')).toBeDefined()
    expect(dispatchOnly.projectRun).toBeUndefined()

    // Opt-in deployment: the bootstrap config turns the host bootstrap on;
    // the composition must mount the project controller for it, and the
    // approved-digest registration runs against the real ledger.
    const formal = await loadComposition(await writeCompositionConfig({ bootstrap: true }), ctx => {
      ctx.provide('projectController', { find: () => undefined } as never)
    })
    expect(formal.projectRun).toBeDefined()
    const checks = {
      version: 1 as const,
      checks: [{
        checkId: 'probe',
        executable: process.execPath,
        arguments: ['-e', 'process.exit(0)'],
        cwd: root,
      }],
    }
    const digest = await formal.projectRun.approveTaskChecks({ taskId: TaskId('task-1'), checks })
    expect(digest).toBeDefined()
    const again = await formal.projectRun.approveTaskChecks({ taskId: TaskId('task-1'), checks })
    expect(again).toBe(digest)
  })
})
