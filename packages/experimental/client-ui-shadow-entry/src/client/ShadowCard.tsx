/**
 * The resident sidebar-foot Shadow entry: a trigger row (icon, label, status
 * dot) above Settings and a manage dropdown with read-only configuration
 * items. The trigger opens the Shadow's one permanent conversation — the
 * deployment's designated session — through the standard conversation
 * surface; the card renders no conversation of its own. The manage dropdown
 * holds the honest phase facts, the designated session, the authorized
 * roots, and the controller preset, portaled beside the sidebar because the
 * sidebar column clips overflow.
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties, RefObject } from 'react'
import { createPortal } from 'react-dom'
import clsx from 'clsx'
import {
  IconBranchOutline16,
  IconRefreshOutline16,
  IconSettingsOutline16,
  useDismissOnOutsidePointer,
} from '@deepseek-ai/dsh-client-ui-primitives'
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
  issue: 'status.issue',
}

/** Honest one-line detail per phase; `loading`, `error`, and `online` add none. */
const PHASE_DETAILS: Partial<Record<ShadowPhase, ShadowKey>> = {
  unmounted: 'detail.unmounted',
  disabled: 'status.disabled',
  configured: 'detail.configured',
  issue: 'detail.issue',
}

/** Viewport margin kept between the portaled menu and the window edges. */
const VIEWPORT_MARGIN = 12

/**
 * Fixed style for the manage dropdown portaled to document.body: right-aligned
 * to the manage button and opened above it — the button sits at the window's
 * bottom edge, so opening downward would leave the viewport — size-capped to
 * the space actually available. Repositions on window resize while open.
 */
function useAboveEndAnchorStyle(open: boolean, anchor: RefObject<HTMLElement | null>): CSSProperties | null {
  const [style, setStyle] = useState<CSSProperties | null>(null)
  useLayoutEffect(() => {
    if (!open) { setStyle(null); return }
    const place = (): void => {
      const rect = anchor.current?.getBoundingClientRect()
      if (rect === undefined) return
      const right = Math.max(window.innerWidth - rect.right, VIEWPORT_MARGIN)
      setStyle({
        position: 'fixed',
        right,
        bottom: window.innerHeight - rect.top + 4,
        maxWidth: Math.max(window.innerWidth - right - VIEWPORT_MARGIN, 200),
        maxHeight: Math.max(Math.min(window.innerHeight * 0.72, 480), 120),
      })
    }
    place()
    window.addEventListener('resize', place)
    return () => { window.removeEventListener('resize', place) }
  }, [open, anchor])
  return style
}

/** Render the resident Shadow entry card. */
export function ShadowCard({
  wide, useStatus, useSessions, onRefresh, onOpenConversation, t,
}: ShadowCardProps) {
  const status = useStatus(status => status)
  const currentSession = useSessions(state => state.current)
  const [manageOpen, setManageOpen] = useState(false)
  const manageButtonRef = useRef<HTMLButtonElement>(null)
  const manageMenuRef = useRef<HTMLDivElement>(null)

  useDismissOnOutsidePointer(manageButtonRef, manageOpen, setManageOpen, manageMenuRef)
  const manageMenuStyle = useAboveEndAnchorStyle(manageOpen, manageButtonRef)

  // One read on mount keeps the resident card honest without a click, and
  // every manage open re-reads so a long-lived page converges on the current
  // facts.
  useEffect(() => { onRefresh() }, [onRefresh])

  const model = presentShadowStatus(status)
  const detail = PHASE_DETAILS[model.phase]
  const actionable = model.phase === 'configured' || model.phase === 'online'
  // The designated conversation may already be the current session — the
  // trigger opened it earlier, or the human resumed it — so the click lands
  // on the same conversation with no visible change. Surface that fact on
  // the trigger instead of leaving the click feeling dead.
  const shadowCurrent = actionable
    && model.shadowSessionId !== null
    && currentSession === model.shadowSessionId

  // Close the manage dropdown when the phase changes (a refresh may
  // invalidate the configuration the menu reflects).
  useEffect(() => { setManageOpen(false) }, [model.phase])

  return (
    <div className={clsx(css.layer, !wide && css.rail)}>
      <div className={css.triggerRow}>
        <button
          type="button"
          className={css.trigger}
          data-shadow-phase={model.phase}
          data-shadow-error={model.error ?? undefined}
          data-shadow-active={shadowCurrent || undefined}
          aria-pressed={shadowCurrent}
          aria-label={t('trigger.aria')}
          onClick={() => {
            // Fail closed on a designation issue: opening the cwd-less
            // session would render as a fresh conversation, hiding the fault.
            if (model.phase !== 'issue') void onOpenConversation()
          }}
        >
          <IconBranchOutline16 size={wide ? 16 : 18} />
          {wide && <span className={css.triggerLabel}>{t('trigger.label')}</span>}
        </button>
        {detail !== undefined && (
          <span className={css.triggerDetail} data-shadow-detail>{t(detail)}</span>
        )}
        {wide && (
          <div className={css.manageAnchor}>
            <button
              ref={manageButtonRef}
              type="button"
              className={css.manageButton}
              data-shadow-manage
              aria-label={t('trigger.manage')}
              aria-expanded={manageOpen}
              onClick={() => {
                setManageOpen(value => !value)
                if (!manageOpen) onRefresh()
              }}
            >
              <IconSettingsOutline16 size={14} />
            </button>
            {manageOpen && createPortal(
              <div ref={manageMenuRef} className={css.manageMenu} style={manageMenuStyle ?? undefined} role="menu" data-shadow-manage-menu>
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
                    <span className={css.menuValue}>{t('manage.controller.value')}</span>
                  </div>
                </div>
              </div>,
              document.body,
            )}
          </div>
        )}
      </div>
    </div>
  )
}
