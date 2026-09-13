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
import type { StoredEntry } from '@deepseek-ai/dsh-client-ui-slots'
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

async function bench(
  options: { registrationFailure?: boolean; readFailure?: boolean; sessionIdMissing?: boolean; sessionNotListed?: boolean } = {},
): Promise<{
  ctx: Context
  fiber: ReturnType<Context['plugin']>
  calls: string[]
  /** Internal-session classifications the plugin registered, in order. */
  internal: { marked: string[]; released: number }
  remote: RemoteStub
  entry: () => StoredEntry | undefined
}> {
  const ctx = new Context()
  const calls: string[] = []
  const internal = { marked: [] as string[], released: 0 }
  const remote = new RemoteStub(ctx)
  // The client never creates a Shadow session — the agent-created designated
  // session records no cwd, so the create RPC refuses to adopt it. Opening is
  // the only path, so this stub deliberately exposes no `create`.
  ctx.provide('sessions', {
    open: (id: string) => { calls.push(`sessions/open:${id}`) },
    list: { getSnapshot: () => ({ ids: options.sessionNotListed === true ? [] : ['session-shadow'] }) },
    refresh: async () => { calls.push('sessions/refresh') },
    markInternal: (id: string) => {
      internal.marked.push(id)
      return () => { internal.released += 1 }
    },
  })
  ctx.provide('remote.shadow', {
    readStatus: () => {
      calls.push('shadow/readStatus')
      return Promise.resolve(options.readFailure === true
        ? { ok: false as const, error: { code: 'gateway/internal', message: 'offline', details: {} } }
        : {
          ok: true as const,
          value: {
            mounted: true,
            shadowSessionId: options.sessionIdMissing === true ? undefined : 'session-shadow',
            shadowLive: true,
            authorizedRoots: ['D:/projects'],
            bindings: [],
          },
        })
    },
    readConversation: (request: { after?: number }) => {
      calls.push(`shadow/readConversation:${JSON.stringify(request)}`)
      return Promise.resolve({ ok: true as const, value: { messages: [], cursor: 0 } })
    },
    postMessage: (request: { text: string }) => {
      calls.push(`shadow/postMessage:${request.text}`)
      return Promise.resolve({ ok: true as const, value: { messageId: 'msg-chat-1' } })
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
  return { ctx, fiber, calls, internal, remote, entry }
}

describe('ui-shadow-entry browser plugin', () => {
  it('registers one disposable footer action with the status face and locale namespace', async () => {
    const b = await bench()
    expect(inject).toEqual(['remote', 'slots', 'locale', 'sessions'])
    expect(b.entry()).toMatchObject({
      options: { id: 'shadow-entry', order: 30 },
      locale: 'shadow',
    })
    expect(b.remote.mount).toHaveBeenCalledExactlyOnceWith(CONTRIBUTION)

    const face = (b.entry()!.inject as unknown as () => {
      hooks: { status: { getSnapshot: () => unknown }; conversation: { getSnapshot: () => unknown } }
      onRefresh: () => void
      onOpenConversation: () => Promise<void>
      onLoadConversation: () => void
      onPollConversation: () => void
      onPostMessage: (text: string) => Promise<{ ok: boolean }>
    })()
    expect(face.hooks.status.getSnapshot()).toEqual({ view: undefined, error: undefined })
    expect(face.hooks.conversation.getSnapshot()).toEqual({ messages: [], cursor: undefined, error: undefined })
    face.onRefresh()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(b.calls).toEqual(['shadow/readStatus'])
    expect(face.hooks.status.getSnapshot()).toMatchObject({ view: { shadowSessionId: 'session-shadow' } })

    // The conversation face loads the tail on demand and posts verbatim.
    face.onLoadConversation()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(face.hooks.conversation.getSnapshot()).toEqual({ messages: [], cursor: 0, error: undefined })
    // A poll continues from the cursor the tail load settled.
    face.onPollConversation()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(b.calls).toContain('shadow/readConversation:{"after":0}')
    await expect(face.onPostMessage('hello shadow')).resolves.toMatchObject({ ok: true })

    // Opening the conversation selects the Shadow's permanent designated
    // session — the same durable conversation every time — and never creates
    // one: an agent-created session records no cwd, so the create RPC would
    // refuse to adopt it (session/conflict).
    await face.onOpenConversation()
    expect(b.calls).not.toContain('sessions/create:session-shadow')
    expect(b.calls).toContain('sessions/open:session-shadow')

    expect(b.calls).toEqual([
      'shadow/readStatus',
      'shadow/readConversation:{}',
      'shadow/readConversation:{"after":0}',
      'shadow/postMessage:hello shadow',
      'shadow/readStatus',
      'sessions/open:session-shadow',
    ])

    await b.fiber.dispose()
    expect(b.entry()).toBeUndefined()
    expect(b.remote.disposeMount).toHaveBeenCalledOnce()
  })

  it('does not adopt a session when the status read fails or names no session', async () => {
    const failed = await bench({ readFailure: true })
    const failedFace = (failed.entry()!.inject as unknown as () => { onOpenConversation: () => Promise<void> })()
    await expect(failedFace.onOpenConversation()).resolves.toBeUndefined()
    expect(failed.calls).toEqual(['shadow/readStatus'])

    const unassigned = await bench({ sessionIdMissing: true })
    const unassignedFace = (unassigned.entry()!.inject as unknown as () => { onOpenConversation: () => Promise<void> })()
    await expect(unassignedFace.onOpenConversation()).resolves.toBeUndefined()
    expect(unassigned.calls).toEqual(['shadow/readStatus'])
  })

  it('opens the designated session without create when it is not listed yet', async () => {
    const b = await bench({ sessionNotListed: true })
    const face = (b.entry()!.inject as unknown as () => { onOpenConversation: () => Promise<void> })()
    await expect(face.onOpenConversation()).resolves.toBeUndefined()
    expect(b.calls).toEqual(['shadow/readStatus', 'sessions/refresh', 'sessions/open:session-shadow'])
  })

  it('classifies the designated session as internal so the session list grows no row', async () => {
    const b = await bench()
    const face = (b.entry()!.inject as unknown as () => { onRefresh: () => void })()
    expect(b.internal.marked).toEqual([])
    face.onRefresh()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(b.internal.marked).toEqual(['session-shadow'])
    expect(b.internal.released).toBe(0)

    // A later read re-registers the current designation instead of stacking one.
    face.onRefresh()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(b.internal.marked).toEqual(['session-shadow', 'session-shadow'])
    expect(b.internal.released).toBe(1)

    // Unmounting withdraws it: the classification belongs to this surface.
    await b.fiber.dispose()
    expect(b.internal.released).toBe(2)
  })

  it('classifies nothing when the status read fails or names no session', async () => {
    const failed = await bench({ readFailure: true })
    const failedFace = (failed.entry()!.inject as unknown as () => { onRefresh: () => void })()
    failedFace.onRefresh()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(failed.internal.marked).toEqual([])

    const unassigned = await bench({ sessionIdMissing: true })
    const unassignedFace = (unassigned.entry()!.inject as unknown as () => { onRefresh: () => void })()
    unassignedFace.onRefresh()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(unassigned.internal.marked).toEqual([])

    await failed.fiber.dispose()
    await unassigned.fiber.dispose()
    expect(failed.internal.released).toBe(0)
    expect(unassigned.internal.released).toBe(0)
  })

  it('unmounts the Remote contribution when later registration fails', async () => {
    const ctx = new Context()
    const remote = new RemoteStub(ctx)
    ctx.provide('sessions', { create: async () => 'session-created', open: () => {} })
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
