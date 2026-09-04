// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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

  it('keeps the English dictionary key-identical for the new keys', () => {
    const keys = Object.keys(zh).filter(key => key.startsWith('sessionId.') || key === 'menu.sessionId')
    expect(keys.length).toBeGreaterThanOrEqual(6)
  })
})
