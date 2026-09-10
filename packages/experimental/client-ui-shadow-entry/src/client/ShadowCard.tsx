/**
 * The resident sidebar-foot Shadow entry: a trigger row (icon, label, status
 * dot) above Settings, plus the fixed action panel it opens. The panel is the
 * human's global Shadow surface: an honest phase line, the authorized roots,
 * the multi-project list of open projects with per-project send and release
 * actions, and the open-project form. Every action runs through the injected
 * write verbs and shows the service's success or failure verbatim.
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

/** Render the resident Shadow entry card. */
export function ShadowCard({ wide, useStatus, onRefresh, onOpenProject, onSendToController, onReleaseProject, t }: ShadowCardProps) {
  const status = useStatus(status => status)
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const [anchor, setAnchor] = useState<{ left: number; bottom: number }>()
  const [path, setPath] = useState('')
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<string>()
  const [outcome, setOutcome] = useState<ShadowWriteOutcome>({ state: 'idle' })

  // The panel is fixed so the sidebar's overflow clip cannot cut it; the
  // offsets are measured from the trigger before paint and re-measured on
  // window resizes while open.
  useLayoutEffect(() => {
    if (!open) return
    const place = (): void => {
      const rect = /* v8 ignore next -- the ref is mounted before the panel can open */
        rootRef.current?.getBoundingClientRect()
      if (rect !== undefined) setAnchor({ left: rect.left, bottom: window.innerHeight - rect.top + 8 })
    }
    place()
    window.addEventListener('resize', place)
    return () => { window.removeEventListener('resize', place) }
  }, [open])

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
        setOutcome({ state: 'failed', kind, message: result.error?.message ?? String(result.error) })
      }
    })
  }

  const submitOpen = (): void => {
    const trimmed = path.trim()
    if (trimmed.length === 0 || actionsLocked) return
    runWrite('open', 'open', async () => await onOpenProject(trimmed), () => setPath(''))
  }

  const submitSend = (workspaceId: ShadowWorkspaceId): void => {
    const text = (drafts[workspaceId] ?? '').trim()
    if (text.length === 0 || actionsLocked) return
    runWrite(`send:${workspaceId}`, 'send', async () => await onSendToController(workspaceId, text), () => setDrafts(drafts => ({ ...drafts, [workspaceId]: '' })))
  }

  const submitRelease = (workspaceId: ShadowWorkspaceId): void => {
    if (actionsLocked) return
    runWrite(`release:${workspaceId}`, 'release', async () => await onReleaseProject(workspaceId))
  }

  return (
    <div ref={rootRef} className={clsx(css.layer, !wide && css.rail)}>
      {open && anchor !== undefined && (
        <section className={css.panel} style={anchor} role="dialog" aria-label={t('panel.aria')} data-shadow-panel>
          <header className={css.header}>
            <h2 className={css.title}>{t('panel.title')}</h2>
            <button type="button" className={css.refreshButton} data-shadow-refresh aria-label={t('panel.refresh')} disabled={actionsLocked} onClick={() => { onRefresh() }}>
              {t('panel.refresh')}
            </button>
          </header>
          <div className={css.body}>
            <p className={css.statusLine} data-shadow-status={model.phase}>
              <span className={css.dot} aria-hidden="true" />
              {t(PHASE_LABELS[model.phase])}
            </p>
            {detail !== undefined && <p className={css.note}>{t(detail)}</p>}
            {model.error !== null && (
              <p className={css.readError} role="alert" data-shadow-error>{t('status.readFailed', { message: model.error })}</p>
            )}
            {write !== undefined && (
              <p className={css.writeLine} role="status" aria-live="polite" data-shadow-write={write.tone}>
                {t(write.key, write.params)}
              </p>
            )}
            {(model.phase === 'configured' || model.phase === 'online') && (
              <>
                <dl className={css.facts}>
                  <dt className={css.group}>{t('panel.session')}</dt>
                  <dd className={css.mono} data-shadow-session>{model.shadowSessionId}</dd>
                </dl>
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
          </div>
        </section>
      )}
      <button
        type="button"
        className={css.trigger}
        data-shadow-phase={model.phase}
        aria-label={t('trigger.aria')}
        aria-expanded={open}
        onClick={() => { setOpen(value => !value) }}
      >
        <IconBranchOutline16 size={wide ? 16 : 18} />
        {wide && <span className={css.triggerLabel}>{t('trigger.label')}</span>}
      </button>
    </div>
  )
}
