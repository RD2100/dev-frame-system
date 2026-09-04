import { afterEach, describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import Include from '@deepseek-ai/cordis-plugin-include'
import AgentPresets from '@deepseek-ai/dsh-agent-presets'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import AgentDefaultModel from '@deepseek-ai/dsh-agent-default-model'
import * as AgentInstructions from '@deepseek-ai/dsh-agent-instructions'
import GoalService from '@deepseek-ai/dsh-goal'
import * as GoalRoundDriver from '@deepseek-ai/dsh-goal-round-driver'
import LocalFileSystem from '@deepseek-ai/dsh-fs-local'
import LlmRuntime, { LlmAdapter } from '@deepseek-ai/dsh-llm'
import type { GenerateOptions, StreamChunk } from '@deepseek-ai/dsh-llm'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import type { ToolDefinition } from '@deepseek-ai/dsh-tools'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import {
  DevFrameControlSessions,
  globalControllerSessionId,
  projectControllerSessionId,
} from '../src/index.ts'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type { Workspace } from '@deepseek-ai/dsh-workspace'

class ScriptedAdapter extends LlmAdapter {
  readonly requests: GenerateOptions[] = []

  override async *stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    this.requests.push(options)
    yield { type: 'block-start', index: 0, blockType: 'text' }
    yield { type: 'block-end', index: 0, block: { type: 'text', text: 'bounded response' } }
    yield { type: 'finish', reason: { kind: 'stop' } }
  }
}

interface Harness {
  readonly ctx: Context
  readonly home: string
  readonly adapter?: ScriptedAdapter
  readonly projectRoot: string
  readonly workspaceId: string
}

const harnesses: Harness[] = []

afterEach(async () => {
  for (const harness of harnesses.splice(0).reverse()) {
    await harness.ctx.fiber.dispose()
    await rm(harness.home, { recursive: true, force: true })
  }
  vi.unstubAllEnvs()
})

async function harness(withModel: boolean): Promise<Harness> {
  const home = await mkdtemp(join(tmpdir(), 'dsh-devframe-dispatch-'))
  const projectRoot = await mkdtemp(join(home, 'project-'))
  const presetRoot = join(home, 'agent-presets')
  await mkdir(join(presetRoot, 'standard'), { recursive: true })
  // Keep the roster id native (`standard`) while loading the real DSH
  // filesystem plugin through AgentPresets. The shipped Web roster adds more
  // rows, but these are the two capabilities this focused project harness
  // must prove are visible after setup and absent from Global.
  await writeFile(join(presetRoot, 'standard', 'agent.cordis.yml'), [
    '- id: tool-fs',
    "  name: '@deepseek-ai/dsh-tool-fs'",
    '',
  ].join('\n'))
  const workspaceId = 'workspace_dispatch_test'
  vi.stubEnv('DSH_HOME', home)
  const ctx = new Context()
  harnesses.push({ ctx, home, projectRoot, workspaceId })
  // Resolve bare preset package names from this package's workspace
  // installation, mirroring the installed app's module fallback.
  ctx.baseUrl = pathToFileURL(join(process.cwd(), 'packages/devframe/control-session')).href + '/'
  await ctx.plugin(Loader)
  ctx.loader.builtins.include = Include
  await ctx.plugin(LlmRuntime)
  await ctx.plugin(SessionStore)
  await ctx.plugin(SystemPrompt)
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(LocalFileSystem, { cwd: '/' })
  await ctx.plugin(AgentInstructions, { maxBytes: 64 * 1024 })
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(AgentLoop, { agents: [] })
  if (withModel) await ctx.plugin(AgentDefaultModel, {
    provider: 'deepseek-official',
    model: 'deepseek-v4-flash',
  })
  await ctx.plugin(JsonlSessionPersistence, { root: join(home, 'sessions'), compression: 'none' })
  await ctx.plugin(GoalService)
  await ctx.plugin(GoalRoundDriver)
  await ctx.plugin(AgentPresets, {
    default: 'standard',
    roots: [{ path: presetRoot, trust: 'system' }],
    includeUserRoot: false,
  })
  const workspace: Workspace = {
    id: WorkspaceId(workspaceId),
    path: projectRoot,
    title: 'dispatch-test',
    createdAt: new Date(0).toISOString(),
    updatedAt: new Date(0).toISOString(),
    sessionIds: [],
    status: async () => 'ok',
    attachSession: async () => undefined,
    detachSession: async () => undefined,
    insertSessionBefore: async () => undefined,
    setTitle: async () => undefined,
  }
  ctx.provide('workspaceRegistry', {
    get: (id: Workspace['id']) => id === workspace.id ? workspace : undefined,
    list: () => [],
  } as never)
  const projectProbe: ToolDefinition = {
    name: 'project_probe',
    description: 'A harness-only project capability probe.',
    parameters: { type: 'object', properties: {} },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value as string }],
    },
    execute: async () => 'ok',
  }
  ctx.tools.register(projectProbe)
  await ctx.plugin(DevFrameControlSessions)
  if (!withModel) return { ctx, home, projectRoot, workspaceId }
  const adapter = new ScriptedAdapter()
  ctx.llm.registerAdapter(['deepseek-official'], adapter)
  return { ctx, home, adapter, projectRoot, workspaceId }
}

describe('bounded Global Goal dispatch', () => {
  it('drives one real Goal Round through AgentLoop and persists the pathless trace', async () => {
    const test = await harness(true)

    const trace = await test.ctx.devframeControlSessions.dispatchGlobalGoal({
      profileId: 'dispatch-test',
      objective: 'prove one bounded dispatch',
      maxGoalRounds: 1,
    })

    expect(typeof trace.goalId).toBe('string')
    expect(trace.revision).toBe(1)
    expect(trace.round).toBe(1)
    expect(trace.sessionId).toBe(globalControllerSessionId('dispatch-test'))
    expect(trace.provider).toBe('deepseek-official')
    expect(trace.model).toBe('deepseek-v4-flash')
    expect(trace.outcome).toBe('completed')
    expect(test.adapter?.requests).toHaveLength(1)

    const stored = await test.ctx.sessionPersistence.inspect(trace.sessionId)
    const events = stored.events
    const goalChange = events.find(event => event.type === 'goal/change')
    expect(goalChange?.type).toBe('goal/change')
    if (goalChange?.type === 'goal/change' && goalChange.data.operation !== 'clear') {
      expect(goalChange.data.goal.id).toBe(trace.goalId)
      expect(goalChange.data.goal.maxGoalRounds).toBe(1)
    }
    expect(events.some(event => event.type === 'user/message'
      && event.data.source.kind === 'goal'
      && event.data.source.round === 1)).toBe(true)
    expect(events.some(event => event.type === 'request/header'
      && event.data.header.config.provider === 'deepseek-official'
      && event.data.header.config.model === 'deepseek-v4-flash')).toBe(true)
    expect(events.some(event => event.type === 'assistant/message')).toBe(true)
    expect(events.some(event => event.type === 'turn/end'
      && event.data.turn === 1)).toBe(true)
  })

  it('fails closed before opening Global when the default model capability is absent', async () => {
    const test = await harness(false)

    await expect(test.ctx.devframeControlSessions.dispatchGlobalGoal({
      profileId: 'missing-model',
      objective: 'must not dispatch',
    })).rejects.toMatchObject({ code: 'MODEL_UNAVAILABLE' })
    expect(test.ctx.agents.get(SessionId('devframe-global:missing-model'))).toBeUndefined()
  })
})

describe('bounded Project Goal dispatch', () => {
  // Slice 0 hard-fails project write dispatch: the Slice 1A authority and
  // Slice 1C policy gates do not exist yet, and a Project Controller mounts
  // the shipped coding preset with project File/Shell tools. The full dispatch
  // machinery is preserved for the gated Slice 1 slice; these tests pin the
  // fail-closed posture and the still-working identity-only openProject path.
  it('fails closed for project write dispatch until Slice 1A/1C gates exist', async () => {
    const test = await harness(true)

    await expect(test.ctx.devframeControlSessions.dispatchProjectGoal({
      profileId: 'dispatch-test',
      projectId: test.workspaceId,
      projectRoot: test.projectRoot,
      objective: 'inspect the project workspace',
      maxGoalRounds: 1,
    })).rejects.toMatchObject({ code: 'PROJECT_DISPATCH_DISABLED' })
    expect(test.adapter?.requests).toHaveLength(0)
    const projectId = projectControllerSessionId(test.workspaceId)
    expect(test.ctx.agents.get(projectId)).toBeUndefined()
    await expect(test.ctx.sessionPersistence.inspect(projectId)).rejects.toBeDefined()

    // The identity-only path stays available: openProject still validates the
    // registered Workspace, writes exactly one controller/identity first event,
    // and flushes before returning.
    const project = await test.ctx.devframeControlSessions.openProject({
      profileId: 'dispatch-test',
      workspaceId: test.workspaceId,
    })
    expect(project.id).toBe(projectId)
    expect(project.role).toBe('project')
    const stored = await test.ctx.sessionPersistence.inspect(projectId)
    expect(stored.meta.agentPreset).toBe('standard')
    expect(stored.events.filter(event => event.type === 'controller/identity')).toHaveLength(1)
    const identity = stored.events.find(event => event.type === 'controller/identity')
    expect(identity?.type === 'controller/identity' && identity.data.role).toBe('project')
    const projectIdentity = identity?.type === 'controller/identity' && identity.data.role === 'project'
      ? identity.data
      : undefined
    expect(projectIdentity?.workspaceId).toBe(test.workspaceId)
  })

  it('fails closed before any project validation runs', async () => {
    const test = await harness(true)

    // The gate precedes root/workspace validation: even a mismatched root is
    // reported as the Slice 0 disabled code, never a project-side verdict.
    await expect(test.ctx.devframeControlSessions.dispatchProjectGoal({
      profileId: 'dispatch-test',
      projectId: test.workspaceId,
      projectRoot: test.home,
      objective: 'must not run outside the registered project',
    })).rejects.toMatchObject({ code: 'PROJECT_DISPATCH_DISABLED' })
    expect(test.ctx.agents.get(projectControllerSessionId(test.workspaceId))).toBeUndefined()
  })
})
