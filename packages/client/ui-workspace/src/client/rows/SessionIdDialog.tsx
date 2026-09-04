import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { IconCheckOutline16, IconCopyOutline16, Modal, writeClipboard } from '@deepseek-ai/dsh-client-ui-primitives'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type { WorkspaceBrowserProps } from '../contract/slots.ts'
import css from './SessionIdDialog.module.css'

/** The browser root's locale seat, shared with the row components. */
type DialogTranslate = WorkspaceBrowserProps['t']

/** How long the copied confirmation stays before returning to idle, in ms. */
const COPIED_FEEDBACK_MS = 1_200

/** Write outcomes the dialog distinguishes; a refused write never reads as success. */
type WriteState = 'idle' | 'copied' | 'failed'

/** Props of the session-ID dialog opened from a session row's actions menu. */
export type SessionIdDialogProps = {
  /** The row session's durable id, shown verbatim and never regenerated. */
  sessionId: SessionId
  /** Close request from the dialog's own chrome (Escape, mask, close button). */
  onClose: () => void
  /** The browser root's locale seat. */
  t: DialogTranslate
}

/**
 * Small dialog showing one session's full id with copy affordances. Both the
 * id text itself and the explicit copy button write the complete value through
 * the shared clipboard helper; the id renders as a button so keyboard and
 * screen-reader users get the same one-activation copy. A refused write shows
 * an explicit failure message instead of a success state.
 * @param props - the row session id, close callback, and locale seat.
 * @returns the modal dialog tree.
 */
export function SessionIdDialog({ sessionId, onClose, t }: SessionIdDialogProps) {
  const [write, setWrite] = useState<WriteState>('idle')
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => {
    if (resetTimer.current !== null) clearTimeout(resetTimer.current)
  }, [])

  const copy = (): void => {
    if (resetTimer.current !== null) clearTimeout(resetTimer.current)
    void writeClipboard(String(sessionId)).then((ok) => {
      setWrite(ok ? 'copied' : 'failed')
      if (ok) resetTimer.current = setTimeout(() => { setWrite('idle') }, COPIED_FEEDBACK_MS)
    })
  }

  return (
    <Modal open onClose={onClose} title={t('sessionId.title')} description={t('sessionId.description')} closeLabel={t('sessionId.close')}>
      <div className={css.root}>
        <button type="button" className={css.id} aria-label={t('sessionId.copy')} onClick={copy}>
          {sessionId}
        </button>
        <div className={css.copyRow}>
          <button type="button" className={css.copy} autoFocus aria-label={t('sessionId.copy')} onClick={copy}>
            {write === 'copied' ? <IconCheckOutline16 size={14} /> : <IconCopyOutline16 size={14} />}
            {t('sessionId.copy')}
          </button>
          <span className={clsx(css.status, write === 'failed' && css.statusFailed)} role="status">
            {write === 'copied' ? t('sessionId.copied') : write === 'failed' ? t('sessionId.copyFailed') : undefined}
          </span>
        </div>
      </div>
    </Modal>
  )
}
