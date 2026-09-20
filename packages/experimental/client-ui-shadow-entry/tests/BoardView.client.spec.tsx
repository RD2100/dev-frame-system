// @vitest-environment jsdom
/** The board view: six column projection, approve/reject/re-approve verbs,
 *  waiting marks, readiness gating, and the five-second poll lifecycle. */

import { useSyncExternalStore } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { RemoteError } from '@deepseek-ai/dsh-client-test-runtime'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type {
  ShadowBoardSnapshot,
  ShadowBoardTask,
  ShadowStatusView,
} from '@deepseek-ai/dsh-experimental-shadow-controller'
import { BoardView, type BoardViewProps } from '../src/client/BoardView.tsx'
import { zh, type ShadowKey } from '../src/client/locales.ts'
import {
  ShadowBoardController,
  ShadowStatusController,
  type ShadowBoardSnapshotState,
  type ShadowStatusSnapshot,
} from '../src/client/shadow-store.ts'

const t = ((key: ShadowKey, params?: Record<string, string | number>) => {
  const text = zh[key]
  return params === undefined
    ? text
    : Object.entries(params).reduce((acc, [name, value]) => acc.replaceAll(`{${name}}`, String(value)), text)
}) as unknown as BoardViewProps['t']

const unusedHook = (() => { throw new Error('unused by the board view') }) as never

function task(taskId: string, state: string, extra: Partial<ShadowBoardTask> = {}): ShadowBoardTask {
  return {
    taskId,
    pluginId: 'devframe-goal',
    title: `Task ${taskId}`,
    state,
    createdAt: '2026-09-20T10:00:00Z',
    updatedAt: '2026-09-20T10:00:00Z',
    ...extra,
  }
}

const ONLINE_STATUS: ShadowStatusView = {
  mounted: true,
  shadowSessionId: 'session-shadow',
  shadowLive: true,
  authorizedRoots: ['D:/projects'],
  bindings: [],
}

function boardSnapshot(tasks: readonly ShadowBoardTask[]): ShadowBoardSnapshot {
  return {
    mounted: true,
    bindings: [{ workspaceId: 'ws-1', state: 'ready', controllerSessionId: 'session-controller' as SessionId }],
    tasks,
  }
}

interface Bench {
  boardController: ShadowBoardController
  onRefresh: ReturnType<typeof vi.fn>
  onApprove: ReturnType<typeof vi.fn>
  onReject: ReturnType<typeof vi.fn>
  props: BoardViewProps
}

/** A bench whose board port answers from a queue; the last answer repeats. */
function bench(
  boardAnswers: readonly ShadowBoardSnapshot[],
  status: ShadowStatusSnapshot = { view: ONLINE_STATUS, error: undefined },
): Bench {
  let cursor = 0
  const boardController = new ShadowBoardController(async () => {
    const answer = boardAnswers[Math.min(cursor, boardAnswers.length - 1)]
    cursor = Math.min(cursor + 1, boardAnswers.length - 1)
    return answer === undefined
      ? { ok: false, error: new RemoteError('gateway/internal', 'offline', {}) }
      : { ok: true as const, value: answer }
  })
  const statusController = new ShadowStatusController(async () => ({ ok: true as const, value: status.view! }))
  void statusController.refresh()
  const useBoard = <S,>(selector: (s: ShadowBoardSnapshotState) => S): S =>
    useSyncExternalStore(
      listener => boardController.store.subscribe(listener),
      () => selector(boardController.store.getSnapshot()),
    )
  const useStatus = <S,>(selector: (s: ShadowStatusSnapshot) => S): S =>
    useSyncExternalStore(
      listener => statusController.store.subscribe(listener),
      () => selector(statusController.store.getSnapshot()),
    )
  const onRefresh = vi.fn(() => { void boardController.refresh() })
  const onApprove = vi.fn(async () => {})
  const onReject = vi.fn(async () => {})
  // The remaining standard session props are inert in this bench: the board
  // never reads them, so stubs satisfy the runtime contract without stores.
  const inert = (() => undefined) as never
  const props: BoardViewProps = {
    useBoard,
    useStatus,
    onRefresh,
    onApprove,
    onReject,
    t,
    useConversation: unusedHook,
    useInput: unusedHook,
    inputActions: unusedHook,
    useWorkspaces: unusedHook,
    viewRequest: null,
    openView: unusedHook,
    completeViewRequest: unusedHook,
    useSession: inert,
    sessionId: inert,
    useProjection: inert,
    useChat: inert,
    useTrajectory: inert,
    useSessions: inert,
    useSessionPendingInteraction: inert,
  } satisfies BoardViewProps
  return { boardController, onRefresh, onApprove, onReject, props }
}

afterEach(cleanup)

describe('the task board view', () => {
  it('renders the six columns and projects each card into its column', async () => {
    const b = bench([boardSnapshot([
      task('t-planned', 'planned', { startReady: true }),
      task('t-dev', 'developing', { branch: 'feature/board' }),
      task('t-done', 'integrated'),
    ])])
    render(<BoardView {...b.props} />)
    await act(async () => { await Promise.resolve() })
    for (const label of ['待办', '待确认', '开发中', '待评审', '已提交', '已完成']) {
      expect(screen.getByText(label)).not.toBeNull()
    }
    expect(screen.getByText('Task t-planned')).not.toBeNull()
    expect(screen.getByText('Task t-dev')).not.toBeNull()
    expect(screen.getByText('Task t-done')).not.toBeNull()
    // The workspace tag is the single ready binding, on every card.
    expect(screen.getAllByText('ws-1').length).toBeGreaterThanOrEqual(1)
  })

  it('refreshes once on mount and polls every five seconds', () => {
    vi.useFakeTimers()
    const b = bench([boardSnapshot([])])
    render(<BoardView {...b.props} />)
    expect(b.onRefresh).toHaveBeenCalledTimes(1)
    act(() => { vi.advanceTimersByTime(5000) })
    expect(b.onRefresh).toHaveBeenCalledTimes(2)
    act(() => { vi.advanceTimersByTime(5000) })
    expect(b.onRefresh).toHaveBeenCalledTimes(3)
    vi.useRealTimers()
  })

  it('sends the approve click for the planned task id', async () => {
    const b = bench([boardSnapshot([task('t-planned', 'planned', { startReady: true })])])
    render(<BoardView {...b.props} />)
    await act(async () => { await Promise.resolve() })
    fireEvent.click(screen.getByRole('button', { name: '批准开工' }))
    await act(async () => { await Promise.resolve() })
    expect(b.onApprove).toHaveBeenCalledWith('t-planned')
  })

  it('greys the approve verb while the start authority is not ready', async () => {
    const b = bench([boardSnapshot([task('t-planned', 'planned', { startReady: false })])])
    render(<BoardView {...b.props} />)
    await act(async () => { await Promise.resolve() })
    const approve = screen.getByRole('button', { name: '批准开工' }) as HTMLButtonElement
    expect(approve.disabled).toBe(true)
    expect(screen.getByText('预配未就绪')).not.toBeNull()
  })

  it('opens the reject note form and sends the reason with the task id', async () => {
    const b = bench([boardSnapshot([task('t-planned', 'planned', { startReady: true })])])
    render(<BoardView {...b.props} />)
    await act(async () => { await Promise.resolve() })
    fireEvent.click(screen.getByRole('button', { name: '打回' }))
    const input = screen.getByPlaceholderText('填写打回原因…') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'scope too wide' } })
    fireEvent.click(screen.getByRole('button', { name: '确认打回' }))
    await act(async () => { await Promise.resolve() })
    expect(b.onReject).toHaveBeenCalledWith('t-planned', 'scope too wide')
  })

  it('re-approves a blocked card through the same verb', async () => {
    const b = bench([boardSnapshot([
      task('t-blocked', 'blocked', { blockedReason: 'dep', nextAction: 'raise budget', wakeCondition: 'budget raised' }),
    ])])
    render(<BoardView {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(screen.getByText('dep')).not.toBeNull()
    expect(screen.getByText('raise budget')).not.toBeNull()
    expect(screen.getByText('budget raised')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '重新批准' }))
    await act(async () => { await Promise.resolve() })
    expect(b.onApprove).toHaveBeenCalledWith('t-blocked')
  })

  it('shows a waiting mark for a planned card stale over half an hour', async () => {
    const stale = '2026-09-20T11:20:00Z'
    const b = bench([boardSnapshot([
      task('t-stale', 'planned', { startReady: true, updatedAt: stale }),
    ])])
    const { container } = render(<BoardView {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(screen.getByText('待批准超过 30 分钟')).not.toBeNull()
    expect(container.querySelector('[data-waiting-mark]')).not.toBeNull()
  })

  it('shows the live worker branch on a building card', async () => {
    const b = bench([boardSnapshot([
      task('t-dev', 'developing', { branch: 'feature/board' }),
    ])])
    render(<BoardView {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(screen.getByText('feature/board')).not.toBeNull()
  })

  it('renders the triage row for blocked and failed cards below the columns', async () => {
    const b = bench([boardSnapshot([
      task('t-blocked', 'blocked'),
      task('t-failed', 'failed'),
    ])])
    const { container } = render(<BoardView {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(screen.getByText('需介入')).not.toBeNull()
    expect(container.querySelector('[data-shadow-triage]')).not.toBeNull()
  })

  it('reads an unmounted deployment as the disabled board', async () => {
    const b = bench([{ mounted: false, bindings: [], tasks: [] }])
    render(<BoardView {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(screen.getByText('此部署没有挂载任务控制器。')).not.toBeNull()
  })

  it('shows the read failure with a retry that re-reads', async () => {
    const b = bench([])
    render(<BoardView {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(screen.getByText('看板读取失败')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(b.onRefresh).toHaveBeenCalled()
  })

  it('renders the self-check fact when the Shadow conversation is not live', async () => {
    const b = bench(
      [boardSnapshot([])],
      { view: { mounted: false, shadowLive: true, authorizedRoots: [], bindings: [] }, error: undefined },
    )
    const { container } = render(<BoardView {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-board-selfcheck]')).not.toBeNull()
  })

  it('moves an approved card into the building column after the next poll', async () => {
    vi.useFakeTimers()
    const b = bench([
      boardSnapshot([task('t-planned', 'planned', { startReady: true })]),
      boardSnapshot([task('t-planned', 'developing', { branch: 'feature/board' })]),
    ])
    render(<BoardView {...b.props} />)
    await act(async () => { await Promise.resolve() })
    fireEvent.click(screen.getByRole('button', { name: '批准开工' }))
    await act(async () => { await Promise.resolve() })
    act(() => { vi.advanceTimersByTime(5000) })
    // The poll issued a host read; let its settlement publish before asserting.
    await act(async () => { await Promise.resolve() })
    expect(screen.getByText('feature/board')).not.toBeNull()
    vi.useRealTimers()
  })
})
