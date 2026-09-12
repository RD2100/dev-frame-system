import { describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { remoteMethods } from '@deepseek-ai/dsh-typert-protocol'
import type { ProjectOpenResult, ProjectSendResult, ProjectStopResult } from '@deepseek-ai/dsh-experimental-shadow-router'
import type { ShadowRouter, ShadowRouterStatus } from '@deepseek-ai/dsh-experimental-shadow-router'
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

function routerStub(status: ShadowRouterStatus, writes?: Partial<RecordedWrites>): ShadowRouter {
  return {
    readStatus: () => status,
    openProjectForHost: writes?.openProjectForHost ?? (async () => ({}) as ProjectOpenResult),
    sendToProjectForHost: writes?.sendToProjectForHost ?? (async () => ({}) as ProjectSendResult),
    releaseProjectForHost: writes?.releaseProjectForHost ?? (async () => ({}) as ProjectStopResult),
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
