import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { remoteMethods } from '@deepseek-ai/dsh-typert-protocol'
import type { ShadowRouter, ShadowRouterStatus } from '@deepseek-ai/dsh-experimental-shadow-router'
import ShadowController, { type ShadowStatusView } from '../src/index.ts'

/**
 * A router double carrying only the read the controller consumes. The
 * controller reaches the router through `ctx.get`, so the double is narrowed
 * by cast to the declared service key rather than by a test seam on the class.
 */
function routerStub(status: ShadowRouterStatus): ShadowRouter {
  return { readStatus: () => status } as unknown as ShadowRouter
}

const configured: ShadowRouterStatus = {
  shadowSessionId: 'session-shadow',
  shadowLive: true,
  authorizedRoots: ['D:/projects'],
  bindings: [{
    workspaceId: 'ws-1',
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
})
