/**
 * The resident sidebar-foot Shadow entry: a trigger row (icon, label, status
 * dot) above Settings, plus the large centered dialog it opens. The dialog is
 * the human's global Shadow surface and leads with the conversation: the full
 * message stream with the designated Shadow (tail load on open, incremental
 * polling while open and online, one post verb) fills the dialog above a
 * bottom composer. A view toggle switches to the management pane: the honest
 * phase facts, the authorized roots, the open-project form, and the
 * multi-project list with per-project send and release actions. Every action
 * runs through the injected write verbs and shows the service's success or
 * failure verbatim.
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { IconBranchOutline16, useDismissOnOutsidePointer } from '@deepseek-ai/dsh-client-ui-primitives'
import type { InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type { ShadowCardFace, ShadowWorkspaceId } from './slots.ts'
import {
  presentShadowStatus,
  presentWriteOutcome,
  type ShadowPhase,
  type ShadowWriteKind,
  type ShadowWriteOutcome,
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
  disabled: 'detail.disabled',
  configured: 'detail.configured',
}

/** Compact wall-clock label for one conversation row timestamp. */
function formatChatTime(at: string): string {
  return new Date(at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/** Render the resident Shadow entry card. */
export function ShadowCard({
  wide, useStatus, useConversation, onRefresh, onOpenConversation, onLoadConversation, onPollConversation,
  onOpenProject, onSendToController, onReleaseProject, onPostMessage, t,
}: ShadowCardProps) {
  const status = useStatus(status => status)
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const [view, setView] = useState<'chat' | 'projects'>('chat')
  const [path, setPath] = useState('')
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<string>()
  const [outcome, setOutcome] = useState<ShadowWriteOutcome>({ state: 'idle' })
  const chat = useConversation(snapshot => snapshot)
  const [chatDraft, setChatDraft] = useState('')
  const [chatPending, setChatPending] = useState(false)
  const [chatError, setChatError] = useState<string>()
  const chatListRef = useRef<HTMLDivElement>(null)

  useDismissOnOutsidePointer(rootRef, open, setOpen)

  // One read on mount keeps the resident card honest without a click, and
  // every open re-reads so a long-lived page converges on the current facts.
  useEffect(() => { onRefresh() }, [onRefresh])
  useEffect(() => {
    if (open) onRefresh()
  }, [onRefresh, open])

  const model = presentShadowStatus(status)
  const write = presentWriteOutcome(outcome)
  const detail = PHASE_DETAILS[model.phase]
  const actionsLocked = busy !== undefined
  const actionable = model.phase === 'configured' || model.phase === 'online'

  /** Run one panel write: lock the actions, land the outcome, refresh and clear the draft on success. */
  const runWrite = (
    key: string,
    kind: ShadowWriteKind,
    action: () => Promise<{ ok: boolean; error?: { message: string } }>,
    onSuccess?: () => void,
  ): void => {
    setBusy(key)
    setOutcome({ state: 'busy', kind })
    void action().then((result) => {
      setBusy(undefined)
      if (result.ok) {
        setOutcome({ state: 'ok', kind })
        onRefresh()
        onSuccess?.()
      } else {
        /* v8 ignore next -- a Remote failure always carries an error message. */
        setOutcome({ state: 'failed', kind, message: result.error?.message ?? 'unknown error' })
      }
    })
  }

  const submitOpen = (): void => {
    const trimmed = path.trim()
    /* v8 ignore next -- the open button is disabled while the path is blank or a write is in flight. */
    if (trimmed.length === 0 || actionsLocked) return
    runWrite('open', 'open', async () => await onOpenProject(trimmed), () =>{  setPath('') })
  }

  const submitSend = (workspaceId: ShadowWorkspaceId): void => {
    const text = (drafts[workspaceId] ?? '').trim()
    if (text.length === 0 || actionsLocked) return
    runWrite(`send:${workspaceId}`, 'send', async () => await onSendToController(workspaceId, text), () =>{  setDrafts(drafts => ({ ...drafts, [workspaceId]: '' })) })
  }

  const submitRelease = (workspaceId: ShadowWorkspaceId): void => {
    /* v8 ignore next -- the release button is disabled while a write is in flight. */
    if (actionsLocked) return
    runWrite(`release:${workspaceId}`, 'release', async () => await onReleaseProject(workspaceId))
  }

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

  // While the dialog is open and the Shadow is online, load the tail once and
  // poll incrementally so replies arrive without a click.
  useEffect(() => {
    if (!open || model.phase !== 'online') return
    onLoadConversation()
    const timer = window.setInterval(() => { onPollConversation() }, 3000)
    return () => { window.clearInterval(timer) }
  }, [open, model.phase, onLoadConversation, onPollConversation])

  // Keep the newest row visible; the stream is the dialog's only inner scroller.
  useLayoutEffect(() => {
    const list = chatListRef.current
    if (list === null) return
    list.scrollTop = list.scrollHeight
  }, [chat.messages.length, view])

  return (
    <div ref={rootRef} className={clsx(css.layer, !wide && css.rail)}>
      {open && (
        <section className={css.panel} role="dialog" aria-label={t('panel.aria')} data-shadow-panel data-shadow-view={view}>
          <header className={css.header}>
            <h2 className={css.title}>{t('panel.title')}</h2>
            <p className={css.statusLine} data-shadow-status={model.phase}>
              <span className={css.dot} aria-hidden="true" />
              {t(PHASE_LABELS[model.phase])}
            </p>
            {actionable && (
              <button
                type="button"
                className={css.viewToggle}
                data-shadow-view-toggle
                aria-pressed={view === 'projects'}
                onClick={() => { setView(view === 'chat' ? 'projects' : 'chat') }}
              >
                {view === 'chat' ? t('panel.projectsTab') : t('chat.title')}
              </button>
            )}
            <button type="button" className={css.refreshButton} data-shadow-refresh aria-label={t('panel.refresh')} disabled={actionsLocked} onClick={() => { onRefresh() }}>
              {t('panel.refresh')}
            </button>
            <button type="button" className={css.closeButton} data-shadow-close aria-label={t('panel.close')} onClick={() => { setOpen(false) }}>
              ×
            </button>
          </header>
          <div className={css.body} data-shadow-body={view}>
            {model.error !== null && (
              <p className={css.readError} role="alert" data-shadow-error>{t('status.readFailed', { message: model.error })}</p>
            )}
            {detail !== undefined && <p className={css.note}>{t(detail)}</p>}
            {write !== undefined && (
              <p className={css.writeLine} role="status" aria-live="polite" data-shadow-write={write.tone}>
                {t(write.key, write.params)}
              </p>
            )}
            {actionable && (
              <dl className={css.facts}>
                <dt className={css.group}>{t('panel.session')}</dt>
                <dd className={css.mono} data-shadow-session>{model.shadowSessionId}</dd>
              </dl>
            )}
            {actionable && view === 'projects' && (
              <>
                <section className={css.section}>
                  <h3 className={css.group}>{t('panel.roots')}</h3>
                  {model.authorizedRoots.length === 0
                    ? <p className={css.note}>{t('panel.rootsEmpty')}</p>
                    : (
                      <>
                        <p className={css.note}>{t('panel.rootsHint')}</p>
                        <ul className={css.roots}>
                          {model.authorizedRoots.map(root => <li key={root} className={css.mono}>{root}</li>)}
                        </ul>
                      </>
                    )}
                </section>
                <section className={css.section}>
                  <h3 className={css.group}>{t('panel.openTitle')}</h3>
                  <div className={css.rowActions}>
                    <input
                      type="text"
                      className={css.rowInput}
                      value={path}
                      placeholder={t('open.pathPlaceholder')}
                      aria-label={t('open.inputAria')}
                      disabled={actionsLocked}
                      data-shadow-open-input
                      onChange={(event) => { setPath(event.currentTarget.value) }}
                    />
                    <button
                      type="button"
                      className={css.rowButton}
                      disabled={actionsLocked || path.trim().length === 0}
                      data-shadow-open
                      onClick={() => { submitOpen() }}
                    >
                      {t('open.submit')}
                    </button>
                  </div>
                </section>
                <section className={css.section}>
                  <h3 className={css.group}>{t('panel.projects')}</h3>
                  {model.projects.length === 0
                    ? <p className={css.note}>{t('panel.projectsEmpty')}</p>
                    : (
                      <ul className={css.projects}>
                        {model.projects.map(row => (
                          <li key={row.workspaceId} className={css.project} data-shadow-project>
                            <div className={css.projectHead}>
                              <span className={clsx(css.projectPath, css.mono)}>{row.canonicalPath}</span>
                              <span className={css.projectMeta}>
                                <span className={css.mono}>{row.workspaceId}</span>
                                <span>{t('project.revision', { revision: row.bindingRevision })}</span>
                                <span>{t(row.stateKey)}</span>
                              </span>
                            </div>
                            {row.stateKey === 'state.ready' && (
                              <div className={css.rowActions}>
                                <input
                                  type="text"
                                  className={css.rowInput}
                                  value={drafts[row.workspaceId] ?? ''}
                                  placeholder={t('send.placeholder')}
                                  aria-label={t('send.inputAria')}
                                  disabled={actionsLocked}
                                  data-shadow-send-input={row.workspaceId}
                                  onChange={(event) => {
                                    const { value } = event.currentTarget
                                    setDrafts(previous => ({ ...previous, [row.workspaceId]: value }))
                                  }}
                                />
                                <button
                                  type="button"
                                  className={css.rowButton}
                                  disabled={actionsLocked}
                                  data-shadow-send={row.workspaceId}
                                  onClick={() => { submitSend(row.workspaceId) }}
                                >
                                  {t('send.submit')}
                                </button>
                              </div>
                            )}
                            {row.stateKey !== 'state.stopping' && row.stateKey !== 'state.stopped' && (
                              <div className={css.rowActions}>
                                <button
                                  type="button"
                                  className={css.releaseButton}
                                  disabled={actionsLocked}
                                  data-shadow-release={row.workspaceId}
                                  onClick={() => { submitRelease(row.workspaceId) }}
                                >
                                  {t('release.button')}
                                </button>
                              </div>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                </section>
              </>
            )}
            {actionable && view === 'chat' && (
              <div className={css.chatPane} data-shadow-chat>
                {model.phase !== 'online'
                  ? <p className={css.note} data-shadow-chat-offline>{t('chat.offline')}</p>
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
                          className={css.rowButton}
                          disabled={chatPending || chatDraft.trim().length === 0}
                          data-shadow-chat-submit
                          onClick={() => { submitChat() }}
                        >
                          {t('chat.submit')}
                        </button>
                      </div>
                      {chatError !== undefined && (
                        <p className={css.writeLine} role="alert" data-shadow-chat-send-failed>{t('chat.sendFailed', { message: chatError })}</p>
                      )}
                    </>
                  )}
              </div>
            )}
          </div>
        </section>
      )}
      <button
        type="button"
        className={css.trigger}
        data-shadow-phase={model.phase}
        aria-label={t('trigger.aria')}
        onClick={() => { void onOpenConversation() }}
      >
        <IconBranchOutline16 size={wide ? 16 : 18} />
        {wide && <span className={css.triggerLabel}>{t('trigger.label')}</span>}
      </button>
      {wide && (
        <button
          type="button"
          className={css.manageButton}
          data-shadow-manage
          aria-label={t('trigger.manage')}
          aria-expanded={open}
          onClick={() => { setOpen(value => !value) }}
        >
          {t('trigger.manage')}
        </button>
      )}
    </div>
  )
}
