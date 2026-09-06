import { afterEach, describe, expect, it } from 'vitest'
import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { Context } from '@deepseek-ai/cordis'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import GoalService from '@deepseek-ai/dsh-goal'
import { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SubagentService from '@deepseek-ai/dsh-subagent'
import TeamService from '../src/index.ts'
import * as toolTeam from '../../tool-agent-team/src/index.ts'
import {
  ControllerSessionId,
  GoalBindingController,
  MemoryGoalBindingStore,
  TaskId,
  createHumanAuthorization,
} from '../../devframe/src/controller/goal-binding.ts'
import type { NativeGoalPort } from '../../devframe/src/controller/goal-binding.ts'
import { AcceptanceHash, DevFrameSnapshotId, SourceFingerprint, WorkspaceId } from '../../devframe/src/shared/types.ts'

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
  const storageRoot = mkdtempSync(join(tmpdir(), 'dsh-devframe-qa-composition-'))
  roots.push(storageRoot)
  await ctx.plugin(JsonlSessionPersistence, { root: storageRoot })
  await ctx.plugin(AgentLoop, { agents: [] })
  await ctx.plugin(SubagentService)
  await ctx.plugin(GoalService)
  await ctx.plugin(TeamService)
  await ctx.plugin(toolTeam)
  const lead = ctx.agentLoop.create(SessionId('devframe-qa-lead'), {})
  return { ctx, lead }
}

function execute(ctx: Context, agent: ReturnType<Awaited<ReturnType<typeof setup>>['ctx']['agentLoop']['create']>, name: string, args: unknown) {
  return ctx.tools.execute({
    callId: ToolCallId(`devframe-qa-${++callNumber}`),
    name,
    arguments: args,
    agent,
    signal: new AbortController().signal,
  })
}

describe('DevFrame QA composition', () => {
  it('binds a real Team task to a native Goal and retains the exact result identity', async () => {
    const { ctx, lead } = await setup()
    const task = await ctx.agentTeams.createTask(lead, {
      subject: 'bound composition task',
      description: 'complete the task through the real Team tool path',
      blockedBy: [],
      writeScopes: ['src'],
    })
    const goals: NativeGoalPort = {
      create: request => ctx.goals.create(lead, request),
      disarm: () => ctx.goals.disarm(lead),
      get: () => ctx.goals.get(lead),
      resume: ref => ctx.goals.resume(lead, ref),
      complete: ref => ctx.goals.complete(lead, ref),
    }
    const controller = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-qa-composition'),
      controllerSessionId: ControllerSessionId(lead.id),
      goals,
      store: new MemoryGoalBindingStore(),
    })

    const binding = await controller.start({
      objective: 'run the bound composition task',
      taskIds: [TaskId(task.id)],
      acceptanceHash: AcceptanceHash('qa-acceptance-a'),
      sourceFingerprint: SourceFingerprint('qa-source-a'),
      snapshotId: DevFrameSnapshotId('qa-snapshot-a'),
      budget: { maxAttempts: 1 },
      authorization: createHumanAuthorization('qa-confirm-a'),
    })

    expect(controller.assertAdmitted(binding)).toEqual(binding)
    expect(ctx.goals.get(lead)).toMatchObject({ id: binding.goalId, revision: binding.goalRevision, phase: 'active' })

    const claimed = await execute(ctx, lead, 'team_task_update', {
      task_id: task.id,
      expected_revision: task.revision,
      action: 'claim',
    })
    expect(claimed.isError).toBe(false)
    const completed = await execute(ctx, lead, 'team_task_update', {
      task_id: task.id,
      expected_revision: task.revision + 1,
      action: 'complete',
    })
    expect(completed.isError).toBe(false)

    const resultBinding = controller.resolveResultBinding({
      controllerSessionId: binding.controllerSessionId,
      goalId: binding.goalId,
      goalRevision: binding.goalRevision,
      taskIds: [TaskId(task.id)],
      acceptanceHash: binding.acceptanceHash,
      workspaceId: binding.workspaceId,
      sourceFingerprint: binding.sourceFingerprint,
      snapshotId: binding.snapshotId,
    })
    expect(resultBinding).toEqual(binding)

    await ctx.sessions.flush(lead.session)
    const stored = await ctx.sessionPersistence.inspect(lead.id)
    expect(stored.events.filter(event => event.type === 'goal/change')).toHaveLength(2)
    expect(stored.events.some(event => event.type === 'team/task'
      && event.data.task.id === task.id
      && event.data.task.status === 'completed')).toBe(true)
  })
})
