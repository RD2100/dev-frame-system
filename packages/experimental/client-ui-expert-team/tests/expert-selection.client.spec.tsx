// @vitest-environment jsdom
/** The Expert center handoff stages a normal blank Session and exposes the
 * chosen expert in the composer without adding a second submission path. */

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { SessionListState } from '@deepseek-ai/dsh-api-session-controller/client'
import { bindSnapshotSelector } from '@deepseek-ai/dsh-client-test-runtime'
import { createSnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type { ExpertSelectionChipProps } from '../src/client/ExpertSelectionChip.tsx'
import { ExpertSelectionChip } from '../src/client/ExpertSelectionChip.tsx'
import {
  ExpertSelectionController,
  type ExpertSelectionState,
  type ExpertSelectionTarget,
} from '../src/client/selection.ts'
import { zh, type ExpertTeamKey } from '../src/client/locales.ts'

afterEach(cleanup)

const SESSION_ID = 'session-1' as SessionId
const TARGET: ExpertSelectionTarget = {
  teamId: 'dev',
  teamTitle: '软件开发专家团',
  expertId: 'architect',
  expertName: '架构师',
}

function translate(key: ExpertTeamKey, params?: Record<string, unknown>): string {
  const template = zh[key]
  return params === undefined
    ? template
    : Object.entries(params).reduce((result, [name, value]) => result.replaceAll(`{${name}}`, String(value)), template)
}

function sessionList(blank: boolean, current: SessionId | undefined = SESSION_ID): SessionListState {
  return {
    ids: current === undefined ? [] : [current],
    byId: current === undefined ? {} : {
      [current]: { id: current, displayTitle: '测试会话', blank, running: false, updatedAt: 1 },
    },
    current,
    phase: 'ready',
    subagentsByParent: {},
    jobsBySession: {},
    currentAddress: undefined,
  }
}

function contextFor(
  sessions: ReturnType<typeof createSnapshotStore<SessionListState>>,
  setDraft: ReturnType<typeof vi.fn>,
  startSession: ReturnType<typeof vi.fn>,
): ClientContext {
  const scope = {} as never
  return {
    sessions: { list: sessions, scope: vi.fn(() => scope) },
    conversation: { input: { for: vi.fn(() => ({ setDraft })) } },
    uiWorkspace: { startSession },
  } as unknown as ClientContext
}

describe('expert selection handoff', () => {
  it('opens the normal new-session flow and seeds the blank composer', async () => {
    const sessions = createSnapshotStore(sessionList(true))
    const setDraft = vi.fn()
    const startSession = vi.fn()
    const controller = new ExpertSelectionController(contextFor(sessions, setDraft, startSession))

    controller.summon(TARGET, '请让架构师帮我评审这个方案。')
    await act(async () => { await Promise.resolve() })

    expect(startSession).toHaveBeenCalledOnce()
    expect(setDraft).toHaveBeenCalledWith('请让架构师帮我评审这个方案。')
    expect(controller.store.getSnapshot()).toEqual({ target: TARGET, sessionId: SESSION_ID })

    controller.clear()
    expect(controller.store.getSnapshot()).toEqual({ target: null, sessionId: undefined })
  })

  it('keeps the selection staged until an asynchronous blank Session arrives', async () => {
    const sessions = createSnapshotStore(sessionList(false))
    const setDraft = vi.fn()
    const startSession = vi.fn()
    const controller = new ExpertSelectionController(contextFor(sessions, setDraft, startSession))

    controller.summon(TARGET)
    expect(controller.store.getSnapshot().target).toEqual(TARGET)
    expect(setDraft).not.toHaveBeenCalled()

    const nextId = 'session-2' as SessionId
    sessions.set({
      ...sessionList(true, nextId),
      byId: {
        [nextId]: { id: nextId, displayTitle: '新会话', blank: true, running: false, updatedAt: 2 },
      },
    })
    controller.reconcile()
    expect(controller.store.getSnapshot().sessionId).toBe(nextId)
    expect(controller.store.getSnapshot().target).toEqual(TARGET)
  })

  it('renders and clears the selected expert chip in a blank Session', () => {
    const selection = createSnapshotStore<ExpertSelectionState>({ target: TARGET, sessionId: SESSION_ID })
    const sessions = createSnapshotStore(sessionList(true))
    const clear = vi.fn()
    render(<ExpertSelectionChip {...({
      sessionId: SESSION_ID,
      useSessions: bindSnapshotSelector(sessions),
      useExpertSelection: bindSnapshotSelector(selection),
      clear,
      t: translate,
    } as unknown as ExpertSelectionChipProps)} />)

    expect(screen.getByText('架构师')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '移除已选择的架构师' }))
    expect(clear).toHaveBeenCalledOnce()
  })
})
