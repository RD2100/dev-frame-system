// @vitest-environment jsdom
/** The resident card: trigger opens a chat dialog, manage opens a settings
 *  dropdown. The card renders honest phases, the conversation surface, and
 *  the chat post verb's success and failure surfaces. */

import { useSyncExternalStore } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ShadowStatusBinding } from '@deepseek-ai/dsh-experimental-shadow-routing'
import type { RemoteResult } from '@deepseek-ai/dsh-typert-protocol'
import type { ShadowConversationAccepted, ShadowConversationMessage, ShadowConversationPage, ShadowConversationReadInput, ShadowStatusView } from '@deepseek-ai/dsh-experimental-shadow-controller'
import { ShadowCard, type ShadowCardProps } from '../src/client/ShadowCard.tsx'
import { zh, type ShadowKey } from '../src/client/locales.ts'
import { ShadowConversationController } from '../src/client/shadow-conversation-store.ts'
import { ShadowStatusController, type ShadowStatusPort } from '../src/client/shadow-store.ts'

const t = ((key: ShadowKey, params?: Record<string, string | number>) => {
  const text = zh[key]
  return params === undefined
    ? text
    : Object.entries(params).reduce((acc, [name, value]) => acc.replaceAll(`{${name}}`, String(value)), text)
}) as unknown as ShadowCardProps['t']

// The card consumes only the status and conversation faces; the seat's
// standard hooks stay unused, so their stubs fail loud if a future edit
// starts reading them.
const unusedHook = (() => { throw new Error('unused by the shadow card') }) as never
const wid = (id: string): ShadowStatusBinding['workspaceId'] => id as ShadowStatusBinding['workspaceId']

const ONLINE_VIEW: ShadowStatusView = {
  mounted: true,
  shadowSessionId: 'session-shadow',
  shadowLive: true,
  authorizedRoots: ['D:/projects', 'D:/work'],
  bindings: [{
    workspaceId: wid('ws-1'),
    canonicalPath: 'D:/projects/alpha',
    bindingRevision: 7,
    state: 'ready' as const,
  }],
}

type ChatAnswer =
  | { ok: true; value: { messages: ShadowConversationMessage[]; cursor: number } }
  | { ok: false; error: { code: string; message: string; details: Record<string, never> } }

const CHAT_ROW: ShadowConversationMessage = { seq: 4, role: 'user', text: '帮我把 demo 跑起来', at: '2026-09-10T12:00:00.000Z' }
const CHAT_REPLY: ShadowConversationMessage = { seq: 5, role: 'shadow', text: '好的，正在启动。', at: '2026-09-10T12:00:05.000Z' }
const EMPTY_PAGE: ChatAnswer = { ok: true, value: { messages: [], cursor: 0 } }

interface ChatBench {
  controller: ShadowConversationController
  reads: ReturnType<typeof vi.fn>
  onPostMessage: ReturnType<typeof vi.fn>
}

function chatBench(
  _readsAnswer: ChatAnswer = EMPTY_PAGE,
): ChatBench {
  const reads = vi.fn<(request: ShadowConversationReadInput) => Promise<RemoteResult<ShadowConversationPage>>>(
    (): Promise<RemoteResult<ShadowConversationPage>> => Promise.resolve(EMPTY_PAGE as RemoteResult<ShadowConversationPage>),
  )
  const controller = new ShadowConversationController(async request => await reads(request))
  const onPostMessage = vi.fn(async (): Promise<RemoteResult<ShadowConversationAccepted>> =>
    ({ ok: true, value: { messageId: 'msg-chat-1' } }))
  return { controller, reads, onPostMessage }
}

interface Bench {
  controller: ShadowStatusController
  onRefresh: ReturnType<typeof vi.fn>
  onOpenConversation: ReturnType<typeof vi.fn>
  chat: ChatBench
  props: ShadowCardProps
  ready: Promise<void>
}

function bench(
  answer: { ok: true; value: ShadowStatusView } | { ok: false; error: { code: string; message: string; details: Record<string, never> } } | 'hang' = { ok: true, value: { ...ONLINE_VIEW } },
  chat: ChatBench = chatBench(),
): Bench {
  const port: ShadowStatusPort = () => {
    if (answer === 'hang') return new Promise(() => {})
    return Promise.resolve(answer as { ok: true; value: ShadowStatusView })
  }
  const controller = new ShadowStatusController(port)
  const onRefresh = vi.fn(() => { void controller.refresh() })
  const onOpenConversation = vi.fn(async () => {})
  // useStatus and useConversation are bound selector hooks produced by InjectFace
  // from the hooks compartment; the bench wires them to the real stores.
  const useStatus = (selector: (s: ShadowStatusSnapshot) => ShadowStatusSnapshot) =>
    useSyncExternalStore(controller.store.subscribe, () => selector(controller.store.getSnapshot()))
  const useConversation = (selector: (s: ShadowConversationSnapshot) => ShadowConversationSnapshot) =>
    useSyncExternalStore(chat.controller.store.subscribe, () => selector(chat.controller.store.getSnapshot()))
  // Pre-load the status so the first render sees a settled snapshot.
  const ready = controller.refresh()
  const props: ShadowCardProps = {
    wide: true,
    useStatus,
    useConversation,
    onRefresh,
    onOpenConversation,
    onLoadConversation: () => { void chat.controller.loadTail() },
    onPollConversation: () => { void chat.controller.poll() },
    onPostMessage: chat.onPostMessage,
    t,
    useSessions: unusedHook,
    useSessionPendingInteraction: unusedHook,
    useWorkspaces: unusedHook,
  } satisfies ShadowCardProps
  return { controller, onRefresh, onOpenConversation, chat, props, ready }
}

/** Render, settle the first read, and open the chat dialog via the trigger. */
async function openChat(
  answer?: { ok: true; value: ShadowStatusView } | { ok: false; error: { code: string; message: string; details: Record<string, never> } } | 'hang',
  chat?: ChatBench,
): Promise<{ container: HTMLElement } & Bench> {
  const b = bench(answer, chat)
  await act(async () => { await b.ready })
  const rendered = render(<ShadowCard {...b.props} />)
  await act(async () => { await Promise.resolve() })
  const trigger = screen.getByRole('button', { name: '打开影子对话' })
  fireEvent.click(trigger)
  return { container: rendered.container, ...b }
}

afterEach(cleanup)

describe('the sidebar Shadow entry card', () => {
  it('renders the resident trigger and refreshes once on mount', async () => {
    const b = bench()
    await act(async () => { await b.ready })
    render(<ShadowCard {...b.props} />)
    const trigger = screen.getByRole('button', { name: '打开影子对话' })
    await act(async () => { await Promise.resolve() })
    expect(trigger.getAttribute('data-shadow-phase')).toBe('online')
    expect(b.onRefresh).toHaveBeenCalledTimes(1)
    fireEvent.click(trigger)
    expect(b.onOpenConversation).toHaveBeenCalledTimes(1)
  })

  it('opens the chat dialog on trigger click and shows the conversation surface', async () => {
    const b = await openChat()
    const dialog = screen.getByRole('dialog', { name: '对话' })
    expect(dialog).not.toBeNull()
    expect(b.container.querySelector('[data-shadow-chat-dialog]')).not.toBeNull()
    // The dialog renders its body when actionable (online/configured); with no
    // messages it shows the empty-state paragraph, with messages the list.
    const hasChatSurface = b.container.querySelector('[data-shadow-chat-list]') !== null
      || b.container.querySelector('[data-shadow-chat-empty]') !== null
    if (!hasChatSurface) {
      console.log('FULL DIALOG HTML:', dialog.innerHTML)
      console.log('FULL CONTAINER:', b.container.innerHTML.substring(0, 500))
    }
    expect(hasChatSurface).toBe(true)
    expect(b.container.querySelector('[data-shadow-chat-input]')).not.toBeNull()
    expect(b.container.querySelector('[data-shadow-chat-input]')).not.toBeNull()
    expect(b.container.querySelector('[data-shadow-chat-submit]')).not.toBeNull()
  })

  it('shows the empty-state copy when the conversation has no rows', async () => {
    const b = await openChat()
    await act(async () => { await Promise.resolve() })
    expect(b.container.querySelector('[data-shadow-chat-empty]')?.textContent).toBe('还没有消息——发一条开始对话。')
    expect(b.container.querySelector('[data-shadow-chat-list]')).toBeNull()
  })

  it('loads the conversation tail when the chat dialog opens online and renders the rows', async () => {
    const chat = chatBench()
    chat.reads.mockResolvedValueOnce({ ok: true, value: { messages: [CHAT_ROW, CHAT_REPLY], cursor: 5 } })
    const b = await openChat(undefined, chat)
    await act(async () => { await Promise.resolve() })
    expect(chat.reads).toHaveBeenCalledExactlyOnceWith({})
    expect(b.container.querySelectorAll('[data-shadow-chat-list] [data-shadow-chat-row]')).toHaveLength(2)
    expect(b.container.querySelector('[data-shadow-chat-row="user"]')?.textContent).toContain('帮我把 demo 跑起来')
    expect(b.container.querySelector('[data-shadow-chat-row="shadow"]')?.textContent).toContain('好的，正在启动。')
    expect(b.container.textContent).toContain('你')
    expect(b.container.textContent).toContain('影子')
  })

  it('offers no conversation input while the Shadow is not online', async () => {
    await openChat({ ok: true, value: { ...ONLINE_VIEW, shadowLive: false } })
    // Configured-but-not-live is actionable: the dialog opens but shows the
    // offline notice, with no input or submit button.
    const dialog = screen.queryByRole('dialog', { name: '对话' })
    expect(dialog).not.toBeNull()
    const offline = dialog?.querySelector('[data-shadow-chat-offline]')
    expect(offline?.textContent).toBe('Shadow 在线后可开始对话。')
    expect(dialog?.querySelector('[data-shadow-chat-input]')).toBeNull()
    expect(dialog?.querySelector('[data-shadow-chat-submit]')).toBeNull()
  })

  it('shows the conversation read failure verbatim', async () => {
    const chat = chatBench()
    chat.reads.mockResolvedValue({ ok: false, error: { code: 'gateway/internal', message: 'conversation host missing', details: {} } })
    const b = await openChat(undefined, chat)
    await act(async () => { await Promise.resolve() })
    expect(b.container.querySelector('[data-shadow-chat-read-error]')?.textContent).toBe('读取对话失败：conversation host missing')
  })

  it('posts one chat message, polls for the surface, and clears the draft', async () => {
    const chat = chatBench()
    const b = await openChat(undefined, chat)
    await act(async () => { await Promise.resolve() })
    chat.reads.mockResolvedValueOnce({ ok: true, value: { messages: [CHAT_ROW], cursor: 4 } })
    const input = b.container.querySelector('[data-shadow-chat-input]') as HTMLTextAreaElement
    await act(async () => { fireEvent.change(input, { target: { value: '  帮我把 demo 跑起来  ' } }) })
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-chat-submit]') as HTMLElement) })
    expect(chat.onPostMessage).toHaveBeenCalledExactlyOnceWith('帮我把 demo 跑起来')
    expect(chat.reads).toHaveBeenCalledWith({ after: 0 })
    expect(b.container.querySelector('[data-shadow-chat-row="user"]')?.textContent).toContain('帮我把 demo 跑起来')
    expect((b.container.querySelector('[data-shadow-chat-input]') as HTMLTextAreaElement).value).toBe('')
  })

  it('shows the pending line while a chat post is in flight', async () => {
    const chat = chatBench()
    chat.onPostMessage.mockReturnValueOnce(new Promise<RemoteResult<ShadowConversationAccepted>>(() => {}))
    const b = await openChat(undefined, chat)
    await act(async () => { await Promise.resolve() })
    const input = b.container.querySelector('[data-shadow-chat-input]') as HTMLTextAreaElement
    await act(async () => { fireEvent.change(input, { target: { value: 'hello shadow' } }) })
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-chat-submit]') as HTMLElement) })
    expect(b.container.querySelector('[data-shadow-chat-pending]')).not.toBeNull()
  })

  it('submits the chat draft on Enter', async () => {
    const chat = chatBench()
    const b = await openChat(undefined, chat)
    await act(async () => { await Promise.resolve() })
    const input = b.container.querySelector('[data-shadow-chat-input]') as HTMLTextAreaElement
    await act(async () => { fireEvent.change(input, { target: { value: 'hello shadow' } }) })
    await act(async () => { fireEvent.keyDown(input, { key: 'Enter' }) })
    expect(chat.onPostMessage).toHaveBeenCalledExactlyOnceWith('hello shadow')
  })

  it('ignores a blank chat draft on Enter and leaves other keys alone', async () => {
    const chat = chatBench()
    const b = await openChat(undefined, chat)
    await act(async () => { await Promise.resolve() })
    const input = b.container.querySelector('[data-shadow-chat-input]') as HTMLTextAreaElement
    await act(async () => { fireEvent.keyDown(input, { key: 'Enter' }) })
    await act(async () => { fireEvent.keyDown(input, { key: 'a' }) })
    await act(async () => { fireEvent.keyDown(input, { key: 'Enter', shiftKey: true }) })
    expect(chat.onPostMessage).not.toHaveBeenCalled()
  })

  it('shows the send failure verbatim and keeps the draft', async () => {
    const chat = chatBench()
    chat.onPostMessage.mockResolvedValue({ ok: false, error: { code: 'gateway/internal', message: 'the conversation is unavailable' } })
    const b = await openChat(undefined, chat)
    await act(async () => { await Promise.resolve() })
    const input = b.container.querySelector('[data-shadow-chat-input]') as HTMLTextAreaElement
    await act(async () => { fireEvent.change(input, { target: { value: 'hello shadow' } }) })
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-chat-submit]') as HTMLElement) })
    expect(b.container.querySelector('[data-shadow-chat-send-failed]')?.textContent).toBe('发送失败：the conversation is unavailable')
    expect((b.container.querySelector('[data-shadow-chat-input]') as HTMLTextAreaElement).value).toBe('hello shadow')
  })

  it('polls the conversation on an interval while the chat dialog is open and online', async () => {
    vi.useFakeTimers()
    try {
      const chat = chatBench()
      const b = await openChat(undefined, chat)
      await act(async () => { await Promise.resolve() })
      const readsAfterOpen = chat.reads.mock.calls.length
      expect(readsAfterOpen).toBeGreaterThanOrEqual(1) // the tail load on open
      await act(async () => { await vi.advanceTimersByTimeAsync(6500) })
      expect(chat.reads.mock.calls.length).toBeGreaterThan(readsAfterOpen)
      const closing = b
      fireEvent.click(screen.getByRole('button', { name: '关闭' }))
      await act(async () => { await Promise.resolve() })
      const readsAfterClose = closing.chat.reads.mock.calls.length
      await act(async () => { await vi.advanceTimersByTimeAsync(9000) })
      expect(closing.chat.reads.mock.calls.length).toBe(readsAfterClose)
    } finally {
      vi.useRealTimers()
    }
  })

  it('closes the chat dialog on an outside pointerdown and re-reads status on next open', async () => {
    const b = bench()
    await act(async () => { await b.ready })
    render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    const trigger = screen.getByRole('button', { name: '打开影子对话' })
    // First open: mount refresh (1) + chat-open refresh (2).
    fireEvent.click(trigger)
    expect(screen.getByRole('dialog', { name: '对话' })).not.toBeNull()
    expect(b.onRefresh).toHaveBeenCalledTimes(2)
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('dialog', { name: '对话' })).toBeNull()
    // Re-open triggers another status read.
    fireEvent.click(trigger)
    expect(b.onRefresh).toHaveBeenCalledTimes(3)
  })

  it('renders the manage dropdown with status, roots, and controller info', async () => {
    await openChat()
    const manage = screen.getByRole('button', { name: '管理' })
    fireEvent.click(manage)
    const menu = screen.getByRole('menu')
    expect(menu).not.toBeNull()
    expect(menu.textContent).toContain('Shadow 状态')
    expect(menu.textContent).toContain('控制者会话')
    expect(menu.textContent).toContain('session-shadow')
    expect(menu.textContent).toContain('授权根目录')
    expect(menu.textContent).toContain('D:/projects')
    expect(menu.textContent).toContain('控制器')
    expect(menu.textContent).toContain('控制器预设')
  })

  it('renders the rail mode without the label', async () => {
    const b = bench()
    render(<ShadowCard {...b.props} wide={false} />)
    await act(async () => { await Promise.resolve() })
    expect(screen.queryByText('影子')).toBeNull()
    expect(screen.getByRole('button', { name: '打开影子对话' })).not.toBeNull()
  })

  it('keeps the not-enabled copy honest while the router is mounted but unconfigured', async () => {
    const b = bench({ ok: true, value: { mounted: true, shadowLive: true, authorizedRoots: ['D:/projects'], bindings: [] } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="disabled"]')).not.toBeNull()
    const trigger = screen.getByRole('button', { name: '打开影子对话' })
    fireEvent.click(trigger)
    // Not actionable: the trigger calls onOpenConversation but opens no dialog.
    expect(screen.queryByRole('dialog', { name: '对话' })).toBeNull()
    expect(b.onOpenConversation).toHaveBeenCalledTimes(1)
  })

  it('reads an absent router as the honest not-enabled state', async () => {
    const b = bench({ ok: true, value: { mounted: false, shadowLive: true, authorizedRoots: [], bindings: [] } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="unmounted"]')).not.toBeNull()
    // Not actionable: no dialog, no detail text in the container.
    expect(screen.queryByRole('dialog', { name: '对话' })).toBeNull()
  })

  it('reads a configured designation whose session is not live as configured, not online', async () => {
    const b = bench({ ok: true, value: { ...ONLINE_VIEW, shadowLive: false } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="configured"]')).not.toBeNull()
    // Configured is actionable: the trigger opens the dialog.
    const trigger = screen.getByRole('button', { name: '打开影子对话' })
    fireEvent.click(trigger)
    expect(screen.getByRole('dialog', { name: '对话' })).not.toBeNull()
    expect(container.textContent).toContain('控制者会话尚未标记为 Shadow。')
    expect(container.textContent).toContain('session-shadow')
  })

  it('shows the read failure instead of pretending a state', async () => {
    const b = bench({ ok: false, error: { code: 'gateway/internal', message: 'offline', details: {} } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="error"]')).not.toBeNull()
    // The error is recorded on the trigger button's data-shadow-error attribute.
    expect(container.querySelector('[data-shadow-error]')?.getAttribute('data-shadow-error')).toBe('offline')
  })

  it('stays in the loading phase until the first read settles', () => {
    const b = bench('hang')
    const { container } = render(<ShadowCard {...b.props} />)
    expect(container.querySelector('[data-shadow-phase="loading"]')).not.toBeNull()
    const trigger = screen.getByRole('button', { name: '打开影子对话' })
    fireEvent.click(trigger)
    expect(screen.queryByRole('dialog', { name: '对话' })).toBeNull()
  })

  it('shows the empty-copy line when the enabled deployment has no roots', async () => {
    await openChat({ ok: true, value: { ...ONLINE_VIEW, authorizedRoots: [] } })
    const manage = screen.getByRole('button', { name: '管理' })
    fireEvent.click(manage)
    expect(screen.getByText('未授权任何根目录。')).not.toBeNull()
  })

  it('closes the chat dialog from the header close button', async () => {
    await openChat()
    expect(screen.getByRole('dialog', { name: '对话' })).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    expect(screen.queryByRole('dialog', { name: '对话' })).toBeNull()
  })

  it('opens the chat dialog again after closing and re-triggers the tail load', async () => {
    const chat = chatBench()
    chat.reads.mockResolvedValueOnce({ ok: true, value: { messages: [CHAT_ROW], cursor: 4 } })
    await openChat(undefined, chat)
    await act(async () => { await Promise.resolve() })
    const initialReads = chat.reads.mock.calls.length
    // Close and reopen.
    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    await act(async () => { await Promise.resolve() })
    fireEvent.click(screen.getByRole('button', { name: '打开影子对话' }))
    await act(async () => { await Promise.resolve() })
    expect(chat.reads.mock.calls.length).toBeGreaterThan(initialReads)
  })
})
