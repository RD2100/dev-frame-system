// @vitest-environment jsdom
/**
 * The browser plugin through a real Client composition: the generated Remote
 * contribution mounts, the card registers into the sidebar footer-action seat
 * with the status face, and the registrations roll back together.
 */

import { Context, Service } from '@deepseek-ai/cordis'
import { describe, expect, it, vi } from 'vitest'
import { LocaleRuntime } from '@deepseek-ai/dsh-client-locale/client'
import { SlotRegistry } from '@deepseek-ai/dsh-client-ui-renderer/client'
import type { TypertRemoteContribution } from '@deepseek-ai/dsh-typert-protocol'
import { ShadowCard } from '../src/client/ShadowCard.tsx'
import { inject, mountShadowEntryUi } from '../src/client/mount.ts'
import { apply as nodeApply } from '../src/index.ts'

const CONTRIBUTION: TypertRemoteContribution = {
  package: '@deepseek-ai/dsh-experimental-shadow-controller',
  descriptors: [],
}

class RemoteStub extends Service {
  readonly disposeMount = vi.fn(() => Promise.resolve())
  readonly mount = vi.fn((_contribution: unknown) => Promise.resolve(this.disposeMount))

  constructor(serviceCtx: Context) {
    super(serviceCtx, 'remote')
  }

  $mount(contribution: unknown): Promise<() => Promise<void>> {
    return this.mount(contribution)
  }
}

async function bench(options: { registrationFailure?: boolean; readFailure?: boolean } = {}): Promise<{
  ctx: Context
  fiber: ReturnType<Context['plugin']>
  calls: string[]
  remote: RemoteStub
  entry: () => { options: { id?: string; order?: number }; locale?: string; inject?: () => unknown } | undefined
}> {
  const ctx = new Context()
  const calls: string[] = []
  const remote = new RemoteStub(ctx)
  ctx.provide('remote.shadow', {
    readStatus: () => {
      calls.push('shadow/readStatus')
      return Promise.resolve(options.readFailure === true
        ? { ok: false as const, error: { code: 'gateway/internal', message: 'offline', details: {} } }
        : {
          ok: true as const,
          value: {
            mounted: true,
            shadowSessionId: 'session-shadow',
            shadowLive: true,
            authorizedRoots: ['D:/projects'],
            bindings: [],
          },
        })
    },
  })
  ctx.provide('locale', new LocaleRuntime(ctx))
  await ctx.plugin(SlotRegistry).await()
  // The sidebar declares the footer-action seat; its declaration is what the
  // injection waits on and what authorizes the registration.
  ctx.slots.register({
    name: 'root',
    children: { 'sidebar.footer.action': { kind: 'list', scope: 'root' } },
  } as never, () => null)
  if (options.registrationFailure === true) {
    vi.spyOn(ctx.slots, 'inject').mockImplementationOnce(() => { throw new Error('slot registration failed') })
  }
  const fiber = ctx.plugin({ inject: [...inject], apply: clientCtx => mountShadowEntryUi(clientCtx, CONTRIBUTION) })
  await fiber.await()
  const entry = () => ctx.slots.entries('sidebar.footer.action')
    .find(candidate => candidate.component === ShadowCard)
  return { ctx, fiber, calls, remote, entry }
}

describe('ui-shadow-entry browser plugin', () => {
  it('registers one disposable footer action with the status face and locale namespace', async () => {
    const b = await bench()
    expect(inject).toEqual(['remote', 'slots', 'locale'])
    expect(b.entry()).toMatchObject({
      options: { id: 'shadow-entry', order: 30 },
      locale: 'shadow',
    })
    expect(b.remote.mount).toHaveBeenCalledExactlyOnceWith(CONTRIBUTION)

    const face = (b.entry()!.inject as unknown as () => { hooks: { status: { getSnapshot: () => unknown } }; onRefresh: () => void })()
    expect(face.hooks.status.getSnapshot()).toEqual({ view: undefined, error: undefined })
    face.onRefresh()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(b.calls).toEqual(['shadow/readStatus'])
    expect(face.hooks.status.getSnapshot()).toMatchObject({ view: { shadowSessionId: 'session-shadow' } })

    await b.fiber.dispose()
    expect(b.entry()).toBeUndefined()
    expect(b.remote.disposeMount).toHaveBeenCalledOnce()
  })

  it('unmounts the Remote contribution when later registration fails', async () => {
    const ctx = new Context()
    const remote = new RemoteStub(ctx)
    ctx.provide('remote.shadow', { readStatus: () => Promise.resolve({ ok: true as const, value: { mounted: false, shadowSessionId: undefined, shadowLive: false, authorizedRoots: [], bindings: [] } }) })
    ctx.provide('locale', new LocaleRuntime(ctx))
    await ctx.plugin(SlotRegistry).await()
    vi.spyOn(ctx.slots, 'inject').mockImplementationOnce(() => { throw new Error('slot registration failed') })
    await expect(mountShadowEntryUi(ctx, CONTRIBUTION)).rejects.toMatchObject({ message: 'slot registration failed' })
    expect(remote.mount).toHaveBeenCalledOnce()
    expect(remote.disposeMount).toHaveBeenCalledOnce()
    await ctx.fiber.dispose()
  })

  it('keeps the node half inert', () => {
    expect(() => { nodeApply() }).not.toThrow()
  })
})
