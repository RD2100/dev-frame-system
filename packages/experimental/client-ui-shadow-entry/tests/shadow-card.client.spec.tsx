// @vitest-environment jsdom
/** The resident card: honest phases, the actionable panel, and the write verbs' success and failure surfaces. */

import { useSyncExternalStore } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ProjectOpenResult, ProjectSendResult, ProjectStopResult, ShadowMessageId } from '@deepseek-ai/dsh-experimental-shadow-router'
import type { ShadowStatusView } from '@deepseek-ai/dsh-experimental-shadow-controller'
import type { ShadowStatusBinding } from '@deepseek-ai/dsh-experimental-shadow-router'
import { RemoteError, type RemoteResult } from '@deepseek-ai/dsh-typert-protocol'
import { ShadowCard, type ShadowCardProps } from '../src/client/ShadowCard.tsx'
import { zh, type ShadowKey } from '../src/client/locales.ts'
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

/** Bench: a real controller over a scripted port plus the framework stubs. */
function bench(answer: TestAnswer = { ok: true, value: { ...ONLINE_VIEW } }, writes: WriteBench = writeBench()): {
  controller: ShadowStatusController
  onRefresh: ReturnType<typeof vi.fn>
  writes: WriteBench
  props: ShadowCardProps
} {
  const port: ShadowStatusPort = () => {
    if (answer === 'hang') return new Promise(() => {})
    return Promise.resolve(answer as Awaited<ReturnType<ShadowStatusPort>>)
  }
  const controller = new ShadowStatusController(port)
  const onRefresh = vi.fn(() => { void controller.refresh() })
  const props = {
    wide: true,
    // The renderer binds the declared hooks compartment to use<Name> seats;
    // the stub binds the same store through the framework's own channel.
    useStatus: ((selector: (snapshot: ReturnType<ShadowStatusController['store']['getSnapshot']>) => unknown) =>
      useSyncExternalStore(controller.store.subscribe, () => selector(controller.store.getSnapshot()))) as unknown as ShadowCardProps['useStatus'],
    onRefresh,
    onOpenProject: writes.onOpenProject as unknown as ShadowCardProps['onOpenProject'],
    onSendToController: writes.onSendToController as unknown as ShadowCardProps['onSendToController'],
    onReleaseProject: writes.onReleaseProject as unknown as ShadowCardProps['onReleaseProject'],
    t,
    useSessions: unusedHook,
    useSessionPendingInteraction: unusedHook,
    useWorkspaces: unusedHook,
  } satisfies ShadowCardProps
  return { controller, onRefresh, writes, props }
}

/** Render, settle the first read, and open the panel. */
async function openPanel(answer?: TestAnswer, writes?: WriteBench): Promise<{ container: HTMLElement } & ReturnType<typeof bench>> {
  const b = bench(answer, writes)
  const rendered = render(<ShadowCard {...b.props} />)
  await act(async () => { await Promise.resolve() })
  fireEvent.click(screen.getByRole('button', { name: 'Shadow 服务状态' }))
  return { container: rendered.container, ...b }
}

afterEach(cleanup)

describe('the sidebar Shadow entry card', () => {
  it('renders the resident trigger and refreshes once on mount', async () => {
    const b = bench()
    render(<ShadowCard {...b.props} />)
    const trigger = screen.getByRole('button', { name: 'Shadow 服务状态' })
    expect(trigger.getAttribute('aria-expanded')).toBe('false')
    await act(async () => { await Promise.resolve() })
    expect(trigger.getAttribute('data-shadow-phase')).toBe('online')
    expect(b.onRefresh).toHaveBeenCalledTimes(1)
  })

  it('opens the panel as a multi-project list with roots, rows, and per-row actions', async () => {
    const b = await openPanel()
    expect(screen.getByRole('dialog', { name: 'Shadow 服务状态面板' })).not.toBeNull()
    expect(b.container.querySelector('[data-shadow-status]')?.textContent).toBe('在线')
    expect(b.container.querySelector('[data-shadow-session]')?.textContent).toBe('session-shadow')
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
    expect(screen.getByRole('button', { name: 'Shadow 服务状态' }).getAttribute('aria-expanded')).toBe('true')
  })

  it('shows the empty-state copy and the open form when no project is open', async () => {
    const b = await openPanel({ ok: true, value: { ...ONLINE_VIEW, bindings: [] } })
    expect(b.container.textContent).toContain('尚未打开任何项目——输入项目路径开始。')
    expect(b.container.querySelector('[data-shadow-open-input]')).not.toBeNull()
    expect(b.container.querySelector('[data-shadow-open]')).not.toBeNull()
    // The refactored surface speaks of open projects, never of bindings.
    expect(b.container.textContent).not.toContain('绑定')
  })

  it('opens a project from the form and lands the honest success line', async () => {
    const b = await openPanel()
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
    const input = b.container.querySelector('[data-shadow-send-input="ws-1"]') as HTMLInputElement
    await act(async () => { fireEvent.change(input, { target: { value: 'ship the release' } }) })
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-send="ws-1"]') as HTMLElement) })
    expect(b.writes.onSendToController).toHaveBeenCalledExactlyOnceWith('ws-1', 'ship the release')
    expect(b.container.querySelector('[data-shadow-write]')?.textContent).toBe('消息已被项目总控接收。')
    expect((b.container.querySelector('[data-shadow-send-input="ws-1"]') as HTMLInputElement).value).toBe('')
  })

  it('releases a project from its row and lands the honest success line', async () => {
    const b = await openPanel()
    await act(async () => { fireEvent.click(b.container.querySelector('[data-shadow-release="ws-1"]') as HTMLElement) })
    expect(b.writes.onReleaseProject).toHaveBeenCalledExactlyOnceWith('ws-1')
    expect(b.container.querySelector('[data-shadow-write]')?.textContent).toBe('项目已解除并停止。')
  })

  it('shows the service failure verbatim when a release is rejected', async () => {
    const b = await openPanel(undefined, writeBench({ message: 'workspace "ws-1" is stopping and does not admit deliveries' }))
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
    const trigger = screen.getByRole('button', { name: 'Shadow 服务状态' })
    await act(async () => { await Promise.resolve() })
    fireEvent.click(trigger)
    fireEvent.click(trigger)
    fireEvent.click(trigger)
    expect(b.onRefresh).toHaveBeenCalledTimes(3)
  })

  it('keeps the not-enabled copy honest while the router is mounted but unconfigured', async () => {
    const b = bench({ ok: true, value: { mounted: true, shadowLive: true, authorizedRoots: ['D:/projects'], bindings: [] } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="disabled"]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Shadow 服务状态' }))
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
    fireEvent.click(screen.getByRole('button', { name: 'Shadow 服务状态' }))
    expect(container.textContent).toContain('此部署没有挂载 Shadow 服务。')
  })

  it('reads a configured designation whose session is not live as configured, not online', async () => {
    const b = bench({ ok: true, value: { ...ONLINE_VIEW, shadowLive: false } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="configured"]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Shadow 服务状态' }))
    expect(container.querySelector('[data-shadow-status]')?.textContent).toBe('已配置，未在线')
    expect(container.textContent).toContain('控制者会话尚未标记为 Shadow。')
    expect(container.textContent).toContain('session-shadow')
  })

  it('shows the read failure instead of pretending a state', async () => {
    const b = bench({ ok: false, error: { code: 'gateway/internal', message: 'offline', details: {} } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="error"]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Shadow 服务状态' }))
    expect(container.querySelector('[data-shadow-status]')?.textContent).toBe('状态读取失败')
    expect(container.querySelector('[data-shadow-error]')?.textContent).toBe('读取 Shadow 状态失败：offline')
  })

  it('stays in the loading phase until the first read settles', () => {
    const b = bench('hang')
    const { container } = render(<ShadowCard {...b.props} />)
    expect(container.querySelector('[data-shadow-phase="loading"]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Shadow 服务状态' }))
    expect(container.querySelector('[data-shadow-status]')?.textContent).toBe('读取状态中…')
  })

  it('shows the empty-copy line when the enabled deployment has no roots', async () => {
    const b = await openPanel({ ok: true, value: { ...ONLINE_VIEW, authorizedRoots: [] } })
    expect(b.container.textContent).toContain('未授权任何根目录。')
  })

  it('renders the rail mode without the label', async () => {
    const b = bench()
    render(<ShadowCard {...b.props} wide={false} />)
    await act(async () => { await Promise.resolve() })
    expect(screen.queryByText('影子')).toBeNull()
    expect(screen.getByRole('button', { name: 'Shadow 服务状态' })).not.toBeNull()
  })

  it('closes on an outside pointerdown and re-measures the anchor on resizes', async () => {
    const b = bench()
    render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    const trigger = screen.getByRole('button', { name: 'Shadow 服务状态' })
    fireEvent.click(trigger)
    expect(screen.getByRole('dialog')).not.toBeNull()
    fireEvent(window, new Event('resize'))
    expect(screen.getByRole('dialog')).not.toBeNull()
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(trigger.getAttribute('aria-expanded')).toBe('false')
  })
})
