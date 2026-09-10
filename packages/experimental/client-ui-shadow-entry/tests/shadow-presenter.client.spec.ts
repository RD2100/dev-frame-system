/** The presenter folds: every honest phase, the multi-project projection, and the write outcome lines. */

import { describe, expect, it } from 'vitest'
import type { ShadowRouterStatus, ShadowStatusBinding } from '@deepseek-ai/dsh-experimental-shadow-router'
import type { ShadowStatusView } from '@deepseek-ai/dsh-experimental-shadow-controller'
import {
  presentShadowStatus,
  presentWriteOutcome,
  type ShadowWriteOutcome,
} from '../src/client/shadow-presenter.ts'
import type { ShadowStatusSnapshot } from '../src/client/shadow-store.ts'

const wid = (id: string): ShadowStatusBinding['workspaceId'] => id as ShadowStatusBinding['workspaceId']

const READY_VIEW: ShadowStatusView = {
  mounted: true,
  shadowSessionId: 'session-shadow',
  shadowLive: true,
  authorizedRoots: ['D:/projects'],
  bindings: [{
    workspaceId: wid('ws-1'),
    canonicalPath: 'D:/projects/alpha',
    bindingRevision: 7,
    state: 'ready',
  }],
}

function snapshotOf(partial: Partial<ShadowStatusSnapshot>): ShadowStatusSnapshot {
  return { view: undefined, error: undefined, ...partial }
}

describe('the Shadow card presentation fold', () => {
  it('reads a pending store as the loading phase with an empty model', () => {
    expect(presentShadowStatus(snapshotOf({}))).toEqual({
      phase: 'loading',
      shadowSessionId: null,
      authorizedRoots: [],
      projects: [],
      error: null,
    })
  })

  it('reads a failed read as the error phase carrying the transport message', () => {
    const model = presentShadowStatus(snapshotOf({ error: 'offline' }))
    expect(model.phase).toBe('error')
    expect(model.error).toBe('offline')
    expect(model.shadowSessionId).toBeNull()
    expect(model.projects).toEqual([])
  })

  it('reads an unmounted deployment as the honest not-enabled phase', () => {
    const model = presentShadowStatus(snapshotOf({
      view: { mounted: false, shadowLive: true, authorizedRoots: [], bindings: [] },
    }))
    expect(model.phase).toBe('unmounted')
    expect(model.shadowSessionId).toBeNull()
  })

  it('reads a mounted router without a designation as the not-enabled phase', () => {
    const model = presentShadowStatus(snapshotOf({
      view: { mounted: true, shadowLive: true, authorizedRoots: ['D:/projects'], bindings: [] },
    }))
    expect(model.phase).toBe('disabled')
    expect(model.shadowSessionId).toBeNull()
  })

  it('projects every open project as one row beside the session and roots', () => {
    const model = presentShadowStatus(snapshotOf({
      view: { ...READY_VIEW, bindings: [...READY_VIEW.bindings, {
        workspaceId: wid('ws-2'),
        canonicalPath: 'D:/projects/beta',
        bindingRevision: 3,
        state: 'needs_attention' as const,
      }] },
    }))
    expect(model.phase).toBe('online')
    expect(model.shadowSessionId).toBe('session-shadow')
    expect(model.authorizedRoots).toEqual(['D:/projects'])
    expect(model.projects).toEqual([
      {
        workspaceId: 'ws-1',
        canonicalPath: 'D:/projects/alpha',
        bindingRevision: 7,
        stateKey: 'state.ready',
      },
      {
        workspaceId: 'ws-2',
        canonicalPath: 'D:/projects/beta',
        bindingRevision: 3,
        stateKey: 'state.needsAttention',
      },
    ])
  })

  it('reads a live designated session as the online phase with no projects when none are open', () => {
    const model = presentShadowStatus(snapshotOf({ view: { ...READY_VIEW, bindings: [] } }))
    expect(model.phase).toBe('online')
    expect(model.projects).toEqual([])
  })

  it('projects every durable project state to its locale key', () => {
    const states: readonly ShadowStatusBinding['state'][] = [
      'reserving', 'provisioning', 'ready', 'stopping', 'stopped', 'needs_attention', 'failed',
    ]
    const status: ShadowRouterStatus = {
      shadowSessionId: 'session-shadow',
      shadowLive: false,
      authorizedRoots: [],
      bindings: states.map((state, index) => ({
        workspaceId: wid(`ws-${String(index)}`),
        canonicalPath: `D:/projects/${String(index)}`,
        bindingRevision: index + 1,
        state,
      })),
    }
    const model = presentShadowStatus(snapshotOf({ view: { ...READY_VIEW, bindings: status.bindings } }))
    expect(model.projects.map(row => row.stateKey)).toEqual([
      'state.reserving', 'state.provisioning', 'state.ready',
      'state.stopping', 'state.stopped', 'state.needsAttention', 'state.failed',
    ])
  })
})

describe('the write outcome fold', () => {
  it('keeps an idle outcome unrendered', () => {
    expect(presentWriteOutcome({ state: 'idle' })).toBeUndefined()
  })

  it('reads a busy outcome as the neutral working line', () => {
    expect(presentWriteOutcome({ state: 'busy', kind: 'open' })).toEqual({ tone: 'busy', key: 'write.busy' })
    expect(presentWriteOutcome({ state: 'busy', kind: 'send' })).toEqual({ tone: 'busy', key: 'write.busy' })
  })

  it('reads each completed kind as its own honest success line', () => {
    expect(presentWriteOutcome({ state: 'ok', kind: 'open' })).toEqual({ tone: 'ok', key: 'write.openDone' })
    expect(presentWriteOutcome({ state: 'ok', kind: 'send' })).toEqual({ tone: 'ok', key: 'write.sendDone' })
    expect(presentWriteOutcome({ state: 'ok', kind: 'release' })).toEqual({ tone: 'ok', key: 'write.releaseDone' })
  })

  it('carries the service failure message verbatim into the failed line', () => {
    const outcome: ShadowWriteOutcome = { state: 'failed', kind: 'release', message: 'workspace "ws-1" is stopping' }
    expect(presentWriteOutcome(outcome)).toEqual({
      tone: 'failed',
      key: 'write.failed',
      params: { message: 'workspace "ws-1" is stopping' },
    })
  })
})
