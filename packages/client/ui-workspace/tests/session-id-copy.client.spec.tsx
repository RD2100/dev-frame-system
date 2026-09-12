// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import { makeTranslate } from '@deepseek-ai/dsh-client-test-runtime'
import { zh as commonZh } from '@deepseek-ai/dsh-client-locale/src/locales/zh.ts'
import { AgentNodeItem, SessionNodeItem } from '../src/client/rows/Rows.tsx'
import type { AgentNode, SessionNode } from '../src/client/tree.ts'
import { en, zh } from '../src/client/locales.ts'

afterEach(cleanup)

const t = makeTranslate(zh, commonZh) as never
const sid = (id: string) => id as SessionId

function sessionNode(id: string, title = `Title ${id}`): SessionNode {
  return {
    id: sid(id), title, blank: false, running: false,
    runningSubagentCount: 0, completed: false, hasActiveSchedule: false, updatedAt: 0,
  }
}

function agentNode(id: string, title = `Title ${id}`): AgentNode {
  return {
    id: sid(id), title, blank: false, running: false,
    runningSubagentCount: 0, completed: false, hasActiveSchedule: false, updatedAt: 0,
    children: [],
  }
}

function renderSessionRow(node: SessionNode, onOpen = vi.fn()): void {
  render(<SessionNodeItem node={node} currentId={undefined} now={0} onOpen={onOpen}
    onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t} />)
}

function renderAgentRow(node: AgentNode): void {
  render(<AgentNodeItem node={node} depth={0} currentId={undefined} now={0}
    expandedOf={() => false} onToggle={vi.fn()} onOpen={vi.fn()}
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

/** Open a row's actions menu and choose its direct-copy action. */
function copySessionIdFromMenu(title: string): void {
  fireEvent.click(screen.getByRole('button', { name: `会话“${title}”的操作` }))
  fireEvent.click(screen.getByRole('menuitem', { name: zh['menu.sessionId'] }))
}

describe('Session-ID menu action', () => {
  it('offers a copy action without opening the session or a dialog', () => {
    const onOpen = vi.fn()
    renderSessionRow(sessionNode('session-alpha'), onOpen)
    copySessionIdFromMenu('Title session-alpha')

    expect(onOpen).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('copies the complete Session ID directly from a session row', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined)
    const restore = installClipboard(writeText)
    try {
      const id = 'session-alpha-0123456789abcdef0123456789abcdef01234567'
      renderSessionRow(sessionNode(id, 'Alpha'))
      copySessionIdFromMenu('Alpha')

      await waitFor(() =>{  expect(writeText).toHaveBeenCalledWith(id) })
      expect(screen.queryByRole('dialog')).toBeNull()
      expect(screen.getByRole('alert').textContent).toBe(zh['sessionId.copied'])
    } finally {
      restore()
    }
  })

  it('uses the same direct-copy action for an Agent tree row', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined)
    const restore = installClipboard(writeText)
    try {
      const id = 'agent-session-0123456789abcdef'
      renderAgentRow(agentNode(id, 'Lead'))
      copySessionIdFromMenu('Lead')

      await waitFor(() =>{  expect(writeText).toHaveBeenCalledWith(id) })
      expect(screen.queryByRole('dialog')).toBeNull()
      expect(screen.getByRole('alert').textContent).toBe(zh['sessionId.copied'])
    } finally {
      restore()
    }
  })

  it('reports a refused clipboard write without claiming success', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockRejectedValue(new Error('denied'))
    const restore = installClipboard(writeText)
    try {
      renderSessionRow(sessionNode('session-denied'))
      copySessionIdFromMenu('Title session-denied')

      const alert = await screen.findByRole('alert')
      await waitFor(() =>{  expect(alert.textContent).toBe(zh['sessionId.copyFailed']) })
      expect(screen.queryByText(zh['sessionId.copied'])).toBeNull()
    } finally {
      restore()
    }
  })

  it('keeps the menu and feedback wording available in both locales', () => {
    expect(zh['menu.sessionId']).toBe('复制会话 ID')
    expect(en['menu.sessionId']).toBe('Copy session ID')
    expect(zh['sessionId.copied']).toBe('已复制')
    expect(zh['sessionId.copyFailed']).toBe('复制失败，请重试。')
  })
})
