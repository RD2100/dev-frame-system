/** Expert-center trigger and catalog surface for mounted expert teams. */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  Button,
  IconAgentPresetOutline16,
  IconCloseOutline16,
  IconLinkOutline16,
  IconQueueOutline14,
  IconRefreshOutline16,
  IconSearchOutline16,
  IconSendOutline14,
  IconSkillOutline16,
  Input,
  Modal,
  StateDot,
} from '@deepseek-ai/dsh-client-ui-primitives'
import type { RemoteResult } from '@deepseek-ai/dsh-api-remotes/client'
import type { InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type {
  ExpertTeamApproveRequest,
  ExpertTeamConsultRequest,
  ExpertTeamConsultResult,
  ExpertTeamRunDetail,
  ExpertTeamRunRequest,
  ExpertTeamSnapshot,
  ExpertTeamRunView,
  ExpertTeamStartRunRequest,
  ExpertTeamView,
  GateDecision,
} from '@deepseek-ai/dsh-experimental-expert-team/client'
import { NS, type ExpertTeamKey } from './locales.ts'
import type { ExpertSelectionTarget } from './selection.ts'
import css from './ExpertTeamCard.module.css'

/** Host status read and run actions injected by the browser mount. */
export interface ExpertTeamCardFace {
  /** Read mounted teams and live-process run history. */
  load: () => Promise<RemoteResult<ExpertTeamSnapshot>>
  /** Stage an expert in a new conversation and optionally seed its draft. */
  summon: (target: ExpertSelectionTarget, draft?: string) => void
  /** Start one pipeline or hierarchical run and return its first parked snapshot. */
  startRun: (request: ExpertTeamStartRunRequest) => Promise<RemoteResult<ExpertTeamRunDetail>>
  /** Consult one expert outside any pipeline and return the bounded answer. */
  consult: (request: ExpertTeamConsultRequest) => Promise<RemoteResult<ExpertTeamConsultResult>>
  /** Record a human gate decision and resume the run. */
  approve: (request: ExpertTeamApproveRequest) => Promise<RemoteResult<ExpertTeamRunDetail>>
  /** Read one live run's full snapshot, including per-phase gate state. */
  getRun: (request: ExpertTeamRunRequest) => Promise<RemoteResult<ExpertTeamRunDetail>>
}

/** Full props composed by the sidebar footer-action slot. */
export type ExpertTeamCardProps =
  PropsRuntime<'sidebar.footer.action'> & InjectFace<ExpertTeamCardFace> & PropsLocale<typeof NS>

type CenterTab = 'experts' | 'skills' | 'connectors'
type SortMode = 'recommended' | 'name'

interface ExpertRecord {
  readonly team: ExpertTeamView
  readonly expert: ExpertTeamView['experts'][number]
}

interface ExpertCenterProps {
  readonly loading: boolean
  readonly snapshot: ExpertTeamSnapshot | null
  readonly error: string | null
  readonly onClose: () => void
  readonly onRefresh: () => void
  readonly onSummon: (target: ExpertSelectionTarget, draft?: string) => void
  readonly onStartRun: ExpertTeamCardFace['startRun']
  readonly onConsult: ExpertTeamCardFace['consult']
  readonly onApprove: ExpertTeamCardFace['approve']
  readonly onGetRun: ExpertTeamCardFace['getRun']
  readonly t: ExpertTeamCardProps['t']
}

/** Map one run status to a localized key and a dot state. */
function runPresentation(status: ExpertTeamRunView['status']): {
  readonly label: ExpertTeamKey
  readonly dot: 'done' | 'warning' | 'ongoing' | 'error'
} {
  switch (status) {
    case 'running': return { label: 'run.running', dot: 'ongoing' }
    case 'waiting-approval': return { label: 'run.waiting-approval', dot: 'warning' }
    case 'completed': return { label: 'run.completed', dot: 'done' }
    case 'failed': return { label: 'run.failed', dot: 'error' }
    default: return assertNever(status)
  }
}

/** Keep the closed run-status union exhaustive when the protocol evolves. */
function assertNever(value: never): never {
  throw new Error(`unknown expert-team run status: ${String(value)}`)
}

/** Mode label stays data-driven so the card never emits product copy directly. */
function modeKey(mode: ExpertTeamView['mode']): ExpertTeamKey {
  return mode === 'hierarchical' ? 'mode.hierarchical' : 'mode.pipeline'
}

/** Flatten the Host catalog without creating another client-side data source. */
function flattenExperts(teams: readonly ExpertTeamView[]): ExpertRecord[] {
  return teams.flatMap(team => team.experts.map(expert => ({ team, expert })))
}

/** Build a stable catalog key from the pack-owned team and expert ids. */
function expertKey(record: ExpertRecord): string {
  return `${record.team.team}/${record.expert.id}`
}

/** Use the first displayed character as a deterministic avatar fallback. */
function expertInitial(name: string): string {
  return Array.from(name.trim())[0] ?? '?'
}

/** Convert a catalog record into the plain identity used by the session handoff. */
function expertTarget(record: ExpertRecord): ExpertSelectionTarget {
  return {
    teamId: record.team.team,
    teamTitle: record.team.title,
    expertId: record.expert.id,
    expertName: record.expert.name,
  }
}

/** Build the editable prompt that introduces a selected expert to the model. */
function summonPrompt(
  target: ExpertSelectionTarget,
  t: ExpertTeamCardProps['t'],
  suggestion?: string,
): string {
  const introduction = t('center.defaultPrompt', {
    team: target.teamTitle,
    expert: target.expertName,
    id: target.expertId,
  })
  return suggestion === undefined ? introduction : `${introduction}${suggestion}`
}

const SUGGESTION_KEYS = [
  'center.suggestion.1',
  'center.suggestion.2',
  'center.suggestion.3',
] as const satisfies readonly ExpertTeamKey[]

/** Render the resident expert-center trigger and catalog surface. */
export function ExpertTeamCard({ wide, load, summon, startRun, consult, approve, getRun, t }: ExpertTeamCardProps) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [snapshot, setSnapshot] = useState<ExpertTeamSnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const requestSequence = useRef(0)

  const refresh = useCallback(async (): Promise<void> => {
    const sequence = ++requestSequence.current
    setLoading(true)
    try {
      const result = await load()
      if (sequence !== requestSequence.current) return
      setLoading(false)
      if (result.ok) {
        setSnapshot(result.value)
        setError(null)
      } else {
        setError(result.error.message)
      }
    } catch (cause: unknown) {
      if (sequence !== requestSequence.current) return
      setLoading(false)
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }, [load])

  useEffect(() => {
    void refresh()
    return () => { requestSequence.current += 1 }
  }, [refresh])

  const activeRuns = snapshot?.runs.filter(run => run.status === 'running' || run.status === 'waiting-approval').length ?? 0

  return (
    <>
      <div className={css.root} data-expert-team-entry>
        <button
          type="button"
          className={css.trigger}
          data-expert-team-active={activeRuns > 0 || undefined}
          aria-expanded={open}
          aria-label={t('trigger.aria')}
          onClick={() => {
            setOpen(true)
            void refresh()
          }}
        >
          <IconAgentPresetOutline16 size={wide ? 16 : 18} />
          {wide && <span className={css.triggerLabel}>{t('trigger.label')}</span>}
          {wide && activeRuns > 0 && <span className={css.count}>{activeRuns}</span>}
        </button>
      </div>
      <Modal
        open={open}
        onClose={() => { setOpen(false) }}
        title={t('center.title')}
        headless
        className={css.centerModal as string}
      >
        <ExpertCenter
          loading={loading}
          snapshot={snapshot}
          error={error}
          onClose={() => { setOpen(false) }}
          onRefresh={() => { void refresh() }}
          onSummon={(target, draft) => {
            setOpen(false)
            summon(target, draft)
          }}
          onStartRun={startRun}
          onConsult={consult}
          onApprove={approve}
          onGetRun={getRun}
          t={t}
        />
      </Modal>
    </>
  )
}

/** Full-screen catalog surface rendered by the resident trigger. */
function ExpertCenter({
  loading,
  snapshot,
  error,
  onClose,
  onRefresh,
  onSummon,
  onStartRun,
  onConsult,
  onApprove,
  onGetRun,
  t,
}: ExpertCenterProps) {
  const [tab, setTab] = useState<CenterTab>('experts')
  const [query, setQuery] = useState('')
  const [teamFilter, setTeamFilter] = useState('all')
  const [sort, setSort] = useState<SortMode>('recommended')
  const [selectedKey, setSelectedKey] = useState<string | null>(null)

  const teams = snapshot?.teams ?? []
  const records = useMemo(() => flattenExperts(teams), [teams])
  const selected = useMemo(
    () => records.find(record => expertKey(record) === selectedKey),
    [records, selectedKey],
  )
  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase()
    const matches = records.filter((record) => {
      if (teamFilter !== 'all' && record.team.team !== teamFilter) return false
      if (needle === '') return true
      const searchable = [
        record.expert.name,
        record.expert.role,
        record.expert.id,
        record.team.title,
        record.team.team,
      ].join(' ').toLocaleLowerCase()
      return searchable.includes(needle)
    })
    if (sort === 'name') {
      return [...matches].sort((left, right) => left.expert.name.localeCompare(right.expert.name, 'zh-CN'))
    }
    return matches
  }, [query, records, sort, teamFilter])

  useEffect(() => {
    if (selectedKey !== null && selected === undefined) setSelectedKey(null)
  }, [selected, selectedKey])

  const runs = snapshot?.runs.slice(-6).reverse() ?? []

  return (
    <div className={css.center} data-expert-center>
      <header className={css.centerHeader}>
        <nav className={css.centerTabs} aria-label={t('center.navigation')} role="tablist">
          <CenterTabButton
            active={tab === 'experts'}
            icon={<IconAgentPresetOutline16 size={16} />}
            label={t('center.tab.experts')}
            onClick={() => { setTab('experts') }}
            t={t}
          />
          <CenterTabButton
            active={tab === 'skills'}
            icon={<IconSkillOutline16 size={16} />}
            label={t('center.tab.skills')}
            onClick={() => { setTab('skills') }}
            t={t}
          />
          <CenterTabButton
            active={tab === 'connectors'}
            icon={<IconLinkOutline16 size={16} />}
            label={t('center.tab.connectors')}
            onClick={() => { setTab('connectors') }}
            t={t}
          />
        </nav>
        <div className={css.headerActions}>
          {tab === 'experts' && (
            <Input
              className={css.search as string}
              icon={<IconSearchOutline16 size={16} />}
              aria-label={t('center.searchLabel')}
              placeholder={t('center.searchPlaceholder')}
              value={query}
              onChange={(event) => { setQuery(event.currentTarget.value) }}
            />
          )}
          <button type="button" className={css.closeButton} aria-label={t('center.close')} onClick={onClose}>
            <IconCloseOutline16 size={16} />
          </button>
        </div>
      </header>

      {tab === 'experts'
        ? (
          <>
            <div className={css.catalogToolbar}>
              <div className={css.filters} role="group" aria-label={t('center.teamFilter')}>
                <FilterButton active={teamFilter === 'all'} label={t('center.all')} onClick={() => { setTeamFilter('all') }} />
                {teams.map(team => (
                  <FilterButton
                    key={team.team}
                    active={teamFilter === team.team}
                    label={team.title}
                    onClick={() => { setTeamFilter(team.team) }}
                  />
                ))}
              </div>
              <div className={css.sorts} role="group" aria-label={t('center.sortLabel')}>
                <span className={css.sortLabel}>{t('center.sortLabel')}</span>
                <FilterButton active={sort === 'recommended'} label={t('center.sort.recommended')} onClick={() => { setSort('recommended') }} />
                <FilterButton active={sort === 'name'} label={t('center.sort.name')} onClick={() => { setSort('name') }} />
              </div>
            </div>
            {error !== null && <div className={css.error} role="alert">{t('center.readError', { message: error })}</div>}
            {snapshot === null && loading
              ? <div className={css.centerNotice}>{t('center.loading')}</div>
              : snapshot === null
                ? <div className={css.centerNotice}>{t('center.empty')}</div>
                : (
                  <>
                    <div className={css.catalogSummary}>
                      <div>
                        <h1>{t('center.catalogTitle')}</h1>
                        <p>{t('center.summary', { teams: teams.length, experts: records.length })}</p>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<IconRefreshOutline16 size={14} />}
                        aria-label={t('center.refresh')}
                        disabled={loading}
                        onClick={onRefresh}
                      >
                        {t('center.refreshLabel')}
                      </Button>
                    </div>
                    <div className={css.catalogBody} data-detail-open={selected !== undefined || undefined}>
                      <main className={css.catalogList} aria-label={t('center.catalogTitle')}>
                        {filtered.length === 0
                          ? <div className={css.centerNotice}>{t('center.noMatch')}</div>
                          : <div className={css.cardGrid}>
                            {filtered.map(record => (
                              <ExpertCard
                                key={expertKey(record)}
                                record={record}
                                selected={expertKey(record) === selectedKey}
                                onSelect={() => { setSelectedKey(expertKey(record)) }}
                                onSummon={() => {
                                  const target = expertTarget(record)
                                  onSummon(target, summonPrompt(target, t))
                                }}
                                t={t}
                              />
                            ))}
                          </div>}
                        <RunSection
                          runs={runs}
                          onRefresh={onRefresh}
                          onApprove={onApprove}
                          onGetRun={onGetRun}
                          loading={loading}
                          t={t}
                        />
                      </main>
                      {selected !== undefined && (
                        <ExpertDetail
                          record={selected}
                          onClose={() => { setSelectedKey(null) }}
                          onStartRun={onStartRun}
                          onConsult={onConsult}
                          t={t}
                        />
                      )}
                    </div>
                  </>
                )}
          </>
        )
        : <CatalogPlaceholder tab={tab} t={t} />}
    </div>
  )
}

function CenterTabButton({ active, icon, label, onClick, t }: {
  active: boolean
  icon: ReactNode
  label: string
  onClick: () => void
  t: ExpertTeamCardProps['t']
}) {
  return (
    <button
      type="button"
      className={css.centerTab}
      data-active={active || undefined}
      role="tab"
      aria-selected={active}
      aria-label={t('center.openTab', { tab: label })}
      onClick={onClick}
    >
      {icon}
      <span>{label}</span>
    </button>
  )
}

function FilterButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button type="button" className={css.filterButton} data-active={active || undefined} aria-pressed={active} onClick={onClick}>
      {label}
    </button>
  )
}

function ExpertCard({ record, selected, onSelect, onSummon, t }: {
  record: ExpertRecord
  selected: boolean
  onSelect: () => void
  onSummon: () => void
  t: ExpertTeamCardProps['t']
}) {
  const { expert, team } = record
  return (
    <article className={css.expertCard} data-selected={selected || undefined}>
      <button type="button" className={css.cardMain} onClick={onSelect}>
        <span className={css.cardTop}>
          <span className={css.avatar} aria-hidden="true">{expertInitial(expert.name)}</span>
          <span className={css.cardIdentity}>
            <strong>{expert.name}</strong>
            <small>{team.title}</small>
          </span>
        </span>
        <span className={css.cardRole}>{expert.role}</span>
        <span className={css.cardMeta}>{t('center.mode')}: {t(modeKey(team.mode))} · {team.phases.length} {t('phases')}</span>
        <span className={css.tagRow}>
          {expert.tools.slice(0, 4).map(tool => <span key={tool} className={css.tag}>{tool}</span>)}
        </span>
      </button>
      <Button
        className={css.summonButton}
        variant="primary"
        size="sm"
        icon={<IconSendOutline14 size={14} />}
        aria-label={t('center.summon')}
        onClick={onSummon}
      >
        {t('center.summon')}
      </Button>
    </article>
  )
}

type ConsultState =
  | { readonly status: 'idle' }
  | { readonly status: 'consulting' }
  | { readonly status: 'done'; readonly answer: string; readonly truncated: boolean }
  | { readonly status: 'error'; readonly message: string }

function ExpertDetail({ record, onClose, onStartRun, onConsult, t }: {
  record: ExpertRecord
  onClose: () => void
  onStartRun: ExpertTeamCardFace['startRun']
  onConsult: ExpertTeamCardFace['consult']
  t: ExpertTeamCardProps['t']
}) {
  const { expert, team } = record
  const phases = team.phases.filter(phase => phase.expert === expert.id)
  const [task, setTask] = useState('')
  const [starting, setStarting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [consult, setConsult] = useState<ConsultState>({ status: 'idle' })

  const input = task.trim()
  const canAct = input !== '' && !starting && consult.status !== 'consulting'

  const runStart = async (): Promise<void> => {
    if (input === '') return
    setStarting(true)
    setActionError(null)
    try {
      const result = await onStartRun({ teamId: team.team, input })
      if (!result.ok) {
        setActionError(result.error.message)
        return
      }
      setTask('')
    } catch (cause: unknown) {
      setActionError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setStarting(false)
    }
  }

  const askConsult = async (): Promise<void> => {
    if (input === '') return
    setConsult({ status: 'consulting' })
    setActionError(null)
    try {
      const result = await onConsult({ teamId: team.team, expertId: expert.id, question: input })
      if (result.ok) {
        setConsult({ status: 'done', answer: result.value.answer, truncated: result.value.truncated })
      } else {
        setConsult({ status: 'error', message: result.error.message })
      }
    } catch (cause: unknown) {
      setConsult({ status: 'error', message: cause instanceof Error ? cause.message : String(cause) })
    }
  }

  return (
    <aside className={css.detail} aria-label={t('center.detailLabel')}>
      <div className={css.detailHeader}>
        <span>{t('center.detailLabel')}</span>
        <button type="button" className={css.detailClose} aria-label={t('center.closeDetail')} onClick={onClose}>
          <IconCloseOutline16 size={14} />
        </button>
      </div>
      <div className={css.detailHero}>
        <span className={css.detailAvatar} aria-hidden="true">{expertInitial(expert.name)}</span>
        <h2>{expert.name}</h2>
        <p>{expert.role}</p>
      </div>
      <div className={css.detailAction}>
        <Input
          className={css.taskInput as string}
          aria-label={t('center.taskLabel')}
          placeholder={t('center.taskPlaceholder')}
          value={task}
          onChange={(event) => { setTask(event.currentTarget.value) }}
        />
        <div className={css.detailActions}>
          <Button
            variant="primary"
            size="sm"
            icon={<IconQueueOutline14 size={14} />}
            disabled={!canAct}
            aria-label={t('center.startRun')}
            onClick={() => { void runStart() }}
          >
            {t('center.startRun')}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={<IconSendOutline14 size={14} />}
            disabled={!canAct}
            aria-label={t('center.summonExpert')}
            onClick={() => { void askConsult() }}
          >
            {t('center.summonExpert')}
          </Button>
        </div>
        {starting && <p className={css.muted}>{t('center.starting')}</p>}
        {actionError !== null && <p className={css.error} role="alert">{actionError}</p>}
        {consult.status === 'consulting' && <p className={css.muted}>{t('center.consulting')}</p>}
        {consult.status === 'error' && <p className={css.error} role="alert">{t('center.consultError', { message: consult.message })}</p>}
        {consult.status === 'done' && (
          <section className={css.consultResult} aria-label={t('center.consultResult')}>
            <h3>{t('center.consultResult')}{consult.truncated ? t('center.consultTruncated') : ''}</h3>
            <p>{consult.answer}</p>
          </section>
        )}
      </div>
      <dl className={css.detailFacts}>
        <div><dt>{t('center.team')}</dt><dd>{team.title}</dd></div>
        <div><dt>{t('center.mode')}</dt><dd>{t(modeKey(team.mode))}</dd></div>
      </dl>
      <section className={css.detailSection}>
        <h3>{t('center.phases')}</h3>
        {phases.length === 0
          ? <p className={css.muted}>{t('center.noPhases')}</p>
          : <ul>{phases.map(phase => <li key={phase.id}>{phase.id}{phase.gate === 'human-review' ? ` · ${t('center.gate.humanReview')}` : ''}</li>)}</ul>}
      </section>
      <section className={css.detailSection}>
        <h3>{t('center.tools')}</h3>
        {expert.tools.length === 0
          ? <p className={css.muted}>{t('center.noTools')}</p>
          : <div className={css.detailTags}>{expert.tools.map(tool => <span key={tool} className={css.tag}>{tool}</span>)}</div>}
      </section>
      <section className={css.detailSection}>
        <h3>{t('center.suggestedPrompts')}</h3>
        <div className={css.suggestionList}>
          {SUGGESTION_KEYS.map(key => (
            <button
              key={key}
              type="button"
              className={css.suggestion}
              onClick={() => { setTask(t(key)); setActionError(null) }}
            >
              <span>{t(key)}</span>
              <IconQueueOutline14 size={14} />
            </button>
          ))}
        </div>
      </section>
    </aside>
  )
}

function RunSection({ runs, onRefresh, onApprove, onGetRun, loading, t }: {
  runs: readonly ExpertTeamRunView[]
  onRefresh: () => void
  onApprove: ExpertTeamCardFace['approve']
  onGetRun: ExpertTeamCardFace['getRun']
  loading: boolean
  t: ExpertTeamCardProps['t']
}) {
  return (
    <section className={css.runSection}>
      <div className={css.runHeading}>
        <div>
          <h2>{t('center.runs')}</h2>
          <p>{t('center.runDescription')}</p>
        </div>
        <Button variant="ghost" size="sm" icon={<IconRefreshOutline16 size={14} />} disabled={loading} onClick={onRefresh}>
          {t('center.refreshLabel')}
        </Button>
      </div>
      {runs.length === 0
        ? <p className={css.muted}>{t('noRuns')}</p>
        : <div className={css.runList}>
          {runs.map(run => (
            <RunRow
              key={run.runId}
              run={run}
              onApprove={onApprove}
              onGetRun={onGetRun}
              onRefresh={onRefresh}
              t={t}
            />
          ))}
        </div>}
    </section>
  )
}

function RunRow({ run, onApprove, onGetRun, onRefresh, t }: {
  run: ExpertTeamRunView
  onApprove: ExpertTeamCardFace['approve']
  onGetRun: ExpertTeamCardFace['getRun']
  onRefresh: () => void
  t: ExpertTeamCardProps['t']
}) {
  const presentation = runPresentation(run.status)
  const canReview = run.status === 'waiting-approval'
  const [expanded, setExpanded] = useState(false)
  const [detail, setDetail] = useState<ExpertTeamRunDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)

  const toggle = async (): Promise<void> => {
    if (!canReview) return
    if (expanded) {
      setExpanded(false)
      return
    }
    setExpanded(true)
    setLoading(true)
    setError(null)
    try {
      const result = await onGetRun({ runId: run.runId })
      if (result.ok) {
        setDetail(result.value)
      } else {
        setDetail(null)
        setError(result.error.message)
      }
    } catch (cause: unknown) {
      setDetail(null)
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setLoading(false)
    }
  }

  const decide = async (decision: GateDecision): Promise<void> => {
    setBusy(true)
    setError(null)
    try {
      const trimmed = comment.trim()
      const result = await onApprove({
        runId: run.runId,
        decision,
        ...(trimmed === '' ? {} : { comment: trimmed }),
      })
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      setExpanded(false)
      setComment('')
      onRefresh()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  const gatedPhase = detail?.phases.find(phase => phase.status === 'gate-pending')
  const questions = gatedPhase?.userQuestions ?? []

  return (
    <article className={css.runRow} data-expert-team-run={run.runId}>
      <StateDot state={presentation.dot} />
      <strong>{run.teamId}</strong>
      <span className={css.runStatus}>{t(presentation.label)}</span>
      <code>{run.runId}</code>
      {canReview && (
        <button
          type="button"
          className={css.reviewToggle}
          aria-label={t('center.approveToggle')}
          aria-expanded={expanded}
          onClick={() => { void toggle() }}
        >
          {expanded ? t('center.approveCollapse') : t('center.approveToggle')}
        </button>
      )}
      {expanded && (
        <div className={css.approvalPanel}>
          {loading && <p className={css.muted}>{t('center.approveLoading')}</p>}
          {error !== null && <p className={css.error} role="alert">{error}</p>}
          {!loading && error === null && detail !== null && (
            <>
              {questions.length === 0
                ? <p className={css.muted}>{t('center.approveNoQuestions')}</p>
                : (
                  <section className={css.approvalQuestions}>
                    <h4>{t('center.approveQuestions')}</h4>
                    <ul>{questions.map(question => <li key={question}>{question}</li>)}</ul>
                  </section>
                )}
              <Input
                className={css.commentInput as string}
                aria-label={t('center.commentPlaceholder')}
                placeholder={t('center.commentPlaceholder')}
                value={comment}
                onChange={(event) => { setComment(event.currentTarget.value) }}
              />
              <div className={css.approvalActions}>
                <Button
                  variant="primary"
                  size="sm"
                  disabled={busy}
                  aria-label={t('center.approve')}
                  onClick={() => { void decide('approved') }}
                >
                  {t('center.approve')}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  aria-label={t('center.reject')}
                  onClick={() => { void decide('rejected') }}
                >
                  {t('center.reject')}
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </article>
  )
}

function CatalogPlaceholder({ tab, t }: { tab: Exclude<CenterTab, 'experts'>; t: ExpertTeamCardProps['t'] }) {
  const copy = tab === 'skills'
    ? { icon: <IconSkillOutline16 size={28} />, title: t('center.skills.title'), description: t('center.skills.description') }
    : { icon: <IconLinkOutline16 size={28} />, title: t('center.connectors.title'), description: t('center.connectors.description') }
  return (
    <main className={css.placeholder}>
      <div className={css.placeholderIcon}>{copy.icon}</div>
      <h1>{copy.title}</h1>
      <p>{copy.description}</p>
      <span>{t('center.comingSoon')}</span>
    </main>
  )
}
