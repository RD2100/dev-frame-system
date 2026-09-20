/** Selected-expert chip rendered in the blank Session composer. */

import type {} from '@deepseek-ai/dsh-api-session-controller/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import type {} from '@deepseek-ai/dsh-client-ui-session/client'
import type { InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import { IconAgentPresetOutline16, IconCloseOutline16 } from '@deepseek-ai/dsh-client-ui-primitives'
import { NS } from './locales.ts'
import type { ExpertSelectionInjected } from './selection.ts'
import css from './ExpertSelectionChip.module.css'

/** Full props composed by the session-scoped composer-left slot. */
export type ExpertSelectionChipProps =
  PropsRuntime<'conversation.input.left'>
  & InjectFace<ExpertSelectionInjected>
  & PropsLocale<typeof NS>

/** Render the selected expert only while the current Session is still blank. */
export function ExpertSelectionChip({
  sessionId, useSessions, useExpertSelection, clear, t,
}: ExpertSelectionChipProps) {
  const selection = useExpertSelection(snapshot => snapshot)
  const summary = useSessions(snapshot => snapshot.byId[sessionId])
  const target = selection.target
  if (target === null || selection.sessionId !== sessionId || summary?.blank !== true) return null

  const initial = Array.from(target.expertName.trim())[0] ?? '?'
  return (
    <button
      type="button"
      className={css.chip}
      title={t('selection.hint', { team: target.teamTitle, expert: target.expertName })}
      aria-label={t('selection.remove', { expert: target.expertName })}
      onClick={clear}
    >
      <span className={css.avatar} aria-hidden="true">
        {initial}
      </span>
      <IconAgentPresetOutline16 size={14} />
      <span className={css.name}>{target.expertName}</span>
      <IconCloseOutline16 size={12} />
    </button>
  )
}
