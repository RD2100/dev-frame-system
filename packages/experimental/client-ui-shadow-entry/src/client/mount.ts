/**
 * Source-safe Shadow entry browser registration and Remote mount lifecycle.
 * The generated `shadow` Remote contribution mounts beside the shared
 * assembly, and the card registers into the sidebar footer-action seat the
 * shell stacks above Settings.
 */

import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { TypertRemoteContribution } from '@deepseek-ai/dsh-typert-protocol'
import type { ISessions } from '@deepseek-ai/dsh-api-session-controller/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import type {} from '@deepseek-ai/dsh-api-session-controller/client'
import type {} from '@deepseek-ai/dsh-client-ui-session/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import { ShadowStatusController } from './shadow-store.ts'
import { ShadowCard } from './ShadowCard.tsx'
import type { ShadowCardFace } from './slots.ts'
import { en, NS, zh } from './locales.ts'

/** Required browser services for RPC, slots, localized copy, and the standard session domain. */
export const inject = ['remote', 'slots', 'locale', 'sessions']

function registerUi(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'client-ui-shadow-entry: dictionaries')
  // The Host and browser project references merge different `Context.sessions`
  // faces; the browser face is the contract used by this entry.
  // oxlint-disable-next-line typescript/no-unnecessary-type-assertion -- the project-reference compiler needs the explicit browser face.
  const sessions = ctx.sessions as unknown as ISessions
  // The designated conversation is a dedicated surface, not a browsable
  // session: every status read classifies its id as internal so the session
  // list never grows a row for it, and a redeployed Host that designates
  // another id moves the classification with it. A failed read keeps the last
  // classification rather than withdrawing it.
  let releaseDesignation: (() => void) | undefined
  const classifyDesignation = (designated: string | undefined): void => {
    if (designated === undefined) return
    releaseDesignation?.()
    try {
      releaseDesignation = sessions.markInternal(designated as SessionId)
    } catch {
      // The Desktop client's sessions face does not expose markInternal; the
      // designated session simply stays visible in the list.
    }
  }
  ctx.effect(() => () => { releaseDesignation?.() }, 'client-ui-shadow-entry: designated session classification')
  const controller = new ShadowStatusController(async () => {
    const result = await ctx.remote.shadow.readStatus()
    if (result.ok) classifyDesignation(result.value.shadowSessionId)
    return result
  })

  const face: ShadowCardFace = {
    hooks: { status: controller.store },
    onRefresh: () => { void controller.refresh() },
    // The Shadow is one permanent independent agent conversation: select its
    // designated Session so every trigger opens the same durable conversation
    // through the standard surface. The session is host-created at boot, so it
    // is normally already listed; a not-yet-listed id is adopted by refreshing
    // the Host-authoritative list, never through create() — an agent-created
    // session records no cwd and the create RPC would refuse to adopt it.
    onOpenConversation: async () => {
      const status = await ctx.remote.shadow.readStatus()
      // A designation issue means the session cannot render as history;
      // fail closed rather than opening a fresh-looking conversation.
      if (!status.ok || status.value.designIssue !== undefined) return
      const sessionId = status.value.shadowSessionId
      if (sessionId === undefined) return
      if (!sessions.list.getSnapshot().ids.includes(sessionId as SessionId)) {
        await sessions.refresh()
      }
      sessions.open(sessionId as SessionId)
    },
  }
  ctx.slots.inject(
    'sidebar.footer.action',
    () => ctx.slots.register({
      name: 'sidebar.footer.action',
      id: 'shadow-entry',
      order: 30,
      locale: NS,
      inject: () => face,
    }, ShadowCard),
  )
}

/**
 * Mount one generated Shadow Remote contribution, then register the card.
 * @param ctx - Client Context carrying Remote, slot, and locale services.
 * @param contribution - generated Shadow descriptors selected by the browser entry.
 * @returns disposer for both the card registration and the Remote namespace.
 */
export async function mountShadowEntryUi(
  ctx: ClientContext,
  contribution: TypertRemoteContribution,
): Promise<() => Promise<void>> {
  const disposeRemote = await ctx.remote.$mount(contribution)
  const ui = ctx.inject(['remote.shadow', 'slots', 'locale', 'sessions'], registerUi)
  try {
    await ui
  } catch (error) {
    await ui.dispose()
    await disposeRemote()
    throw error
  }
  return async () => {
    await ui.dispose()
    await disposeRemote()
  }
}
