/** Browser registration for the Library Remote and its capability-center page. */

import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-session/client'
import type {} from '@deepseek-ai/dsh-client-ui-settings-plugin-inventory/client'
import type {} from '@deepseek-ai/dsh-client-ui-workspace/client'
import type {} from '@deepseek-ai/dsh-experimental-project-memory/remote'
import type { TypertRemoteContribution } from '@deepseek-ai/dsh-typert-protocol'
import { LibraryCard, type LibraryCardFace } from './LibraryCard.tsx'
import { en, NS, zh } from './locales.ts'
import { LibraryReferenceController } from './reference.ts'

/** Required browser services for RPC, slots, and localized copy. */
export const inject = ['remote', 'slots', 'locale']

function registerUi(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'client-ui-project-memory: dictionaries')
  const references = new LibraryReferenceController(ctx)
  const face: LibraryCardFace = {
    load: () => ctx.remote.library.view(),
    list: request => ctx.remote.library.list(request),
    read: request => ctx.remote.library.read(request),
    search: request => ctx.remote.library.search(request),
    reference: line => references.reference(line),
  }
  ctx.slots.inject('capabilities.center.tab', () => ctx.slots.register({
    name: 'capabilities.center.tab',
    key: 'library',
    locale: NS,
    inject: () => face,
  }, LibraryCard))
}

/**
 * Mount the generated Remote contribution and then register the Library tab.
 * @param ctx - Client context carrying Remote, slot, and locale services.
 * @param contribution - Generated Library Remote descriptors.
 * @returns disposer for both the tab registration and Remote namespace.
 */
export async function mountLibraryUi(
  ctx: ClientContext,
  contribution: TypertRemoteContribution,
): Promise<() => Promise<void>> {
  const disposeRemote = await ctx.remote.$mount(contribution)
  const ui = ctx.inject(
    ['remote.library', 'slots', 'locale', 'conversation', 'sessions'],
    registerUi,
  )
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
