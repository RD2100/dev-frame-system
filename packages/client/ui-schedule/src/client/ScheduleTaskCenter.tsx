import { useState, type ReactNode } from 'react'
import type { SessionListState, SessionSummary } from '@deepseek-ai/dsh-api-session-controller/client'
import type { ClientRemote, SessionId } from '@deepseek-ai/dsh-api-remotes/client'
import type { ScheduleHistoryEntry, ScheduleId, ScheduleRecord, ScheduleTemplate } from '@deepseek-ai/dsh-schedule/client'
import type { InjectFace, PropsLocale, PropsRuntime, TranslateNS } from '@deepseek-ai/dsh-client-ui-slots'
import { NS } from './locales.ts'
import css from './ScheduleTaskCenter.module.css'

/** Props for the root settings task-center section. */
export type ScheduleTaskCenterProps =
  PropsRuntime<'settings.section'> & PropsLocale<typeof NS> & InjectFace<{ readonly schedule: ClientRemote['schedule'] }>

interface ActiveRow {
  readonly sessionId: SessionId
  readonly sessionTitle: string
  readonly record: ScheduleRecord
}

interface HistoryRow {
  readonly sessionId: SessionId
  readonly sessionTitle: string
  readonly entry: ScheduleHistoryEntry
}

const EMPTY_RECORDS: readonly ScheduleRecord[] = []
const EMPTY_HISTORY: readonly ScheduleHistoryEntry[] = []

// Keep browser presentation metadata local to this feature. Runtime imports from
// another feature package would create a cross-plugin client bundle edge.
const SCHEDULE_TEMPLATES: readonly ScheduleTemplate[] = Object.freeze([
  Object.freeze({
    id: 'follow-up',
    label: 'Follow up',
    description: 'One reminder after one hour.',
    rule: Object.freeze({ afterSeconds: 3_600 }),
  }),
  Object.freeze({
    id: 'daily-check',
    label: 'Daily check',
    description: 'Repeat every 24 hours.',
    rule: Object.freeze({ everySeconds: 86_400 }),
  }),
])

function statusLabel(record: ScheduleRecord, now: number, t: TranslateNS<typeof NS>): string {
  if (record.paused) return t('status.paused')
  return Date.parse(record.scheduledAt) <= now
    ? t('status.overdue')
    : t('status.scheduled')
}

function operationLabel(
  operation: ScheduleHistoryEntry['operation'],
  t: TranslateNS<typeof NS>,
): string {
  return t(`center.operation.${operation}` as const)
}

function resultLabel(entry: ScheduleHistoryEntry, t: TranslateNS<typeof NS>): string | undefined {
  return entry.result === undefined ? undefined : t(`center.outcome.${entry.result.outcome}` as const)
}

function sessionTitle(summary: SessionSummary | undefined, id: string): string {
  return summary?.displayTitle ?? summary?.title ?? id
}

type TemplateLocaleKey =
  | 'template.follow-up.label'
  | 'template.follow-up.description'
  | 'template.daily-check.label'
  | 'template.daily-check.description'

function templateText(templateId: string, field: 'label' | 'description'): TemplateLocaleKey {
  if (templateId === 'follow-up') return field === 'label' ? 'template.follow-up.label' : 'template.follow-up.description'
  return field === 'label' ? 'template.daily-check.label' : 'template.daily-check.description'
}

function collectRows(
  state: SessionListState,
): { readonly active: readonly ActiveRow[]; readonly history: readonly HistoryRow[] } {
  const active: ActiveRow[] = []
  const history: HistoryRow[] = []
  for (const id of state.ids) {
    const summary = state.byId[id]
    const title = sessionTitle(summary, id)
    for (const record of summary?.projectionValues?.schedule ?? EMPTY_RECORDS) {
      active.push({ sessionId: id, sessionTitle: title, record })
    }
    for (const entry of summary?.projectionValues?.scheduleHistory ?? EMPTY_HISTORY) {
      history.push({ sessionId: id, sessionTitle: title, entry })
    }
  }
  return { active, history }
}

type ScheduleAction = 'pause' | 'resume' | 'run' | 'delete'

/** Settings task center backed by host Session projections and Schedule Remotes. */
export function ScheduleTaskCenter({ useSessions, schedule, t }: ScheduleTaskCenterProps) {
  const rows = collectRows(useSessions(state => state))
  const now = Date.now()
  const [pending, setPending] = useState<string | undefined>()
  const [actionError, setActionError] = useState(false)

  const runAction = async (action: ScheduleAction, sessionId: SessionId, id: ScheduleId): Promise<void> => {
    const key = `${sessionId}:${id}:${action}`
    setPending(key)
    setActionError(false)
    try {
      const result = await schedule[action]({ sessionId, id })
      if (!result.ok) throw new Error(result.error.message)
    } catch {
      setActionError(true)
    } finally {
      setPending(current => current === key ? undefined : current)
    }
  }

  const actionButton = (action: ScheduleAction, sessionId: SessionId, id: ScheduleId): ReactNode => {
    const key = `${sessionId}:${id}:${action}`
    const label = t(`center.action.${action}` as const)
    return (
      <button
        type="button"
        className={css.actionButton}
        data-schedule-action={action}
        disabled={pending !== undefined}
        aria-label={label}
        onClick={() => { void runAction(action, sessionId, id) }}
      >
        {pending === key ? t('center.working') : label}
      </button>
    )
  }

  return (
    <section className={css.section} aria-labelledby="schedule-center-title">
      <h2 id="schedule-center-title" className={css.title}>{t('center.title')}</h2>
      <p className={css.description}>{t('center.description')}</p>
      {actionError ? <p className={css.actionError} role="alert">{t('center.actionError')}</p> : null}
      <section className={css.group} aria-labelledby="schedule-center-templates">
        <h3 id="schedule-center-templates" className={css.heading}>{t('center.templates')}</h3>
        <ul className={css.list}>
          {SCHEDULE_TEMPLATES.map(template => (
            <li key={template.id} className={css.row}>
              <div className={css.rowHeader}>
                <strong>{t(templateText(template.id, 'label'))}</strong>
                <span>{template.id}</span>
              </div>
              <div className={css.metadata}>
                <span>{t(templateText(template.id, 'description'))}</span>
              </div>
            </li>
          ))}
        </ul>
      </section>
      <section className={css.group} aria-labelledby="schedule-center-active">
        <h3 id="schedule-center-active" className={css.heading}>{t('center.active')}</h3>
        {rows.active.length === 0
          ? <p className={css.empty}>{t('center.empty')}</p>
          : (
            <ul className={css.list}>
              {rows.active.map(({ sessionId, sessionTitle, record }) => (
                <li key={`${sessionId}:${record.id}`} className={css.row}>
                  <div className={css.rowHeader}>
                    <strong>{record.prompt}</strong>
                    <span>{statusLabel(record, now, t)}</span>
                  </div>
                  <div className={css.metadata}>
                    <span>{sessionTitle}</span>
                    <span>{record.kind}</span>
                    <time dateTime={record.scheduledAt}>{record.scheduledAt}</time>
                  </div>
                  <div className={css.actions}>
                    {actionButton(record.paused ? 'resume' : 'pause', sessionId, record.id)}
                    {actionButton('run', sessionId, record.id)}
                    {actionButton('delete', sessionId, record.id)}
                  </div>
                </li>
              ))}
            </ul>
          )}
      </section>
      <section className={css.group} aria-labelledby="schedule-center-history">
        <h3 id="schedule-center-history" className={css.heading}>{t('center.history')}</h3>
        {rows.history.length === 0
          ? <p className={css.empty}>{t('center.historyEmpty')}</p>
          : (
            <ul className={css.list}>
              {rows.history.map(({ sessionId, sessionTitle, entry }, index) => (
                <li key={`${sessionId}:${entry.id}:${entry.occurredAt}:${index}`} className={css.row}>
                  <div className={css.rowHeader}>
                    <strong>{operationLabel(entry.operation, t)}{resultLabel(entry, t) === undefined ? '' : ` · ${resultLabel(entry, t)}`}</strong>
                    <time dateTime={entry.occurredAt}>{entry.occurredAt}</time>
                  </div>
                  <div className={css.metadata}>
                    <span>{sessionTitle}</span>
                    <span>{entry.id}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
      </section>
    </section>
  )
}
