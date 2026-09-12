// @vitest-environment jsdom
/** The resident card: honest phases, the actionable panel, and the write verbs' success and failure surfaces. */

import { useSyncExternalStore } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ProjectOpenResult, ProjectSendResult, ProjectStopResult, ShadowMessageId, ShadowStatusBinding } from '@deepseek-ai/dsh-experimental-shadow-router'
import { RemoteError, type RemoteResult } from '@deepseek-ai/dsh-typert-protocol'
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

// The card consumes only the status face; the seat's standard hooks stay
// unused, so their stubs fail loud if a future edit starts reading them.
const unusedHook = (() => { throw new Error('unused by the shadow card') }) as never
const wid = (id: string): ShadowStatusBinding['workspaceId'] => id as ShadowStatusBinding['workspaceId']
const sid = (id: string): ProjectOpenResult['controllerSessionId'] => id as ProjectOpenResult['controllerSessionId']

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

const OPENED: ProjectOpenResult = {
  workspaceId: wid('ws-2'),
  controllerSessionId: sid('session-controller'),
  bindingRevision: 1,
  state: 'ready',
  canonicalPath: 'D:/projects/beta',
}

type WriteResult<T> = RemoteResult<T>

interface WriteBench {
  onOpenProject: ReturnType<typeof vi.fn>
  onSendToController: ReturnType<typeof vi.fn>
  onReleaseProject: ReturnType<typeof vi.fn>
}

/** Scripted write verbs; every verb resolves ok unless its failure is set. */
function writeBench(failure?: { message: string }): WriteBench {
  const fail = failure === undefined
    ? undefined
    : <T,>(_value: T): WriteResult<T> => ({ ok: false, error: new RemoteError('gateway/internal', failure.message, {}) })
  return {
    onOpenProject: vi.fn(async (path: string): Promise<WriteResult<ProjectOpenResult>> =>
      fail !== undefined ? fail(OPENED) : { ok: true, value: { ...OPENED, canonicalPath: path } }),
    onSendToController: vi.fn(async (): Promise<WriteResult<ProjectSendResult>> =>
      fail !== undefined
        ? fail({ status: 'received', workspaceId: wid('ws-1'), messageId: 'msg-1' as ShadowMessageId })
        : { ok: true, value: { status: 'received', workspaceId: wid('ws-1'), messageId: 'msg-1' as ShadowMessageId } }),
    onReleaseProject: vi.fn(async (): Promise<WriteResult<ProjectStopResult>> =>
      fail !== undefined
        ? fail({ workspaceId: wid('ws-1'), status: 'stopped', cancelledDeliveries: 0, bindingRevision: 2 })
        : { ok: true, value: { workspaceId: wid('ws-1'), status: 'stopped', cancelledDeliveries: 0, bindingRevision: 2 } }),
  }
}

type TestAnswer =
  | { ok: true; value: typeof ONLINE_VIEW }
  | { ok: false; error: { code: string; message: string; details: Record<string, never> } }
  | 'hang'

type ConversationAnswer =
  | { ok: true; value: { messages: ShadowConversationMessage[]; cursor: number } }
  | { ok: false; error: { code: string; message: string; details: Record<string, never> } }

const CHAT_ROW: ShadowConversationMessage = { seq: 4, role: 'user', text: '帮我把 demo 跑起来', at: '2026-09-10T12:00:00.000Z' }
const CHAT_REPLY: ShadowConversationMessage = { seq: 5, role: 'shadow', text: '好的，正在启动。', at: '2026-09-10T12:00:05.000Z' }
const EMPTY_PAGE: ConversationAnswer = { ok: true, value: { messages: [], cursor: 0 } }

interface ChatBench {
  controller: ShadowConversationController
  reads: ReturnType<typeof vi.fn>
  onPostMessage: ReturnType<typeof vi.fn>
}

/** A real conversation controller over a scripted read port; tests queue answers per call. */
function chatBench(): ChatBench {
  const reads = vi.fn<(request: ShadowConversationReadInput) => Promise<RemoteResult<ShadowConversationPage>>>(
    (): Promise<RemoteResult<ShadowConversationPage>> => Promise.resolve(EMPTY_PAGE as RemoteResult<ShadowConversationPage>),
  )
  const controller = new ShadowConversationController(reads)
  const onPostMessage = vi.fn(async (): Promise<RemoteResult<ShadowConversationAccepted>> =>
    ({ ok: true, value: { messageId: 'msg-chat-1' } }))
  return { controller, reads, onPostMessage }
}

/** Bench: a real controller over a scripted port plus the framework stubs. */
function bench(
  answer: TestAnswer = { ok: true, value: { ...ONLINE_VIEW } },
  writes: WriteBench = writeBench(),
  chat: ChatBench = chatBench(),
): {
  controller: ShadowStatusController
  onRefresh: ReturnType<typeof vi.fn>
  onOpenConversation: ReturnType<typeof vi.fn>
  writes: WriteBench
  chat: ChatBench
  props: ShadowCardProps
} {
  const port: ShadowStatusPort = () => {
    if (answer === 'hang') return new Promise(() => {})
    return Promise.resolve(answer as Awaited<ReturnType<ShadowStatusPort>>)
  }
  const controller = new ShadowStatusController(port)
  const onRefresh = vi.fn(() => { void controller.refresh() })
  // Arrow wrappers keep the store subscribe calls off unbound-method references.
  const subscribeStatus = (listener: () => void) => controller.store.subscribe(listener)
  const subscribeConversation = (listener: () => void) => chat.controller.store.subscribe(listener)
  const props = {
    wide: true,
    // The renderer binds the declared hooks compartment to use<Name> seats;
    // the stub binds the same store through the framework's own channel.
    useStatus: ((selector: (snapshot: ReturnType<ShadowStatusController['store']['getSnapshot']>) => unknown) =>
      useSyncExternalStore(subscribeStatus, () => selector(controller.store.getSnapshot()))) as unknown as ShadowCardProps['useStatus'],
    useConversation: ((selector: (snapshot: ReturnType<ShadowConversationController['store']['getSnapshot']>) => unknown) =>
      useSyncExternalStore(subscribeConversation, () => selector(chat.controller.store.getSnapshot()))) as unknown as ShadowCardProps['useConversation'],
    onRefresh,
    onOpenConversation: vi.fn(async (): Promise<void> => {}),
    onLoadConversation: () => { void chat.controller.loadTail() },
    onPollConversation: () => { void chat.controller.poll() },
    onOpenProject: writes.onOpenProject as unknown as ShadowCardProps['onOpenProject'],
    onSendToController: writes.onSendToController as unknown as ShadowCardProps['onSendToController'],
    onReleaseProject: writes.onReleaseProject as unknown as ShadowCardProps['onReleaseProject'],
    onPostMessage: chat.onPostMessage as unknown as ShadowCardProps['onPostMessage'],
    t,
    useSessions: unusedHook,
    useSessionPendingInteraction: unusedHook,
    useWorkspaces: unusedHook,
  } satisfies ShadowCardProps
  return { controller, onRefresh, onOpenConversation: props.onOpenConversation as ReturnType<typeof vi.fn>, writes, chat, props }
}

/** Render, settle the first read, and open the panel. */
async function openPanel(answer?: TestAnswer, writes?: WriteBench, chat?: ChatBench): Promise<
  { container: HTMLElement } & ReturnType<typeof bench>
> {
  const b = bench(answer, writes, chat)
  const rendered = render(<ShadowCard {...b.props} />)
  await act(async () => { await Promise.resolve() })
  fireEvent.click(screen.getByRole('button', { name: '管理' }))
  return { container: rendered.container, ...b }
}

/** Switch the open dialog to the projects management view. */
function showProjects(b: { container: HTMLElement }): void {
  fireEvent.click(b.container.querySelector('[data-shadow-view-toggle]') as HTMLElement)
}

afterEach(cleanup)

describe('the sidebar Shadow entry card', () => {
  it('renders the resident trigger and refreshes once on mount', async () => {
    const b = bench()
    render(<ShadowCard {...b.props} />)
    const trigger = screen.getByRole('button', { name: '打开影子对话' })
    await act(async () => { await Promise.resolve() })
    expect(trigger.getAttribute('data-shadow-phase')).toBe('online')
    expect(b.onRefresh).toHaveBeenCalledTimes(1)
    fireEvent.click(trigger)
    expect(b.onOpenConversation).toHaveBeenCalledTimes(1)
  })

  it('opens the dialog on the conversation and switches to the multi-project list with roots, rows, and per-row actions', async () => {
    const b = await openPanel()
    expect(screen.getByRole('dialog', { name: 'Shadow 服务状态面板' })).not.toBeNull()
    expect(b.container.querySelector('[data-shadow-status]')?.textContent).toBe('在线')
    expect(b.container.querySelector('[data-shadow-session]')?.textContent).toBe('session-shadow')
    expect(b.container.querySelector('[data-shadow-chat]')).not.toBeNull()
    showProjects(b)
    expect(b.container.textContent).toContain('授权根目录')
    expect(b.container.textContent).toContain('D:/projects')
    expect(b.container.textContent).toContain('D:/work')
    expect(b.container.textContent).toContain('打开的项目')
    expect(b.container.querySelectorAll('[data-shadow-project]')).toHaveLength(1)
    expect(b.container.textContent).toContain('D:/projects/alpha')
    expect(b.container.textContent).toContain('ws-1')
    expect(b.container.textContent).toContain('修订 7')
    expect(b.container.textContent).toContain('就绪')
    expect(b.container.querySelector('[data-shadow-send="ws-1"]')).not.toBeNull()
    expect(b.container.querySelector('[data-shadow-release="ws-1"]')).not.toBeNull()
    expect(screen.getByRole('button', { name: '管理' }).getAttribute('aria-expanded')).toBe('true')
  })

  it('shows the empty-state copy and the open form when no project is open', async () => {
    const b = await openPanel({ ok: true, value: { ...ONLINE_VIEW, bindings: [] } })
    showProjects(b)
    expect(b.container.textContent).toContain('尚未打开任何项目——输入项目路径开始。')
    expect(b.container.querySelector('[data-shadow-open-input]')).not.toBeNull()
    expect(b.container.querySelector('[data-shadow-open]')).not.toBeNull()
    // The refactored surface speaks of open projects, never of bindings.
    expect(b.container.textContent).not.toContain('绑定')
  })

  it('opens a project from the form and lands the honest success line', async () => {
    const b = await openPanel()
    showProjects(b)
    const input = b.container.querySelector('[data-shadow-open-input]') as HTMLInputElement
    await act(async () => { fireEvent.change(input, { target: { value: 'D:/projects/beta' } }) })
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-open]') as HTMLElement) })
    expect(b.writes.onOpenProject).toHaveBeenCalledExactlyOnceWith('D:/projects/beta')
    expect(b.container.querySelector('[data-shadow-write]')?.textContent).toBe('项目已打开。')
    expect((b.container.querySelector('[data-shadow-open-input]') as HTMLInputElement).value).toBe('')
    expect(b.onRefresh).toHaveBeenCalledTimes(3) // mount + panel open + post-write
  })

  it('shows the service failure verbatim when the open is rejected', async () => {
    const b = await openPanel(undefined, writeBench({ message: 'root "D:/elsewhere" is not covered by any authorized root' }))
    showProjects(b)
    const input = b.container.querySelector('[data-shadow-open-input]') as HTMLInputElement
    await act(async () => { fireEvent.change(input, { target: { value: 'D:/elsewhere/gamma' } }) })
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-open]') as HTMLElement) })
    expect(b.writes.onOpenProject).toHaveBeenCalledExactlyOnceWith('D:/elsewhere/gamma')
    expect(b.container.querySelector('[data-shadow-write="failed"]')?.textContent)
      .toBe('操作失败：root "D:/elsewhere" is not covered by any authorized root')
    expect(b.onRefresh).toHaveBeenCalledTimes(2) // no refresh after a failure
  })

  it('sends one message to the project controller from the row input', async () => {
    const b = await openPanel()
    showProjects(b)
    const input = b.container.querySelector('[data-shadow-send-input="ws-1"]') as HTMLInputElement
    await act(async () => { fireEvent.change(input, { target: { value: 'ship the release' } }) })
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-send="ws-1"]') as HTMLElement) })
    expect(b.writes.onSendToController).toHaveBeenCalledExactlyOnceWith('ws-1', 'ship the release')
    expect(b.container.querySelector('[data-shadow-write]')?.textContent).toBe('消息已被项目总控接收。')
    expect((b.container.querySelector('[data-shadow-send-input="ws-1"]') as HTMLInputElement).value).toBe('')
  })

  it('ignores a blank row draft and a disabled open button', async () => {
    const b = await openPanel()
    showProjects(b)
    // The open button is disabled while the path is blank, so the write never starts.
    const open = b.container.querySelector('[data-shadow-open]') as HTMLButtonElement
    expect(open.disabled).toBe(true)
    await act(async () => { fireEvent.click(open) })
    // The send button stays enabled for an empty draft; the guard drops it.
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-send="ws-1"]') as HTMLElement) })
    expect(b.writes.onOpenProject).not.toHaveBeenCalled()
    expect(b.writes.onSendToController).not.toHaveBeenCalled()
    expect(b.container.querySelector('[data-shadow-write]')).toBeNull()
  })

  it('releases a project from its row and lands the honest success line', async () => {
    const b = await openPanel()
    showProjects(b)
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-release="ws-1"]') as HTMLElement) })
    expect(b.writes.onReleaseProject).toHaveBeenCalledExactlyOnceWith('ws-1')
    expect(b.container.querySelector('[data-shadow-write]')?.textContent).toBe('项目已解除并停止。')
  })

  it('shows the service failure verbatim when a release is rejected', async () => {
    const b = await openPanel(undefined, writeBench({ message: 'workspace "ws-1" is stopping and does not admit deliveries' }))
    showProjects(b)
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-release="ws-1"]') as HTMLElement) })
    expect(b.container.querySelector('[data-shadow-write="failed"]')?.textContent)
      .toBe('操作失败：workspace "ws-1" is stopping and does not admit deliveries')
  })

  it('locks every action while one write is in flight', async () => {
    const writes = {
      onOpenProject: vi.fn(async () => new Promise<WriteResult<ProjectOpenResult>>(() => {})),
      onSendToController: vi.fn(async (): Promise<WriteResult<ProjectSendResult>> => ({ ok: true, value: { status: 'received', workspaceId: wid('ws-1'), messageId: 'msg-1' as ShadowMessageId } })),
      onReleaseProject: vi.fn(async (): Promise<WriteResult<ProjectStopResult>> => ({ ok: true, value: { workspaceId: wid('ws-1'), status: 'stopped', cancelledDeliveries: 0, bindingRevision: 2 } })),
    }
    const b = await openPanel(undefined, writes)
    showProjects(b)
    const input = b.container.querySelector('[data-shadow-open-input]') as HTMLInputElement
    await act(async () => { fireEvent.change(input, { target: { value: 'D:/projects/beta' } }) })
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-open]') as HTMLElement) })
    expect(b.container.querySelector('[data-shadow-write="busy"]')?.textContent).toBe('正在执行…')
    expect((b.container.querySelector('[data-shadow-open]') as HTMLButtonElement).disabled).toBe(true)
    expect((b.container.querySelector('[data-shadow-send="ws-1"]') as HTMLButtonElement).disabled).toBe(true)
    expect((b.container.querySelector('[data-shadow-release="ws-1"]') as HTMLButtonElement).disabled).toBe(true)
  })

  it('hides per-row actions a state cannot serve: stopped rows keep no send or release', async () => {
    const b = await openPanel({ ok: true, value: {
      ...ONLINE_VIEW,
      bindings: [
        { workspaceId: wid('ws-1'), canonicalPath: 'D:/projects/alpha', bindingRevision: 7, state: 'ready' },
        { workspaceId: wid('ws-2'), canonicalPath: 'D:/projects/beta', bindingRevision: 8, state: 'stopped' },
      ],
    } })
    showProjects(b)
    expect(b.container.querySelectorAll('[data-shadow-project]')).toHaveLength(2)
    expect(b.container.querySelector('[data-shadow-send="ws-1"]')).not.toBeNull()
    expect(b.container.querySelector('[data-shadow-release="ws-1"]')).not.toBeNull()
    expect(b.container.querySelector('[data-shadow-send="ws-2"]')).toBeNull()
    expect(b.container.querySelector('[data-shadow-release="ws-2"]')).toBeNull()
    expect(b.container.textContent).toContain('已停止')
  })

  it('refreshes from the panel header button', async () => {
    const b = await openPanel()
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-refresh]') as HTMLElement) })
    expect(b.onRefresh).toHaveBeenCalledTimes(3) // mount + panel open + explicit
  })

  it('re-reads the status each time the panel opens', async () => {
    const b = bench()
    render(<ShadowCard {...b.props} />)
    const manage = screen.getByRole('button', { name: '管理' })
    await act(async () => { await Promise.resolve() })
    fireEvent.click(manage)
    fireEvent.click(manage)
    fireEvent.click(manage)
    expect(b.onRefresh).toHaveBeenCalledTimes(3)
  })

  it('keeps the not-enabled copy honest while the router is mounted but unconfigured', async () => {
    const b = bench({ ok: true, value: { mounted: true, shadowLive: true, authorizedRoots: ['D:/projects'], bindings: [] } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="disabled"]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '管理' }))
    expect(container.querySelector('[data-shadow-status]')?.textContent).toBe('Shadow 未启用')
    expect(container.textContent).toContain('宿主组合尚未声明控制者会话。')
    expect(container.querySelector('[data-shadow-session]')).toBeNull()
    expect(container.textContent).not.toContain('打开的项目')
  })

  it('reads an absent router as the honest not-enabled state with its own detail', async () => {
    const b = bench({ ok: true, value: { mounted: false, shadowLive: true, authorizedRoots: [], bindings: [] } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="unmounted"]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '管理' }))
    expect(container.textContent).toContain('此部署没有挂载 Shadow 服务。')
  })

  it('reads a configured designation whose session is not live as configured, not online', async () => {
    const b = bench({ ok: true, value: { ...ONLINE_VIEW, shadowLive: false } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="configured"]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '管理' }))
    expect(container.querySelector('[data-shadow-status]')?.textContent).toBe('已配置，未在线')
    expect(container.textContent).toContain('控制者会话尚未标记为 Shadow。')
    expect(container.textContent).toContain('session-shadow')
  })

  it('shows the read failure instead of pretending a state', async () => {
    const b = bench({ ok: false, error: { code: 'gateway/internal', message: 'offline', details: {} } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="error"]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '管理' }))
    expect(container.querySelector('[data-shadow-status]')?.textContent).toBe('状态读取失败')
    expect(container.querySelector('[data-shadow-error]')?.textContent).toBe('读取 Shadow 状态失败：offline')
  })

  it('stays in the loading phase until the first read settles', () => {
    const b = bench('hang')
    const { container } = render(<ShadowCard {...b.props} />)
    expect(container.querySelector('[data-shadow-phase="loading"]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '管理' }))
    expect(container.querySelector('[data-shadow-status]')?.textContent).toBe('读取状态中…')
  })

  it('shows the empty-copy line when the enabled deployment has no roots', async () => {
    const b = await openPanel({ ok: true, value: { ...ONLINE_VIEW, authorizedRoots: [] } })
    showProjects(b)
    expect(b.container.textContent).toContain('未授权任何根目录。')
  })

  it('switches back to the conversation and closes from the header button', async () => {
    const b = await openPanel()
    showProjects(b)
    expect(b.container.querySelector('[data-shadow-chat]')).toBeNull()
    fireEvent.click(b.container.querySelector('[data-shadow-view-toggle]') as HTMLElement)
    expect(b.container.querySelector('[data-shadow-chat]')).not.toBeNull()
    fireEvent.click(b.container.querySelector('[data-shadow-close]') as HTMLElement)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByRole('button', { name: '管理' }).getAttribute('aria-expanded')).toBe('false')
  })

  it('renders the rail mode without the label', async () => {
    const b = bench()
    render(<ShadowCard {...b.props} wide={false} />)
    await act(async () => { await Promise.resolve() })
    expect(screen.queryByText('影子')).toBeNull()
    expect(screen.getByRole('button', { name: '打开影子对话' })).not.toBeNull()
  })

  it('loads the conversation tail when the panel opens online and renders the rows', async () => {
    const chat = chatBench()
    chat.reads.mockResolvedValueOnce({ ok: true, value: { messages: [CHAT_ROW, CHAT_REPLY], cursor: 5 } })
    const b = await openPanel(undefined, undefined, chat)
    await act(async () => { await Promise.resolve() })
    expect(chat.reads).toHaveBeenCalledExactlyOnceWith({})
    expect(b.container.querySelectorAll('[data-shadow-chat-list] [data-shadow-chat-row]')).toHaveLength(2)
    expect(b.container.querySelector('[data-shadow-chat-row="user"]')?.textContent).toContain('帮我把 demo 跑起来')
    expect(b.container.querySelector('[data-shadow-chat-row="shadow"]')?.textContent).toContain('好的，正在启动。')
    expect(b.container.textContent).toContain('你')
    expect(b.container.textContent).toContain('影子')
  })

  it('shows the empty copy while the conversation has no rows', async () => {
    const b = await openPanel()
    await act(async () => { await Promise.resolve() })
    expect(b.container.querySelector('[data-shadow-chat-empty]')?.textContent).toBe('还没有消息——发一条开始对话。')
    expect(b.container.querySelector('[data-shadow-chat-list]')).toBeNull()
  })

  it('offers no conversation input while the Shadow is not online', async () => {
    const b = await openPanel({ ok: true, value: { ...ONLINE_VIEW, shadowLive: false } })
    expect(b.container.querySelector('[data-shadow-chat-offline]')?.textContent).toBe('Shadow 在线后可开始对话。')
    expect(b.container.querySelector('[data-shadow-chat-input]')).toBeNull()
    expect(b.container.querySelector('[data-shadow-chat-submit]')).toBeNull()
  })

  it('shows the conversation read failure verbatim', async () => {
    const chat = chatBench()
    chat.reads.mockResolvedValue({ ok: false, error: { code: 'gateway/internal', message: 'conversation host missing', details: {} } })
    const b = await openPanel(undefined, undefined, chat)
    await act(async () => { await Promise.resolve() })
    expect(b.container.querySelector('[data-shadow-chat-read-error]')?.textContent).toBe('读取对话失败：conversation host missing')
  })

  it('posts one chat message, polls for the surface, and clears the draft', async () => {
    const chat = chatBench()
    const b = await openPanel(undefined, undefined, chat)
    await act(async () => { await Promise.resolve() })
    chat.reads.mockResolvedValueOnce({ ok: true, value: { messages: [CHAT_ROW], cursor: 4 } })
    const input = b.container.querySelector('[data-shadow-chat-input]') as HTMLInputElement
    await act(async () => { fireEvent.change(input, { target: { value: '  帮我把 demo 跑起来  ' } }) })
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-chat-submit]') as HTMLElement) })
    expect(chat.onPostMessage).toHaveBeenCalledExactlyOnceWith('帮我把 demo 跑起来')
    expect(chat.reads).toHaveBeenCalledWith({ after: 0 })
    expect(b.container.querySelector('[data-shadow-chat-row="user"]')?.textContent).toContain('帮我把 demo 跑起来')
    expect((b.container.querySelector('[data-shadow-chat-input]') as HTMLInputElement).value).toBe('')
  })

  it('shows the pending line while a chat post is in flight', async () => {
    const chat = chatBench()
    chat.onPostMessage.mockReturnValueOnce(new Promise<RemoteResult<ShadowConversationAccepted>>(() => {}))
    const b = await openPanel(undefined, undefined, chat)
    await act(async () => { await Promise.resolve() })
    const input = b.container.querySelector('[data-shadow-chat-input]') as HTMLTextAreaElement
    await act(async () => { fireEvent.change(input, { target: { value: 'hello shadow' } }) })
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-chat-submit]') as HTMLElement) })
    expect(b.container.querySelector('[data-shadow-chat-pending]')).not.toBeNull()
  })

  it('submits the chat draft on Enter', async () => {
    const chat = chatBench()
    const b = await openPanel(undefined, undefined, chat)
    await act(async () => { await Promise.resolve() })
    const input = b.container.querySelector('[data-shadow-chat-input]') as HTMLInputElement
    await act(async () => { fireEvent.change(input, { target: { value: 'hello shadow' } }) })
    await act(async () => { fireEvent.keyDown(input, { key: 'Enter' }) })
    expect(chat.onPostMessage).toHaveBeenCalledExactlyOnceWith('hello shadow')
  })

  it('ignores a blank chat draft on Enter and leaves other keys alone', async () => {
    const chat = chatBench()
    const b = await openPanel(undefined, undefined, chat)
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
    const b = await openPanel(undefined, undefined, chat)
    await act(async () => { await Promise.resolve() })
    const input = b.container.querySelector('[data-shadow-chat-input]') as HTMLInputElement
    await act(async () => { fireEvent.change(input, { target: { value: 'hello shadow' } }) })
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-chat-submit]') as HTMLElement) })
    expect(b.container.querySelector('[data-shadow-chat-send-failed]')?.textContent).toBe('发送失败：the conversation is unavailable')
    expect((b.container.querySelector('[data-shadow-chat-input]') as HTMLInputElement).value).toBe('hello shadow')
  })

  it('polls the conversation on an interval while the panel is open and online', async () => {
    vi.useFakeTimers()
    try {
      const chat = chatBench()
      const b = await openPanel(undefined, undefined, chat)
      await act(async () => { await Promise.resolve() })
      const readsAfterOpen = chat.reads.mock.calls.length
      expect(readsAfterOpen).toBeGreaterThanOrEqual(1) // the tail load on open
      await act(async () => { await vi.advanceTimersByTimeAsync(6500) })
      expect(chat.reads.mock.calls.length).toBeGreaterThan(readsAfterOpen)
      const closing = b
      fireEvent.click(screen.getByRole('button', { name: '管理' }))
      await act(async () => { await Promise.resolve() })
      const readsAfterClose = closing.chat.reads.mock.calls.length
      await act(async () => { await vi.advanceTimersByTimeAsync(9000) })
      expect(closing.chat.reads.mock.calls.length).toBe(readsAfterClose)
    } finally {
      vi.useRealTimers()
    }
  })

  it('closes on an outside pointerdown and re-measures the anchor on resizes', async () => {
    const b = bench()
    render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    const manage = screen.getByRole('button', { name: '管理' })
    fireEvent.click(manage)
    expect(screen.getByRole('dialog')).not.toBeNull()
    fireEvent(window, new Event('resize'))
    expect(screen.getByRole('dialog')).not.toBeNull()
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(manage.getAttribute('aria-expanded')).toBe('false')
  })
})
