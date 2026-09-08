/**
 * The model-facing dispatch consumer: the `agent_dispatch` tool executes
 * through the real tool runtime against the real engine, the real registries,
 * and real git worktrees. The calling agent is the exact live registry agent,
 * so every dispatch below is the engine's own creation path — refusals are
 * observed as tool errors carrying the classified adapter texts, and the
 * happy path is observed in the registry rows, the durable bindings, and the
 * child's inbox.
 * @module tests/dispatch-consumer
 */

import { execFile } from 'node:child_process'
import { mkdir, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import { afterEach, describe, expect, it } from 'vitest'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import type { UserMessage } from '@deepseek-ai/dsh-llm'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import { defineContentToolFixture } from '@deepseek-ai/dsh-tools'
import type { ToolExecutionResult } from '@deepseek-ai/dsh-tools'
import AgentHierarchy, { type AgentHierarchyConfigInput } from '@deepseek-ai/dsh-experimental-agent-hierarchy'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import SubprocessLocal from '@deepseek-ai/dsh-subprocess-local'
import WorkspaceRegistry, { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import GitWorktreeRegistry from '@deepseek-ai/dsh-worktree-registry'
import * as consumer from '../src/index.ts'
import { TOOL_NAMES } from '../src/index.ts'
import type { Agent } from '@deepseek-ai/dsh-agent'

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
    // The dispatch tool is part of the controller's and the lead's inherited
    // face: without it the restrict() install makes it invisible to exactly
    // the roles that are allowed to dispatch.
    controller: { inheritedTools: ['project_read', 'agent_dispatch'] },
    lead: { inheritedTools: ['project_read', 'agent_dispatch'] },
    worker: { inheritedTools: ['project_read'] },
  },
}

const contexts: Context[] = []
const roots: string[] = []

interface Setup {
  ctx: Context
  root: string
  repo: string
  workspaceId: WorkspaceId
  controller: Agent
  createWorktree: (name: string, branch: string) => Promise<{ id: string; path: string; branch: string }>
  execute: (name: string, args: unknown, agent: Agent) => Promise<ToolExecutionResult>
  inserted: UserMessage[]
}

afterEach(async () => {
  await Promise.all(contexts.splice(0).map(ctx => ctx.fiber.dispose()))
  await Promise.all(roots.splice(0).map(root => rm(root, { recursive: true, force: true })))
})

/**
 * Boot the full stack the consumer needs: agent loop, storage, both
 * registries, the hierarchy engine, the system prompt, and the plugin under
 * test — then register the repository workspace and one live controller.
 */
async function setup(leadPluginScopes: AgentHierarchyConfigInput['leadPluginScopes'] = {}): Promise<Setup> {
  const root = await mkdtemp(join(tmpdir(), 'dsh-agent-dispatch-consumer-'))
  roots.push(root)
  const ctx = new Context()
  contexts.push(ctx)
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
      description: 'agent-dispatch consumer probe project_read',
      parameters: {},
      async execute() {
        return []
      },
    }))
    await ctx.plugin(AgentHierarchy, { ...rolesConfig, leadPluginScopes })
    // The plugin's formal bootstrap is opt-in; the plugin-face suites run
    // dispatch-only, so no project controller is mounted.
    await ctx.plugin(consumer)

    const repo = join(root, 'repo')
    await mkdir(repo)
    await git(root, 'init', '-b', 'main', repo)
    await git(repo, 'config', 'user.email', 'agent-dispatch-consumer@test.local')
    await git(repo, 'config', 'user.name', 'Agent Dispatch Consumer Tests')
    await git(repo, 'commit', '--allow-empty', '-m', 'init')
    const workspace = await ctx.workspaceRegistry.create(repo)

    const inserted: UserMessage[] = []
    ctx.on('agent/created', ({ agent }) => {
      agent.ctx.on('agent/inbox/inserted', ({ message }) => { inserted.push(message) })
    })

    const controller = (await ctx.agents.create({
      sessionId: SessionId('consumer-controller'),
      meta: { cwd: repo },
    })).agent
    await ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })

    return {
      ctx,
      root,
      repo,
      workspaceId: workspace.id,
      controller,
      createWorktree: async (name, branch) => {
        const worktree = await ctx.worktreeRegistry.create({
          workspaceId: workspace.id,
          path: join(root, name),
          branch,
        })
        return { id: String(worktree.id), path: worktree.path, branch: worktree.branch }
      },
      execute: (name, args, agent) => ctx.tools.execute({
        signal: new AbortController().signal,
        callId: ToolCallId(`call-${String(agent.id)}-${name}`),
        name,
        arguments: args,
        agent,
      }),
      inserted,
    }
  } catch (error: unknown) {
    await ctx.fiber.dispose()
    contexts.splice(contexts.indexOf(ctx), 1)
    await rm(root, { recursive: true, force: true })
    roots.splice(roots.indexOf(root), 1)
    throw error
  }
}

/** The model-facing text of one result. */
function textOf(result: ToolExecutionResult): string {
  return (result.content[0] as { text: string }).text
}

/** The canonical value of a successful result. */
function valueOf(result: ToolExecutionResult): Record<string, unknown> {
  if (result.isError) throw new Error(`expected success, got: ${textOf(result)}`)
  return result.value as Record<string, unknown>
}

describe('agent dispatch tool schema', () => {
  it('registers the stable model-facing name with model-oriented parameters', async () => {
    const { ctx } = await setup()

    expect(TOOL_NAMES).toEqual(['agent_dispatch'])
    const definition = ctx.tools.get('agent_dispatch')
    expect(definition).toBeDefined()
    expect(definition!.description.length).toBeGreaterThan(40)
    const parameters = definition!.parameters as unknown as {
      properties: Record<string, unknown>
      required?: string[]
    }
    expect(Object.keys(parameters.properties)).toEqual([
      'role', 'taskId', 'pluginId', 'worktreeId', 'prompt', 'retry', 'followup', 'childId',
    ])
    expect(parameters.required).toEqual(['role', 'taskId', 'pluginId', 'worktreeId'])
  })
})

describe('agent dispatch tool behavior over the real engine', () => {
  it('dispatches a lead as the exact live controller, binds the lock, and queues the briefing', async () => {
    const { ctx, workspaceId, controller, createWorktree, execute, inserted } = await setup({
      'dispatch-lead': ['plugin-a'],
    })
    const tree = await createWorktree('wt-lead', 'feature/lead')

    const result = await execute('agent_dispatch', {
      role: 'lead',
      taskId: 'task-1',
      pluginId: 'plugin-a',
      worktreeId: tree.id,
      prompt: 'build the thing',
    }, controller)
    const value = valueOf(result) as { childId: string; role: string; taskId: string; worktreeId: string; reused: boolean }

    expect(value.reused).toBe(false)
    expect(value.role).toBe('lead')
    expect(value.taskId).toBe('task-1')
    expect(value.worktreeId).toBe(tree.id)
    const row = ctx.worktreeRegistry.list(workspaceId).find(entry => String(entry.id) === tree.id)
    expect(String(row?.lockedBy)).toBe(value.childId)
    const record = ctx.agentBindings.find(SessionId(value.childId))
    expect(record?.taskId).toBe('task-1')
    expect(record?.role).toBe('lead')
    expect(inserted).toHaveLength(1)
    expect(JSON.stringify(inserted[0])).toContain('build the thing')
    expect(textOf(result)).toContain('Dispatched lead child')
  })

  it('refuses a blind same-task redispatch and reuses through retry without re-briefing', async () => {
    const { controller, createWorktree, execute, inserted } = await setup({
      'dispatch-lead': ['plugin-a'],
    })
    const tree = await createWorktree('wt-retry', 'feature/retry')
    const args = {
      role: 'lead',
      taskId: 'task-1',
      pluginId: 'plugin-a',
      worktreeId: tree.id,
      prompt: 'the briefing',
    }
    const first = valueOf(await execute('agent_dispatch', args, controller)) as { childId: string }
    expect(inserted).toHaveLength(1)

    const blind = await execute('agent_dispatch', args, controller)
    expect(blind.isError).toBe(true)
    expect(textOf(blind)).toContain(first.childId)
    expect(textOf(blind)).toContain('retry by passing that id as sessionId')

    // The retry path reuses the returned identity; even a carried prompt is
    // never re-delivered to the already-running child. The ack reports the
    // honest state the log proves — with no model route the turn may still
    // be pending (briefed), open (claimed), or already ended in error
    // (terminal) — and the stub harness has no durability bridge, so the
    // flush verdict is deterministically `durable: false`.
    const retried = valueOf(await execute('agent_dispatch', { ...args, retry: true, prompt: 're-brief' }, controller)) as {
      childId: string
      reused: boolean
      ack: { state: string; durable: boolean }
    }
    expect(retried.reused).toBe(true)
    expect(retried.childId).toBe(first.childId)
    expect(retried.ack.state).toBeDefined()
    expect(retried.ack.durable).toBe(false)
    expect(inserted).toHaveLength(1)
    expect(textOf(await execute('agent_dispatch', { ...args, retry: true }, controller)))
      .toContain(`Reusing lead child ${retried.childId}`)
  })

  it('delivers an explicit followup to the existing child and refuses a followup without one', async () => {
    const { ctx, controller, createWorktree, execute } = await setup({
      'dispatch-lead': ['plugin-a'],
    })
    const tree = await createWorktree('wt-followup', 'feature/followup')

    // A followup on a task with no dispatched child is a model-facing
    // refusal that names the fix.
    const blind = await execute('agent_dispatch', {
      role: 'lead',
      taskId: 'ghost-task',
      pluginId: 'plugin-a',
      worktreeId: tree.id,
      followup: true,
      prompt: 'continue the work',
    }, controller)
    expect(blind.isError).toBe(true)
    expect(textOf(blind)).toContain('has no dispatched child to follow up')

    const first = valueOf(await execute('agent_dispatch', {
      role: 'lead',
      taskId: 'task-1',
      pluginId: 'plugin-a',
      worktreeId: tree.id,
    }, controller)) as { childId: string }

    // The explicit continuation reaches the existing child's inbox under
    // its own deterministic-prefix identity, with no second child created.
    const followed = valueOf(await execute('agent_dispatch', {
      role: 'lead',
      taskId: 'task-1',
      pluginId: 'plugin-a',
      worktreeId: tree.id,
      followup: true,
      prompt: 'lead-review-c14: review the delivered work now.',
    }, controller)) as { childId: string; reused: boolean; followup: boolean }
    expect(followed.reused).toBe(true)
    expect(followed.followup).toBe(true)
    expect(followed.childId).toBe(first.childId)

    const childAgent = ctx.agents.get(SessionId(first.childId))
    expect(childAgent).toBeDefined()
    const followups = childAgent!.session.snapshotEvents()
      .filter(event => event.type === 'agent/inbox/spliced')
      .flatMap(event => (event.data as { inserted?: Array<{ id?: string; content?: unknown }> }).inserted ?? [])
      .filter(message => typeof message.id === 'string' && message.id.startsWith('dispatch-followup:'))
    expect(followups).toHaveLength(1)
    expect(JSON.stringify(followups[0])).toContain('lead-review-c14: review the delivered work now.')
  })

  it('refuses a followup without instructions instead of silently reusing the child', async () => {
    const { controller, createWorktree, execute } = await setup({
      'dispatch-lead': ['plugin-a'],
    })
    const tree = await createWorktree('wt-followup-bare', 'feature/followup-bare')
    await execute('agent_dispatch', {
      role: 'lead',
      taskId: 'task-1',
      pluginId: 'plugin-a',
      worktreeId: tree.id,
    }, controller)

    // followup: true with no prompt is a caller mistake: it fails loud
    // instead of degrading to a no-op reuse that hides the missing
    // instructions behind an honest-looking receipt.
    const bare = await execute('agent_dispatch', {
      role: 'lead',
      taskId: 'task-1',
      pluginId: 'plugin-a',
      worktreeId: tree.id,
      followup: true,
    }, controller)
    expect(bare.isError).toBe(true)
    expect(textOf(bare)).toContain('passed followup: true without a prompt')
    expect(textOf(bare)).toContain('dispatch without followup')
  })

  it('carries the controller-to-lead-to-worker chain through the model face', async () => {
    const { ctx, controller, createWorktree, execute } = await setup({
      // Approved sets are keyed by durable identities: the configured lead id
      // reaches the tool through the model's childId argument.
      'dispatch-lead': ['plugin-a'],
    })
    const leadTree = await createWorktree('wt-lead', 'feature/lead')
    const lead = valueOf(await execute('agent_dispatch', {
      role: 'lead',
      taskId: 'task-1',
      pluginId: 'plugin-a',
      worktreeId: leadTree.id,
      childId: 'dispatch-lead',
    }, controller)) as { childId: string }
    expect(lead.childId).toBe('dispatch-lead')

    const leadAgent = ctx.agents.get(SessionId(lead.childId))
    expect(leadAgent).toBeDefined()
    const workerTree = await createWorktree('wt-worker', 'feature/worker')
    const worker = valueOf(await execute('agent_dispatch', {
      role: 'worker',
      taskId: 'task-2',
      pluginId: 'plugin-a',
      worktreeId: workerTree.id,
    }, leadAgent!)) as { childId: string; role: string }
    expect(worker.role).toBe('worker')
    expect(ctx.agentBindings.find(SessionId(worker.childId))?.role).toBe('worker')
  })

  it('surfaces the hierarchy denial for a worker dispatcher and unknown worktrees', async () => {
    const { ctx, controller, createWorktree, execute, repo } = await setup({
      'dispatch-lead': ['plugin-a'],
    })
    const tree = await createWorktree('wt-lead', 'feature/lead')
    const lead = valueOf(await execute('agent_dispatch', {
      role: 'lead',
      taskId: 'task-1',
      pluginId: 'plugin-a',
      worktreeId: tree.id,
    }, controller)) as { childId: string }
    const leadAgent = ctx.agents.get(SessionId(lead.childId))
    const workerTree = await createWorktree('wt-worker', 'feature/worker')

    // A lead may not dispatch another lead.
    const leadCascade = await execute('agent_dispatch', {
      role: 'lead',
      taskId: 'task-3',
      pluginId: 'plugin-a',
      worktreeId: workerTree.id,
    }, leadAgent!)
    expect(leadCascade.isError).toBe(true)
    expect(textOf(leadCascade)).toContain('a lead dispatches only workers')

    // A worker dispatches nothing at all — and the role policy's restrict()
    // makes the dispatch tool INVISIBLE to the worker role in the first
    // place, so the model face refuses as unknown before any policy runs.
    const workerAgent = (await ctx.agents.create({
      sessionId: SessionId('plain-worker'),
      meta: { cwd: repo },
    })).agent
    await ctx.agentBindings.bind({ agentId: workerAgent.id, role: 'worker' })
    const fromWorker = await execute('agent_dispatch', {
      role: 'worker',
      taskId: 'task-4',
      pluginId: 'plugin-a',
      worktreeId: workerTree.id,
    }, workerAgent)
    expect(fromWorker.isError).toBe(true)
    expect(textOf(fromWorker)).toContain('unknown tool')

    const unknown = await execute('agent_dispatch', {
      role: 'lead',
      taskId: 'task-5',
      pluginId: 'plugin-a',
      worktreeId: 'wt-never-registered',
    }, controller)
    expect(unknown.isError).toBe(true)
    expect(textOf(unknown)).toContain('not registered under the calling session')
  })
})
