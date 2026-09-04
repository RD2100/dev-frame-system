import { afterEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SubagentService from '@deepseek-ai/dsh-subagent'
import * as SubagentFork from '@deepseek-ai/dsh-subagent-fork-in-process'
import * as SubagentSpawn from '@deepseek-ai/dsh-subagent-spawn-in-process'
import { defineContentToolFixture } from '@deepseek-ai/dsh-tools'
import { MockAdapter } from '../../../core/agent-loop/tests/mock-adapter.ts'
import TeamService from '../../agent-team/src/index.ts'
import * as toolTeam from '../src/index.ts'
import { installRolePolicy } from '../../devframe/src/permissions/index.ts'

const SIGNAL = new AbortController().signal
const roots: string[] = []
const contexts: Context[] = []
let callNumber = 0

afterEach(async () => {
  for (const ctx of contexts.splice(0).reverse()) await ctx.fiber.dispose()
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

async function setup() {
  const ctx = new Context()
  contexts.push(ctx)
  await mountAgentLoopTestDependencies(ctx)
  await ctx.plugin(SessionProjectionRegistry)
  const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-team-role-denial-'))
  roots.push(storageRoot)
  await ctx.plugin(JsonlSessionPersistence, { root: storageRoot })
  await ctx.plugin(AgentLoop, { agents: [] })
  await ctx.plugin(SubagentService)
  await ctx.plugin(SubagentSpawn, { providerName: 'spawn' })
  await ctx.plugin(SubagentFork, { providerName: 'fork' })
  await ctx.plugin(TeamService)
  await ctx.plugin(toolTeam)
  ctx.llm.registerAdapter(['mock'], new MockAdapter(['hang', 'hang']))
  const lead = ctx.agentLoop.create(SessionId('role-denial-lead'), { provider: 'mock', model: 'mock' })
  return { ctx, lead }
}

function execute(ctx: Context, agent: Agent, name: string, args: unknown) {
  return ctx.tools.execute({
    callId: ToolCallId(`role-denial-${++callNumber}`),
    name,
    arguments: args,
    signal: SIGNAL,
    agent,
  })
}

function resultText(result: Awaited<ReturnType<typeof execute>>): string {
  return result.content.flatMap(block => block.type === 'text' ? [block.text] : []).join('')
}

async function waitRunning(ctx: Context, id: SessionId): Promise<Agent> {
  return vi.waitFor(() => {
    const agent = ctx.agents.get(id)
    expect(agent?.status).toBe('running')
    return agent!
  }, { timeout: 5_000 })
}

function toolNames(ctx: Context, agent: Agent): string[] {
  return ctx.tools.schemas(agent).map(schema => schema.name)
}

function registerProjectTool(ctx: Context, name: string, calls: string[]): void {
  ctx.tools.register(defineContentToolFixture({
    name,
    description: `role-denial fixture ${name}`,
    parameters: {},
    async execute() {
      calls.push(name)
      return [{ type: 'text' as const, text: `${name}:ran` }]
    },
  }))
}

describe('Team role denial through the real dispatcher', () => {
  it('keeps global restrictions and rejects a reviewer local mutation after allow', async () => {
    const { ctx, lead } = await setup()
    const calls: string[] = []
    for (const name of ['project_read', 'project_write', 'run_checks', 'goal_complete']) {
      registerProjectTool(ctx, name, calls)
    }

    const workerResult = await ctx.agentTeams.spawnTeammate(lead, {
      name: 'worker',
      description: 'writes in the approved project scope',
      prompt: [{ type: 'text', text: 'stay available' }],
      context: 'fresh',
      provider: 'spawn',
      signal: SIGNAL,
    })
    const worker = await waitRunning(ctx, workerResult.member.id)
    const reviewerResult = await ctx.agentTeams.spawnTeammate(lead, {
      name: 'reviewer',
      description: 'reads the project and reports findings',
      prompt: [{ type: 'text', text: 'stay available' }],
      context: 'fresh',
      provider: 'spawn',
      signal: SIGNAL,
    })
    const reviewer = await waitRunning(ctx, reviewerResult.member.id)

    const policy = installRolePolicy(ctx, {
      controller: { inheritedTools: ['project_read'] },
      worker: { inheritedTools: ['project_read', 'project_write', 'run_checks'] },
      reviewer: { inheritedTools: ['project_read'] },
    })
    policy.assign(lead, 'controller')
    policy.assign(worker, 'worker')
    policy.assign(reviewer, 'reviewer')

    // These are the role's inherited global capabilities. The Team tools are
    // scope-local and intentionally remain visible after each restriction.

    expect(toolNames(ctx, lead)).toContain('team_task_update')
    expect(toolNames(ctx, worker)).toContain('team_task_update')
    expect(toolNames(ctx, reviewer)).toContain('team_task_update')
    expect(toolNames(ctx, lead)).not.toContain('project_write')
    expect(toolNames(ctx, worker)).toContain('project_write')
    expect(toolNames(ctx, reviewer)).not.toContain('project_write')

    await expect(execute(ctx, lead, 'project_read', {})).resolves.toMatchObject({ isError: false })
    await expect(execute(ctx, lead, 'project_write', {})).resolves.toMatchObject({ isError: true })
    await expect(execute(ctx, worker, 'project_write', {})).resolves.toMatchObject({ isError: false })
    await expect(execute(ctx, reviewer, 'project_read', {})).resolves.toMatchObject({ isError: false })
    await expect(execute(ctx, reviewer, 'project_write', {})).resolves.toMatchObject({ isError: true })

    const workerTaskResult = await execute(ctx, lead, 'team_task_create', {
      subject: 'worker task',
      description: 'a task the worker may claim',
      blocked_by: [],
      write_scopes: ['src'],
    })
    expect(workerTaskResult.isError).toBe(false)
    const workerTask = JSON.parse(resultText(workerTaskResult)) as { id: string; revision: number }
    const claimed = await execute(ctx, worker, 'team_task_update', {
      task_id: workerTask.id,
      expected_revision: workerTask.revision,
      action: 'claim',
    })
    expect(claimed.isError).toBe(false)

    const reviewerTaskResult = await execute(ctx, lead, 'team_task_create', {
      subject: 'review task',
      description: 'an unowned task used to probe the reviewer guard',
      blocked_by: [],
      write_scopes: ['docs'],
    })
    expect(reviewerTaskResult.isError).toBe(false)
    const reviewerTask = JSON.parse(resultText(reviewerTaskResult)) as { id: string; revision: number }

    // A later allow listener is the bypass this regression must close. The
    // production role guard remains authoritative after the extensible policy.
    reviewer.ctx.on('tools/pre-execute', () => Promise.resolve({ kind: 'allow' as const }), { prepend: true })
    const denied = await execute(ctx, reviewer, 'team_task_update', {
      task_id: reviewerTask.id,
      expected_revision: reviewerTask.revision,
      action: 'claim',
    })
    expect(denied.isError).toBe(true)
    expect(resultText(denied)).toContain('reviewer')
    expect(calls).toEqual(['project_read', 'project_write', 'project_read'])

    const unchanged = await execute(ctx, lead, 'team_task_get', { task_id: reviewerTask.id })
    expect(JSON.parse(resultText(unchanged))).toMatchObject({
      id: reviewerTask.id,
      revision: reviewerTask.revision,
      status: 'pending',
    })
  })
})
