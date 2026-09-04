// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { makeTranslate } from '@deepseek-ai/dsh-client-test-runtime'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import { SessionIdBadge, type SessionIdBadgeProps } from '../src/client/SessionIdBadge.tsx'
import { zh } from '../src/client/locales.ts'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

beforeEach(() => {
  vi.useFakeTimers()
})

const SESSION = 'session-abc123' as SessionId
const t: SessionIdBadgeProps['t'] = makeTranslate(zh)

function props(sessionId: SessionId | undefined): SessionIdBadgeProps {
  return { sessionId, t } as unknown as SessionIdBadgeProps
}

describe('SessionIdBadge', () => {
  it('renders nothing without a session id so the blank Hero stays clean', () => {
    const { container } = render(<SessionIdBadge {...props(undefined)} />)
    expect(container.innerHTML).toBe('')
  })

  it('shows the session id verbatim', () => {
    render(<SessionIdBadge {...props(SESSION)} />)
    expect(screen.getByLabelText(zh['badge.aria']).textContent).toContain(SESSION)
  })

  it('copies the full id and shows success feedback for one second', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    render(<SessionIdBadge {...props(SESSION)} />)
    fireEvent.click(screen.getByRole('button', { name: zh.copy }))
    await act(async () => { await Promise.resolve() })
    expect(writeText).toHaveBeenCalledWith(SESSION)
    expect(screen.getByRole('button', { name: zh.copied })).toBeDefined()
    act(() => { vi.advanceTimersByTime(1_000) })
    expect(screen.getByRole('button', { name: zh.copy })).toBeDefined()
  })

  it('keeps the copy affordance when the host refuses the write', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockRejectedValue(new Error('denied'))
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    render(<SessionIdBadge {...props(SESSION)} />)
    fireEvent.click(screen.getByRole('button', { name: zh.copy }))
    await act(async () => { await Promise.resolve() })
    expect(screen.getByRole('button', { name: zh.copy })).toBeDefined()
  })
})
