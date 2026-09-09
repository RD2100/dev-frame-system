/**
 * Source-safe Shadow entry browser registration and Remote mount lifecycle.
 * The generated `shadow` Remote contribution mounts beside the shared
 * assembly, and the card registers into the sidebar footer-action seat the
 * shell stacks above Settings.
 */

import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { TypertRemoteContribution } from '@deepseek-ai/dsh-typert-protocol'
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import { ShadowStatusController } from './shadow-store.ts'
import { ShadowCard } from './ShadowCard.tsx'
import type { ShadowCardFace } from './slots.ts'
import { en, NS, zh } from './locales.ts'

/** Required browser services for RPC, slots, and localized copy. */
export const inject = ['remote', 'slots', 'locale']

function registerUi(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'client-ui-shadow-entry: dictionaries')
  const controller = new ShadowStatusController(async () => await ctx.remote.shadow.readStatus())

  const face: ShadowCardFace = {
    hooks: { status: controller.store },
    onRefresh: () => { void controller.refresh() },
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
  const ui = ctx.inject(['remote.shadow', 'slots', 'locale'], registerUi)
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
