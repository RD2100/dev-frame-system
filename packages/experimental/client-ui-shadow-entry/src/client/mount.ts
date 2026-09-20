/**
 * Source-safe Shadow entry browser registration and Remote mount lifecycle.
 * The generated `shadow` Remote contribution mounts beside the shared
 * assembly, and the card registers into the sidebar footer-action seat the
 * shell stacks above Settings.
 */

import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { TypertRemoteContribution } from '@deepseek-ai/dsh-typert-protocol'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace/types'
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import type {} from '@deepseek-ai/dsh-api-session-controller/client'
import type {} from '@deepseek-ai/dsh-client-ui-session/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import { ShadowBoardController, ShadowStatusController } from './shadow-store.ts'
import { ShadowCard } from './ShadowCard.tsx'
import { BoardView } from './BoardView.tsx'
import { BoardToggle } from './BoardToggle.tsx'
import type { BoardToggleFace, BoardViewFace, ShadowCardFace } from './slots.ts'
import { en, NS, zh } from './locales.ts'

/** Required browser services for RPC, slots, localized copy, and the standard session domain. */
export const inject = ['remote', 'slots', 'locale', 'sessions']

function registerUi(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'client-ui-shadow-entry: dictionaries')
  // The Host and browser project references merge different `Context.sessions`
  // faces; the browser face is the contract used by this entry.
  const sessions = ctx.sessions
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

  // The Shadow is one permanent independent agent conversation: select its
  // designated Session so every trigger opens the same durable conversation
  // through the standard surface. The session is host-created at boot, so it
  // is normally already listed; a not-yet-listed id is adopted by refreshing
  // the Host-authoritative list, never through create() — an agent-created
  // session records no cwd and the create RPC would refuse to adopt it.
  const openShadowConversation = async (): Promise<void> => {
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
  }

  const boardController = new ShadowBoardController(async () => {
    return await ctx.remote.shadow.readBoard()
  })
  // Approve/reject target the single ready workspace binding; the v2 desktop
  // is single-workspace, so the first ready binding is the deployment's one.
  const readyWorkspaceId = async (): Promise<string | undefined> => {
    const state = boardController.store.getSnapshot()
    const ready = state.board?.bindings.find(binding => binding.state === 'ready')
    if (ready !== undefined) return ready.workspaceId
    await boardController.refresh()
    return boardController.store.getSnapshot().board?.bindings
      .find(binding => binding.state === 'ready')?.workspaceId
  }
  const boardVerbs = {
    onApprove: async (taskId: string): Promise<void> => {
      const workspaceId = await readyWorkspaceId()
      if (workspaceId === undefined) throw new Error('no ready workspace binding')
      const result = await ctx.remote.shadow.approveTask({ workspaceId: workspaceId as WorkspaceId, taskId })
      if (!result.ok) throw result.error
      void boardController.refresh()
    },
    onReject: async (taskId: string, reason: string): Promise<void> => {
      const workspaceId = await readyWorkspaceId()
      if (workspaceId === undefined) throw new Error('no ready workspace binding')
      const result = await ctx.remote.shadow.rejectTask({ workspaceId: workspaceId as WorkspaceId, taskId, reason })
      if (!result.ok) throw result.error
      void boardController.refresh()
    },
  }

  const face: ShadowCardFace = {
    hooks: { status: controller.store },
    onRefresh: () => { void controller.refresh() },
    onOpenConversation: openShadowConversation,
  }
  const boardFace = (): BoardViewFace => ({
    hooks: { board: boardController.store, status: controller.store },
    onRefresh: () => { void boardController.refresh() },
    ...boardVerbs,
  })
  const toggleFace = (): BoardToggleFace => ({ onOpen: openShadowConversation })
  const t = ctx.locale.bind(NS)
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
  ctx.slots.inject(
    'conversation.view',
    () => ctx.slots.register({
      name: 'conversation.view',
      id: 'board',
      order: 10,
      locale: NS,
      label: () => t('board.tab'),
      inject: boardFace,
    }, BoardView),
  )
  ctx.slots.inject(
    'conversation.session.header.actions',
    () => ctx.slots.register({
      name: 'conversation.session.header.actions',
      id: 'shadow-board-toggle',
      order: 10,
      locale: NS,
      inject: toggleFace,
    }, BoardToggle),
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
