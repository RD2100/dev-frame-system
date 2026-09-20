/** The status controller: latest read wins, superseded reads never publish. */

import { describe, expect, it } from 'vitest'
import { RemoteError } from '@deepseek-ai/dsh-client-test-runtime'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type { ShadowBoardSnapshot, ShadowStatusView } from '@deepseek-ai/dsh-experimental-shadow-controller'
import {
  ShadowBoardController,
  ShadowStatusController,
  type ShadowBoardPort,
  type ShadowStatusPort,
} from '../src/client/shadow-store.ts'

const VIEW: ShadowStatusView = {
  mounted: true,
  shadowSessionId: 'session-shadow',
  shadowLive: true,
  authorizedRoots: ['D:/projects'],
  bindings: [],
}

/** A port whose reads are released one call at a time under test control. */
function gatedPort(): {
  port: ShadowStatusPort
  releaseNext: (answer?: { ok: false; error: RemoteError<'gateway/internal'> }) => void
  calls: () => number
} {
  const pending: ((answer?: { ok: false; error: RemoteError<'gateway/internal'> }) => void)[] = []
  let calls = 0
  const port: ShadowStatusPort = () => {
    calls += 1
    return new Promise((resolve) => {
      pending.push((answer) => {
        resolve(answer ?? { ok: true as const, value: VIEW })
      })
    })
  }
  return {
    port,
    releaseNext: (answer) => { pending.shift()?.(answer) },
    calls: () => calls,
  }
}

describe('the Shadow status controller', () => {
  it('starts pending and publishes a good read into the store', async () => {
    const gate = gatedPort()
    const controller = new ShadowStatusController(gate.port)
    expect(controller.store.getSnapshot()).toEqual({ view: undefined, error: undefined })

    const running = controller.refresh()
    expect(gate.calls()).toBe(1)
    gate.releaseNext()
    await running
    expect(controller.store.getSnapshot()).toEqual({ view: VIEW, error: undefined })
  })

  it('publishes the failure message of a failed read', async () => {
    const gate = gatedPort()
    const controller = new ShadowStatusController(gate.port)
    const running = controller.refresh()
    gate.releaseNext({ ok: false, error: new RemoteError('gateway/internal', 'offline', {}) })
    await running
    expect(controller.store.getSnapshot()).toEqual({ view: undefined, error: 'offline' })
  })

  it('never publishes a read a later read has superseded', async () => {
    const gate = gatedPort()
    const controller = new ShadowStatusController(gate.port)
    const first = controller.refresh()
    const second = controller.refresh()
    gate.releaseNext()
    await first
    expect(controller.store.getSnapshot()).toEqual({ view: undefined, error: undefined })
    gate.releaseNext()
    await second
    expect(controller.store.getSnapshot()).toEqual({ view: VIEW, error: undefined })
  })

  it('keeps the last good view while a later read failed', async () => {
    const gate = gatedPort()
    const controller = new ShadowStatusController(gate.port)
    const first = controller.refresh()
    gate.releaseNext()
    await first
    const second = controller.refresh()
    gate.releaseNext({ ok: false, error: new RemoteError('gateway/internal', 'offline', {}) })
    await second
    expect(controller.store.getSnapshot()).toEqual({ view: VIEW, error: 'offline' })
  })
})

const BOARD: ShadowBoardSnapshot = {
  mounted: true,
  bindings: [{ workspaceId: 'ws-1', state: 'ready', controllerSessionId: 'session-controller' as SessionId }],
  tasks: [{
    taskId: 'task-1', pluginId: 'devframe-goal', title: 'Ship the board', state: 'planned',
    createdAt: '2026-09-20T10:00:00Z', updatedAt: '2026-09-20T10:00:00Z', startReady: true,
  }],
}

/** A port whose reads are released one call at a time under test control. */
function gatedBoardPort(): {
  port: ShadowBoardPort
  releaseNext: (answer?: { ok: false; error: RemoteError<'gateway/internal'> }) => void
  calls: () => number
} {
  const pending: ((answer?: { ok: false; error: RemoteError<'gateway/internal'> }) => void)[] = []
  let calls = 0
  const port: ShadowBoardPort = () => {
    calls += 1
    return new Promise((resolve) => {
      pending.push((answer) => {
        resolve(answer ?? { ok: true as const, value: BOARD })
      })
    })
  }
  return {
    port,
    releaseNext: (answer) => { pending.shift()?.(answer) },
    calls: () => calls,
  }
}

describe('the Shadow board controller', () => {
  it('starts pending and publishes a good read into the store', async () => {
    const gate = gatedBoardPort()
    const controller = new ShadowBoardController(gate.port)
    expect(controller.store.getSnapshot()).toEqual({ board: undefined, error: undefined })

    const running = controller.refresh()
    expect(gate.calls()).toBe(1)
    gate.releaseNext()
    await running
    expect(controller.store.getSnapshot()).toEqual({ board: BOARD, error: undefined })
  })

  it('publishes the failure message of a failed read', async () => {
    const gate = gatedBoardPort()
    const controller = new ShadowBoardController(gate.port)
    const running = controller.refresh()
    gate.releaseNext({ ok: false, error: new RemoteError('gateway/internal', 'offline', {}) })
    await running
    expect(controller.store.getSnapshot()).toEqual({ board: undefined, error: 'offline' })
  })

  it('never publishes a read a later read has superseded', async () => {
    const gate = gatedBoardPort()
    const controller = new ShadowBoardController(gate.port)
    const first = controller.refresh()
    const second = controller.refresh()
    gate.releaseNext()
    await first
    expect(controller.store.getSnapshot()).toEqual({ board: undefined, error: undefined })
    gate.releaseNext()
    await second
    expect(controller.store.getSnapshot()).toEqual({ board: BOARD, error: undefined })
  })

  it('keeps the last good board while a later read failed', async () => {
    const gate = gatedBoardPort()
    const controller = new ShadowBoardController(gate.port)
    const first = controller.refresh()
    gate.releaseNext()
    await first
    const second = controller.refresh()
    gate.releaseNext({ ok: false, error: new RemoteError('gateway/internal', 'offline', {}) })
    await second
    expect(controller.store.getSnapshot()).toEqual({ board: BOARD, error: 'offline' })
  })
})
