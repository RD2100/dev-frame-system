/** The presenter fold: every honest phase and the row projection. */

import { describe, expect, it } from 'vitest'
import type { ShadowRouterStatus, ShadowStatusBinding } from '@deepseek-ai/dsh-experimental-shadow-router'
import type { ShadowStatusView } from '@deepseek-ai/dsh-experimental-shadow-controller'
import { presentShadowStatus } from '../src/client/shadow-presenter.ts'
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
      bindings: [],
      error: null,
    })
  })

  it('reads a failed read as the error phase carrying the transport message', () => {
    const model = presentShadowStatus(snapshotOf({ error: 'offline' }))
    expect(model.phase).toBe('error')
    expect(model.error).toBe('offline')
    expect(model.shadowSessionId).toBeNull()
    expect(model.bindings).toEqual([])
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

  it('reads a configured designation whose session is not live as the configured phase', () => {
    const model = presentShadowStatus(snapshotOf({ view: { ...READY_VIEW, shadowLive: false } }))
    expect(model.phase).toBe('configured')
    expect(model.shadowSessionId).toBe('session-shadow')
    expect(model.authorizedRoots).toEqual(['D:/projects'])
    expect(model.bindings).toEqual([{
      workspaceId: 'ws-1',
      canonicalPath: 'D:/projects/alpha',
      bindingRevision: 7,
      stateKey: 'state.ready',
    }])
  })

  it('reads a live designated session as the online phase', () => {
    const model = presentShadowStatus(snapshotOf({ view: READY_VIEW }))
    expect(model.phase).toBe('online')
  })

  it('projects every durable binding state to its locale key', () => {
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
    expect(model.bindings.map(row => row.stateKey)).toEqual([
      'state.reserving', 'state.provisioning', 'state.ready',
      'state.stopping', 'state.stopped', 'state.needsAttention', 'state.failed',
    ])
  })
})
