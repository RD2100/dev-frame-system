import { describe, expect, it, vi } from 'vitest'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { mkdtempSync } from 'node:fs'
import { Context } from '@deepseek-ai/cordis'
import { remoteMethods } from '@deepseek-ai/dsh-typert-protocol'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type {
  ProjectOpenResult,
  ProjectSendResult,
  ProjectStopResult,
  ShadowBindingRecord,
  ShadowBindingState,
  ShadowRouter,
  ShadowRouterStatus,
} from '@deepseek-ai/dsh-experimental-shadow-routing'
import ShadowController, { type ShadowStatusView } from '../src/index.ts'
import type { ShadowAgent } from '../src/shadow-agent.ts'

/**
 * A router double carrying the read and the three host bridges the controller
 * consumes. The controller reaches the router through `ctx.get`, so the
 * double is narrowed by cast to the declared service key rather than by a test
 * seam on the class.
 */
interface RecordedWrites {
  openProjectForHost: ReturnType<typeof vi.fn>
  sendToProjectForHost: ReturnType<typeof vi.fn>
  releaseProjectForHost: ReturnType<typeof vi.fn>
}

function routerStub(status: ShadowRouterStatus, writes?: Partial<RecordedWrites>, records?: ShadowBindingRecord[]): ShadowRouter {
  return {
    readStatus: () => status,
    listBindings: () => records ?? [],
    openProjectForHost: writes?.openProjectForHost ?? (async () => ({}) as ProjectOpenResult),
    sendToProjectForHost: writes?.sendToProjectForHost ?? (async () => ({}) as ProjectSendResult),
    releaseProjectForHost: writes?.releaseProjectForHost ?? (async () => ({}) as ProjectStopResult),
    findBinding: (workspaceId: ShadowBindingRecord['workspaceId']) => records?.find(binding => binding.workspaceId === workspaceId),
  } as unknown as ShadowRouter
}

/** A conversation-host double carrying only the verbs the controller delegates. */
function hostStub(): ShadowAgent {
  return {
    postMessage: async (text: string) => ({ messageId: `msg-for-${text}` }),
    readConversation: async (request: { after?: number; limit?: number }) => ({ messages: [], cursor: request.after ?? 0 }),
  } as unknown as ShadowAgent
}

const wid = (id: string): ShadowRouterStatus['bindings'][number]['workspaceId'] =>
  id as ShadowRouterStatus['bindings'][number]['workspaceId']

const configured: ShadowRouterStatus = {
  shadowSessionId: 'session-shadow',
  shadowLive: true,
  authorizedRoots: ['D:/projects'],
  bindings: [{
    workspaceId: wid('ws-1'),
    canonicalPath: 'D:/projects/alpha',
    bindingRevision: 3,
    state: 'ready',
  }],
}

describe('the shadow Remote namespace a host status surface calls', () => {
  it('publishes the shadow namespace from its own service key', async () => {
    const ctx = new Context()
    await ctx.plugin(ShadowController)
    const controller = ctx.shadowController
    expect(controller.typertRemote.serviceKey).toBe('shadowController')
    expect(controller.typertRemote.namespace).toBe('shadow')
    expect(remoteMethods(controller)).toEqual([
      { method: 'readStatus', invocation: { kind: 'direct' } },
      { method: 'openProject', invocation: { kind: 'direct' } },
      { method: 'sendToController', invocation: { kind: 'direct' } },
      { method: 'releaseProject', invocation: { kind: 'direct' } },
      { method: 'postMessage', invocation: { kind: 'direct' } },
      { method: 'readConversation', invocation: { kind: 'direct' } },
      { method: 'approveTask', invocation: { kind: 'direct' } },
      { method: 'rejectTask', invocation: { kind: 'direct' } },
      { method: 'readBoard', invocation: { kind: 'direct' } },
    ])
  })

  it('mounts and disposes as one registration', async () => {
    const ctx = new Context()
    const fiber = ctx.plugin(ShadowController)
    await fiber.await()
    expect(ctx.get('shadowController')).toBeDefined()
    await fiber.dispose()
    expect(ctx.get('shadowController')).toBeUndefined()
  })

  it('answers mounted:false honestly while no shadow router is mounted', () => {
    const ctx = new Context()
    const controller = new ShadowController(ctx)
    expect(controller.readStatus()).toEqual({
      mounted: false,
      shadowSessionId: undefined,
      shadowLive: false,
      authorizedRoots: [],
      bindings: [],
    })
  })

  it('projects the router snapshot verbatim beside the mount fact', () => {
    const ctx = new Context()
    ctx.provide('shadowRouter', routerStub(configured))
    const controller = new ShadowController(ctx)
    const view: ShadowStatusView = controller.readStatus()
    expect(view).toEqual({ mounted: true, ...configured })
  })

  it('keeps an unconfigured designation undefined instead of inventing one', () => {
    const ctx = new Context()
    ctx.provide('shadowRouter', routerStub({
      shadowLive: false,
      authorizedRoots: [],
      bindings: [],
    }))
    const controller = new ShadowController(ctx)
    const view: ShadowStatusView = controller.readStatus()
    expect(view).toMatchObject({ mounted: true, shadowLive: false })
    expect(view.shadowSessionId).toBeUndefined()
  })

  it('mints a fresh request id per open and delegates to the router bridge', async () => {
    const openProjectForHost = vi.fn(async () => ({}) as ProjectOpenResult)
    const ctx = new Context()
    ctx.provide('shadowRouter', routerStub(configured, { openProjectForHost }))
    const controller = new ShadowController(ctx)
    await expect(controller.openProject({ path: 'D:/projects/alpha' })).resolves.toBeDefined()
    expect(openProjectForHost).toHaveBeenCalledExactlyOnceWith({
      path: 'D:/projects/alpha',
      requestId: expect.stringMatching(/^[0-9a-f-]{36}$/) as string,
    })
  })

  it('mints a fresh request id per send and delegates to the router bridge', async () => {
    const sendToProjectForHost = vi.fn(async () => ({}) as ProjectSendResult)
    const ctx = new Context()
    ctx.provide('shadowRouter', routerStub(configured, { sendToProjectForHost }))
    const controller = new ShadowController(ctx)
    await expect(controller.sendToController({ workspaceId: wid('ws-1'), text: 'ship it' })).resolves.toBeDefined()
    expect(sendToProjectForHost).toHaveBeenCalledExactlyOnceWith({
      workspaceId: 'ws-1',
      text: 'ship it',
      requestId: expect.stringMatching(/^[0-9a-f-]{36}$/) as string,
    })
  })

  it('mints a fresh request id per release and delegates to the router bridge', async () => {
    const releaseProjectForHost = vi.fn(async () => ({ status: 'stopped' }) as ProjectStopResult)
    const ctx = new Context()
    ctx.provide('shadowRouter', routerStub(configured, { releaseProjectForHost }))
    const controller = new ShadowController(ctx)
    await expect(controller.releaseProject({ workspaceId: wid('ws-1') })).resolves.toMatchObject({ status: 'stopped' })
    expect(releaseProjectForHost).toHaveBeenCalledExactlyOnceWith({
      workspaceId: 'ws-1',
      requestId: expect.stringMatching(/^[0-9a-f-]{36}$/) as string,
    })
  })

  it('fails every write face loud when no router is mounted', async () => {
    const ctx = new Context()
    const controller = new ShadowController(ctx)
    await expect(controller.openProject({ path: 'D:/projects/alpha' }))
      .rejects.toThrow('this deployment has no shadow router mounted')
    await expect(controller.sendToController({ workspaceId: wid('ws-1'), text: 'ship it' }))
      .rejects.toThrow('this deployment has no shadow router mounted')
    await expect(controller.releaseProject({ workspaceId: wid('ws-1') }))
      .rejects.toThrow('this deployment has no shadow router mounted')
  })

  it('delegates the conversation faces to the conversation host', async () => {
    const ctx = new Context()
    ctx.provide('shadowAgent', hostStub())
    const controller = new ShadowController(ctx)
    await expect(controller.postMessage({ text: 'open alpha' }))
      .resolves.toEqual({ messageId: 'msg-for-open alpha' })
    await expect(controller.readConversation({ after: 7, limit: 3 }))
      .resolves.toEqual({ messages: [], cursor: 7 })
  })

  it('fails the conversation faces loud when no conversation host is mounted', async () => {
    const ctx = new Context()
    const controller = new ShadowController(ctx)
    await expect(controller.postMessage({ text: 'hello' }))
      .rejects.toThrow('this deployment has no shadow conversation host mounted')
    await expect(controller.readConversation({}))
      .rejects.toThrow('this deployment has no shadow conversation host mounted')
  })
})

/** A live agent double: identity and session must line up with the binding rows. */
interface AgentDouble {
  id: string
  session: { id: string; header: { cwd: string } }
  followup?: ReturnType<typeof vi.fn>
}

/**
 * Build a ctx whose authorities satisfy the full task-start admission: a live
 * root controller on its locked worktree, an open Goal admitting the task, and
 * exactly one Worker with its parent lead on two further locked worktrees.
 * The controller, the delivery registry, and the ledger store are stubbed so
 * approveTask's state transitions and registrations are observable.
 */
function approvalFixture(taskId: string, options?: {
  taskState?: string
  registry?: boolean
  bindingState?: ShadowBindingState
  defaultCommitPaths?: readonly string[]
  listTasks?: () => ReadonlyArray<{
    taskId: string
    pluginId: string
    title: string
    state: string
    worktreeId?: string
    createdAt?: string
    updatedAt?: string
    blockedReason?: string
    nextAction?: string
    wakeCondition?: string
  }>
  branchStatus?: () => Promise<{ directoryExists: boolean; branch?: string }>
}) {
  const taskIdStr = taskId
  const pluginId = 'devframe-goal'
  const controllerCwd = mkdtempSync(join(tmpdir(), 'shadow-wt-controller-'))
  const workerCwd = mkdtempSync(join(tmpdir(), 'shadow-wt-worker-'))
  const leadCwd = mkdtempSync(join(tmpdir(), 'shadow-wt-lead-'))
  const controllerAgent: AgentDouble = { id: 'agent-controller', session: { id: 'session-controller', header: { cwd: controllerCwd } } }
  const workerAgent: AgentDouble = { id: 'agent-worker', session: { id: 'session-worker', header: { cwd: workerCwd } }, followup: vi.fn() }
  const controllerBinding = {
    role: 'controller' as const, parentSessionId: undefined, agentId: 'agent-controller',
    sessionId: 'session-controller', worktreeId: 'wt-controller', worktreePath: controllerCwd, pluginId,
  }
  const workerBinding = {
    role: 'worker' as const, parentSessionId: 'session-lead', agentId: 'agent-worker',
    sessionId: 'session-worker', worktreeId: 'wt-worker', worktreePath: workerCwd, pluginId, taskId,
  }
  const leadBinding = {
    role: 'lead' as const, parentSessionId: 'session-controller', agentId: 'agent-lead',
    sessionId: 'session-lead', worktreeId: 'wt-lead', worktreePath: leadCwd, pluginId,
  }
  const goalState = {
    failure: null,
    lifecycle: null,
    bindings: [{ lifecycle: 'admission_open', goalId: 'goal-1', controllerSessionId: 'session-controller', workspaceId: 'ws-goal', taskIds: [taskIdStr] }],
  }
  const rows = [
    { id: 'wt-controller', path: controllerCwd, lockedBy: 'session-controller', workspaceId: 'ws-goal' },
    { id: 'wt-worker', path: workerCwd, lockedBy: 'session-worker', workspaceId: 'ws-goal' },
    { id: 'wt-lead', path: leadCwd, lockedBy: 'session-lead', workspaceId: 'ws-goal' },
  ]
  const assign = vi.fn(async (_taskId: string, _assignee: string, opts: { beforePersist: () => void }) => { opts.beforePersist(); return { state: 'assigned' } })
  const startDevelopment = vi.fn(async (_taskId: string, opts: { beforePersist: () => void }) => { opts.beforePersist(); return { state: 'developing' } })
  // The find double follows the live task state: a blocked re-approval moves
  // it to assigned through resume, which the authority re-resolution observes.
  let liveTaskState = options?.taskState
  const find = vi.fn((_id: string) => (options?.listTasks?.() ?? []).find(task => task.taskId === _id)
    ?? (liveTaskState === undefined
      ? undefined
      : { taskId: taskIdStr, title: 'Refactor the board', pluginId, state: liveTaskState }))
  const block = vi.fn(async (_taskId: string, detail: unknown) => { void detail; return { state: 'blocked' } })
  const resume = vi.fn(async (_taskId: string) => { liveTaskState = 'assigned'; return { state: 'assigned' } })
  const registerTask = vi.fn()
  const host = hostStub()
  const record: ShadowBindingRecord = {
    workspaceId: wid('ws-1'), canonicalPath: 'D:/repo', controllerSessionId: 'session-controller' as SessionId,
    profileKey: 'devframe', bindingRevision: 1, requestId: 'req-1', state: options?.bindingState ?? 'ready',
    createdAt: '2026-01-01T00:00:00.000Z', updatedAt: '2026-01-01T00:00:00.000Z',
  }
  const ctx = new Context()
  ctx.provide('shadowRouter', routerStub({
    shadowSessionId: 'session-shadow',
    shadowLive: true,
    authorizedRoots: ['D:/repo'],
    bindings: [{
      workspaceId: wid('ws-1'), canonicalPath: 'D:/repo', bindingRevision: 1, state: record.state,
    }],
  }, undefined, [record]))
  ctx.provide('shadowAgent', host)
  ctx.provide('agents', {
    get: (id: string) => id === 'agent-controller' || id === 'session-controller' ? controllerAgent
      : id === 'agent-worker' ? workerAgent : undefined,
  })
  ctx.provide('agentBindings', {
    find: (sessionId: string) => sessionId === 'session-controller' ? controllerBinding
      : sessionId === 'session-worker' ? workerBinding : sessionId === 'session-lead' ? leadBinding : undefined,
    list: () => [controllerBinding, workerBinding, leadBinding],
  })
  ctx.provide('sessionProjections', { stateOf: (_session: unknown, _key: string) => goalState })
  ctx.provide('workspaceRegistry', { list: () => [{ id: 'ws-goal' }] })
  ctx.provide('worktreeRegistry', {
    list: (_workspaceId: string) => rows,
    status: options?.branchStatus ?? (async () => ({ directoryExists: true, branch: 'feature/board' })),
  })
  ctx.provide('projectController', {
    list: () => (options?.listTasks ?? (() => []))() as never,
    find, assign, startDevelopment, block, resume,
  })
  if (options?.registry ?? true) {
    ctx.provide('projectDeliveryRegistry', {
      ledgerPath: join(mkdtempSync(join(tmpdir(), 'shadow-ledger-')), 'ledger.json'),
      ...(options?.defaultCommitPaths === undefined ? {} : { defaultCommitPaths: options.defaultCommitPaths }),
      registerTask,
      unregisterTask: vi.fn(),
    })
  }
  const controller = new ShadowController(ctx)
  return { ctx, controller, host, assign, startDevelopment, registerTask, block, resume, find, controllerAgent, workerAgent }
}

describe('the host approve/reject board faces', () => {
  it('approves a planned task: persists the checkset, registers, assigns, starts, briefs, and notifies', async () => {
    const { controller, host, assign, startDevelopment, registerTask } = approvalFixture('task-1', { taskState: 'planned' })
    const postMessage = vi.spyOn(host, 'postMessage').mockResolvedValue({ messageId: 'msg' })
    const result = await controller.approveTask({ workspaceId: wid('ws-1'), taskId: 'task-1' })
    expect(result).toEqual({ taskId: 'task-1', state: 'developing' })
    expect(registerTask).toHaveBeenCalledWith('task-1', { digest: expect.any(String) as string })
    expect(assign).toHaveBeenCalledWith('task-1', 'session-worker', { beforePersist: expect.any(Function) as () => void })
    expect(startDevelopment).toHaveBeenCalledWith('task-1', { beforePersist: expect.any(Function) as () => void })
    expect(postMessage).toHaveBeenCalledWith(expect.stringContaining('Approved task task-1') as string)
  })

  it('fails loud when the binding is not ready', async () => {
    const { controller } = approvalFixture('task-1', { bindingState: 'provisioning' })
    await expect(controller.approveTask({ workspaceId: wid('ws-1'), taskId: 'task-1' }))
      .rejects.toThrow('approveTask requires a ready workspace binding')
  })

  it('fails loud when the task is neither planned nor blocked', async () => {
    const { controller } = approvalFixture('task-1', { taskState: 'developing' })
    await expect(controller.approveTask({ workspaceId: wid('ws-1'), taskId: 'task-1' }))
      .rejects.toThrow('approveTask requires a planned or blocked task')
  })

  it('re-approves a blocked task: resumes to assigned and starts without re-assigning', async () => {
    const { controller, host, assign, startDevelopment, resume, registerTask } =
      approvalFixture('task-1', { taskState: 'blocked' })
    const postMessage = vi.spyOn(host, 'postMessage').mockResolvedValue({ messageId: 'msg' })
    const result = await controller.approveTask({ workspaceId: wid('ws-1'), taskId: 'task-1' })
    expect(result).toEqual({ taskId: 'task-1', state: 'developing' })
    expect(resume).toHaveBeenCalledWith('task-1')
    expect(assign).not.toHaveBeenCalled()
    expect(startDevelopment).toHaveBeenCalledWith('task-1', { beforePersist: expect.any(Function) as () => void })
    expect(registerTask).toHaveBeenCalledWith('task-1', { digest: expect.any(String) as string })
    expect(postMessage).toHaveBeenCalledWith(expect.stringContaining('Approved task task-1') as string)
  })

  it('fails loud when the delivery registry is not mounted', async () => {
    const { controller } = approvalFixture('task-1', { taskState: 'planned', registry: false })
    await expect(controller.approveTask({ workspaceId: wid('ws-1'), taskId: 'task-1' }))
      .rejects.toThrow('approveTask requires the project delivery registry')
  })

  it('falls back to the deployment default commit scope when the request omits one', async () => {
    const { controller, registerTask } = approvalFixture('task-1', {
      taskState: 'planned', defaultCommitPaths: ['packages/alpha/src/index.ts'],
    })
    await controller.approveTask({ workspaceId: wid('ws-1'), taskId: 'task-1' })
    expect(registerTask).toHaveBeenCalledWith('task-1', {
      digest: expect.any(String) as string,
      commitPaths: ['packages/alpha/src/index.ts'],
    })
  })

  it('prefers a request commit scope over the deployment default', async () => {
    const { controller, registerTask } = approvalFixture('task-1', {
      taskState: 'planned', defaultCommitPaths: ['packages/alpha/src/index.ts'],
    })
    await controller.approveTask({ workspaceId: wid('ws-1'), taskId: 'task-1', commitPaths: ['packages/beta/src/index.ts'] })
    expect(registerTask).toHaveBeenCalledWith('task-1', {
      digest: expect.any(String) as string,
      commitPaths: ['packages/beta/src/index.ts'],
    })
  })

  it('rejects a planned task into blocked with the host reason and notifies', async () => {
    const { controller, host, block } = approvalFixture('task-1', { taskState: 'planned' })
    const postMessage = vi.spyOn(host, 'postMessage').mockResolvedValue({ messageId: 'msg' })
    const result = await controller.rejectTask({ workspaceId: wid('ws-1'), taskId: 'task-1', reason: 'scope too wide' })
    expect(result).toEqual({ taskId: 'task-1', state: 'blocked' })
    expect(block).toHaveBeenCalledWith('task-1', expect.objectContaining({ blockedReason: 'scope too wide' }) as never)
    expect(postMessage).toHaveBeenCalledWith(expect.stringContaining('Rejected task task-1') as string)
  })

  it('fails loud rejecting a task that is not planned', async () => {
    const { controller } = approvalFixture('task-1', { taskState: 'developing' })
    await expect(controller.rejectTask({ workspaceId: wid('ws-1'), taskId: 'task-1', reason: 'nope' }))
      .rejects.toThrow('rejectTask requires a planned task')
  })
})

describe('the host board read face', () => {
  it('answers mounted:false honestly while no project controller is mounted', async () => {
    const ctx = new Context()
    const controller = new ShadowController(ctx)
    await expect(controller.readBoard()).resolves.toEqual({ mounted: false, bindings: [], tasks: [] })
  })

  it('keeps bindings empty while the project controller is mounted without a shadow router', async () => {
    const ctx = new Context()
    ctx.provide('projectController', { list: () => [] })
    const controller = new ShadowController(ctx)
    await expect(controller.readBoard()).resolves.toEqual({ mounted: true, bindings: [], tasks: [] })
  })

  it('projects the binding digest and every task in stable order', async () => {
    const { controller } = approvalFixture('task-1', {
      listTasks: () => [
        // The controller list is already in stable (createdAt, taskId) order;
        // the board projects it verbatim and never re-sorts.
        { taskId: 'task-2', pluginId: 'devframe-goal', title: 'Ship the fix', state: 'integrated', createdAt: '2026-01-01T00:00:00.000Z', updatedAt: '2026-01-03T00:00:00.000Z' },
        { taskId: 'task-1', pluginId: 'devframe-goal', title: 'Refactor the board', state: 'planned', createdAt: '2026-01-02T00:00:00.000Z', updatedAt: '2026-01-02T00:00:00.000Z' },
      ],
    })
    const board = await controller.readBoard()
    expect(board.mounted).toBe(true)
    expect(board.bindings).toEqual([{
      workspaceId: 'ws-1', state: 'ready', controllerSessionId: 'session-controller',
    }])
    expect(board.tasks.map(task => task.taskId)).toEqual(['task-2', 'task-1'])
    expect(board.tasks[1]).toMatchObject({
      taskId: 'task-1', pluginId: 'devframe-goal', title: 'Refactor the board', state: 'planned',
      startReady: true,
    })
    expect(board.tasks[0]).toMatchObject({
      taskId: 'task-2', state: 'integrated',
    })
    expect(board.tasks[0]?.startReady).toBeUndefined()
  })

  it('derives startReady false when the start authority cannot resolve', async () => {
    // The fixture's Goal admits only task-1; a planned task-other cannot be
    // admitted, so the board reports it not ready without advancing state.
    const { controller } = approvalFixture('task-1', {
      listTasks: () => [
        { taskId: 'task-other', pluginId: 'devframe-goal', title: 'Not admitted', state: 'planned', createdAt: '2026-01-01T00:00:00.000Z', updatedAt: '2026-01-01T00:00:00.000Z' },
      ],
    })
    const board = await controller.readBoard()
    expect(board.tasks[0]?.startReady).toBe(false)
  })

  it('reads the worker worktree branch for a developing task', async () => {
    const status = vi.fn(async () => ({ directoryExists: true, branch: 'feature/board' }))
    const { controller } = approvalFixture('task-1', {
      listTasks: () => [
        { taskId: 'task-1', pluginId: 'devframe-goal', title: 'Building', state: 'developing', worktreeId: 'wt-worker', createdAt: '2026-01-01T00:00:00.000Z', updatedAt: '2026-01-01T00:00:00.000Z' },
      ],
      branchStatus: status,
    })
    const board = await controller.readBoard()
    expect(board.tasks[0]?.branch).toBe('feature/board')
    expect(status).toHaveBeenCalledWith('wt-worker')
  })

  it('reports null branch when the worktree status read fails', async () => {
    const { controller } = approvalFixture('task-1', {
      listTasks: () => [
        { taskId: 'task-1', pluginId: 'devframe-goal', title: 'Building', state: 'developing', worktreeId: 'wt-worker', createdAt: '2026-01-01T00:00:00.000Z', updatedAt: '2026-01-01T00:00:00.000Z' },
      ],
      branchStatus: async () => { throw new Error('git is unavailable') },
    })
    const board = await controller.readBoard()
    expect(board.tasks[0]?.branch).toBeNull()
  })

  it('leaves branch absent for an assigned task without a registered worktree', async () => {
    const { controller } = approvalFixture('task-1', {
      listTasks: () => [
        { taskId: 'task-1', pluginId: 'devframe-goal', title: 'Assigned', state: 'assigned', createdAt: '2026-01-01T00:00:00.000Z', updatedAt: '2026-01-01T00:00:00.000Z' },
      ],
    })
    const board = await controller.readBoard()
    expect(board.tasks[0]?.branch).toBeUndefined()
  })
})
