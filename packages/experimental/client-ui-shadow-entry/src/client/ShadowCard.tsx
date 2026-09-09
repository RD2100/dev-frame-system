/**
 * The resident sidebar-foot Shadow entry: a trigger row (icon, label, status
 * dot) above Settings, plus the fixed status panel it opens. The panel shows
 * the honest phase — unmounted and disabled deployments read "Shadow is not
 * enabled" — and, when configured, the controller session, the authorized
 * roots, and the binding rows with workspace, path, and revision.
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { IconBranchOutline16, useDismissOnOutsidePointer } from '@deepseek-ai/dsh-client-ui-primitives'
import type { InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type { ShadowCardFace } from './slots.ts'
import { presentShadowStatus, type ShadowPhase } from './shadow-presenter.ts'
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
export function ShadowCard({ wide, useStatus, onRefresh, t }: ShadowCardProps) {
  const status = useStatus(status => status)
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const [anchor, setAnchor] = useState<{ left: number; bottom: number }>()

  // The panel is fixed so the sidebar's overflow clip cannot cut it; the
  // offsets are measured from the trigger before paint and re-measured on
  // window resizes while open.
  useLayoutEffect(() => {
    if (!open) return
    const place = (): void => {
      const rect = rootRef.current?.getBoundingClientRect()
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
  const detail = PHASE_DETAILS[model.phase]

  return (
    <div ref={rootRef} className={clsx(css.layer, !wide && css.rail)}>
      {open && anchor !== undefined && (
        <section className={css.panel} style={anchor} role="dialog" aria-label={t('panel.aria')} data-shadow-panel>
          <header className={css.header}>
            <h2 className={css.title}>{t('panel.title')}</h2>
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
                      <ul className={css.roots}>
                        {model.authorizedRoots.map(root => <li key={root} className={css.mono}>{root}</li>)}
                      </ul>
                    )}
                </section>
                <section className={css.section}>
                  <h3 className={css.group}>{t('panel.bindings')}</h3>
                  {model.bindings.length === 0
                    ? <p className={css.note}>{t('panel.bindingsEmpty')}</p>
                    : (
                      <ul className={css.bindings}>
                        {model.bindings.map(row => (
                          <li key={row.workspaceId} className={css.binding} data-shadow-binding>
                            <span className={clsx(css.bindingPath, css.mono)}>{row.canonicalPath}</span>
                            <span className={css.bindingMeta}>
                              <span className={css.mono}>{row.workspaceId}</span>
                              <span>{t('binding.revision', { revision: row.bindingRevision })}</span>
                              <span>{t(row.stateKey)}</span>
                            </span>
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
