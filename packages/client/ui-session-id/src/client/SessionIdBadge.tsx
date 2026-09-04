import { useState } from 'react'
import { IconCheckOutline16, IconCopyOutline16, writeClipboard } from '@deepseek-ai/dsh-client-ui-primitives'
import type { PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import { NS } from './locales.ts'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import css from './SessionIdBadge.module.css'

/** Full props for the session-header SessionID badge. */
export type SessionIdBadgeProps =
  PropsRuntime<'conversation.session.header.utilities'> & PropsLocale<typeof NS>

/** How long the copy button shows its success icon, in ms. */
const COPIED_FEEDBACK_MS = 1000

/**
 * Session-header utility showing this session's id with a copy control. The
 * id text is wire data rendered verbatim; the CSS truncates long ids while
 * the button always copies the full value, and `user-select` lets a reader
 * select the id text directly. Renders nothing without a session id, so the
 * blank-session Hero stays clean.
 * @param props - runtime slot currency plus the namespace translator.
 * @returns the id chip and copy button, or null when no session is open.
 */
export function SessionIdBadge({ sessionId, t }: SessionIdBadgeProps) {
  const [copied, setCopied] = useState(false)
  if (sessionId === undefined) return null

  const copy = (): void => {
    if (copied) return
    void writeClipboard(String(sessionId)).then((ok) => {
      if (!ok) return
      setCopied(true)
      window.setTimeout(() => { setCopied(false) }, COPIED_FEEDBACK_MS)
    })
  }

  return (
    <span className={css.root} aria-label={t('badge.aria')}>
      <span className={css.id}>{sessionId}</span>
      <button
        type="button"
        className={css.copy}
        aria-label={t(copied ? 'copied' : 'copy')}
        title={t(copied ? 'copied' : 'copy')}
        onClick={copy}
      >
        {copied ? <IconCheckOutline16 size={12} /> : <IconCopyOutline16 size={12} />}
      </button>
    </span>
  )
}
