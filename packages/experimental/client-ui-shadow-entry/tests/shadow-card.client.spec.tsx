// @vitest-environment jsdom
/** The resident card: the trigger opens the Shadow's designated session
 *  through the standard surface, and the manage button opens a read-only
 *  settings dropdown portaled beside the sidebar. The card renders honest
 *  phases and no conversation of its own. */

import { useSyncExternalStore } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ShadowStatusView } from '@deepseek-ai/dsh-experimental-shadow-controller'
import { ShadowCard, type ShadowCardProps } from '../src/client/ShadowCard.tsx'
import { zh, type ShadowKey } from '../src/client/locales.ts'
import { ShadowStatusController, type ShadowStatusPort, type ShadowStatusSnapshot } from '../src/client/shadow-store.ts'

const t = ((key: ShadowKey, params?: Record<string, string | number>) => {
  const text = zh[key]
  return params === undefined
    ? text
    : Object.entries(params).reduce((acc, [name, value]) => acc.replaceAll(`{${name}}`, String(value)), text)
}) as unknown as ShadowCardProps['t']

// The card consumes the status face and the sessions feed's current selection;
// the seat's remaining standard hooks stay unused, so their stubs fail loud if
// a future edit starts reading them.
const unusedHook = (() => { throw new Error('unused by the shadow card') }) as never

/** The sessions-feed state the card reads: the current selection only. */
function useSessionsBench(current?: string) {
  return ((selector: (s: { current: string | undefined }) => string | undefined) =>
    selector({ current })) as unknown as ShadowCardProps['useSessions']
}

const ONLINE_VIEW: ShadowStatusView = {
  mounted: true,
  shadowSessionId: 'session-shadow',
  shadowLive: true,
  authorizedRoots: ['D:/projects', 'D:/work'],
  bindings: [],
}

interface Bench {
  controller: ShadowStatusController
  onRefresh: ReturnType<typeof vi.fn>
  onOpenConversation: ReturnType<typeof vi.fn>
  props: ShadowCardProps
  ready: Promise<void>
}

function bench(
  answer: { ok: true; value: ShadowStatusView } | { ok: false; error: { code: string; message: string; details: Record<string, never> } } | 'hang' = { ok: true, value: { ...ONLINE_VIEW } },
  current?: string,
): Bench {
  const port: ShadowStatusPort = () => {
    if (answer === 'hang') return new Promise(() => {})
    return Promise.resolve(answer as { ok: true; value: ShadowStatusView })
  }
  const controller = new ShadowStatusController(port)
  const onRefresh = vi.fn(() => { void controller.refresh() })
  const onOpenConversation = vi.fn(async () => {})
  // useStatus is the bound selector hook produced by InjectFace from the
  // hooks compartment; the bench wires it to the real store.
  const useStatus = <S,>(selector: (s: ShadowStatusSnapshot) => S): S =>
    useSyncExternalStore(
      listener => controller.store.subscribe(listener),
      () => selector(controller.store.getSnapshot()),
    )
  // Pre-load the status so the first render sees a settled snapshot.
  const ready = controller.refresh()
  const props: ShadowCardProps = {
    wide: true,
    useStatus,
    useSessions: useSessionsBench(current),
    onRefresh,
    onOpenConversation,
    t,
    useSessionPendingInteraction: unusedHook,
    useWorkspaces: unusedHook,
  } satisfies ShadowCardProps
  return { controller, onRefresh, onOpenConversation, props, ready }
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
  })

  it('sends the trigger click to the standard surface and renders no conversation of its own', async () => {
    const b = bench()
    await act(async () => { await b.ready })
    render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    fireEvent.click(screen.getByRole('button', { name: '打开影子对话' }))
    expect(b.onOpenConversation).toHaveBeenCalledTimes(1)
    // No in-card chat surface: the conversation lives in the standard
    // conversation surface the trigger adopts.
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(document.querySelector('[data-shadow-chat-dialog]')).toBeNull()
    expect(document.querySelector('[data-shadow-chat-input]')).toBeNull()
  })

  it('opens the manage dropdown with status, session, roots, and preset info and re-reads status', async () => {
    const b = bench()
    await act(async () => { await b.ready })
    render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    fireEvent.click(screen.getByRole('button', { name: '管理' }))
    const menu = screen.getByRole('menu')
    expect(menu).not.toBeNull()
    expect(menu.textContent).toContain('Shadow 状态')
    expect(menu.textContent).toContain('在线')
    expect(menu.textContent).toContain('控制者会话')
    expect(menu.textContent).toContain('session-shadow')
    expect(menu.textContent).toContain('授权根目录')
    expect(menu.textContent).toContain('D:/projects')
    expect(menu.textContent).toContain('控制器预设')
    // Opening the menu re-reads the status so the facts converge.
    expect(b.onRefresh).toHaveBeenCalledTimes(2)
  })

  it('closes the manage dropdown on an outside pointerdown', async () => {
    const b = bench()
    await act(async () => { await b.ready })
    render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    fireEvent.click(screen.getByRole('button', { name: '管理' }))
    expect(screen.getByRole('menu')).not.toBeNull()
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('renders the rail mode without the label and without the manage affordance', async () => {
    const b = bench()
    render(<ShadowCard {...b.props} wide={false} />)
    await act(async () => { await Promise.resolve() })
    expect(screen.queryByText('影子')).toBeNull()
    expect(screen.queryByRole('button', { name: '管理' })).toBeNull()
    expect(screen.getByRole('button', { name: '打开影子对话' })).not.toBeNull()
  })

  it('keeps the not-enabled copy honest while the router is mounted but unconfigured', async () => {
    const b = bench({ ok: true, value: { mounted: true, shadowLive: true, authorizedRoots: ['D:/projects'], bindings: [] } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="disabled"]')).not.toBeNull()
    expect(container.querySelector('[data-shadow-detail]')?.textContent).toBe('Shadow 未启用')
    // The trigger still forwards the click; the open verb decides adoption.
    fireEvent.click(screen.getByRole('button', { name: '打开影子对话' }))
    expect(b.onOpenConversation).toHaveBeenCalledTimes(1)
  })

  it('reads an absent router as the honest not-enabled state', async () => {
    const b = bench({ ok: true, value: { mounted: false, shadowLive: true, authorizedRoots: [], bindings: [] } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="unmounted"]')).not.toBeNull()
    expect(container.querySelector('[data-shadow-detail]')?.textContent).toBe('此部署没有挂载 Shadow 服务。')
  })

  it('reads a configured designation whose session is not live as configured, not online', async () => {
    const b = bench({ ok: true, value: { ...ONLINE_VIEW, shadowLive: false } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="configured"]')).not.toBeNull()
    expect(container.querySelector('[data-shadow-detail]')?.textContent).toBe('控制者会话尚未标记为 Shadow。')
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
  })

  it('marks the trigger active while the designated conversation is the current session', async () => {
    const b = bench({ ok: true, value: { ...ONLINE_VIEW } }, 'session-shadow')
    render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    const trigger = screen.getByRole('button', { name: '打开影子对话' })
    expect(trigger.getAttribute('data-shadow-active')).toBe('true')
    expect(trigger.getAttribute('aria-pressed')).toBe('true')
  })

  it('keeps the trigger inactive for another current session or a not-enabled service', async () => {
    const b = bench({ ok: true, value: { ...ONLINE_VIEW } }, 'session-other')
    const first = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    const trigger = screen.getByRole('button', { name: '打开影子对话' })
    expect(trigger.getAttribute('data-shadow-active')).toBeNull()
    expect(trigger.getAttribute('aria-pressed')).toBe('false')
    first.unmount()

    const disabled = bench({ ok: true, value: { mounted: true, shadowLive: true, authorizedRoots: ['D:/projects'], bindings: [] } }, 'session-shadow')
    render(<ShadowCard {...disabled.props} />)
    await act(async () => { await Promise.resolve() })
    const disabledTrigger = screen.getByRole('button', { name: '打开影子对话' })
    expect(disabledTrigger.getAttribute('data-shadow-active')).toBeNull()
  })

  it('shows the empty-copy line when the enabled deployment has no roots', async () => {
    const b = bench({ ok: true, value: { ...ONLINE_VIEW, authorizedRoots: [] } })
    await act(async () => { await b.ready })
    render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    fireEvent.click(screen.getByRole('button', { name: '管理' }))
    expect(screen.getByText('未授权任何根目录。')).not.toBeNull()
  })

  it('fails closed on a designation issue: shows the issue copy and does not open', async () => {
    const b = bench({ ok: true, value: { ...ONLINE_VIEW, designIssue: 'designated-session-missing-cwd' } })
    const { container } = render(<ShadowCard {...b.props} />)
    await act(async () => { await Promise.resolve() })
    expect(container.querySelector('[data-shadow-phase="issue"]')).not.toBeNull()
    expect(container.querySelector('[data-shadow-detail]')?.textContent).toContain('缺少工作区')
    // The trigger must not open a conversation that would render as fresh.
    fireEvent.click(screen.getByRole('button', { name: '打开影子对话' }))
    expect(b.onOpenConversation).not.toHaveBeenCalled()
  })
})
