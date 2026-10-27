/** Browser registration for the expert-team Remote and sidebar Capability center. */

import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import type {} from '@deepseek-ai/dsh-api-session-controller/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-session/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type {} from '@deepseek-ai/dsh-client-ui-workspace/client'
import type {} from '@deepseek-ai/dsh-experimental-expert-team/remote'
import type { TypertRemoteContribution } from '@deepseek-ai/dsh-typert-protocol'
import { ExpertSelectionChip } from './ExpertSelectionChip.tsx'
import { ExpertTeamCard, type ExpertTeamCardFace } from './ExpertTeamCard.tsx'
import { en, NS, zh } from './locales.ts'
import { ExpertSelectionController } from './selection.ts'

/** Required browser services for RPC, slots, and localized copy. */
export const inject = ['remote', 'slots', 'locale']

function registerUi(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'client-ui-expert-team: dictionaries')
  const selection = new ExpertSelectionController(ctx)
  const face: ExpertTeamCardFace = {
    load: () => ctx.remote.expertTeam.view(),
    summon: (target, draft) => { selection.summon(target, draft) },
    startRun: request => ctx.remote.expertTeam.startRun(request),
    consult: request => ctx.remote.expertTeam.consult(request),
    approve: request => ctx.remote.expertTeam.approve(request),
    getRun: request => ctx.remote.expertTeam.getRun(request),
  }
  ctx.effect(() => {
    const stop = ctx.sessions.list.subscribe(() => { selection.reconcile() })
    selection.reconcile()
    return stop
  }, 'client-ui-expert-team: selected expert session handoff')
  ctx.slots.inject(
    'sidebar.footer.action',
    () => ctx.slots.register({
      name: 'sidebar.footer.action',
      id: 'expert-team',
      order: 20,
      locale: NS,
      children: { 'capabilities.center.tab': { kind: 'keyed', scope: 'root' } },
      inject: () => face,
    }, ExpertTeamCard),
  )
  ctx.slots.inject(
    'conversation.input.left',
    () => ctx.slots.register({
      name: 'conversation.input.left',
      id: 'expert-selection',
      order: -20,
      locale: NS,
      inject: () => selection.injected(),
    }, ExpertSelectionChip),
  )
}

/**
 * Mount the generated Remote contribution and then register the sidebar card.
 * @param ctx - Client context carrying Remote, slot, and locale services.
 * @param contribution - Generated expert-team Remote descriptors.
 * @returns disposer for both the card registration and Remote namespace.
 */
export async function mountExpertTeamUi(
  ctx: ClientContext,
  contribution: TypertRemoteContribution,
): Promise<() => Promise<void>> {
  const disposeRemote = await ctx.remote.$mount(contribution)
  const ui = ctx.inject(
    ['remote.expertTeam', 'slots', 'locale', 'conversation', 'sessions', 'uiWorkspace'],
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
