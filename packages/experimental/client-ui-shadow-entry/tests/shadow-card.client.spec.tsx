// @vitest-environment jsdom
/** The resident card: honest phases, the open panel, and refresh behavior. */

import { useSyncExternalStore } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ShadowStatusView } from '@deepseek-ai/dsh-experimental-shadow-controller'
import type { ShadowStatusBinding } from '@deepseek-ai/dsh-experimental-shadow-router'
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

const ONLINE_VIEW: ShadowStatusView = {
  mounted: true,
  shadowSessionId: 'session-shadow',
  shadowLive: true,
  authorizedRoots: ['D:/projects'],
  bindings: [{
    workspaceId: wid('ws-1'),
    canonicalPath: 'D:/projects/alpha',
    bindingRevision: 7,
    state: 'ready' as const,
  }],
}

type TestAnswer =
  | { ok: true; value: typeof ONLINE_VIEW }
  | { ok: false; error: { code: string; message: string; details: Record<string, never> } }
  | 'hang'

/** Bench: a real controller over a scripted port plus the framework stubs. */
function bench(answer: TestAnswer = { ok: true, value: { ...ONLINE_VIEW } }): {
  controller: ShadowStatusController
  onRefresh: ReturnType<typeof vi.fn>
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
    t,
    useSessions: unusedHook,
    useSessionPendingInteraction: unusedHook,
    useWorkspaces: unusedHook,
  } satisfies ShadowCardProps
  return { controller, onRefresh, props }
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

  it('opens the panel with the session, roots, and binding rows', async () => {
    const b = bench()
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    fireEvent.click(screen.getByRole('button', { name: 'Shadow 服务状态' }))
    expect(screen.getByRole('dialog', { name: 'Shadow 服务状态面板' })).not.toBeNull()
    expect(container.querySelector('[data-shadow-status]')?.textContent).toBe('在线')
    expect(container.querySelector('[data-shadow-session]')?.textContent).toBe('session-shadow')
    expect(container.textContent).toContain('D:/projects')
    expect(container.textContent).toContain('D:/projects/alpha')
    expect(container.textContent).toContain('ws-1')
    expect(container.textContent).toContain('修订 7')
    expect(container.textContent).toContain('就绪')
    expect(screen.getByRole('button', { name: 'Shadow 服务状态' }).getAttribute('aria-expanded')).toBe('true')
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
    expect(container.textContent).not.toContain('项目绑定')
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

  it('shows the empty-copy lines when the enabled deployment has no roots or bindings', async () => {
    const b = bench({ ok: true, value: { ...ONLINE_VIEW, authorizedRoots: [], bindings: [] } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    fireEvent.click(screen.getByRole('button', { name: 'Shadow 服务状态' }))
    expect(container.textContent).toContain('未授权任何根目录。')
    expect(container.textContent).toContain('暂无项目绑定。')
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
