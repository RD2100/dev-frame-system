/**
 * The task board view: the six column projection of the Host board plus the
 * blocked/failed triage row. The board is a second conversation view beside
 * the Shadow chat, so a session can flip between dialogue and state. Cards
 * carry the single primary CTA (approve / re-approve) with the reject verb
 * beside it, honouring the start authority and the deployment's stalls.
 */

import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import type { InjectFace, PropsLocale } from '@deepseek-ai/dsh-client-ui-slots'
import type { ConvViewProps } from '@deepseek-ai/dsh-client-ui-conversation/client'
import type { BoardViewFace } from './slots.ts'
import {
  presentShadowBoard,
  presentShadowStatus,
  type BoardColumnId,
  type BoardTaskModel,
} from './shadow-presenter.ts'
import type { ShadowKey } from './locales.ts'
import css from './BoardView.module.css'

/** Full props composed by the conversation.view slot. */
export type BoardViewProps = ConvViewProps & InjectFace<BoardViewFace> & PropsLocale<'shadow'>

/** Column labels in reading order. */
const COLUMN_LABELS: Record<BoardColumnId, ShadowKey> = {
  backlog: 'board.column.backlog',
  toConfirm: 'board.column.toConfirm',
  building: 'board.column.building',
  toReview: 'board.column.toReview',
  submitted: 'board.column.submitted',
  done: 'board.column.done',
}

/** The board polls the Host snapshot and its own clock every five seconds. */
const POLL_MS = 5000

/** Render the six-column task board. */
export function BoardView({
  useBoard, useStatus, onRefresh, onApprove, onReject, t,
}: BoardViewProps) {
  const board = useBoard(state => state)
  const status = useStatus(state => state)
  const [now, setNow] = useState(() => Date.now())

  // One read on mount, then a poll: each tick refreshes the snapshot and
  // advances the clock so waiting marks and relative times stay honest.
  useEffect(() => {
    onRefresh()
    const id = setInterval(() => { onRefresh(); setNow(Date.now()) }, POLL_MS)
    return () => { clearInterval(id) }
  }, [onRefresh])

  const model = useMemo(() => presentShadowBoard(board, now), [board, now])
  // Self-check: the Shadow session is the board's control surface; when it is
  // unmounted or lacks a workspace, the board stays readable but states the
  // fact instead of pretending the pipeline is fully live.
  const selfCheck = presentShadowStatus(status).phase

  return (
    <div className={css.board} data-shadow-board>
      {model.phase === 'loading' && <div className={css.placeholder}>{t('board.loading')}</div>}
      {model.phase === 'error' && (
        <div className={css.placeholder} data-shadow-board-error>
          <div>{t('board.error')}</div>
          <div className={css.errorDetail}>{model.error}</div>
          <button type="button" className={css.retry} onClick={onRefresh}>{t('board.retry')}</button>
        </div>
      )}
      {model.phase === 'disabled' && <div className={css.placeholder}>{t('board.disabled')}</div>}
      {model.phase === 'board' && (
        <>
          {selfCheck === 'unmounted' && (
            <div className={css.selfCheck} data-shadow-board-selfcheck>{t('detail.unmounted')}</div>
          )}
          {selfCheck === 'issue' && (
            <div className={css.selfCheck} data-shadow-board-selfcheck>{t('detail.issue')}</div>
          )}
          <div className={css.columns}>
            {model.columns.map((column) => {
              const cards = model.tasks.filter(task => task.column === column)
              return (
                <section key={column} className={css.column} data-column={column}>
                  <header className={css.columnHeader}>
                    <span>{t(COLUMN_LABELS[column])}</span>
                    <span className={css.columnCount}>{cards.length}</span>
                  </header>
                  <div className={css.cards}>
                    {cards.map(task => (
                      <TaskCard
                        key={task.taskId}
                        task={task}
                        workspaceId={workspaceLabel(model)}
                        now={now}
                        onApprove={onApprove}
                        onReject={onReject}
                        t={t}
                      />
                    ))}
                  </div>
                </section>
              )
            })}
          </div>
          {model.triage.length > 0 && (
            <section className={css.triage} data-shadow-triage>
              <header className={css.columnHeader}>{t('board.triage.title')}</header>
              <div className={css.cards}>
                {model.triage.map(task => (
                  <TaskCard
                    key={task.taskId}
                    task={task}
                    workspaceId={workspaceLabel(model)}
                    now={now}
                    onApprove={onApprove}
                    onReject={onReject}
                    t={t}
                  />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}

/** Single-workspace v2: the workspace label is the first ready binding. */
function workspaceLabel(model: ReturnType<typeof presentShadowBoard>): string | null {
  const ready = model.bindings.find(binding => binding.state === 'ready')
  return ready === undefined ? null : ready.workspaceId
}

/** One card: title, workspace tag, live facts, and the approve/reject verbs. */
function TaskCard({
  task, workspaceId, now, onApprove, onReject, t,
}: {
  task: BoardTaskModel
  workspaceId: string | null
  now: number
  onApprove: (taskId: string) => Promise<void>
  onReject: (taskId: string, reason: string) => Promise<void>
  t: (key: ShadowKey) => string
}) {
  const [pending, setPending] = useState<'idle' | 'approving' | 'rejecting'>('idle')
  const [failed, setFailed] = useState(false)
  const [reason, setReason] = useState('')
  const [rejectOpen, setRejectOpen] = useState(false)
  const reapproving = task.state === 'blocked'

  const runApprove = async (): Promise<void> => {
    if (pending !== 'idle') return
    setPending('approving')
    setFailed(false)
    try {
      await onApprove(task.taskId)
      setPending('idle')
    } catch {
      setPending('idle')
      setFailed(true)
    }
  }
  const runReject = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault()
    if (pending !== 'idle' || reason.trim() === '') return
    setPending('rejecting')
    setFailed(false)
    try {
      await onReject(task.taskId, reason)
      setPending('idle')
      setReason('')
      setRejectOpen(false)
    } catch {
      setPending('idle')
      setFailed(true)
    }
  }

  const actionable = task.state === 'planned' || task.state === 'blocked'
  const approveDisabled = task.state === 'planned'
    ? !task.startReady || task.startReadyUnknown || pending !== 'idle'
    : pending !== 'idle'

  return (
    <article className={clsx(css.card, task.waiting && css.waiting)} data-state={task.state} data-waiting={task.waiting || undefined}>
      <header className={css.cardHeader}>
        <h3 className={css.cardTitle}>{task.title}</h3>
        {workspaceId !== null && <span className={css.workspaceTag}>{workspaceId}</span>}
      </header>
      {task.waiting && (
        <div className={css.waitingMark} data-waiting-mark>
          {t(task.waitingReason === 'long-planned' ? 'board.card.waiting.planned' : 'board.card.waiting.building')}
        </div>
      )}
      {(task.blockedReason !== undefined || task.nextAction !== undefined || task.wakeCondition !== undefined) && (
        <dl className={css.recovery}>
          {task.blockedReason !== undefined && (
            <div><dt>{t('board.card.blockedReason')}</dt><dd>{task.blockedReason}</dd></div>
          )}
          {task.nextAction !== undefined && (
            <div><dt>{t('board.card.nextAction')}</dt><dd>{task.nextAction}</dd></div>
          )}
          {task.wakeCondition !== undefined && (
            <div><dt>{t('board.card.wakeCondition')}</dt><dd>{task.wakeCondition}</dd></div>
          )}
        </dl>
      )}
      {task.state === 'developing' && (
        <div className={css.live} data-live>
          <span className={css.liveBranch} data-branch>{task.branch ?? '—'}</span>
          <span className={css.liveTime}>{t('board.card.updated')} {formatRelative(now, task.updatedAt, t)}</span>
        </div>
      )}
      <footer className={css.cardFooter}>
        <span className={css.cardTime}>{formatRelative(now, task.updatedAt, t)}</span>
        {actionable && (
          <div className={css.actions}>
            {task.state === 'planned' && !task.startReady && (
              <span className={css.notReady} data-not-ready>{t('board.card.notReady')}</span>
            )}
            {task.state === 'planned' && (
              <button
                type="button"
                className={css.approve}
                data-approve={task.taskId}
                disabled={approveDisabled}
                onClick={() => { void runApprove() }}
              >
                {t('board.card.approve')}
              </button>
            )}
            {task.state === 'blocked' && (
              <button
                type="button"
                className={css.approve}
                data-reapprove={task.taskId}
                disabled={approveDisabled}
                onClick={() => { void runApprove() }}
              >
                {t('board.card.reapprove')}
              </button>
            )}
            {task.state === 'planned' && !rejectOpen && (
              <button
                type="button"
                className={css.reject}
                data-reject={task.taskId}
                disabled={pending !== 'idle'}
                onClick={() => { setRejectOpen(true) }}
              >
                {t('board.card.reject')}
              </button>
            )}
          </div>
        )}
      </footer>
      {rejectOpen && (
        <form className={css.rejectForm} data-reject-form onSubmit={(event) => { void runReject(event) }}>
          <input
            className={css.rejectInput}
            value={reason}
            aria-label={t('board.card.rejectPlaceholder')}
            placeholder={t('board.card.rejectPlaceholder')}
            onChange={(event) => { setReason(event.target.value) }}
          />
          <button type="submit" className={css.approve} disabled={pending !== 'idle' || reason.trim() === ''}>
            {t('board.card.rejectConfirm')}
          </button>
          <button type="button" className={css.reject} onClick={() => { setRejectOpen(false); setReason('') }}>
            {t('board.card.rejectCancel')}
          </button>
        </form>
      )}
      {failed && (
        <div className={css.failed} data-failed>
          {t(reapproving ? 'board.card.reapproveFail' : 'board.card.approveFail')}
        </div>
      )}
    </article>
  )
}

/** Format one ISO timestamp relative to the clock. */
export function formatRelative(now: number, iso: string, t: (key: ShadowKey) => string): string {
  const updated = Date.parse(iso)
  if (!Number.isFinite(updated)) return t('time.unknown')
  const diff = now - updated
  if (diff < 60_000) return t('time.justNow')
  if (diff < 3_600_000) return t('time.minutesAgo').replace('{n}', String(Math.floor(diff / 60_000)))
  if (diff < 86_400_000) return t('time.hoursAgo').replace('{n}', String(Math.floor(diff / 3_600_000)))
  return t('time.daysAgo').replace('{n}', String(Math.floor(diff / 86_400_000)))
}
