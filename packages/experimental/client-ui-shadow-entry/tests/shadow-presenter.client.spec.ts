/** The presenter folds: every honest phase of the Shadow card's display model. */

import { describe, expect, it } from 'vitest'
import type { ShadowBoardSnapshot, ShadowBoardTask, ShadowStatusView } from '@deepseek-ai/dsh-experimental-shadow-controller'
import { presentShadowBoard, presentShadowStatus } from '../src/client/shadow-presenter.ts'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type { ShadowStatusSnapshot } from '../src/client/shadow-store.ts'

const READY_VIEW: ShadowStatusView = {
  mounted: true,
  shadowSessionId: 'session-shadow',
  shadowLive: true,
  authorizedRoots: ['D:/projects'],
  bindings: [],
}

function snapshotOf(partial: Partial<ShadowStatusSnapshot>): ShadowStatusSnapshot {
  return { view: undefined, error: undefined, ...partial }
}

describe('the Shadow card presentation fold', () => {
  it('reads a pending store as the loading phase with an empty model', () => {
    expect(presentShadowStatus(snapshotOf({}))).toEqual({
      phase: 'loading',
      shadowSessionId: null,
      authorizedRoots: [],
      error: null,
    })
  })

  it('reads a failed read as the error phase carrying the transport message', () => {
    const model = presentShadowStatus(snapshotOf({ error: 'offline' }))
    expect(model.phase).toBe('error')
    expect(model.error).toBe('offline')
    expect(model.shadowSessionId).toBeNull()
    expect(model.authorizedRoots).toEqual([])
  })

  it('reads an unmounted deployment as the honest not-enabled phase', () => {
    const model = presentShadowStatus(snapshotOf({
      view: { mounted: false, shadowLive: true, authorizedRoots: [], bindings: [] },
    }))
    expect(model.phase).toBe('unmounted')
    expect(model.shadowSessionId).toBeNull()
  })

  it('reads a mounted router without a designation as the not-enabled phase', () => {
    const model = presentShadowStatus(snapshotOf({
      view: { mounted: true, shadowLive: true, authorizedRoots: ['D:/projects'], bindings: [] },
    }))
    expect(model.phase).toBe('disabled')
    expect(model.shadowSessionId).toBeNull()
    expect(model.authorizedRoots).toEqual(['D:/projects'])
  })

  it('reads a live designated session as the online phase with its session and roots', () => {
    const model = presentShadowStatus(snapshotOf({ view: READY_VIEW }))
    expect(model.phase).toBe('online')
    expect(model.shadowSessionId).toBe('session-shadow')
    expect(model.authorizedRoots).toEqual(['D:/projects'])
    expect(model.error).toBeNull()
  })

  it('reads a configured designation whose session is not live as configured, not online', () => {
    const model = presentShadowStatus(snapshotOf({ view: { ...READY_VIEW, shadowLive: false } }))
    expect(model.phase).toBe('configured')
    expect(model.shadowSessionId).toBe('session-shadow')
  })

  it('keeps open-project bindings out of the display model the card renders', () => {
    // The manage dropdown surfaces only the phase, the session, and the
    // authorized roots; binding rows stay in the wire view untouched.
    const model = presentShadowStatus(snapshotOf({
      view: { ...READY_VIEW, bindings: [{
        workspaceId: 'ws-1',
        canonicalPath: 'D:/projects/alpha',
        bindingRevision: 7,
        state: 'ready',
      } as ShadowStatusView['bindings'][number]] },
    }))
    expect(model.phase).toBe('online')
    expect(model).not.toHaveProperty('projects')
  })

  it('reads a designation issue as the issue phase while keeping the session facts', () => {
    const model = presentShadowStatus(snapshotOf({
      view: { ...READY_VIEW, designIssue: 'designated-session-missing-cwd' },
    }))
    expect(model.phase).toBe('issue')
    expect(model.shadowSessionId).toBe('session-shadow')
    expect(model.authorizedRoots).toEqual(['D:/projects'])
    expect(model.error).toBeNull()
  })
})

describe('the Shadow board presentation fold', () => {
  const NOW = Date.parse('2026-09-20T12:00:00Z')
  const FRESH = '2026-09-20T11:59:00Z'
  const STALE = '2026-09-20T11:20:00Z'

  function boardOf(partial: Partial<ShadowBoardSnapshot>): ShadowBoardSnapshot {
    return { mounted: true, bindings: [], tasks: [], ...partial }
  }

  it('reads a pending board as loading and a failed read as the error phase', () => {
    expect(presentShadowBoard({ board: undefined, error: undefined }, NOW).phase).toBe('loading')
    const failed = presentShadowBoard({ board: undefined, error: 'offline' }, NOW)
    expect(failed.phase).toBe('error')
    expect(failed.error).toBe('offline')
  })

  it('reads an unmounted deployment as the honest disabled model', () => {
    const model = presentShadowBoard({ board: boardOf({ mounted: false }), error: undefined }, NOW)
    expect(model.phase).toBe('disabled')
    expect(model.tasks).toEqual([])
    expect(model.triage).toEqual([])
  })

  it('projects every state into its column in reading order', () => {
    const board = boardOf({
      bindings: [{ workspaceId: 'ws-1', state: 'ready', controllerSessionId: 'session-controller' as SessionId }],
      tasks: [
        task('t-planned', 'planned', FRESH, { startReady: true }),
        task('t-assigned', 'assigned', FRESH),
        task('t-dev', 'developing', FRESH, { branch: 'feature/board' }),
        task('t-review', 'reviewing', FRESH),
        task('t-submitted', 'submitted', FRESH),
        task('t-integrated', 'integrated', FRESH),
        task('t-completed', 'completed', FRESH),
      ],
    })
    const model = presentShadowBoard({ board, error: undefined }, NOW)
    expect(model.phase).toBe('board')
    expect(model.bindings[0]?.workspaceId).toBe('ws-1')
    expect(model.columns).toEqual(['backlog', 'toConfirm', 'building', 'toReview', 'submitted', 'done'])
    expect(model.tasks.map(row => `${row.taskId}:${row.column}`)).toEqual([
      't-planned:backlog', 't-assigned:toConfirm', 't-dev:building', 't-review:toReview',
      't-submitted:submitted', 't-integrated:done', 't-completed:done',
    ])
    expect(model.triage).toEqual([])
  })

  it('keeps blocked and failed cards out of the columns and in the triage row', () => {
    const board = boardOf({
      tasks: [
        task('t-blocked', 'blocked', FRESH, { blockedReason: 'dep on #9', nextAction: 'raise budget', wakeCondition: 'budget raised' }),
        task('t-failed', 'failed', FRESH),
      ],
    })
    const model = presentShadowBoard({ board, error: undefined }, NOW)
    expect(model.tasks).toEqual([])
    expect(model.triage.map(row => row.taskId)).toEqual(['t-blocked', 't-failed'])
    expect(model.triage[0]?.blockedReason).toBe('dep on #9')
    expect(model.triage[0]?.nextAction).toBe('raise budget')
    expect(model.triage[0]?.wakeCondition).toBe('budget raised')
  })

  it('highlights planned cards waiting over half an hour as long-planned', () => {
    const board = boardOf({ tasks: [task('t-planned', 'planned', STALE, { startReady: true })] })
    const model = presentShadowBoard({ board, error: undefined }, NOW)
    expect(model.tasks[0]?.waiting).toBe(true)
    expect(model.tasks[0]?.waitingReason).toBe('long-planned')
  })

  it('highlights developing cards without progress over half an hour as stalled', () => {
    const board = boardOf({ tasks: [task('t-dev', 'developing', STALE)] })
    const model = presentShadowBoard({ board, error: undefined }, NOW)
    expect(model.tasks[0]?.waiting).toBe(true)
    expect(model.tasks[0]?.waitingReason).toBe('stalled-building')
  })

  it('does not highlight fresh or non-progress cards', () => {
    const board = boardOf({
      tasks: [
        task('t-fresh', 'planned', FRESH, { startReady: true }),
        task('t-review', 'reviewing', STALE),
      ],
    })
    const model = presentShadowBoard({ board, error: undefined }, NOW)
    expect(model.tasks.every(row => !row.waiting)).toBe(true)
  })

  it('carries start readiness for planned cards and greys an unready one', () => {
    const board = boardOf({
      tasks: [
        task('t-ready', 'planned', FRESH, { startReady: true }),
        task('t-busy', 'planned', FRESH, { startReady: false }),
        task('t-dev', 'developing', FRESH),
      ],
    })
    const model = presentShadowBoard({ board, error: undefined }, NOW)
    expect(model.tasks[0]?.startReady).toBe(true)
    expect(model.tasks[0]?.startReadyUnknown).toBe(false)
    expect(model.tasks[1]?.startReady).toBe(false)
    expect(model.tasks[1]?.startReadyUnknown).toBe(false)
    expect(model.tasks[2]?.startReady).toBe(false)
    expect(model.tasks[2]?.startReadyUnknown).toBe(false)
  })

  it('marks a planned card without a readiness answer as unknown', () => {
    const board = boardOf({ tasks: [task('t-planned', 'planned', FRESH)] })
    const model = presentShadowBoard({ board, error: undefined }, NOW)
    expect(model.tasks[0]?.startReady).toBe(false)
    expect(model.tasks[0]?.startReadyUnknown).toBe(true)
  })

  it('carries the live worker branch and nulls a missing one', () => {
    const board = boardOf({
      tasks: [
        task('t-dev', 'developing', FRESH, { branch: 'feature/board' }),
        task('t-assigned', 'assigned', FRESH),
      ],
    })
    const model = presentShadowBoard({ board, error: undefined }, NOW)
    expect(model.tasks[0]?.branch).toBe('feature/board')
    expect(model.tasks[1]?.branch).toBeNull()
  })
})

function task(taskId: string, state: string, updatedAt: string, extra: Partial<{
  startReady: boolean
  branch: string
  blockedReason: string
  nextAction: string
  wakeCondition: string
}> = {}): ShadowBoardTask {
  return {
    taskId,
    pluginId: 'devframe-goal',
    title: `Task ${taskId}`,
    state,
    createdAt: '2026-09-20T10:00:00Z',
    updatedAt,
    ...extra,
  }
}
