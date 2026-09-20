/**
 * The board view's header companion: one action that reopens the Shadow
 * conversation from the board tab. The tab strip already flips between chat
 * and board; this action lands on the durable conversation through the same
 * adopted-session path the resident card uses, so a board-focused human can
 * get back to dialogue without hunting the sidebar.
 */

import type { InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
// Type-only: pulls the ui-conversation SlotMap merge (the header actions).
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import type { BoardToggleFace } from './slots.ts'
import css from './BoardToggle.module.css'

/** Full props composed by the conversation.session.header.actions slot. */
export type BoardToggleProps =
  PropsRuntime<'conversation.session.header.actions'>
  & InjectFace<BoardToggleFace>
  & PropsLocale<'shadow'>

/** Render the reopen-conversation header action. */
export function BoardToggle(props: BoardToggleProps) {
  return (
    <button
      type="button"
      className={css.toggle}
      data-shadow-board-toggle
      onClick={() => { void props.onOpen() }}
    >
      {props.t('board.openConversation')}
    </button>
  )
}
