/** The presenter folds: every honest phase of the Shadow card's display model. */

import { describe, expect, it } from 'vitest'
import type { ShadowStatusView } from '@deepseek-ai/dsh-experimental-shadow-controller'
import { presentShadowStatus } from '../src/client/shadow-presenter.ts'
import type { ShadowStatusSnapshot } from '../src/client/shadow-store.ts'

const READY_VIEW: ShadowStatusView = {
  mounted: true,
  shadowSessionId: 'session-shadow',
  shadowLive: true,
  authorizedRoots: ['D:/projects'],
  bindings: [],
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
      error: null,
    })
  })

  it('reads a failed read as the error phase carrying the transport message', () => {
    const model = presentShadowStatus(snapshotOf({ error: 'offline' }))
    expect(model.phase).toBe('error')
    expect(model.error).toBe('offline')
    expect(model.shadowSessionId).toBeNull()
    expect(model.authorizedRoots).toEqual([])
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
    expect(model.authorizedRoots).toEqual(['D:/projects'])
  })

  it('reads a live designated session as the online phase with its session and roots', () => {
    const model = presentShadowStatus(snapshotOf({ view: READY_VIEW }))
    expect(model.phase).toBe('online')
    expect(model.shadowSessionId).toBe('session-shadow')
    expect(model.authorizedRoots).toEqual(['D:/projects'])
    expect(model.error).toBeNull()
  })

  it('reads a configured designation whose session is not live as configured, not online', () => {
    const model = presentShadowStatus(snapshotOf({ view: { ...READY_VIEW, shadowLive: false } }))
    expect(model.phase).toBe('configured')
    expect(model.shadowSessionId).toBe('session-shadow')
  })

  it('keeps open-project bindings out of the display model the card renders', () => {
    // The manage dropdown surfaces only the phase, the session, and the
    // authorized roots; binding rows stay in the wire view untouched.
    const model = presentShadowStatus(snapshotOf({
      view: { ...READY_VIEW, bindings: [{
        workspaceId: 'ws-1',
        canonicalPath: 'D:/projects/alpha',
        bindingRevision: 7,
        state: 'ready',
      } as ShadowStatusView['bindings'][number]] },
    }))
    expect(model.phase).toBe('online')
    expect(model).not.toHaveProperty('projects')
  })
})
