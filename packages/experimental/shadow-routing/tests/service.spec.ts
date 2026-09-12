import { describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import ShadowRouterDefault, { ShadowRouter } from '../src/index.ts'
import type { ShadowDeliveryRecord, ShadowMessageId } from '../src/index.ts'

/**
 * Minimal concrete subclass exposing the protected emit helper for tests.
 * Every abstract member is a not-under-test stub: this suite pins the seam's
 * registration and event dispatch, not any routing behavior.
 */
class StubRouter extends ShadowRouter {
  emitDeliveryReceivedForTest(workspaceId: Parameters<ShadowRouter['emitDeliveryReceived']>[0], delivery: ShadowDeliveryRecord): void {
    this.emitDeliveryReceived(workspaceId, delivery)
  }

  override markShadow(): void { throw new Error('not under test') }
  override isShadow(agent: Agent | undefined): agent is Agent { void agent; throw new Error('not under test') }
  override async openProject(): Promise<never> { throw new Error('not under test') }
  override async sendToProject(): Promise<never> { throw new Error('not under test') }
  override async stopProject(): Promise<never> { throw new Error('not under test') }
  override async projectStatus(): Promise<never> { throw new Error('not under test') }
  override async confirmProjectStopped(): Promise<never> { throw new Error('not under test') }
  override async openProjectForHost(): Promise<never> { throw new Error('not under test') }
  override async sendToProjectForHost(): Promise<never> { throw new Error('not under test') }
  override async releaseProjectForHost(): Promise<never> { throw new Error('not under test') }
  override async setActiveGoal(): Promise<never> { throw new Error('not under test') }
  override async completeDelivery(): Promise<never> { throw new Error('not under test') }
  override async recoverDeliveries(): Promise<never> { throw new Error('not under test') }
  override async reconcileProject(): Promise<never> { throw new Error('not under test') }
  override findBinding(): undefined { throw new Error('not under test') }
  override listBindings(): readonly never[] { throw new Error('not under test') }
  override listDeliveries(): readonly never[] { throw new Error('not under test') }
  override readStatus(): never { throw new Error('not under test') }
}

const WORKSPACE_ID = WorkspaceId('ws-1')

/** One `received`-state record snapshot; only the fields the event payloads carry matter here. */
function deliveryRecord(messageId: string): ShadowDeliveryRecord {
  return Object.freeze({
    messageId: messageId as ShadowMessageId,
    state: 'received',
  }) as ShadowDeliveryRecord
}

describe('ShadowRouter seam', () => {
  it('a concrete subclass registers as ctx.shadowRouter and unregisters on disposal (HMR safety)', async () => {
    const ctx = new Context()
    const fiber = await ctx.plugin(StubRouter)
    expect(ctx.get('shadowRouter')).toBeInstanceOf(StubRouter)
    await fiber.dispose()
    expect(ctx.get('shadowRouter')).toBeUndefined()
  })

  it('loading a second implementation throws (one shadow router per context — cordis standard)', async () => {
    const ctx = new Context()
    await ctx.plugin(StubRouter)
    await expect(ctx.plugin(StubRouter)).rejects.toThrow(/service "shadowRouter" has been registered/)
  })

  it('emitDeliveryReceived dispatches the workspace id and record snapshot to every listener', () => {
    const ctx = new Context()
    const spy = vi.fn()
    ctx.on('shadow/delivery-received', spy)
    const router = new StubRouter(ctx)
    const record = deliveryRecord('msg-1')
    router.emitDeliveryReceivedForTest(WORKSPACE_ID, record)
    expect(spy).toHaveBeenCalledOnce()
    expect(spy).toHaveBeenCalledWith(WORKSPACE_ID, record)
  })

  it('contains a throwing listener PER LISTENER: later listeners still run, nothing propagates', () => {
    const ctx = new Context()
    const warn = vi.spyOn(ctx.logger, 'warn').mockImplementation(() => ctx.logger)
    const reached: string[] = []
    ctx.on('shadow/delivery-received', () => { throw new Error('bad listener') })
    ctx.on('shadow/delivery-received', (workspaceId) => { reached.push(workspaceId) })
    const router = new StubRouter(ctx)
    expect(() => { router.emitDeliveryReceivedForTest(WORKSPACE_ID, deliveryRecord('msg-2')) }).not.toThrow()
    expect(reached).toEqual([WORKSPACE_ID])
    expect(warn).toHaveBeenCalledOnce()
    expect(String(warn.mock.calls[0]![0])).toContain('shadow/delivery-received listener threw')
  })

  it('contains an asynchronously rejected listener without starving peers', async () => {
    const ctx = new Context()
    const warn = vi.spyOn(ctx.logger, 'warn').mockImplementation(() => ctx.logger)
    const seen: string[] = []
    // Runtime listeners may return thenables even though the declaration's observable result is void.
    // oxlint-disable-next-line typescript/no-misused-promises -- exercises rejected-listener containment
    ctx.on('shadow/delivery-received', async () => { throw new Error('async observer failed') })
    ctx.on('shadow/delivery-received', (workspaceId) => { seen.push(workspaceId) })
    const router = new StubRouter(ctx)
    router.emitDeliveryReceivedForTest(WORKSPACE_ID, deliveryRecord('msg-3'))
    await Promise.resolve()
    expect(seen).toEqual([WORKSPACE_ID])
    expect(String(warn.mock.calls[0]![0])).toContain('listener rejected')
  })

  it('containment is total: a listener throwing a value whose coercion throws neither propagates nor starves later listeners', () => {
    const ctx = new Context()
    const warn = vi.spyOn(ctx.logger, 'warn').mockImplementation(() => ctx.logger)
    const reached: string[] = []
    ctx.on('shadow/delivery-received', () => {
      throw { toString: () => { throw new Error('coercion trap') } }
    })
    ctx.on('shadow/delivery-received', (workspaceId) => { reached.push(workspaceId) })
    const router = new StubRouter(ctx)
    expect(() => { router.emitDeliveryReceivedForTest(WORKSPACE_ID, deliveryRecord('msg-4')) }).not.toThrow()
    expect(reached).toEqual([WORKSPACE_ID])
    expect(warn).toHaveBeenCalledOnce()
    expect(String(warn.mock.calls[0]![0])).toContain('[unrenderable thrown value]')
  })

  it('has the expected exports (default = the abstract service class)', () => {
    expect(ShadowRouterDefault).toBe(ShadowRouter)
  })
})
