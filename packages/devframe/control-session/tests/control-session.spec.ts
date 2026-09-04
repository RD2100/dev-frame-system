import { afterEach, describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import Include from '@deepseek-ai/cordis-plugin-include'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import AgentRegistry, { agentEvents } from '@deepseek-ai/dsh-agent'
import AgentPresets from '@deepseek-ai/dsh-agent-presets'
import type {
  Agent,
  AgentHandle,
  CreateAgentOptions,
  ResumeAgentOptions,
} from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import * as AgentInstructions from '@deepseek-ai/dsh-agent-instructions'
import LocalFileSystem from '@deepseek-ai/dsh-fs-local'
import { dshHomePath } from '@deepseek-ai/dsh-home-paths'
import LlmRuntime, { CallId } from '@deepseek-ai/dsh-llm'
import SessionStore, {
  SESSION_FORMAT_VERSION,
  Session,
  SessionId,
} from '@deepseek-ai/dsh-session'
import type { SessionEvent, SessionHeader } from '@deepseek-ai/dsh-session'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime, { defineTool } from '@deepseek-ai/dsh-tools'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type { Workspace } from '@deepseek-ai/dsh-workspace/types'
import {
  type ControlSessionResult,
  ControlSessionError,
  DevFrameControlSessions,
  globalControllerSessionId,
} from '../src/index.ts'

interface PersistedSession {
  readonly meta: SessionHeader
  readonly events: readonly SessionEvent[]
}

interface Publication {
  readonly agent: Agent
  readonly agentWasLive: boolean
  readonly sessionWasLive: boolean
  readonly events: readonly SessionEvent[]
  readonly restrict: ReturnType<typeof createToolHooks>['restrict']
  readonly guard: ReturnType<typeof createToolHooks>['guard']
}

type FlushOutcome = boolean | Error

interface HarnessOptions {
  readonly persisted?: ReadonlyMap<SessionId, PersistedSession>
  readonly flushOutcomes?: readonly FlushOutcome[]
  readonly appendOutcomes?: readonly FlushOutcome[]
  readonly disposeFailure?: Error
  readonly workspace?: Workspace
}

const contexts: Context[] = []
const tempDirs: string[] = []
let originalCwd: string | undefined

afterEach(async () => {
  if (originalCwd !== undefined) {
    process.chdir(originalCwd)
    originalCwd = undefined
  }
  for (const ctx of contexts.splice(0).reverse()) await ctx.fiber.dispose()
  for (const dir of tempDirs.splice(0).reverse()) await rm(dir, { recursive: true, force: true })
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

function trackContext(ctx: Context): Context {
  contexts.push(ctx)
  return ctx
}

async function temporaryDirectory(label: string): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), label))
  tempDirs.push(dir)
  return dir
}

function changeCwd(path: string): void {
  originalCwd ??= process.cwd()
  process.chdir(path)
}

function header(id: SessionId, cwd?: string, agentPreset?: string): SessionHeader {
  return {
    version: SESSION_FORMAT_VERSION,
    id,
    createdAt: 1,
    ...cwd === undefined ? {} : { cwd },
    ...agentPreset === undefined ? {} : { agentPreset },
  }
}

function globalHeader(id: SessionId): SessionHeader {
  return header(id, dshHomePath('devframe-control'))
}

function createToolHooks() {
  return {
    restrict: vi.fn((_filter: { readonly allow?: readonly string[]; readonly deny?: readonly string[] }) => () => undefined),
    guard: vi.fn((_guard: (execution: unknown) => string | undefined) => () => undefined),
  }
}

function createAgentFixture(ctx: Context, session: Session) {
  const tools = createToolHooks()
  const mutableAgent = {
    id: session.id,
    session,
    ctx,
  }
  const agent = mutableAgent as unknown as Agent
  mutableAgent.ctx = ctx.extend({ agent, tools })
  return { agent, tools }
}

function globalIdentityEvents(
  id: SessionId,
  profileId: string,
  duplicate = false,
): readonly SessionEvent[] {
  const session = Session.create(id)
  const data = {
    schemaVersion: 1 as const,
    role: 'global' as const,
    sessionId: id,
    profileId,
    cwd: dshHomePath('devframe-control'),
  }
  session.append('controller/identity', data)
  if (duplicate) session.append('controller/identity', data)
  return session.events
}

function setup(options: HarnessOptions = {}) {
  const ctx = trackContext(new Context())
  const persisted = new Map(options.persisted ?? [])
  const flushOutcomes = [...options.flushOutcomes ?? [true]]
  const appendOutcomes = [...options.appendOutcomes ?? []]
  const pendingHeaders = new Map<SessionId, SessionHeader>()
  const liveAgents = new Map<SessionId, Agent>()
  const liveSessions = new Map<SessionId, Session>()
  const liveHandles = new Map<SessionId, AgentHandle>()
  const publications: Publication[] = []
  const disposedAgents: Agent[] = []

  const publish = async (
    session: Session,
    agentSetup: CreateAgentOptions['setup'],
  ): Promise<AgentHandle> => {
    const fixture = createAgentFixture(ctx, session)
    const setupCommit = await agentSetup?.(fixture.agent.ctx)
    setupCommit?.commit()
    publications.push({
      agent: fixture.agent,
      agentWasLive: liveAgents.has(session.id),
      sessionWasLive: liveSessions.has(session.id),
      events: session.events,
      ...fixture.tools,
    })
    liveSessions.set(session.id, session)
    liveAgents.set(session.id, fixture.agent)
    let disposed = false
    const handle: AgentHandle = {
      agent: fixture.agent,
      dispose: vi.fn(async () => {
        if (disposed) return
        disposed = true
        disposedAgents.push(fixture.agent)
        if (liveAgents.get(session.id) === fixture.agent) liveAgents.delete(session.id)
        if (liveSessions.get(session.id) === session) liveSessions.delete(session.id)
        if (liveHandles.get(session.id) === handle) liveHandles.delete(session.id)
        if (options.disposeFailure !== undefined) throw options.disposeFailure
      }),
    }
    liveHandles.set(session.id, handle)
    return handle
  }

  const create = vi.fn(async (agentOptions: CreateAgentOptions): Promise<AgentHandle> => {
    const session = Session.create(
      agentOptions.sessionId,
      agentOptions.seed,
      header(agentOptions.sessionId, agentOptions.meta?.cwd),
    )
    return publish(session, agentOptions.setup)
  })
  const resume = vi.fn(async (agentOptions: ResumeAgentOptions): Promise<AgentHandle> => {
    const record = persisted.get(agentOptions.resumeSessionId)
    if (record === undefined) throw new Error('persisted session not found')
    const session = Session.fromRestore(
      agentOptions.resumeSessionId,
      structuredClone(record.events),
      structuredClone(record.meta),
    )
    return publish(session, agentOptions.setup)
  })
  const agents = {
    get: (id: SessionId) => liveAgents.get(id),
    create,
    resume,
  }
  const flush = vi.fn(async (session: Session): Promise<boolean> => {
    expect(liveSessions.get(session.id)).toBe(session)
    const outcome = flushOutcomes.shift() ?? true
    if (outcome instanceof Error) throw outcome
    return outcome
  })
  const sessions = {
    get: (id: SessionId) => liveSessions.get(id),
    prepare: (id: SessionId, options?: {
      readonly meta?: { readonly cwd?: string; readonly agentPreset?: string }
    }) => Session.create(id, undefined, header(id, options?.meta?.cwd, options?.meta?.agentPreset)),
    flush,
  }
  const list = vi.fn(async () => [...persisted.values()].map(record => structuredClone(record.meta)))
  const persistenceCreate = vi.fn(async (meta: SessionHeader) => {
    if (persisted.has(meta.id) || pendingHeaders.has(meta.id)) throw new Error('identity already exists')
    pendingHeaders.set(meta.id, structuredClone(meta))
  })
  const persistenceAppend = vi.fn(async (id: SessionId, events: readonly SessionEvent[]) => {
    const outcome = appendOutcomes.shift()
    if (outcome instanceof Error) throw outcome
    const meta = pendingHeaders.get(id)
    if (meta === undefined) throw new Error('identity was not created')
    persisted.set(id, {
      meta: structuredClone(meta),
      events: structuredClone(events),
    })
    pendingHeaders.delete(id)
  })
  const workspaceGet = vi.fn((id: ReturnType<typeof WorkspaceId>) =>
    options.workspace?.id === id ? options.workspace : undefined)
  const workspaceList = vi.fn(() => options.workspace === undefined ? [] : [options.workspace])

  ctx.provide('agents', agents as never)
  ctx.provide('sessions', sessions as never)
  ctx.provide('sessionPersistence', {
    list,
    create: persistenceCreate,
    append: persistenceAppend,
  } as never)
  ctx.provide('agentPresets', {
    resolve: vi.fn(async (id?: string) => ({
      id: id ?? 'standard',
      path: 'test-only',
      trust: 'system' as const,
    })),
    mount: vi.fn(async (_agentCtx: Context, id?: string) => ({
      id: id ?? 'standard',
      path: 'test-only',
      trust: 'system' as const,
    })),
  } as never)
  ctx.provide('workspaceRegistry', { get: workspaceGet, list: workspaceList } as never)
  ctx.provide('tools', {} as never)

  return {
    ctx,
    controller: new DevFrameControlSessions(ctx),
    create,
    resume,
    flush,
    list,
    persistenceCreate,
    persistenceAppend,
    workspaceGet,
    workspaceList,
    liveAgents,
    liveSessions,
    liveHandles,
    publications,
    disposedAgents,
  }
}

function workspaceFixture(path: string) {
  const attachSession = vi.fn(async (_id: SessionId) => undefined)
  const status = vi.fn(async () => 'ok' as const)
  const workspace: Workspace = {
    id: WorkspaceId('workspace-1'),
    path,
    title: 'Workspace',
    createdAt: '2026-08-15T00:00:00.000Z',
    updatedAt: '2026-08-15T00:00:00.000Z',
    sessionIds: [],
    setTitle: async () => undefined,
    attachSession,
    insertSessionBefore: async () => undefined,
    detachSession: async () => undefined,
    status,
  }
  return { workspace, attachSession, status }
}

async function mountRealHarness(root: string, workspace?: Workspace) {
  const ctx = trackContext(new Context())
  const presetRoot = join(root, 'agent-presets')
  await mkdir(join(presetRoot, 'standard'), { recursive: true })
  await writeFile(join(presetRoot, 'standard', 'agent.cordis.yml'), [
    '- id: tool-fs',
    "  name: '@deepseek-ai/dsh-tool-fs'",
    '',
  ].join('\n'))
  ctx.baseUrl = pathToFileURL(join(process.cwd(), 'packages/devframe/control-session')).href + '/'
  await ctx.plugin(Loader)
  ctx.loader.builtins.include = Include
  await ctx.plugin(LlmRuntime)
  const modelStream = vi.spyOn(ctx.llm, 'stream')
  await ctx.plugin(SessionStore)
  await ctx.plugin(SystemPrompt)
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(LocalFileSystem, { cwd: resolve('/') })
  await ctx.plugin(AgentInstructions, { maxBytes: 64 * 1024 })
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(AgentLoop, { agents: [] })
  await ctx.plugin(JsonlSessionPersistence, { root, compression: 'none' })
  await ctx.plugin(AgentPresets, {
    default: 'standard',
    roots: [{ path: presetRoot, trust: 'system' }],
    includeUserRoot: false,
  })
  ctx.provide('workspaceRegistry', {
    get: (id: ReturnType<typeof WorkspaceId>) => workspace?.id === id ? workspace : undefined,
    list: () => workspace === undefined ? [] : [workspace],
  } as never)
  await ctx.plugin(DevFrameControlSessions)
  return { ctx, modelStream }
}

async function effectiveInstructions(ctx: Context, agent: Agent): Promise<string> {
  await agentEvents(ctx, agent).waterfall(
    'agent/pre-step',
    { messages: [], turn: 1, step: 1, signal: AbortSignal.timeout(5_000) },
    async () => ({ kind: 'enter' as const, messages: [] }),
  )
  return agent.inbox.nextStep
    .filter(message => message.source.kind === 'agent-instructions')
    .flatMap(message => message.content)
    .map(block => block.type === 'text' ? block.text : '')
    .join('\n')
}

describe('DevFrameControlSessions', () => {
  it('bootstraps one Global Controller, projects ready, then releases its owned Agent on stop', async () => {
    const test = setup()
    const generation = test.controller.beginGlobalBootstrap()

    await generation.open('profile-1')

    expect(test.controller.readinessSnapshot()).toEqual({
      status: 'ready',
      generation: generation.generation,
      revision: 2,
      sessionId: 'devframe-global:profile-1',
    })
    expect(test.liveAgents.has(SessionId('devframe-global:profile-1'))).toBe(true)

    const stopped = generation.stop()
    expect(test.controller.readinessSnapshot().status).toBe('stopping')
    await stopped
    expect(test.liveAgents.has(SessionId('devframe-global:profile-1'))).toBe(false)
    expect(test.disposedAgents).toHaveLength(1)
  })

  it('stops Global admission while teardown waits for an in-flight bootstrap', async () => {
    const test = setup()
    let releaseList: (() => void) | undefined
    test.list.mockImplementationOnce(async () => {
      await new Promise<void>((resolve) => { releaseList = resolve })
      return []
    })
    const generation = test.controller.beginGlobalBootstrap()
    const opening = generation.open('profile-1')
    await vi.waitFor(() => { expect(test.list).toHaveBeenCalledOnce() })

    const stopping = generation.stop()
    await expect(test.controller.openGlobal({ profileId: 'profile-2' }))
      .rejects.toMatchObject({ code: 'HOST_STOPPING' })
    releaseList?.()
    await Promise.all([opening, stopping])
    expect(test.controller.readinessSnapshot().status).toBe('stopping')
    expect(test.liveAgents.size).toBe(0)
  })

  it('maps bootstrap failures to one pathless readiness code', async () => {
    const test = setup({ appendOutcomes: [new Error('__SECRET__ D:/private/controller')] })
    const generation = test.controller.beginGlobalBootstrap()

    await generation.open('profile-1')

    const snapshot = test.controller.readinessSnapshot()
    expect(snapshot).toEqual({
      status: 'blocked',
      generation: generation.generation,
      revision: 2,
      code: 'CONTROLLER_UNAVAILABLE',
    })
    expect(JSON.stringify(snapshot)).not.toContain('__SECRET__')
    expect(JSON.stringify(snapshot)).not.toContain('D:/private')
  })

  it('collapses concurrent Global opens and publishes one identity-only Agent', async () => {
    const test = setup()

    const [first, second] = await Promise.all([
      test.controller.openGlobal({ profileId: 'profile-1' }),
      test.controller.openGlobal({ profileId: 'profile-1' }),
    ])

    expect(test.resume).toHaveBeenCalledTimes(2)
    expect(test.list).toHaveBeenCalledTimes(1)
    expect(test.create).not.toHaveBeenCalled()
    expect(first.agent).toBe(second.agent)
    expect(first.id).toBe(SessionId('devframe-global:profile-1'))
    expect(test.persistenceCreate).toHaveBeenCalledOnce()
    expect(test.persistenceCreate.mock.calls[0]![0].cwd).toBe(dshHomePath('devframe-control'))
    expect(test.persistenceAppend).toHaveBeenCalledOnce()
    expect(first.agent.session.header.cwd).toBe(dshHomePath('devframe-control'))
    expect(first.agent.session.header).not.toHaveProperty('agentPreset')

    const publication = test.publications[0]!
    expect(publication.agentWasLive).toBe(false)
    expect(publication.sessionWasLive).toBe(false)
    expect(publication.events.filter(event => event.type === 'controller/identity')).toHaveLength(1)
    expect(typeof publication.events[0]!.time).toBe('number')
    expect(publication.events[0]).toEqual({
      type: 'controller/identity',
      seq: 0,
      time: publication.events[0]!.time,
      data: {
        schemaVersion: 1,
        role: 'global',
        sessionId: first.id,
        profileId: 'profile-1',
        cwd: dshHomePath('devframe-control'),
      },
    })
    expect(publication.restrict).toHaveBeenCalledOnce()
    expect(publication.restrict).toHaveBeenCalledWith({ allow: [] })
    expect(publication.guard).toHaveBeenCalledOnce()
    expect(publication.guard.mock.calls[0]![0]({})).toBe('DevFrame Slice 0 controller execution is not enabled')
    expect(test.flush).toHaveBeenCalledOnce()
  })

  it.each([
    ['a missing durability listener', false],
    ['a throwing durability listener', new Error('flush exploded')],
  ] as const)('disposes after %s and does not reuse the failed Agent', async (_label, outcome) => {
    const test = setup({ flushOutcomes: [outcome, true] })
    const id = SessionId('devframe-global:profile-1')

    const failure = await test.controller.openGlobal({ profileId: 'profile-1' }).then(
      () => { throw new Error('expected Global open to fail') },
      (error: unknown) => {
        if (!(error instanceof ControlSessionError)) throw error
        return error
      },
    )
    expect(failure).toMatchObject({ code: 'DURABILITY_FAILED' })
    if (outcome instanceof Error) expect(failure.cause).toBe(outcome)
    expect(test.disposedAgents).toHaveLength(1)
    expect(test.liveAgents.get(id)).toBeUndefined()
    expect(test.liveSessions.get(id)).toBeUndefined()

    const retried = await test.controller.openGlobal({ profileId: 'profile-1' })
    expect(test.create).not.toHaveBeenCalled()
    expect(test.resume).toHaveBeenCalledTimes(3)
    expect(test.persistenceCreate).toHaveBeenCalledOnce()
    expect(test.persistenceAppend).toHaveBeenCalledOnce()
    expect(retried.agent).not.toBe(test.disposedAgents[0])
    expect(test.liveAgents.get(id)).toBe(retried.agent)
  })

  it('retires a fully absent owned handle and resumes the durable identity', async () => {
    const test = setup()
    const id = SessionId('devframe-global:profile-1')
    const first = await test.controller.openGlobal({ profileId: 'profile-1' })
    await test.liveHandles.get(id)?.dispose()

    const resumed = await test.controller.openGlobal({ profileId: 'profile-1' })

    expect(resumed.agent).not.toBe(first.agent)
    expect(test.resume).toHaveBeenCalledTimes(3)
    expect(test.persistenceCreate).toHaveBeenCalledOnce()
    expect(test.persistenceAppend).toHaveBeenCalledOnce()
    expect(test.liveAgents.get(id)).toBe(resumed.agent)
  })

  it('keeps a Host-owned controller alive across caller Loader reloads', async () => {
    const persistenceRoot = await temporaryDirectory('dsh-devframe-caller-reload-jsonl-')
    const dshHome = await temporaryDirectory('dsh-devframe-caller-reload-home-')
    vi.stubEnv('DSH_HOME', dshHome)
    const test = await mountRealHarness(persistenceRoot)
    const opened: Array<Promise<ControlSessionResult>> = []
    const caller = Object.assign((callerCtx: Context) => {
      opened.push(callerCtx.devframeControlSessions.openGlobal({ profileId: 'caller-reload-profile' }))
    }, { inject: ['devframeControlSessions'] })
    test.ctx.loader.builtins.devframeControlCaller = caller
    const callerId = await test.ctx.loader.create({ name: 'cordis:devframeControlCaller' })
    await test.ctx.loader.await()
    const first = await opened[0]!

    await test.ctx.loader.update(callerId, { disabled: true })
    await test.ctx.loader.await()
    expect(test.ctx.agents.get(first.id)).toBe(first.agent)
    expect(test.ctx.sessions.get(first.id)).toBe(first.agent.session)

    await test.ctx.loader.update(callerId, { disabled: false })
    await test.ctx.loader.await()
    await vi.waitFor(() => { expect(opened).toHaveLength(2) })
    const reopened = await opened[1]!
    expect(reopened.agent).toBe(first.agent)
  })

  it('keeps a stable public error when failed-controller cleanup also fails', async () => {
    const test = setup({
      flushOutcomes: [false],
      disposeFailure: new Error('dispose failed'),
    })

    const failure = await test.controller.openGlobal({ profileId: 'profile-1' }).then(
      () => { throw new Error('expected Global open to fail') },
      (error: unknown) => error,
    )
    expect(failure).toBeInstanceOf(ControlSessionError)
    expect(failure).toMatchObject({ code: 'DURABILITY_FAILED' })
    expect((failure as ControlSessionError).cause).toBeInstanceOf(AggregateError)
  })

  it.each([
    ['mismatched', globalIdentityEvents(SessionId('devframe-global:profile-1'), 'other-profile')],
    ['duplicate', globalIdentityEvents(SessionId('devframe-global:profile-1'), 'profile-1', true)],
  ] as const)('fails closed on a %s persisted identity without creating a replacement', async (_label, events) => {
    const id = SessionId('devframe-global:profile-1')
    const test = setup({
      persisted: new Map([[id, { meta: globalHeader(id), events }]]),
    })

    await expect(test.controller.openGlobal({ profileId: 'profile-1' }))
      .rejects.toMatchObject({ code: 'IDENTITY_INVALID' })
    expect(test.resume).toHaveBeenCalledOnce()
    expect(test.list).toHaveBeenCalledOnce()
    expect(test.create).not.toHaveBeenCalled()
    expect(test.publications).toEqual([])
    expect(test.liveAgents.get(id)).toBeUndefined()
    expect(test.liveSessions.get(id)).toBeUndefined()
  })

  it.each([
    ['no cwd', header(SessionId('devframe-global:profile-1'))],
    ['a project cwd', header(
      SessionId('devframe-global:profile-1'),
      resolve('unexpected-project'),
    )],
  ] as const)('fails closed on a Global header with %s', async (_label, meta) => {
    const id = SessionId('devframe-global:profile-1')
    const test = setup({
      persisted: new Map([[
        id,
        { meta, events: globalIdentityEvents(id, 'profile-1') },
      ]]),
    })

    await expect(test.controller.openGlobal({ profileId: 'profile-1' }))
      .rejects.toMatchObject({ code: 'IDENTITY_INVALID' })
    expect(test.create).not.toHaveBeenCalled()
    expect(test.publications).toEqual([])
  })

  it('takes a Project cwd only from the native Workspace and attaches after durability', async () => {
    const canonicalPath = resolve('registered-workspace')
    const untrustedPath = resolve('caller-supplied-workspace')
    const workspace = workspaceFixture(canonicalPath)
    const test = setup({ workspace: workspace.workspace })

    const result = await test.controller.openProject({
      profileId: 'profile-1',
      workspaceId: 'workspace-1',
      cwd: untrustedPath,
    } as never)

    expect(test.workspaceGet).toHaveBeenCalledOnce()
    expect(test.workspaceGet).toHaveBeenCalledWith(WorkspaceId('workspace-1'))
    expect(workspace.status).toHaveBeenCalledOnce()
    expect(test.persistenceCreate.mock.calls[0]![0].cwd).toBe(canonicalPath)
    expect(result.agent.session.header.cwd).toBe(canonicalPath)
    expect(result.agent.session.header.agentPreset).toBe('standard')
    expect(result.agent.session.header.cwd).not.toBe(untrustedPath)
    expect(result.agent.session.events[0]?.data).toEqual({
      schemaVersion: 1,
      role: 'project',
      sessionId: result.id,
      profileId: 'profile-1',
      workspaceId: 'workspace-1',
      cwd: canonicalPath,
    })
    expect(workspace.attachSession).toHaveBeenCalledOnce()
    expect(workspace.attachSession).toHaveBeenCalledWith(result.id)
    expect(test.flush.mock.invocationCallOrder[0])
      .toBeLessThan(workspace.attachSession.mock.invocationCallOrder[0]!)
  })

  it('blocks a Global control cwd that overlaps a registered workspace', async () => {
    const workspaceRoot = await temporaryDirectory('dsh-devframe-workspace-root-')
    const dshHome = join(workspaceRoot, '.dsh')
    await mkdir(dshHome)
    vi.stubEnv('DSH_HOME', dshHome)
    const workspace = workspaceFixture(workspaceRoot)
    const test = setup({ workspace: workspace.workspace })

    await expect(test.controller.openGlobal({ profileId: 'profile-1' }))
      .rejects.toMatchObject({ code: 'GLOBAL_CWD_CONFLICT' })
    expect(test.workspaceList).toHaveBeenCalledOnce()
    expect(test.persistenceCreate).not.toHaveBeenCalled()
    expect(test.publications).toEqual([])
  })

  it('does not publish a controller when cold identity persistence fails and retries safely', async () => {
    const test = setup({ appendOutcomes: [new Error('append failed')] })
    const id = SessionId('devframe-global:profile-1')

    await expect(test.controller.openGlobal({ profileId: 'profile-1' }))
      .rejects.toMatchObject({ code: 'DURABILITY_FAILED' })

    expect(test.persistenceCreate).toHaveBeenCalledOnce()
    expect(test.persistenceAppend).toHaveBeenCalledOnce()
    expect(test.publications).toEqual([])
    expect(test.liveAgents.get(id)).toBeUndefined()
    expect(test.liveSessions.get(id)).toBeUndefined()
    expect(test.create).not.toHaveBeenCalled()

    const retried = await test.controller.openGlobal({ profileId: 'profile-1' })
    expect(retried.id).toBe(id)
    expect(test.persistenceCreate).toHaveBeenCalledOnce()
    expect(test.persistenceAppend).toHaveBeenCalledTimes(2)
    expect(test.publications).toHaveLength(1)
    expect(test.liveAgents.get(id)).toBe(retried.agent)
  })

  it('retries a failed first real JSONL append without restarting the Host', async () => {
    const persistenceRoot = await temporaryDirectory('dsh-devframe-retry-jsonl-')
    const dshHome = await temporaryDirectory('dsh-devframe-retry-home-')
    vi.stubEnv('DSH_HOME', dshHome)
    const test = await mountRealHarness(persistenceRoot)
    const realAppend = test.ctx.sessionPersistence.append.bind(test.ctx.sessionPersistence)
    let attempts = 0
    vi.spyOn(test.ctx.sessionPersistence, 'append').mockImplementation(async (id, events) => {
      attempts += 1
      if (attempts === 1) throw new Error('injected append failure')
      await realAppend(id, events)
    })

    await expect(test.ctx.devframeControlSessions.openGlobal({ profileId: 'retry-profile' }))
      .rejects.toMatchObject({ code: 'DURABILITY_FAILED' })
    expect(test.ctx.agents.get(globalControllerSessionId('retry-profile'))).toBeUndefined()

    const retried = await test.ctx.devframeControlSessions.openGlobal({ profileId: 'retry-profile' })
    expect(retried.id).toBe(globalControllerSessionId('retry-profile'))
    expect(attempts).toBe(2)
    const persisted = await test.ctx.sessionPersistence.inspect(retried.id)
    expect(persisted.events.filter(event => event.type === 'controller/identity'))
      .toEqual([expect.objectContaining({ type: 'controller/identity', seq: 0 })])
  })

  it('bounds a real control-cwd filesystem failure without echoing its path', async () => {
    const root = await temporaryDirectory('dsh-devframe-invalid-home-')
    const invalidHome = join(root, 'not-a-directory')
    await writeFile(invalidHome, 'file')
    vi.stubEnv('DSH_HOME', invalidHome)
    const test = setup()

    const failure = await test.controller.openGlobal({ profileId: 'profile-1' }).then(
      () => { throw new Error('expected Global open to fail') },
      (error: unknown) => error,
    )

    expect(failure).toBeInstanceOf(ControlSessionError)
    expect(failure).toMatchObject({ code: 'CONTROL_CWD_UNAVAILABLE' })
    expect((failure as Error).message).not.toContain(invalidHome)
    expect(test.persistenceCreate).not.toHaveBeenCalled()
  })

  it('keeps a real JSONL controller unpublished until the identity append is durable', async () => {
    const persistenceRoot = await temporaryDirectory('dsh-devframe-prepublish-jsonl-')
    const dshHome = await temporaryDirectory('dsh-devframe-prepublish-home-')
    vi.stubEnv('DSH_HOME', dshHome)
    const test = await mountRealHarness(persistenceRoot)
    const id = SessionId('devframe-global:prepublish-profile')
    const appendEntered = Promise.withResolvers<undefined>()
    const allowAppend = Promise.withResolvers<undefined>()
    const appendCommitted = Promise.withResolvers<undefined>()
    const allowPublish = Promise.withResolvers<undefined>()
    const realAppend = test.ctx.sessionPersistence.append.bind(test.ctx.sessionPersistence)
    vi.spyOn(test.ctx.sessionPersistence, 'append').mockImplementation(async (sessionId, events) => {
      appendEntered.resolve(undefined)
      await allowAppend.promise
      await realAppend(sessionId, events)
      appendCommitted.resolve(undefined)
      await allowPublish.promise
    })

    const opening = test.ctx.devframeControlSessions.openGlobal({ profileId: 'prepublish-profile' })
    try {
      await appendEntered.promise
      expect(test.ctx.agents.get(id)).toBeUndefined()
      expect(test.ctx.sessions.get(id)).toBeUndefined()
      expect((await test.ctx.sessionPersistence.list()).some(header => header.id === id)).toBe(false)

      allowAppend.resolve(undefined)
      await appendCommitted.promise
      expect((await test.ctx.sessionPersistence.list()).some(header => header.id === id)).toBe(true)
      expect(test.ctx.agents.get(id)).toBeUndefined()
      expect(test.ctx.sessions.get(id)).toBeUndefined()
      const cold = await test.ctx.sessionPersistence.inspect(id)
      expect(cold.events).toHaveLength(1)
      expect(cold.events[0]).toMatchObject({ type: 'controller/identity', seq: 0 })

      allowPublish.resolve(undefined)
      const result = await opening
      expect(result.id).toBe(id)
      expect(test.ctx.agents.get(id)).toBe(result.agent)
      expect(test.ctx.sessions.get(id)).toBe(result.agent.session)
    } finally {
      allowAppend.resolve(undefined)
      allowPublish.resolve(undefined)
      await opening.catch(() => undefined)
    }
  })

  it('blocks a real scoped tool before its body can execute', async () => {
    const persistenceRoot = await temporaryDirectory('dsh-devframe-tool-guard-jsonl-')
    const dshHome = await temporaryDirectory('dsh-devframe-tool-guard-home-')
    vi.stubEnv('DSH_HOME', dshHome)
    const test = await mountRealHarness(persistenceRoot)
    const opened = await test.ctx.devframeControlSessions.openGlobal({ profileId: 'tool-guard-profile' })
    let bodyCalls = 0
    opened.agent.ctx.tools.register(defineTool({
      name: 'devframe-danger-probe',
      description: 'must never run for an identity-only controller',
      parameters: {},
      output: {
        schema: { type: 'string' },
        render: (_args, value) => [{ type: 'text', text: value }],
      },
      async execute() {
        bodyCalls += 1
        return 'executed'
      },
    }))

    const result = await test.ctx.tools.execute({
      signal: AbortSignal.timeout(5_000),
      callId: CallId('devframe-tool-guard-probe'),
      name: 'devframe-danger-probe',
      arguments: {},
      agent: opened.agent,
    })

    expect(result).toMatchObject({
      isError: true,
      error: { message: 'DevFrame Slice 0 controller execution is not enabled' },
    })
    expect(bodyCalls).toBe(0)
  })

  it('rejects a real live Agent that already owns the deterministic Global id', async () => {
    const persistenceRoot = await temporaryDirectory('dsh-devframe-live-collision-jsonl-')
    const dshHome = await temporaryDirectory('dsh-devframe-live-collision-home-')
    vi.stubEnv('DSH_HOME', dshHome)
    const test = await mountRealHarness(persistenceRoot)
    const id = globalControllerSessionId('collision-profile')
    const existing = await test.ctx.agents.create({
      sessionId: id,
      meta: { cwd: dshHomePath('devframe-control') },
    })

    await expect(test.ctx.devframeControlSessions.openGlobal({ profileId: 'collision-profile' }))
      .rejects.toMatchObject({ code: 'LIVE_COLLISION' })
    expect(test.ctx.agents.get(id)).toBe(existing.agent)
    expect((await test.ctx.sessionPersistence.list()).some(header => header.id === id)).toBe(false)
  })

  it('restarts a real Global AgentLoop session from JSONL without reading either launch project', async () => {
    const persistenceRoot = await temporaryDirectory('dsh-devframe-control-jsonl-')
    const dshHome = await temporaryDirectory('dsh-devframe-control-home-')
    const firstCwd = await temporaryDirectory('dsh-devframe-control-cwd-a-')
    const secondCwd = await temporaryDirectory('dsh-devframe-control-cwd-b-')
    await Promise.all([
      mkdir(join(firstCwd, '.git')),
      mkdir(join(secondCwd, '.git')),
      writeFile(join(firstCwd, 'AGENTS.md'), 'launch-project-a-secret'),
      writeFile(join(secondCwd, 'AGENTS.md'), 'launch-project-b-secret'),
      writeFile(join(dshHome, 'AGENTS.md'), 'dsh-home-global-instruction'),
    ])
    vi.stubEnv('DSH_HOME', dshHome)
    const controlCwd = join(dshHome, 'devframe-control')

    changeCwd(firstCwd)
    const first = await mountRealHarness(persistenceRoot)
    const firstCreate = vi.spyOn(first.ctx.agents, 'create')
    const firstResume = vi.spyOn(first.ctx.agents, 'resume')
    const created = await first.ctx.devframeControlSessions.openGlobal({ profileId: 'real-profile' })
    expect(await first.ctx.sessions.flush(created.agent.session)).toBe(true)
    expect(firstCreate).not.toHaveBeenCalled()
    expect(firstResume).toHaveBeenCalledTimes(2)
    expect(created.agent.session.header.cwd).toBe(controlCwd)
    expect(created.agent.session.header).not.toHaveProperty('agentPreset')
    expect(created.agent.session.events.filter(event => event.type === 'controller/identity')).toHaveLength(1)
    const firstInstructions = await effectiveInstructions(first.ctx, created.agent)
    expect(firstInstructions).toContain('dsh-home-global-instruction')
    expect(firstInstructions).not.toContain('launch-project-a-secret')
    expect(firstInstructions).not.toContain('launch-project-b-secret')
    expect(first.modelStream).not.toHaveBeenCalled()
    await first.ctx.fiber.dispose()

    changeCwd(secondCwd)
    const second = await mountRealHarness(persistenceRoot)
    const resumedThrough = vi.spyOn(second.ctx.agents, 'resume')
    const replacementCreate = vi.spyOn(second.ctx.agents, 'create')
    const resumed = await second.ctx.devframeControlSessions.openGlobal({ profileId: 'real-profile' })
    expect(await second.ctx.sessions.flush(resumed.agent.session)).toBe(true)

    expect(resumed.id).toBe(created.id)
    expect(resumedThrough).toHaveBeenCalledOnce()
    expect(replacementCreate).not.toHaveBeenCalled()
    expect(resumed.agent.session.header.cwd).toBe(controlCwd)
    expect(resumed.agent.session.header).not.toHaveProperty('agentPreset')
    const identities = resumed.agent.session.events.filter(event => event.type === 'controller/identity')
    expect(identities).toHaveLength(1)
    expect(identities[0]).toMatchObject({
      seq: 0,
      data: {
        schemaVersion: 1,
        role: 'global',
        sessionId: resumed.id,
        profileId: 'real-profile',
        cwd: controlCwd,
      },
    })
    const resumedInstructions = await effectiveInstructions(second.ctx, resumed.agent)
    expect(resumedInstructions).toContain('dsh-home-global-instruction')
    expect(resumedInstructions).not.toContain('launch-project-a-secret')
    expect(resumedInstructions).not.toContain('launch-project-b-secret')
    expect(second.modelStream).not.toHaveBeenCalled()
  })

  it('restarts a real Project Controller from JSONL with the native Workspace identity', async () => {
    const persistenceRoot = await temporaryDirectory('dsh-devframe-project-jsonl-')
    const dshHome = await temporaryDirectory('dsh-devframe-project-home-')
    const projectRoot = await temporaryDirectory('dsh-devframe-project-root-')
    vi.stubEnv('DSH_HOME', dshHome)
    const firstWorkspace = workspaceFixture(projectRoot)
    const first = await mountRealHarness(persistenceRoot, firstWorkspace.workspace)
    const created = await first.ctx.devframeControlSessions.openProject({
      profileId: 'real-profile',
      workspaceId: 'workspace-1',
    })
    expect(created.agent.session.header.cwd).toBe(projectRoot)
    expect(created.agent.session.header.agentPreset).toBe('standard')
    expect(first.ctx.tools.schemas(created.agent).map(tool => tool.name))
      .toEqual(expect.arrayContaining(['read', 'edit']))
    expect(firstWorkspace.attachSession).toHaveBeenCalledWith(created.id)
    expect(first.modelStream).not.toHaveBeenCalled()
    await first.ctx.fiber.dispose()

    const secondWorkspace = workspaceFixture(projectRoot)
    const second = await mountRealHarness(persistenceRoot, secondWorkspace.workspace)
    const resumedThrough = vi.spyOn(second.ctx.agents, 'resume')
    const replacementCreate = vi.spyOn(second.ctx.agents, 'create')
    const resumed = await second.ctx.devframeControlSessions.openProject({
      profileId: 'real-profile',
      workspaceId: 'workspace-1',
    })

    expect(resumed.id).toBe(created.id)
    expect(resumedThrough).toHaveBeenCalledOnce()
    expect(replacementCreate).not.toHaveBeenCalled()
    expect(resumed.agent.session.header.cwd).toBe(projectRoot)
    expect(resumed.agent.session.header.agentPreset).toBe('standard')
    expect(second.ctx.tools.schemas(resumed.agent).map(tool => tool.name))
      .toEqual(expect.arrayContaining(['read', 'edit']))
    expect(resumed.agent.session.events.filter(event => event.type === 'controller/identity'))
      .toEqual([expect.objectContaining({
        type: 'controller/identity',
        seq: 0,
        data: {
          schemaVersion: 1,
          role: 'project',
          sessionId: resumed.id,
          profileId: 'real-profile',
          workspaceId: 'workspace-1',
          cwd: projectRoot,
        },
      })])
    expect(secondWorkspace.attachSession).toHaveBeenCalledWith(resumed.id)
    expect(second.modelStream).not.toHaveBeenCalled()
  })
})
