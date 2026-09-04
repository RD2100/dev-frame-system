// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import type {
  ConversationContextReader,
  ConversationMatch,
  ConversationNodeContext,
  SessionId,
  SessionListState,
  WorkspaceListState,
} from '@deepseek-ai/dsh-client-runtime/client'
import { ConversationEventRegistry, SlotRegistry } from '@deepseek-ai/dsh-client-runtime/client'
import { LocaleRuntime } from '@deepseek-ai/dsh-client-locale/client'
import { makeTranslate } from '@deepseek-ai/dsh-client-test-runtime'
import { en as commonEn } from '@deepseek-ai/dsh-client-locale/src/locales/en.ts'
import type { DevFrameReadinessSnapshot } from '@deepseek-ai/dsh-devframe-control-session/types'
import { apply } from '../src/client/index.ts'
import { ControlIdentityView } from '../src/client/ControlIdentityView.tsx'
import { GlobalControllerAction } from '../src/client/GlobalControllerAction.tsx'
import { en } from '../src/client/locales.ts'
import { controllerIdentityDefinition, type ControllerIdentityView } from '../src/client/definition.ts'
import { GlobalControllerReadiness } from '../src/client/readiness.ts'

const t: Parameters<typeof ControlIdentityView>[0]['t'] = makeTranslate(en, commonEn)
const reader: ConversationContextReader = { previous: () => undefined }
const workspaceState: WorkspaceListState = {
  items: [],
  archivedSessionIds: [],
  state: 'idle',
  phase: 'ready',
  error: null,
  baselinesReady: true,
  recentWorkspaceId: undefined,
}

function readinessState(
  status: DevFrameReadinessSnapshot['status'],
  sessionId?: string,
): DevFrameReadinessSnapshot {
  const common = { generation: 1, revision: 1 }
  if (status === 'ready') {
    if (sessionId === undefined) throw new Error('ready test state requires a Session ID')
    return { status, sessionId, ...common }
  }
  if (status === 'blocked') {
    return { status, code: 'CONTROLLER_UNAVAILABLE', ...common }
  }
  return { status, ...common }
}

function useReadinessOf(
  state: DevFrameReadinessSnapshot,
): <S>(selector: (value: DevFrameReadinessSnapshot) => S) => S {
  return <S,>(selector: (value: DevFrameReadinessSnapshot) => S): S => selector(state)
}

function event(data: unknown, seq = 0) {
  return { type: 'controller/identity', seq, time: 1_700_000_000_000, data }
}

function match(value = event({})): ConversationMatch {
  return { event: value as never, view: undefined, role: 'start', location: { kind: 'session' } }
}

function context(state?: ControllerIdentityView): ConversationNodeContext<ControllerIdentityView> {
  const start = match()
  return {
    key: `devframe-controller-identity:${start.event.seq}`,
    kind: controllerIdentityDefinition.kind,
    id: `controller-identity:${start.event.seq}`,
    matches: [start],
    start,
    state,
    current: new Map(),
  }
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('DevFrame controller identity node', () => {
  it('opens and copies only the exact readiness Session ID when old and current Global IDs coexist', async () => {
    const oldGlobalId = 'devframe-global:profile-old' as SessionId
    const currentGlobalId = 'devframe-global:profile-current' as SessionId
    const state: SessionListState = {
      ids: [oldGlobalId, currentGlobalId],
      byId: {},
      current: undefined,
      phase: 'ready',
      subagentsByParent: {},
      jobsBySession: {},
      currentAddress: undefined,
    }
    const useSessions = <S,>(selector: (value: SessionListState) => S): S => selector(state)
    const open = vi.fn()
    const useWorkspaces = <S,>(selector: (value: WorkspaceListState) => S): S => selector(workspaceState)
    const useReadiness = useReadinessOf(readinessState('ready', currentGlobalId))
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(<GlobalControllerAction
      wide
      useSessions={useSessions}
      useWorkspaces={useWorkspaces}
      useReadiness={useReadiness}
      open={open}
      t={t}
    />)
    fireEvent.click(screen.getByRole('button', { name: 'Global Controller' }))
    expect(open).toHaveBeenCalledWith(currentGlobalId)
    fireEvent.click(screen.getByRole('button', { name: 'Global Controller actions' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Copy Session ID' }))
    await vi.waitFor(() => { expect(writeText).toHaveBeenCalledWith(currentGlobalId) })
  })

  it('exposes the Global Controller Session ID from its own actions menu', () => {
    const globalId = 'devframe-global:profile-1' as SessionId
    const state: SessionListState = {
      ids: [globalId],
      byId: {},
      current: globalId,
      phase: 'ready',
      subagentsByParent: {},
      jobsBySession: {},
      currentAddress: undefined,
    }
    const useSessions = <S,>(selector: (value: SessionListState) => S): S => selector(state)
    const useWorkspaces = <S,>(selector: (value: WorkspaceListState) => S): S => selector(workspaceState)
    const useReadiness = useReadinessOf(readinessState('ready', globalId))
    render(<GlobalControllerAction
      wide
      useSessions={useSessions}
      useWorkspaces={useWorkspaces}
      useReadiness={useReadiness}
      open={vi.fn()}
      t={t}
    />)
    fireEvent.click(screen.getByRole('button', { name: 'Global Controller actions' }))
    expect(screen.getByRole('menuitem', { name: 'Copy Session ID' })).toBeTruthy()
  })

  it.each([
    ['starting', readinessState('starting')],
    ['blocked', readinessState('blocked')],
    ['stopping', readinessState('stopping')],
    ['ready but not catalogued', readinessState('ready', 'devframe-global:profile-missing')],
  ] as const)('fails closed when readiness is %s', (_label, readiness) => {
    const oldGlobalId = 'devframe-global:profile-old' as SessionId
    const currentGlobalId = 'devframe-global:profile-current' as SessionId
    const state: SessionListState = {
      ids: [oldGlobalId, currentGlobalId],
      byId: {},
      current: undefined,
      phase: 'ready',
      subagentsByParent: {},
      jobsBySession: {},
      currentAddress: undefined,
    }
    const useSessions = <S,>(selector: (value: SessionListState) => S): S => selector(state)
    const useWorkspaces = <S,>(selector: (value: WorkspaceListState) => S): S => selector(workspaceState)
    render(<GlobalControllerAction
      wide
      useSessions={useSessions}
      useWorkspaces={useWorkspaces}
      useReadiness={useReadinessOf(readiness)}
      open={vi.fn()}
      t={t}
    />)
    expect(screen.getByRole('button', { name: 'Global Controller' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByText('Global Controller unavailable')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Global Controller actions' })).toBeNull()
  })

  it('accepts only the canonical seq-zero identity event', () => {
    const identity = {
      role: 'global',
      sessionId: 'devframe-global:profile-1',
      profileId: 'profile-1',
      cwd: 'C:/dsh-home/devframe-control',
      schemaVersion: 1,
    }
    expect(controllerIdentityDefinition.match(event(identity, 0) as never)).toEqual({
      id: 'controller-identity:0',
      role: 'start',
    })
    expect(controllerIdentityDefinition.match(event(identity, 1) as never)).toBeNull()
    expect(controllerIdentityDefinition.match({
      ...event(identity, 0),
      type: 'controller/not-identity',
    } as never)).toBeNull()
  })

  it('projects the exact v1 project identity deterministically', () => {
    const input = event({
      role: 'project',
      sessionId: 'devframe-controller:workspace-1',
      profileId: 'profile-1',
      workspaceId: 'workspace-1',
      cwd: 'C:/workspace-1',
      schemaVersion: 1,
    })
    expect(controllerIdentityDefinition.match(input as never))
      .toEqual(controllerIdentityDefinition.match(input as never))
    const state = controllerIdentityDefinition.start(context(), match(input), reader)
    expect(controllerIdentityDefinition.buildViewNode?.(context(state))).toMatchObject({
      kind: 'devframe-controller-identity',
      target: 'chat',
      anchorSeq: 0,
      data: {
        role: 'project',
        sessionId: 'devframe-controller:workspace-1',
        scopeId: 'workspace-1',
        schemaVersion: 1,
        readiness: 'identity-recorded',
      },
    })
  })

  it('fails closed without echoing malformed or extra payload fields', () => {
    const hostile = '__SECRET__<script>alert(1)</script>D:/private/root'
    const state = controllerIdentityDefinition.start(context(), match(event({
      schemaVersion: 1,
      role: 'global',
      sessionId: `devframe-global:${hostile}`,
      profileId: hostile,
      cwd: hostile,
    })), reader)
    expect(state).toEqual({
      role: 'unknown',
      sessionId: '',
      scopeId: '',
      schemaVersion: 1,
      readiness: 'blocked',
    })
    expect(JSON.stringify(state)).not.toContain(hostile)
    expect(() => controllerIdentityDefinition.start(context(), match(event(null)), reader)).not.toThrow()
  })

  it('keeps identity metadata out of the conversation message stream', () => {
    const rendered = render(<ControlIdentityView
      node={{
        key: 'node',
        kind: 'devframe-controller-identity',
        id: 'identity',
        target: 'chat',
        anchorSeq: 0,
        location: { kind: 'session' },
        visibility: 'visible',
        data: {
          role: 'global',
          sessionId: 'devframe-global:profile-1',
          scopeId: 'profile-1',
          schemaVersion: 1,
          readiness: 'identity-recorded',
        },
      }}
      t={t}
    />)
    expect(rendered.container.firstChild).toBeNull()
  })

  it('removes and replaces its real Definition and renderer with the Cordis fiber', async () => {
    const ctx = new Context()
    await ctx.plugin(SlotRegistry).await()
    await ctx.plugin(ConversationEventRegistry).await()
    ctx.provide('locale', new LocaleRuntime(ctx))
    ctx.provide('sessions', {
      list: { getSnapshot: () => ({ ids: [], byId: {}, current: undefined, phase: 'ready', subagentsByParent: {}, jobsBySession: {}, currentAddress: undefined }), subscribe: () => () => {} },
      open: vi.fn(),
    } as never)
    ctx.provide('remote', {
      devframeControlSessions: {
        readiness: vi.fn().mockResolvedValue({ ok: false, error: { code: 'unavailable' } }),
      },
    } as never)
    ctx.slots.register({
      name: 'root',
      children: {
        'conversation.chat.node': { kind: 'keyed', scope: 'session' },
        'sidebar.footer.action': { kind: 'list', scope: 'root' },
      },
    } as never, () => null)

    const fiber = ctx.plugin({ inject: ['slots', 'conversationEvents', 'locale', 'sessions', 'remote'], apply })
    await fiber.await()
    expect(ctx.conversationEvents.entries()).toEqual([controllerIdentityDefinition])
    expect(ctx.slots.entries('conversation.chat.node')).toHaveLength(1)
    expect(ctx.slots.entries('sidebar.footer.action')).toHaveLength(1)

    await fiber.dispose()
    expect(ctx.conversationEvents.entries()).toEqual([])
    expect(ctx.slots.entries('conversation.chat.node')).toEqual([])

    const replacement = ctx.plugin({ inject: ['slots', 'conversationEvents', 'locale', 'sessions', 'remote'], apply })
    await replacement.await()
    expect(ctx.conversationEvents.entries()).toEqual([controllerIdentityDefinition])
    expect(ctx.slots.entries('conversation.chat.node')).toHaveLength(1)
    expect(ctx.slots.entries('sidebar.footer.action')).toHaveLength(1)
    await replacement.dispose()
    await ctx.fiber.dispose()
  })
})

describe('Global Controller readiness remote projection', () => {
  it('uses the Host readiness snapshot and advances the exact revision cursor', async () => {
    const readiness = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        value: {
          status: 'ready',
          generation: 4,
          revision: 7,
          sessionId: 'devframe-global:profile-current',
        },
      })
      .mockImplementation(() => new Promise(() => {}))
    const controller = new GlobalControllerReadiness()
    controller.start({ devframeControlSessions: { readiness } })
    await vi.waitFor(() => {
      expect(controller.store.getSnapshot()).toMatchObject({
        status: 'ready',
        sessionId: 'devframe-global:profile-current',
      })
    })
    expect(readiness).toHaveBeenNthCalledWith(1, -1, expect.any(AbortSignal))
    expect(readiness).toHaveBeenNthCalledWith(2, 7, expect.any(AbortSignal))
    controller.stop()
  })

  it('fails closed on a remote failure and fences a late response after disposal', async () => {
    const absent = new GlobalControllerReadiness()
    absent.start({})
    await vi.waitFor(() => {
      expect(absent.store.getSnapshot()).toMatchObject({
        status: 'blocked',
        code: 'CONTROLLER_UNAVAILABLE',
      })
    })
    absent.stop()

    const failure = vi.fn().mockResolvedValue({ ok: false, error: { code: 'unavailable' } })
    const controller = new GlobalControllerReadiness()
    controller.start({ devframeControlSessions: { readiness: failure } })
    await vi.waitFor(() => {
      expect(controller.store.getSnapshot()).toMatchObject({
        status: 'blocked',
        code: 'CONTROLLER_UNAVAILABLE',
      })
    })

    let resolveLate: ((value: unknown) => void) | undefined
    const late = vi.fn().mockImplementation(() => new Promise((resolve) => { resolveLate = resolve }))
    controller.start({ devframeControlSessions: { readiness: late } })
    controller.stop()
    resolveLate?.({
      ok: true,
      value: {
        status: 'ready',
        generation: 8,
        revision: 9,
        sessionId: 'devframe-global:profile-old',
      },
    })
    await Promise.resolve()
    expect(controller.store.getSnapshot().status).toBe('starting')
  })
})
