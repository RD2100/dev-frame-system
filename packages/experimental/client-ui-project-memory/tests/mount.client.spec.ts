/**
 * The Library page browser plugin through its REAL mount face: the Remote
 * contribution is mounted by `ctx.remote.$mount`, the `library` key is
 * registered in the capability-center tab seat, the NS dictionary is
 * registered, and the composed disposer tears both halves down. Failures in
 * the Client registration dispose the Remote namespace before rethrowing.
 * @module tests/mount
 */

import { Context, Service } from '@deepseek-ai/cordis'
import { describe, expect, it, vi } from 'vitest'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import { LocaleRuntime } from '@deepseek-ai/dsh-client-locale/client'
import { SlotRegistry } from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-settings-plugin-inventory/client'
import type {} from '@deepseek-ai/dsh-experimental-project-memory/remote'
import type { TypertRemoteContribution } from '@deepseek-ai/dsh-typert-protocol'
import { LibraryCard, type LibraryCardFace } from '../src/client/LibraryCard.tsx'
import { NS, zh } from '../src/client/locales.ts'
import { inject, mountLibraryUi } from '../src/client/mount.ts'
import { apply as nodeApply } from '../src/index.ts'

const SESSION = 'library-session' as SessionId
const REMOTE: TypertRemoteContribution = {
  package: '@deepseek-ai/dsh-experimental-project-memory',
  descriptors: [],
}

async function bench(options: { registrationFailure?: boolean } = {}) {
  const ctx = new Context()
  class RemoteService extends Service {
    readonly disposeMount = vi.fn(() => Promise.resolve())
    readonly mount = vi.fn((_contribution: unknown) => Promise.resolve(this.disposeMount))

    constructor(serviceCtx: Context) {
      super(serviceCtx, 'remote')
    }

    $mount(contribution: unknown): Promise<() => Promise<void>> {
      return this.mount(contribution)
    }
  }
  const remote = new RemoteService(ctx)
  ctx.provide('remote.library', {
    view: vi.fn(() => Promise.resolve({ ok: true as const, value: { status: 'ready' as const } })),
    list: vi.fn(() => Promise.resolve({ ok: true as const, value: { files: [] } })),
    read: vi.fn(() => Promise.resolve({ ok: true as const, value: { content: '' } })),
    search: vi.fn(() => Promise.resolve({ ok: true as const, value: { files: [] } })),
  })
  ctx.provide('sessions', {
    list: { getSnapshot: () => ({ current: SESSION }) },
    scope: (id: SessionId) => id === SESSION ? {} : undefined,
  })
  ctx.provide('conversation', {
    input: {
      for: (_scope: unknown) => ({
        state: { getSnapshot: () => ({ draft: '' }) },
        setDraft: vi.fn(),
      }),
    },
  })
  ctx.provide('locale', new LocaleRuntime(ctx))
  await ctx.plugin(SlotRegistry).await()
  ctx.slots.register({
    name: 'root',
    children: { 'capabilities.center.tab': { kind: 'keyed', scope: 'root' } },
  } as never, () => null)
  if (options.registrationFailure === true) {
    vi.spyOn(ctx.slots, 'inject').mockImplementationOnce(() => { throw new Error('slot registration failed') })
  }
  const fiber = options.registrationFailure === true
    ? ctx.plugin({ apply() {} })
    : ctx.plugin({ inject: [...inject], apply: clientCtx => mountLibraryUi(clientCtx, REMOTE) })
  const activation: Promise<unknown> = options.registrationFailure === true
    ? mountLibraryUi(ctx, REMOTE).catch((error: unknown) => error)
    : fiber.await()
  if (options.registrationFailure !== true) {
    await activation
  } else {
    await fiber.await()
  }
  const entry = () => ctx.slots.entries('capabilities.center.tab')
    .find(candidate => candidate.component === LibraryCard)
  return { ctx, fiber, activation, remote, entry }
}

describe('ui-library browser plugin', () => {
  it('registers the NS dictionary and one disposable library tab', async () => {
    const b = await bench()
    expect(inject).toEqual(['remote', 'slots', 'locale'])
    expect(b.entry()).toMatchObject({
      options: { key: 'library' },
      locale: NS,
    })
    expect(b.remote.mount).toHaveBeenCalledOnce()
    expect(b.remote.mount).toHaveBeenCalledWith(REMOTE)
    b.ctx.locale.setLocale('zh')
    expect(b.ctx.locale.bind(NS)('center.title', {})).toBe(zh['center.title'])

    const face = (b.entry()!.inject as unknown as () => LibraryCardFace)()
    expect(typeof face.load).toBe('function')
    expect(typeof face.list).toBe('function')
    expect(typeof face.read).toBe('function')
    expect(typeof face.search).toBe('function')
    expect(typeof face.reference).toBe('function')
    await expect(face.load()).resolves.toMatchObject({ ok: true, value: { status: 'ready' } })
    expect(face.reference('@vault:/lib/a.md')).toBe(true)

    await b.fiber.dispose()
    expect(b.entry()).toBeUndefined()
    expect(b.remote.disposeMount).toHaveBeenCalledOnce()
  })

  it('unmounts the Remote contribution when later Client registration fails', async () => {
    const b = await bench({ registrationFailure: true })
    await expect(b.activation).resolves.toMatchObject({ message: 'slot registration failed' })
    expect(b.remote.mount).toHaveBeenCalledOnce()
    expect(b.remote.disposeMount).toHaveBeenCalledOnce()
  })

  it('keeps the node half inert', () => {
    expect(() => { nodeApply() }).not.toThrow()
  })
})
