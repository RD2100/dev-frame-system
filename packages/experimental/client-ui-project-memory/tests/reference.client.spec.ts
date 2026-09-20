/** The conversation-reference controller appends to the current draft and
 * never creates or switches sessions: without a current session scope the
 * action is an explicit no-op. */

import { describe, expect, it, vi } from 'vitest'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import { LibraryReferenceController } from '../src/client/reference.ts'

interface InputFacadeMock {
  state: { getSnapshot: () => { draft: string } }
  setDraft: ReturnType<typeof vi.fn>
}

function inputFacade(draft: string): InputFacadeMock {
  return {
    state: { getSnapshot: () => ({ draft }) },
    setDraft: vi.fn(),
  }
}

function ctx(overrides: {
  current?: string | undefined
  scope?: unknown
  input?: InputFacadeMock
  startSession?: ReturnType<typeof vi.fn>
} = {}): ClientContext {
  const input = overrides.input ?? inputFacade('')
  return {
    sessions: {
      list: { getSnapshot: () => ({ current: overrides.current, byId: {}, entries: [] }) },
      scope: vi.fn((id: string) => (overrides.scope === undefined ? undefined : { id })),
    },
    conversation: { input: { for: vi.fn(() => input) } },
    uiWorkspace: { startSession: overrides.startSession ?? vi.fn() },
  } as unknown as ClientContext
}

describe('LibraryReferenceController', () => {
  it('appends the reference line to an existing draft without overwriting it', () => {
    const input = inputFacade('帮我看看这个文件')
    const controller = new LibraryReferenceController(ctx({ current: 's1', scope: {}, input }))
    expect(controller.reference('@vault:D:\\vault\\a.md')).toBe(true)
    expect(input.setDraft).toHaveBeenCalledWith('帮我看看这个文件\n@vault:D:\\vault\\a.md')
  })

  it('sets the line directly on an empty draft', () => {
    const input = inputFacade('')
    const controller = new LibraryReferenceController(ctx({ current: 's1', scope: {}, input }))
    expect(controller.reference('@vault:D:\\vault\\a.md')).toBe(true)
    expect(input.setDraft).toHaveBeenCalledWith('@vault:D:\\vault\\a.md')
  })

  it('is a no-op without a current session and never creates one', () => {
    const startSession = vi.fn()
    const controller = new LibraryReferenceController(ctx({ current: undefined, startSession }))
    expect(controller.reference('@vault:D:\\vault\\a.md')).toBe(false)
    expect(startSession).not.toHaveBeenCalled()
  })

  it('is a no-op when the current session has no conversation scope', () => {
    const startSession = vi.fn()
    const controller = new LibraryReferenceController(ctx({ current: 's1', scope: undefined, startSession }))
    expect(controller.reference('@vault:D:\\vault\\a.md')).toBe(false)
    expect(startSession).not.toHaveBeenCalled()
  })
})
