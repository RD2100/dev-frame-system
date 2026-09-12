/**
 * The DevFrame profile layer through a REAL Loader composition: a cordis.yml
 * carrying the nine patch rows' full content (the console logger exporter,
 * session identity, shadow router, the shadow status controller, the Shadow
 * conversation host, project memory, command goal binding, the three-role
 * hierarchy policy, and dispatch) over
 * the necessary base stack is
 * booted by the actual Loader, so the mount face under test is the one the
 * shipped `--patch` invocation uses. The assertions are the ones the static
 * parse suite cannot see: every row mounts (zero unloaded entries), the
 * services exist beside the global `agent_dispatch` and memory tools, the
 * Shadow project tools stay uninstalled until the host designates a Shadow,
 * and the memory tools fail closed for real against the absent Vault this
 * composition configures.
 * @module tests/loader-composition
 */

import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Include from '@deepseek-ai/cordis-plugin-include'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import CommandRuntime from '@deepseek-ai/dsh-commands'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import LlmRuntime from '@deepseek-ai/dsh-llm'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import type { ToolExecutionResult } from '@deepseek-ai/dsh-tools'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import GoalService from '@deepseek-ai/dsh-goal'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import WorkspaceRegistry from '@deepseek-ai/dsh-workspace'
import SubprocessLocal from '@deepseek-ai/dsh-subprocess-local'
import GitWorktreeRegistry from '@deepseek-ai/dsh-worktree-registry'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import ShadowRouter, { SHADOW_TOOL_NAMES, type ShadowRouterStatus } from '@deepseek-ai/dsh-experimental-shadow-router'
import ShadowController from '@deepseek-ai/dsh-experimental-shadow-controller'
import ShadowAgent from '@deepseek-ai/dsh-experimental-shadow-controller/shadow-agent'
import AgentHierarchy from '@deepseek-ai/dsh-experimental-agent-hierarchy'
import * as agentDispatch from '@deepseek-ai/dsh-experimental-agent-dispatch'
import * as commandGoalBinding from '@deepseek-ai/dsh-experimental-command-goal-binding'
import * as projectMemory from '@deepseek-ai/dsh-experimental-project-memory'
import ConsoleExporter from '../../../../vendor/logger-console/src/index.ts'

let root: string | undefined
const contexts: Context[] = []

afterEach(async () => {
  await Promise.all(contexts.splice(0).map(ctx => ctx.fiber.dispose()))
  if (root !== undefined) await rm(root, { recursive: true, force: true })
  root = undefined
})

/**
 * Write the cordis.yml under test: the base stack every DevFrame row needs
 * plus the eight rows' full patch content. The row configs mirror
 * `cordis.patch.yml`, with the two documented deviations a composition test
 * needs: project-memory names a Vault root that does not exist (load
 * succeeds, every call fails closed) and the `!!js process.cwd()` defaults
 * become the concrete absolute composition root.
 */
async function writeCompositionConfig(): Promise<string> {
  const configPath = join(root as string, 'cordis.yml')
  await writeFile(configPath, [
    "- name: '@deepseek-ai/dsh-llm'",
    "- name: '@deepseek-ai/dsh-session'",
    "- name: '@deepseek-ai/dsh-session-persistence-jsonl'",
    '  config:',
    `    root: ${JSON.stringify(join(root as string, 'sessions'))}`,
    '    compression: none',
    '    writeBatchMaxDelayMs: 1',
    "- name: '@deepseek-ai/dsh-session-projection'",
    "- name: '@deepseek-ai/dsh-system-prompt'",
    "- name: '@deepseek-ai/dsh-tools'",
    "- name: '@deepseek-ai/dsh-agent'",
    "- name: '@deepseek-ai/dsh-agent-loop'",
    '  config:',
    '    agents: []',
    "- name: '@deepseek-ai/dsh-commands'",
    "- name: '@deepseek-ai/dsh-goal'",
    "- name: '@deepseek-ai/dsh-storage'",
    "- name: '@deepseek-ai/dsh-storage-json'",
    '  config:',
    `    root: ${JSON.stringify(join(root as string, 'storage'))}`,
    "- name: '@deepseek-ai/dsh-storage-domain'",
    '  config:',
    '    backend: json',
    "- name: '@deepseek-ai/dsh-workspace'",
    "- name: '@deepseek-ai/dsh-subprocess-local'",
    "- name: '@deepseek-ai/dsh-worktree-registry'",
    // The nine DevFrame rows, in cordis.patch.yml order and with its content.
    "- name: '@deepseek-ai/cordis-plugin-logger-console'",
    "- name: '@deepseek-ai/dsh-experimental-session-identity'",
    "- name: '@deepseek-ai/dsh-experimental-shadow-router'",
    "- name: '@deepseek-ai/dsh-experimental-shadow-controller'",
    "- name: '@deepseek-ai/dsh-experimental-shadow-controller/shadow-agent'",
    "- name: '@deepseek-ai/dsh-experimental-project-memory'",
    '  config:',
    '    workspaceId: default',
    `    vaultRoot: ${JSON.stringify(join(root as string, 'absent-vault'))}`,
    '    writeEnabled: true',
    "- name: '@deepseek-ai/dsh-experimental-command-goal-binding'",
    '  config:',
    '    workspaceId: default',
    `    workspaceRoot: ${JSON.stringify(root)}`,
    `    requiredChecksPath: ${JSON.stringify(join(root as string, 'required-checks.json'))}`,
    '    taskIds: [devframe-goal]',
    '    maxAttempts: 3',
    '    maxGoalRounds: 8',
    '    checks:',
    '      version: 1',
    '      checks:',
    `        - { checkId: git-diff-check, executable: git, arguments: ['diff', '--check'], cwd: ${JSON.stringify(root)} }`,
    "- name: '@deepseek-ai/dsh-experimental-agent-hierarchy'",
    '  config:',
    '    roleToolPolicies:',
    '      controller:',
    '        inheritedTools: !!js "[...(process.platform === \'win32\' ? [\'pwsh\'] : [\'bash\']), \'read\', \'write\', \'edit\', \'read_image\', \'str_replace_editor\', \'glob\', \'grep\', \'web_fetch\', \'web_search\', \'skill\', \'todo_write\', \'job_kill\', \'job_list\', \'job_output\', \'subagent\', \'subagent_fork\', \'interrupt_agent\', \'send_message\', \'list_agents\', \'workflow\', \'worktree_create\', \'worktree_list\', \'worktree_prune\', \'worktree_remove\', \'worktree_status\', \'create_goal\', \'get_goal\', \'update_goal\', \'ralph\', \'ralph-loop\', \'cordis_define\', \'cordis_inspect_list\', \'cordis_inspect_query\', \'cordis_inspect_self\', \'cordis_run\', \'cordis_stop\', \'cordis_undefine\', \'agent_dispatch\']"',
    '      lead:',
    '        inheritedTools: !!js "[...(process.platform === \'win32\' ? [\'pwsh\'] : [\'bash\']), \'read\', \'write\', \'edit\', \'read_image\', \'str_replace_editor\', \'glob\', \'grep\', \'web_fetch\', \'web_search\', \'skill\', \'todo_write\', \'job_kill\', \'job_list\', \'job_output\', \'subagent\', \'subagent_fork\', \'interrupt_agent\', \'send_message\', \'list_agents\', \'workflow\', \'worktree_create\', \'worktree_list\', \'worktree_prune\', \'worktree_remove\', \'worktree_status\', \'create_goal\', \'get_goal\', \'update_goal\', \'ralph\', \'ralph-loop\', \'cordis_define\', \'cordis_inspect_list\', \'cordis_inspect_query\', \'cordis_inspect_self\', \'cordis_run\', \'cordis_stop\', \'cordis_undefine\', \'agent_dispatch\']"',
    '      worker:',
    '        inheritedTools: []',
    '    leadPluginScopes: {}',
    "- name: '@deepseek-ai/dsh-experimental-agent-dispatch'",
    '',
  ].join('\n'))
  return configPath
}

/** Boot the written composition through the real Loader and assert zero unloaded rows. */
async function loadComposition(): Promise<Context> {
  const ctx = new Context()
  contexts.push(ctx)
  ctx.baseUrl = pathToFileURL(root as string).href + '/'
  await ctx.plugin(Loader)
  ctx.loader.builtins.include = Include
  const modules = new Map<string, unknown>([
    ['@deepseek-ai/cordis-plugin-logger-console', ConsoleExporter],
    ['@deepseek-ai/dsh-llm', LlmRuntime],
    ['@deepseek-ai/dsh-session', SessionStore],
    ['@deepseek-ai/dsh-session-persistence-jsonl', JsonlSessionPersistence],
    ['@deepseek-ai/dsh-session-projection', SessionProjectionRegistry],
    ['@deepseek-ai/dsh-system-prompt', SystemPrompt],
    ['@deepseek-ai/dsh-tools', ToolRuntime],
    ['@deepseek-ai/dsh-agent', AgentRegistry],
    ['@deepseek-ai/dsh-agent-loop', AgentLoop],
    ['@deepseek-ai/dsh-commands', CommandRuntime],
    ['@deepseek-ai/dsh-goal', GoalService],
    ['@deepseek-ai/dsh-storage', Storage],
    ['@deepseek-ai/dsh-storage-json', StorageJson],
    ['@deepseek-ai/dsh-storage-domain', StorageDomain],
    ['@deepseek-ai/dsh-workspace', WorkspaceRegistry],
    ['@deepseek-ai/dsh-subprocess-local', SubprocessLocal],
    ['@deepseek-ai/dsh-worktree-registry', GitWorktreeRegistry],
    ['@deepseek-ai/dsh-experimental-session-identity', AgentBindingRegistry],
    ['@deepseek-ai/dsh-experimental-shadow-router', ShadowRouter],
    ['@deepseek-ai/dsh-experimental-shadow-controller', ShadowController],
    ['@deepseek-ai/dsh-experimental-shadow-controller/shadow-agent', ShadowAgent],
    ['@deepseek-ai/dsh-experimental-project-memory', projectMemory],
    ['@deepseek-ai/dsh-experimental-command-goal-binding', commandGoalBinding],
    ['@deepseek-ai/dsh-experimental-agent-hierarchy', AgentHierarchy],
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
    config: { path: pathToFileURL(join(root as string, 'cordis.yml')).href },
  })
  await ctx.loader.await()
  const unloaded = [...ctx.loader.entries()]
    .filter(entry => entry.fiber === undefined && !entry.disabled)
    .map(entry => entry.options.name)
  expect(unloaded).toEqual([])
  return ctx
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

/** Boot the full composition and attach one live agent. */
async function boot(): Promise<{ ctx: Context; agent: Agent }> {
  root = await mkdtemp(join(tmpdir(), 'dsh-devframe-profile-loader-'))
  await writeCompositionConfig()
  const ctx = await loadComposition()
  const agent = (await ctx.agents.create({
    sessionId: SessionId(`loader-shadow-${String(contexts.length)}`),
    meta: { cwd: root },
  })).agent
  return { ctx, agent }
}

describe('the DevFrame profile layer through a real Loader composition', () => {
  it('mounts all eight rows: every service, the memory tools, and agent_dispatch are live', async () => {
    const { ctx } = await boot()

    expect(ctx.agentBindings).toBeDefined()
    expect(ctx.shadowRouter).toBeDefined()
    expect(ctx.shadowController).toBeDefined()
    expect(ctx.shadowAgent).toBeDefined()
    const status: ShadowRouterStatus = ctx.shadowController.readStatus()
    expect(status).toMatchObject({ mounted: true, shadowLive: false, bindings: [] })
    expect(status.shadowSessionId).toBeUndefined()
    // The conversation host mounts but stays inert under the fail-closed
    // router: the read face fails loud instead of inventing a session.
    await expect(ctx.shadowAgent.readConversation({}))
      .rejects.toThrow('declares no Shadow session')
    expect(ctx.projectMemory).toBeDefined()
    expect(ctx.reflect.get('agentHierarchy')).toBeDefined()
    expect(ctx.reflect.get('commandGoalBinding')).toBeDefined()
    expect(ctx.agentDispatch).toBeDefined()

    expect(ctx.tools.get('memory_search')).toBeDefined()
    expect(ctx.tools.get('memory_read')).toBeDefined()
    expect(ctx.tools.get('memory_append')).toBeDefined()
    expect(ctx.tools.get('agent_dispatch')).toBeDefined()
  })

  it('keeps the Shadow whitelist closed until the host designates a Shadow', async () => {
    const { ctx, agent } = await boot()

    for (const name of SHADOW_TOOL_NAMES) {
      expect(ctx.tools.get(name), `${name} must not sit on the global face`).toBeUndefined()
      expect(ctx.tools.get(name, agent), `an unmarked scope must not resolve "${name}"`).toBeUndefined()
    }

    ctx.shadowRouter.markShadow(agent)
    expect(ctx.shadowRouter.isShadow(agent)).toBe(true)
    for (const name of SHADOW_TOOL_NAMES) {
      expect(ctx.tools.get(name, agent), `the marked Shadow scope must resolve "${name}"`).toBeDefined()
    }
  })

  it('fails memory calls closed for real against the absent Vault', async () => {
    const { ctx, agent } = await boot()

    const outcome = await execute(ctx, 'memory_search', { scope: 'project', query: 'loader probe' }, agent)
    expect(outcome.isError, 'the absent vault fails the search for real').toBe(true)
    expect(outcome.error?.info?.code).toBe('MEMORY_UNAVAILABLE')
  })
})
