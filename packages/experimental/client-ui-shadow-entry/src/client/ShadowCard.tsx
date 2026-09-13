/**
 * The resident sidebar-foot Shadow entry: a trigger row (icon, label, status
 * dot) above Settings, a chat dialog it opens, and a manage dropdown with
 * configuration items. The chat dialog is the human's conversation with the
 * Shadow: tail load on open, incremental polling while open and online, one
 * post verb. The manage dropdown holds read-only configuration views and
 * actions that do not belong in the primary chat surface.
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import {
  IconBranchOutline16,
  IconCloseOutline16,
  IconRefreshOutline16,
  IconSendOutline16,
  IconSettingsOutline16,
  useDismissOnOutsidePointer,
} from '@deepseek-ai/dsh-client-ui-primitives'
import type { InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type { ShadowCardFace } from './slots.ts'
import {
  presentShadowStatus,
  type ShadowPhase,
} from './shadow-presenter.ts'
import type { ShadowKey } from './locales.ts'
import css from './ShadowCard.module.css'

/** Full card props composed by the sidebar footer-action slot. */
export type ShadowCardProps =
  PropsRuntime<'sidebar.footer.action'> & InjectFace<ShadowCardFace> & PropsLocale<'shadow'>

/** Status-line copy per phase; the disabled phases share the not-enabled label. */
const PHASE_LABELS: Record<ShadowPhase, ShadowKey> = {
  loading: 'status.loading',
  error: 'status.error',
  unmounted: 'status.disabled',
  disabled: 'status.disabled',
  configured: 'status.configured',
  online: 'status.online',
}

/** Honest one-line detail per phase; `loading`, `error`, and `online` add none. */
const PHASE_DETAILS: Partial<Record<ShadowPhase, ShadowKey>> = {
  unmounted: 'detail.unmounted',
  disabled: 'status.disabled',
  configured: 'detail.configured',
}

/** Compact wall-clock label for one conversation row timestamp. */
function formatChatTime(at: string): string {
  return new Date(at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/** Render the resident Shadow entry card. */
export function ShadowCard({
  wide, useStatus, useConversation, onRefresh, onOpenConversation, onLoadConversation, onPollConversation,
  onPostMessage, t,
}: ShadowCardProps) {
  const status = useStatus(status => status)
  const [chatOpen, setChatOpen] = useState(false)
  const [manageOpen, setManageOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const manageRef = useRef<HTMLDivElement>(null)
  const chatRef = useRef<HTMLElement>(null)
  const [chatDraft, setChatDraft] = useState('')
  const [chatPending, setChatPending] = useState(false)
  const [chatError, setChatError] = useState<string>()
  const chat = useConversation(snapshot => snapshot)
  const chatListRef = useRef<HTMLDivElement>(null)

  useDismissOnOutsidePointer(rootRef, chatOpen, setChatOpen, chatRef)
  useDismissOnOutsidePointer(manageRef, manageOpen, setManageOpen)

  // One read on mount keeps the resident card honest without a click, and
  // every chat open re-reads so a long-lived page converges on the current facts.
  useEffect(() => { onRefresh() }, [onRefresh])
  useEffect(() => {
    if (chatOpen) onRefresh()
  }, [onRefresh, chatOpen])

  const model = presentShadowStatus(status)
  const detail = PHASE_DETAILS[model.phase]
  const actionable = model.phase === 'configured' || model.phase === 'online'

  /** Post one chat message: lock the chat input, then poll the surface after acceptance. */
  const submitChat = (): void => {
    const text = chatDraft.trim()
    if (text.length === 0 || chatPending) return
    setChatPending(true)
    void onPostMessage(text).then((result) => {
      setChatPending(false)
      if (result.ok) {
        setChatDraft('')
        setChatError(undefined)
        onPollConversation()
      } else {
        /* v8 ignore next -- a Remote failure always carries an error message. */
        setChatError(result.error.message)
      }
    })
  }

  // While the chat dialog is open and the Shadow is online, load the tail once
  // and poll incrementally so replies arrive without a click.
  useEffect(() => {
    if (!chatOpen || model.phase !== 'online') return
    onLoadConversation()
    const timer = window.setInterval(() => { onPollConversation() }, 3000)
    return () => { window.clearInterval(timer) }
  }, [chatOpen, model.phase, onLoadConversation, onPollConversation])

  // Keep the newest row visible; the stream is the dialog's only inner scroller.
  useLayoutEffect(() => {
    const list = chatListRef.current
    if (list === null) return
    list.scrollTop = list.scrollHeight
  }, [chat.messages.length])

  // Close the manage dropdown when the phase changes (status refresh may
  // invalidate the configuration the menu reflects).
  useEffect(() => { setManageOpen(false) }, [model.phase])

  return (
    <div ref={rootRef} className={clsx(css.layer, !wide && css.rail)}>
      {actionable && chatOpen && (
        <section ref={chatRef} className={css.chatDialog} role="dialog" aria-label={t('chat.title')} data-shadow-chat-dialog>
          <header className={css.chatHeader}>
            <div className={css.chatHeaderLeft}>
              <IconBranchOutline16 size={16} />
              <span className={css.chatTitle}>{t('chat.title')}</span>
            </div>
            <p className={css.chatStatusLine} data-shadow-status={model.phase}>
              <span className={css.dot} aria-hidden="true" />
              {t(PHASE_LABELS[model.phase])}
            </p>
            <button type="button" className={css.closeButton} data-shadow-chat-close aria-label={t('panel.close')} onClick={() => { setChatOpen(false) }}>
              <IconCloseOutline16 size={14} />
            </button>
          </header>
          <div className={css.chatBody} data-shadow-chat-body>
            {model.error !== null && (
              <p className={css.readError} role="alert" data-shadow-error>{t('status.readFailed', { message: model.error })}</p>
            )}
            {detail !== undefined && <p className={css.note}>{t(detail)}</p>}
            {actionable && model.shadowSessionId !== null && (
              <dl className={css.facts}>
                <dt className={css.group}>{t('panel.session')}</dt>
                <dd className={css.mono} data-shadow-session>{model.shadowSessionId}</dd>
              </dl>
            )}
            {model.phase !== 'online'
              ? <p className={css.chatOffline} data-shadow-chat-offline>{t('chat.offline')}</p>
              : (
                <>
                  {chat.error !== undefined && (
                    <p className={css.readError} role="alert" data-shadow-chat-read-error>{t('chat.readFailed', { message: chat.error })}</p>
                  )}
                  {chat.messages.length === 0 && chat.error === undefined
                    ? <p className={css.note} data-shadow-chat-empty>{t('chat.empty')}</p>
                    : (
                      <div className={css.chatList} ref={chatListRef} data-shadow-chat-list>
                        {chat.messages.map(row => (
                          <div key={row.seq} className={css.chatRow} data-shadow-chat-row={row.role}>
                            <span className={css.chatRole}>{row.role === 'user' ? t('chat.roleUser') : t('chat.roleShadow')}</span>
                            <span className={css.chatText}>{row.text}</span>
                            <time className={css.chatTime} dateTime={row.at}>{formatChatTime(row.at)}</time>
                          </div>
                        ))}
                      </div>
                    )}
                  {chatPending && <p className={css.note} data-shadow-chat-pending>{t('chat.pending')}</p>}
                  <div className={css.composer}>
                    <textarea
                      className={css.chatInput}
                      rows={2}
                      value={chatDraft}
                      placeholder={t('chat.placeholder')}
                      aria-label={t('chat.inputAria')}
                      disabled={chatPending}
                      data-shadow-chat-input
                      onChange={(event) => { setChatDraft(event.currentTarget.value) }}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && !event.shiftKey) {
                          event.preventDefault()
                          submitChat()
                        }
                      }}
                    />
                    <button
                      type="button"
                      className={css.sendButton}
                      disabled={chatPending || chatDraft.trim().length === 0}
                      data-shadow-chat-submit
                      onClick={() => { submitChat() }}
                    >
                      <IconSendOutline16 size={14} />
                    </button>
                  </div>
                  {chatError !== undefined && (
                    <p className={css.writeLine} role="alert" data-shadow-chat-send-failed>{t('chat.sendFailed', { message: chatError })}</p>
                  )}
                </>
              )}
          </div>
        </section>
      )}
      <div className={css.triggerRow}>
        <button
          type="button"
          className={css.trigger}
          data-shadow-phase={model.phase}
          data-shadow-error={model.error ?? undefined}
          aria-label={t('trigger.aria')}
          onClick={() => {
            void onOpenConversation()
            if (actionable) setChatOpen(value => !value)
          }}
          onPointerDown={(event) => { event.stopPropagation() }}
        >
          <IconBranchOutline16 size={wide ? 16 : 18} />
          {wide && <span className={css.triggerLabel}>{t('trigger.label')}</span>}
        </button>
        {!actionable && model.phase !== 'loading' && detail !== undefined && (
          <span className={css.triggerDetail} data-shadow-detail>{t(detail)}</span>
        )}
        {wide && (
          <div ref={manageRef} className={css.manageAnchor}>
            <button
              type="button"
              className={css.manageButton}
              data-shadow-manage
              aria-label={t('trigger.manage')}
              aria-expanded={manageOpen}
              onClick={() => { setManageOpen(value => !value) }}
            >
              <IconSettingsOutline16 size={14} />
            </button>
            {manageOpen && (
              <div className={css.manageMenu} role="menu" data-shadow-manage-menu>
                <div className={css.menuGroup}>
                  <div className={css.menuLabel} role="presentation">{t('manage.group.status')}</div>
                  <div className={css.menuItem} role="menuitem" tabIndex={0}>
                    <IconBranchOutline16 size={14} className={css.menuIcon} />
                    <span className={css.menuLabelText}>{t('manage.status.label')}</span>
                    <span className={css.menuValue}>{t(PHASE_LABELS[model.phase])}</span>
                  </div>
                  {actionable && (
                    <div className={css.menuItem} role="menuitem" tabIndex={0}>
                      <IconRefreshOutline16 size={14} className={css.menuIcon} />
                      <span className={css.menuLabelText}>{t('manage.session.label')}</span>
                      <span className={clsx(css.menuValue, css.mono)}>{model.shadowSessionId}</span>
                    </div>
                  )}
                </div>
                <div className={css.menuSeparator} role="separator" />
                <div className={css.menuGroup}>
                  <div className={css.menuLabel} role="presentation">{t('manage.group.roots')}</div>
                  {model.authorizedRoots.length === 0
                    ? <div className={css.menuItem} role="menuitem" tabIndex={-1}>{t('panel.rootsEmpty')}</div>
                    : model.authorizedRoots.map(root =>
                      <div key={root} className={css.menuItem} role="menuitem" tabIndex={0}>
                        <span className={clsx(css.menuValue, css.mono)}>{root}</span>
                      </div>,
                    )
                  }
                </div>
                <div className={css.menuSeparator} role="separator" />
                <div className={css.menuGroup}>
                  <div className={css.menuLabel} role="presentation">{t('manage.group.controller')}</div>
                  <div className={css.menuItem} role="menuitem" tabIndex={0}>
                    <span className={css.menuLabelText}>{t('manage.controller.profile')}</span>
                    <span className={css.menuValue}>standard</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
