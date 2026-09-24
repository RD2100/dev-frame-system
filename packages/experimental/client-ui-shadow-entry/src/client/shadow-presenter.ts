/**
 * Pure presentation folds for the Shadow card. The wire snapshot becomes the
 * honest display model — one phase, the designated session, and the
 * authorized roots. No locale text is produced here; keys are data the
 * component renders through its `t` seat.
 */

import type {
  ShadowBoardBinding,
  ShadowBoardTask,
  ShadowStatusView,
} from '@deepseek-ai/dsh-experimental-shadow-controller'
import type { ShadowBoardSnapshotState, ShadowStatusSnapshot } from './shadow-store.ts'

/** The honest phases the card can render. */
export type ShadowPhase =
  | 'loading'
  | 'error'
  | 'unmounted'
  | 'disabled'
  | 'configured'
  | 'online'
  | 'issue'

/** The display model the card renders. */
export interface ShadowCardModel {
  readonly phase: ShadowPhase
  /** Designated controller session id, present only when configured. */
  readonly shadowSessionId: string | null
  readonly authorizedRoots: readonly string[]
  /** The read failure message, present only on the error phase. */
  readonly error: string | null
}

const EMPTY: Pick<ShadowCardModel, 'shadowSessionId' | 'authorizedRoots' | 'error'> = {
  shadowSessionId: null,
  authorizedRoots: [],
  error: null,
}

/**
 * Fold one store snapshot into the display model.
 * @param snapshot - the store's latest state.
 * @returns the phase plus the facts the card shows.
 */
export function presentShadowStatus(snapshot: ShadowStatusSnapshot): ShadowCardModel {
  if (snapshot.error !== undefined) return { phase: 'error', ...EMPTY, error: snapshot.error }
  const view = snapshot.view
  if (view === undefined) return { phase: 'loading', ...EMPTY }
  return presentView(view)
}

/** Fold one wire answer into the display model. */
function presentView(view: ShadowStatusView): ShadowCardModel {
  if (!view.mounted) return { phase: 'unmounted', ...EMPTY }
  // A mounted router without a designation still reports the roots it
  // authorizes; only the session fact is absent.
  if (view.shadowSessionId === undefined) {
    return { phase: 'disabled', shadowSessionId: null, authorizedRoots: view.authorizedRoots, error: null }
  }
  // The designated session cannot be rendered by workspace-scoped surfaces;
  // report the issue instead of opening a conversation that shows fresh.
  if (view.designIssue !== undefined) {
    return {
      phase: 'issue',
      shadowSessionId: view.shadowSessionId,
      authorizedRoots: view.authorizedRoots,
      error: null,
    }
  }
  return {
    phase: view.shadowLive ? 'online' : 'configured',
    shadowSessionId: view.shadowSessionId,
    authorizedRoots: view.authorizedRoots,
    error: null,
  }
}

// ---- task board ----------------------------------------------------------

/** The six board columns a task can occupy; blocked/failed sit outside them. */
export type BoardColumnId =
  | 'backlog'
  | 'toConfirm'
  | 'building'
  | 'toReview'
  | 'submitted'
  | 'done'

/** The honest phases the board can render. */
export type BoardPhase = 'loading' | 'error' | 'disabled' | 'board'

/** Why a card is highlighted as waiting, when it is. */
export type BoardWaitingReason = 'long-planned' | 'stalled-building'

/** One display-ready task row on the board. */
export interface BoardTaskModel {
  readonly taskId: string
  readonly title: string
  readonly state: string
  /** The column projection; blocked/failed cards live in the triage row. */
  readonly column: BoardColumnId
  readonly updatedAt: string
  readonly blockedReason?: string
  readonly nextAction?: string
  readonly wakeCondition?: string
  /** Live worker branch for building cards; null when unreadable. */
  readonly branch: string | null
  /** Whether the approve verb may start this planned card now. */
  readonly startReady: boolean
  /** True when the host could not derive readiness (planned, no answer). */
  readonly startReadyUnknown: boolean
  /** Whether the card is highlighted as waiting (stale in its column). */
  readonly waiting: boolean
  readonly waitingReason: BoardWaitingReason | null
}

/** The display model the board renders. */
export interface ShadowBoardModel {
  readonly phase: BoardPhase
  /** The read failure message, present only on the error phase. */
  readonly error: string | null
  /** Workspace binding digest, present only on the board phase. */
  readonly bindings: readonly ShadowBoardBinding[]
  /** The six columns in reading order. */
  readonly columns: readonly BoardColumnId[]
  /** Cards folded into their columns, stable per column. */
  readonly tasks: readonly BoardTaskModel[]
  /** Blocked/failed cards needing human triage, below the columns. */
  readonly triage: readonly BoardTaskModel[]
}

/** A planned card is highlighted as waiting after half an hour in backlog. */
export const PLANNED_STALL_MS = 30 * 60 * 1000
/** A building card is highlighted as waiting after half an hour without progress. */
export const DEVELOPING_STALL_MS = 30 * 60 * 1000

/** The reading order of the six columns. */
export const BOARD_COLUMNS: readonly BoardColumnId[] = [
  'backlog', 'toConfirm', 'building', 'toReview', 'submitted', 'done',
]

/**
 * Project the board's wire snapshot into the display model.
 * @param snapshot - Current board state from the Shadow Remote.
 * @param now - Current epoch milliseconds used for task age and deadlines.
 * @returns The localized-independent board presentation model.
 */
export function presentShadowBoard(snapshot: ShadowBoardSnapshotState, now: number): ShadowBoardModel {
  if (snapshot.error !== undefined) {
    return { phase: 'error', error: snapshot.error, bindings: [], columns: BOARD_COLUMNS, tasks: [], triage: [] }
  }
  const board = snapshot.board
  if (board === undefined) {
    return { phase: 'loading', error: null, bindings: [], columns: BOARD_COLUMNS, tasks: [], triage: [] }
  }
  if (!board.mounted) {
    return { phase: 'disabled', error: null, bindings: [], columns: BOARD_COLUMNS, tasks: [], triage: [] }
  }
  // Blocked/failed cards never sit in a column: they render as the triage
  // row below the six columns, carrying the recovery triple.
  const rows = board.tasks.map(task => foldBoardTask(task, now))
  return {
    phase: 'board',
    error: null,
    bindings: board.bindings,
    columns: BOARD_COLUMNS,
    tasks: rows.filter(row => row.state !== 'blocked' && row.state !== 'failed'),
    triage: rows.filter(row => row.state === 'blocked' || row.state === 'failed'),
  }
}

/** Fold one wire task row into the display model. */
function foldBoardTask(task: ShadowBoardTask, now: number): BoardTaskModel {
  const updated = Date.parse(task.updatedAt)
  const stale = Number.isFinite(updated) && now - updated > (
    task.state === 'planned' ? PLANNED_STALL_MS : DEVELOPING_STALL_MS
  )
  const waiting = stale && (task.state === 'planned' || task.state === 'developing')
  return {
    taskId: task.taskId,
    title: task.title,
    state: task.state,
    column: stateColumn(task.state),
    updatedAt: task.updatedAt,
    ...(task.blockedReason === undefined ? {} : { blockedReason: task.blockedReason }),
    ...(task.nextAction === undefined ? {} : { nextAction: task.nextAction }),
    ...(task.wakeCondition === undefined ? {} : { wakeCondition: task.wakeCondition }),
    branch: task.branch ?? null,
    startReady: task.startReady === true,
    startReadyUnknown: task.state === 'planned' && task.startReady === undefined,
    waiting,
    waitingReason: waiting ? (task.state === 'planned' ? 'long-planned' : 'stalled-building') : null,
  }
}

/** The column a task state projects to; triage states share a placeholder column. */
function stateColumn(state: string): BoardColumnId {
  switch (state) {
    case 'planned': return 'backlog'
    case 'assigned': return 'toConfirm'
    case 'developing': return 'building'
    case 'reviewing': return 'toReview'
    case 'submitted': return 'submitted'
    case 'integrated':
    case 'completed': return 'done'
    default: return 'backlog'
  }
}
