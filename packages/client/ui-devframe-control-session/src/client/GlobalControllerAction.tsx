import { useState } from 'react'
import type { SessionId, SessionListState } from '@deepseek-ai/dsh-client-runtime/client'
import type {
  PropsLocale, PropsRuntime, SnapshotSelectorHook,
} from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import {
  IconCopyOutline16, IconEllipsisOutline16, Menu, writeClipboard,
} from '@deepseek-ai/dsh-client-ui-primitives'
import { NS } from './locales.ts'
import type { GlobalControllerReadinessState } from './readiness.ts'
import css from './GlobalControllerAction.module.css'

const GLOBAL_SESSION_ID_PATTERN = /^devframe-global:[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/

function readinessSessionId(state: GlobalControllerReadinessState): SessionId | undefined {
  if (state.status !== 'ready' || !GLOBAL_SESSION_ID_PATTERN.test(state.sessionId)) return undefined
  return state.sessionId as SessionId
}

/** Props for the sidebar Global Controller entry. */
export type GlobalControllerActionProps =
  PropsRuntime<'sidebar.footer.action'>
  & PropsLocale<typeof NS>
  & {
    /** Read the current session catalog through the framework-bound hook. */
    useSessions: SnapshotSelectorHook<SessionListState>
    /** Open the existing Host-owned Global Controller session. */
    open: (sessionId: SessionId) => void
    /** Read the Host-owned readiness snapshot. */
    useReadiness: SnapshotSelectorHook<GlobalControllerReadinessState>
  }

/** Small robot mark for the dedicated Global Controller entry. */
function GlobalControllerIcon({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <path d="M8 2v1.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      <circle cx="8" cy="1.5" r=".75" fill="currentColor" />
      <rect x="2.5" y="4" width="11" height="9" rx="2.25" stroke="currentColor" strokeWidth="1.2" />
      <circle cx="5.75" cy="8" r="1" fill="currentColor" />
      <circle cx="10.25" cy="8" r="1" fill="currentColor" />
      <path d="M5.5 10.75h5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

/** Sidebar action that opens the existing profile-scoped Global Controller session. */
export function GlobalControllerAction({ wide, useSessions, useReadiness, open, t }: GlobalControllerActionProps) {
  const readiness = useReadiness(state => state)
  const readySessionId = readinessSessionId(readiness)
  const globalSessionId = useSessions(state => (
    readySessionId !== undefined && state.ids.includes(readySessionId)
      ? readySessionId
      : undefined
  ))
  const currentSessionId = useSessions(state => state.current)
  const ready = globalSessionId !== undefined
  const current = ready && currentSessionId === globalSessionId
  const [menuOpen, setMenuOpen] = useState(false)
  const action = (
    <button
      type="button"
      className={wide ? css.action : `${css.action} ${css.collapsed}`}
      aria-label={t('global.open')}
      aria-current={current ? 'page' : undefined}
      disabled={!ready}
      onClick={() => {
        if (globalSessionId !== undefined) open(globalSessionId)
      }}
    >
      <GlobalControllerIcon size={wide ? 16 : 18} />
      {wide && <span className={css.label}>{t('global.open')}</span>}
      {!ready && wide && <span className={css.status}>{t('global.unavailable')}</span>}
    </button>
  )
  return (
    <div className={wide ? css.row : css.railRow}>
      {action}
      {wide && ready && (
        <Menu
          open={menuOpen}
          onClose={() => { setMenuOpen(false) }}
          items={[{ id: 'copy-session-id', label: t('global.copySessionId'), icon: <IconCopyOutline16 /> }]}
          onSelect={(id) => {
            setMenuOpen(false)
            if (id === 'copy-session-id') void writeClipboard(globalSessionId)
          }}
          portal
          closeOnPointerLeave
          anchor={(
            <button
              type="button"
              className={css.menuButton}
              aria-label={t('global.actions')}
              onClick={(event) => { event.stopPropagation(); setMenuOpen(value => !value) }}
            >
              <IconEllipsisOutline16 />
            </button>
          )}
        />
      )}
    </div>
  )
}
