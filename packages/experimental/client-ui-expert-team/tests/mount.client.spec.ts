/**
 * The expert-team browser plugin through its REAL mount face: the Remote
 * contribution is mounted by `ctx.remote.$mount`, the sidebar footer action
 * seat and the conversation input selection chip are registered, the NS
 * dictionary is registered, and the composed disposer tears both halves down.
 * Failures in the Client registration dispose the Remote namespace before
 * rethrowing.
 * @module tests/mount
 */

import { Context, Service } from '@deepseek-ai/cordis'
import { describe, expect, it, vi } from 'vitest'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import { LocaleRuntime } from '@deepseek-ai/dsh-client-locale/client'
import { SlotRegistry } from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-experimental-expert-team/remote'
import type { TypertRemoteContribution } from '@deepseek-ai/dsh-typert-protocol'
import { ExpertSelectionChip } from '../src/client/ExpertSelectionChip.tsx'
import { ExpertTeamCard } from '../src/client/ExpertTeamCard.tsx'
import { NS, zh } from '../src/client/locales.ts'
import { inject, mountExpertTeamUi } from '../src/client/mount.ts'
import { apply as nodeApply } from '../src/index.ts'

const SESSION = 'expert-session' as SessionId
const REMOTE: TypertRemoteContribution = {
  package: '@deepseek-ai/dsh-experimental-expert-team',
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
  ctx.provide('remote.expertTeam', {
    view: vi.fn(() => Promise.resolve({ ok: true as const, value: { members: [], tasks: [] } })),
    startRun: vi.fn(() => Promise.resolve({ ok: true as const, value: {} })),
    consult: vi.fn(() => Promise.resolve({ ok: true as const, value: {} })),
    approve: vi.fn(() => Promise.resolve({ ok: true as const, value: {} })),
    getRun: vi.fn(() => Promise.resolve({ ok: true as const, value: {} })),
  })
  ctx.provide('sessions', {
    list: { getSnapshot: () => ({ current: SESSION }), subscribe: () => () => {} },
  })
  ctx.provide('conversation', {
    input: {
      for: (_scope: unknown) => ({
        state: { getSnapshot: () => ({ draft: '' }) },
        setDraft: vi.fn(),
      }),
    },
  })
  ctx.provide('uiWorkspace', {})
  ctx.provide('locale', new LocaleRuntime(ctx))
  await ctx.plugin(SlotRegistry).await()
  ctx.slots.register({
    name: 'root',
    children: {
      'sidebar.footer.action': { kind: 'list', scope: 'root' },
      'conversation.input.left': { kind: 'list', scope: 'root' },
    },
  } as never, () => null)
  if (options.registrationFailure === true) {
    vi.spyOn(ctx.slots, 'inject').mockImplementationOnce(() => { throw new Error('slot registration failed') })
  }
  const fiber = options.registrationFailure === true
    ? ctx.plugin({ apply() {} })
    : ctx.plugin({ inject: [...inject], apply: clientCtx => mountExpertTeamUi(clientCtx, REMOTE) })
  const activation: Promise<unknown> = options.registrationFailure === true
    ? mountExpertTeamUi(ctx, REMOTE).catch((error: unknown) => error)
    : fiber.await()
  if (options.registrationFailure !== true) {
    await activation
  } else {
    await fiber.await()
  }
  const card = () => ctx.slots.entries('sidebar.footer.action')
    .find(candidate => candidate.component === ExpertTeamCard)
  const chip = () => ctx.slots.entries('conversation.input.left')
    .find(candidate => candidate.component === ExpertSelectionChip)
  return { ctx, fiber, activation, remote, card, chip }
}

describe('ui-expert-team browser plugin', () => {
  it('registers the NS dictionary and both disposable seats', async () => {
    const b = await bench()
    expect(inject).toEqual(['remote', 'slots', 'locale'])
    expect(b.card()).toMatchObject({
      options: { id: 'expert-team', order: 20 },
      locale: NS,
    })
    expect(b.chip()).toMatchObject({
      options: { id: 'expert-selection', order: -20 },
      locale: NS,
    })
    const capability = () => null
    const disposeTab = b.ctx.slots.register({
      name: 'capabilities.center.tab', key: 'library',
    }, capability)
    expect(b.ctx.slots.entries('capabilities.center.tab')).toHaveLength(1)
    expect(b.remote.mount).toHaveBeenCalledOnce()
    expect(b.remote.mount).toHaveBeenCalledWith(REMOTE)
    b.ctx.locale.setLocale('zh')
    expect(b.ctx.locale.bind(NS)('trigger.label', {})).toBe(zh['trigger.label'])

    await b.fiber.dispose()
    disposeTab()
    expect(b.card()).toBeUndefined()
    expect(b.chip()).toBeUndefined()
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
