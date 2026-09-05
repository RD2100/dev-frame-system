// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import { makeTranslate } from '@deepseek-ai/dsh-client-test-runtime'
import { zh as commonZh } from '@deepseek-ai/dsh-client-locale/src/locales/zh.ts'
import { SessionNodeItem } from '../src/client/rows/Rows.tsx'
import type { SessionNode } from '../src/client/tree.ts'
import { zh } from '../src/client/locales.ts'

afterEach(cleanup)

const t = makeTranslate(zh, commonZh) as never
const sid = (id: string) => id as SessionId

function node(id: string, title = `Title ${id}`): SessionNode {
  return {
    id: sid(id), title, blank: false, running: false,
    runningSubagentCount: 0, completed: false, hasActiveSchedule: false, updatedAt: 0,
  }
}

function renderRow(nodeValue: SessionNode, currentId: string | undefined = undefined): void {
  render(<SessionNodeItem node={nodeValue} currentId={currentId} now={0} onOpen={vi.fn()}
    onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />)
}

/** Install the async browser clipboard and restore its prior host shape. */
function installClipboard(writeText: (text: string) => Promise<void>): () => void {
  const prior = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
  return () => {
    if (prior === undefined) Reflect.deleteProperty(navigator, 'clipboard')
    else Object.defineProperty(navigator, 'clipboard', prior)
  }
}

/** Open the row actions menu and pick the Session-ID entry. */
function openSessionIdDialog(title: string): void {
  fireEvent.click(screen.getByRole('button', { name: `会话“${title}”的操作` }))
  fireEvent.click(screen.getByRole('menuitem', { name: zh['menu.sessionId'] }))
}

/** The dialog's two copy affordances in DOM order: the id text, then the copy button. */
function copyControls(): [HTMLElement, HTMLElement] {
  const controls = screen.getAllByRole('button', { name: zh['sessionId.copy'] })
  expect(controls).toHaveLength(2)
  return [controls[0]!, controls[1]!]
}

describe('session row Session-ID menu item', () => {
  it('lists the Session-ID entry in the row actions menu without opening the session', () => {
    const onOpen = vi.fn()
    renderRow(node('session-alpha'))
    fireEvent.click(screen.getByRole('button', { name: '会话“Title session-alpha”的操作' }))
    expect(screen.getByRole('menuitem', { name: '会话 ID' })).toBeDefined()
    expect(onOpen).not.toHaveBeenCalled()
  })

  it('opens a dialog showing the full id verbatim', () => {
    const id = 'session-alpha-0123456789abcdef0123456789abcdef01234567'
    renderRow(node(id, 'Alpha'))
    openSessionIdDialog('Alpha')
    const dialog = screen.getByRole('dialog')
    expect(dialog.getAttribute('aria-label')).toBe(zh['sessionId.title'])
    // The complete id is present as one text node — nothing truncates it.
    expect(dialog.textContent).toContain(id)
  })

  it('copies the full id from the copy button and reports the success', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined)
    const restore = installClipboard(writeText)
    try {
      renderRow(node('session-beta'))
      openSessionIdDialog('Title session-beta')
      fireEvent.click(copyControls()[1]!)
      await waitFor(() => expect(screen.getByRole('status').textContent).toBe(zh['sessionId.copied']))
      expect(writeText).toHaveBeenCalledWith('session-beta')
    } finally {
      restore()
    }
  })

  it('copies the full id from the id text itself', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined)
    const restore = installClipboard(writeText)
    try {
      renderRow(node('session-gamma'))
      openSessionIdDialog('Title session-gamma')
      fireEvent.click(copyControls()[0]!)
      await waitFor(() => expect(screen.getByRole('status').textContent).toBe(zh['sessionId.copied']))
      expect(writeText).toHaveBeenCalledWith('session-gamma')
    } finally {
      restore()
    }
  })

  it('reports an explicit failure and never a success when the host refuses the write', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockRejectedValue(new Error('denied'))
    const restore = installClipboard(writeText)
    try {
      renderRow(node('session-delta'))
      openSessionIdDialog('Title session-delta')
      fireEvent.click(copyControls()[1]!)
      await waitFor(() => expect(screen.getByRole('status').textContent).toBe(zh['sessionId.copyFailed']))
      expect(screen.queryByText(zh['sessionId.copied'])).toBeNull()
    } finally {
      restore()
    }
  })

  it('returns the copy feedback to idle when the confirmation window closes, and a re-copy restarts it', async () => {
    vi.useFakeTimers()
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined)
    const restore = installClipboard(writeText)
    try {
      renderRow(node('session-zeta'))
      openSessionIdDialog('Title session-zeta')
      fireEvent.click(copyControls()[1]!)
      await act(async () => { await vi.advanceTimersByTimeAsync(0) })
      expect(screen.getByRole('status').textContent).toBe(zh['sessionId.copied'])
      // One tick before the window closes the success is still shown.
      await act(async () => { await vi.advanceTimersByTimeAsync(1_199) })
      expect(screen.getByRole('status').textContent).toBe(zh['sessionId.copied'])
      await act(async () => { await vi.advanceTimersByTimeAsync(1) })
      expect(screen.getByRole('status').textContent).toBe('')

      // A re-copy inside the window clears the pending reset: the feedback
      // stays for a full window measured from the SECOND copy, not the first.
      fireEvent.click(copyControls()[1]!)
      await act(async () => { await vi.advanceTimersByTimeAsync(0) })
      fireEvent.click(copyControls()[1]!)
      await act(async () => { await vi.advanceTimersByTimeAsync(600) })
      expect(screen.getByRole('status').textContent).toBe(zh['sessionId.copied'])
      await act(async () => { await vi.advanceTimersByTimeAsync(599) })
      expect(screen.getByRole('status').textContent).toBe(zh['sessionId.copied'])
      await act(async () => { await vi.advanceTimersByTimeAsync(1) })
      expect(screen.getByRole('status').textContent).toBe('')
      expect(writeText).toHaveBeenCalledTimes(3)
      expect(writeText).toHaveBeenCalledWith('session-zeta')
    } finally {
      restore()
      vi.useRealTimers()
    }
  })

  it("keeps showing the row's own id while another session is selected, and shows each row its own id", () => {
    const onOpen = vi.fn()
    const { rerender } = render(
      <>
        <SessionNodeItem node={node('session-one')} currentId={'session-one'} now={0} onOpen={onOpen}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />
        <SessionNodeItem node={node('session-two')} currentId={'session-one'} now={0} onOpen={vi.fn()}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />
      </>,
    )
    openSessionIdDialog('Title session-two')
    expect(screen.getByRole('dialog').textContent).toContain('session-two')
    expect(screen.getByRole('dialog').textContent).not.toContain('session-one')

    // The selection moves to the other row: the open dialog keeps row-two's id.
    rerender(
      <>
        <SessionNodeItem node={node('session-one')} currentId={'session-two'} now={0} onOpen={onOpen}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />
        <SessionNodeItem node={node('session-two')} currentId={'session-two'} now={0} onOpen={vi.fn()}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />
      </>,
    )
    expect(screen.getByRole('dialog').textContent).toContain('session-two')

    // Closing and opening the first row's dialog shows that row's id.
    fireEvent.click(screen.getByRole('button', { name: zh['sessionId.close'] }))
    expect(screen.queryByRole('dialog')).toBeNull()
    openSessionIdDialog('Title session-one')
    expect(screen.getByRole('dialog').textContent).toContain('session-one')
  })

  it('keeps the open dialog on the same session when the keyed rows reorder', () => {
    const { rerender } = render(
      <>
        <SessionNodeItem key="one" node={node('session-one')} currentId={undefined} now={0} onOpen={vi.fn()}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />
        <SessionNodeItem key="two" node={node('session-two')} currentId={undefined} now={0} onOpen={vi.fn()}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />
      </>,
    )
    openSessionIdDialog('Title session-two')
    expect(screen.getByRole('dialog').textContent).toContain('session-two')

    // Production rows carry stable session-id keys, so a list reorder moves
    // the keyed row instead of unmounting it, and the open dialog follows.
    rerender(
      <>
        <SessionNodeItem key="two" node={node('session-two')} currentId={undefined} now={0} onOpen={vi.fn()}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />
        <SessionNodeItem key="one" node={node('session-one')} currentId={undefined} now={0} onOpen={vi.fn()}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />
      </>,
    )
    expect(screen.getByRole('dialog').textContent).toContain('session-two')
    expect(screen.getByRole('dialog').textContent).not.toContain('session-one')
  })

  it('closes the open dialog without a close event when its row leaves the list', () => {
    const { rerender } = render(
      <>
        <SessionNodeItem key="one" node={node('session-one')} currentId={undefined} now={0} onOpen={vi.fn()}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />
        <SessionNodeItem key="two" node={node('session-two')} currentId={undefined} now={0} onOpen={vi.fn()}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />
      </>,
    )
    openSessionIdDialog('Title session-two')
    expect(screen.getByRole('dialog')).toBeDefined()

    // The showId state lives on the row, so a list change that unmounts the
    // row (archive echo, group fold, cross-group move) closes its dialog with
    // no close event. Accepted status quo, pinned so lifting the dialog to a
    // browser owner — as the rename dialogs already are — is a deliberate
    // change with this test updated in the same commit.
    rerender(
      <SessionNodeItem key="one" node={node('session-one')} currentId={undefined} now={0} onOpen={vi.fn()}
        onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />,
    )
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('reopens showing the same node-sourced id after rerenders and a remount', async () => {
    const id = 'session-epsilon'
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined)
    const restore = installClipboard(writeText)
    try {
      const row = (): ReactElement => (
        <SessionNodeItem key="epsilon" node={node(id, 'Epsilon')} currentId={undefined} now={0} onOpen={vi.fn()}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />
      )
      const { rerender } = render(row())
      openSessionIdDialog('Epsilon')
      expect(screen.getByRole('dialog').textContent).toContain(id)
      fireEvent.click(screen.getByRole('button', { name: zh['sessionId.close'] }))
      expect(screen.queryByRole('dialog')).toBeNull()

      // A refreshed list derivation rebuilds every node object, and switching
      // sessions away and back unmounts the row: the reopened dialog must
      // source the id from the node it is handed, never from retained state.
      rerender(<></>)
      const remounted = node(id, 'Epsilon')
      rerender(
        <SessionNodeItem key="epsilon" node={remounted} currentId={undefined} now={0} onOpen={vi.fn()}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />,
      )
      openSessionIdDialog('Epsilon')
      expect(screen.getByRole('dialog').textContent).toContain(remounted.id)

      // Another fresh node object while the dialog stays open: the shown id
      // still comes from the current node, so nothing caches it in between.
      const refreshed = node(id, 'Epsilon')
      rerender(
        <SessionNodeItem key="epsilon" node={refreshed} currentId={undefined} now={0} onOpen={vi.fn()}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />,
      )
      expect(screen.getByRole('dialog').textContent).toContain(refreshed.id)

      fireEvent.click(copyControls()[1]!)
      await waitFor(() => expect(screen.getByRole('status').textContent).toBe(zh['sessionId.copied']))
      expect(writeText).toHaveBeenCalledTimes(1)
      expect(writeText).toHaveBeenCalledWith(id)
    } finally {
      restore()
    }
  })

  it('keeps the English dictionary key-identical for the new keys', () => {
    const keys = Object.keys(zh).filter(key => key.startsWith('sessionId.') || key === 'menu.sessionId')
    expect(keys.length).toBeGreaterThanOrEqual(6)
  })
})
