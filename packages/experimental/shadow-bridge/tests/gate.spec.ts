/**
 * Unit evidence for the bridge's forwarder and safety-net loop: the delivery
 * gate's every rejection branch, the event path and the reconciliation polls
 * converging on exactly-once marking, containment of follow-up, marker, and
 * initiator-boundary failures, the bounded follow-up text, and the timer
 * loop's quiescing disposal. The wired composition behavior is covered by
 * the real-Loader spec.
 * @module tests/gate
 */

import { describe, expect, it, vi } from 'vitest'
import type { Agent, AgentRegistry } from '@deepseek-ai/dsh-agent'
import type { UserMessage } from '@deepseek-ai/dsh-llm'
import { AcceptanceHash, ShadowMessageId, ShadowRequestId } from '@deepseek-ai/dsh-experimental-shadow-routing'
import type { ShadowBindingRecord, ShadowDeliveryRecord, ShadowRouter } from '@deepseek-ai/dsh-experimental-shadow-routing'
import type { SessionId } from '@deepseek-ai/dsh-session'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type { KvTable } from '@deepseek-ai/dsh-storage-domain'
import { DeliveryForwarder, forwardableDelivery } from '../src/forwarder.ts'
import { PollLoop } from '../src/loop.ts'
import { deliveryHeader, renderFollowupText } from '../src/text.ts'
import type { ShadowBridgeForwardedRecord } from '../src/spec.ts'

const WORKSPACE = WorkspaceId('ws-test')
const CONTROLLER = 'session-ctrl' as SessionId

const sleep = (ms: number): Promise<void> => new Promise<void>((resolve) => { setTimeout(resolve, ms) })

/** Flatten one message's text blocks. */
function textOf(message: UserMessage): string {
  return message.content.flatMap(block => block.type === 'text' ? [block.text] : []).join('')
}

/** One router delivery row with received-work defaults; overrides replace any field. */
function delivery(overrides: Partial<ShadowDeliveryRecord> = {}): ShadowDeliveryRecord {
  return {
    messageId: ShadowMessageId('msg-test-1'),
    requestId: ShadowRequestId('req-test-1'),
    sourceSessionId: 'session-shadow' as SessionId,
    workspaceId: WORKSPACE,
    bindingRevision: 1,
    goalId: 'goal-1',
    acceptanceHash: AcceptanceHash('hash-12345678'),
    mode: 'work',
    text: 'Please check the gate.',
    state: 'received',
    createdAt: '2026-09-11T00:00:00.000Z',
    updatedAt: '2026-09-11T00:00:01.000Z',
    receivedAt: '2026-09-11T00:00:01.000Z',
    ...overrides,
  }
}

/** One controller binding row with an authorized open run; overrides replace any field. */
function binding(overrides: Partial<ShadowBindingRecord> = {}): ShadowBindingRecord {
  return {
    workspaceId: WORKSPACE,
    canonicalPath: '/tmp/project',
    controllerSessionId: CONTROLLER,
    profileKey: 'devframe',
    bindingRevision: 1,
    requestId: 'req-open-1',
    state: 'ready',
    activeGoalId: 'goal-1',
    activeAcceptanceHash: AcceptanceHash('hash-12345678'),
    createdAt: '2026-09-11T00:00:00.000Z',
    updatedAt: '2026-09-11T00:00:00.000Z',
    ...overrides,
  }
}

/** One fake live agent that records follow-up texts and may reject them. */
function fakeAgent(options: { failFollowup?: Error } = {}): { agent: Agent; texts: string[]; attempts: number } {
  const texts: string[] = []
  let attempts = 0
  const agent = {
    followup: (message: UserMessage): void => {
      attempts += 1
      if (options.failFollowup !== undefined) throw options.failFollowup
      texts.push(textOf(message))
    },
  } as unknown as Agent
  return { agent, texts, get attempts(): number { return attempts } }
}

/** A fake marker table recording puts and optionally failing the next one. */
function markerTable(seed: readonly ShadowMessageId[] = []): {
  table: KvTable<ShadowMessageId, ShadowBridgeForwardedRecord>
  puts: ShadowMessageId[]
  failNextPut: (error: Error) => void
} {
  const rows = new Map<string, ShadowBridgeForwardedRecord>(seed.map((id): [ShadowMessageId, ShadowBridgeForwardedRecord] => [id, {
    messageId: id,
    workspaceId: WORKSPACE,
    controllerSessionId: CONTROLLER,
    forwardedAt: '2026-09-11T00:00:00.000Z',
  }]))
  const puts: ShadowMessageId[] = []
  let failure: Error | undefined
  return {
    puts,
    failNextPut: (error: Error) => { failure = error },
    table: {
      keys: () => [...rows.keys()].map(key => ShadowMessageId(key)).values(),
      put: async (key: ShadowMessageId, value: ShadowBridgeForwardedRecord): Promise<void> => {
        if (failure !== undefined) {
          const error = failure
          failure = undefined
          throw error
        }
        rows.set(key, value)
        puts.push(key)
      },
    } as unknown as KvTable<ShadowMessageId, ShadowBridgeForwardedRecord>,
  }
}

/** Assemble a forwarder over fakes and return every recorded observation. */
function forwarder(options: {
  deliveries?: ShadowDeliveryRecord[]
  bindings?: ShadowBindingRecord[]
  agents?: Map<string, Agent>
  markers?: KvTable<ShadowMessageId, ShadowBridgeForwardedRecord>
  maxChars?: number
  router?: ShadowRouter | undefined
  withoutInitiator?: Pick<AgentRegistry, 'withoutInitiator'>['withoutInitiator']
} = {}): { forwarder: DeliveryForwarder; markers: KvTable<ShadowMessageId, ShadowBridgeForwardedRecord>; logs: string[] } {
  const markers = options.markers ?? markerTable().table
  // An omitted binding list defaults to the one binding the default delivery
  // points at; a forwarded-poll scenario must otherwise resolve no binding.
  const bindings = options.bindings ?? [binding()]
  const router = options.router !== undefined ? options.router : {
    listDeliveries: () => options.deliveries ?? [],
    findBinding: (workspaceId: WorkspaceId) => bindings.find(row => row.workspaceId === workspaceId),
  } as unknown as ShadowRouter
  const agents = options.agents ?? new Map<string, Agent>()
  const logs: string[] = []
  return {
    forwarder: new DeliveryForwarder({
      readRouter: () => router,
      agents: { get: (id: SessionId) => agents.get(id) },
      table: markers,
      maxChars: options.maxChars ?? 10_000,
      withoutInitiator: options.withoutInitiator ?? (operation => operation()),
      log: (message: string) => { logs.push(message) },
    }),
    markers,
    logs,
  }
}

describe('the follow-up text', () => {
  it('opens with the deterministic header naming the delivery and workspace', () => {
    const row = delivery()
    expect(deliveryHeader(row.messageId, row.workspaceId)).toBe('[Shadow delivery msg-test-1 for workspace ws-test]')
    expect(renderFollowupText(row, 10_000)).toBe('[Shadow delivery msg-test-1 for workspace ws-test]\nPlease check the gate.')
  })

  it('keeps a result at exactly the limit and truncates the tail beyond it', () => {
    const row = delivery({ text: 'abcdefghij' })
    const exact = renderFollowupText(row, deliveryHeader(row.messageId, row.workspaceId).length + 1 + 10)
    expect(exact.endsWith('abcdefghij')).toBe(true)
    const truncated = renderFollowupText(row, 40)
    expect(truncated).toHaveLength(40)
    expect(truncated).toContain('msg-test-1')
    expect(truncated).not.toContain('abcdefghij')
  })

  it('cuts the header itself when the limit is smaller than the header', () => {
    const row = delivery()
    expect(renderFollowupText(row, 5)).toBe('[Shad')
  })
})

describe('the delivery gate', () => {
  it('accepts a received work delivery that matches the authorized open run', () => {
    expect(forwardableDelivery(delivery(), binding())).toBe(true)
  })

  it('rejects a stopping or stopped receiver regardless of the run', () => {
    for (const state of ['stopping', 'stopped'] as const) {
      expect(forwardableDelivery(delivery(), binding({ state }))).toBe(false)
    }
  })

  it('rejects a delivery when the binding records no authorized open run', () => {
    const { activeGoalId: _omittedGoal, ...noGoal } = binding()
    expect(forwardableDelivery(delivery(), noGoal)).toBe(false)
    const { activeAcceptanceHash: _omittedHash, ...noHash } = binding()
    expect(forwardableDelivery(delivery(), noHash)).toBe(false)
  })

  it('rejects a delivery owned by a different Goal or acceptance association', () => {
    expect(forwardableDelivery(delivery({ goalId: 'goal-2' }), binding())).toBe(false)
    expect(forwardableDelivery(delivery({ acceptanceHash: AcceptanceHash('other-123456') }), binding())).toBe(false)
  })

  it('forwards on binding facts alone: any receiver state except stopping or stopped', () => {
    expect(forwardableDelivery(delivery(), binding({ state: 'needs_attention' }))).toBe(true)
  })
})

describe('the forwarder poll', () => {
  it('forwards an eligible delivery once, records the marker, and skips it on every later poll', async () => {
    const { agent, texts } = fakeAgent()
    const markers = markerTable()
    const h = forwarder({
      deliveries: [delivery()],
      agents: new Map([[CONTROLLER, agent]]),
      markers: markers.table,
    })
    await h.forwarder.poll()
    expect(texts).toEqual(['[Shadow delivery msg-test-1 for workspace ws-test]\nPlease check the gate.'])
    expect(markers.puts).toEqual([delivery().messageId])
    await h.forwarder.poll()
    expect(texts).toHaveLength(1)
    expect(markers.puts).toHaveLength(1)
  })

  it('skips non-received states and note mode', async () => {
    const { agent, texts } = fakeAgent()
    const h = forwarder({
      deliveries: [
        delivery({ state: 'queued', messageId: ShadowMessageId('msg-test-q') }),
        delivery({ state: 'completed', messageId: ShadowMessageId('msg-test-c') }),
        delivery({ state: 'cancelled', messageId: ShadowMessageId('msg-test-x') }),
        delivery({ mode: 'note', messageId: ShadowMessageId('msg-test-n') }),
      ],
      agents: new Map([[CONTROLLER, agent]]),
    })
    await h.forwarder.poll()
    expect(texts).toEqual([])
  })

  it('skips deliveries already marked forwarded before this process started', async () => {
    const { agent, texts } = fakeAgent()
    const markers = markerTable([delivery().messageId])
    const h = forwarder({
      deliveries: [delivery()],
      agents: new Map([[CONTROLLER, agent]]),
      markers: markers.table,
    })
    await h.forwarder.poll()
    expect(texts).toEqual([])
    expect(markers.puts).toEqual([])
  })

  it('skips a delivery whose binding is missing or fails the gate', async () => {
    const { agent, texts } = fakeAgent()
    const markers = markerTable()
    const noBinding = forwarder({
      deliveries: [delivery()],
      bindings: [],
      agents: new Map([[CONTROLLER, agent]]),
      markers: markers.table,
    })
    await noBinding.forwarder.poll()
    const stopped = forwarder({
      deliveries: [delivery()],
      bindings: [binding({ state: 'stopped' })],
      agents: new Map([[CONTROLLER, agent]]),
      markers: markers.table,
    })
    await stopped.forwarder.poll()
    expect(texts).toEqual([])
    expect(markers.puts).toEqual([])
  })

  it('leaves a delivery unforwarded while no controller is live and forwards once one appears', async () => {
    const { agent, texts } = fakeAgent()
    const agents = new Map<string, Agent>()
    const h = forwarder({ deliveries: [delivery()], agents })
    await h.forwarder.poll()
    expect(texts).toEqual([])
    agents.set(CONTROLLER, agent)
    await h.forwarder.poll()
    expect(texts).toHaveLength(1)
  })

  it('is a no-op while no router is mounted', async () => {
    const { agent, texts } = fakeAgent()
    const markers = markerTable()
    const h = forwarder({ router: undefined, agents: new Map([[CONTROLLER, agent]]), markers: markers.table })
    await h.forwarder.poll()
    expect(texts).toEqual([])
    expect(markers.puts).toEqual([])
  })

  it('contains a rejected follow-up and retries it on the next poll', async () => {
    const failing = fakeAgent({ failFollowup: new Error('agent disposed') })
    const healthy = fakeAgent()
    const agents = new Map<string, Agent>([[CONTROLLER, failing.agent]])
    const markers = markerTable()
    const h = forwarder({
      deliveries: [delivery()],
      agents,
      markers: markers.table,
    })
    await h.forwarder.poll()
    expect(failing.attempts).toBe(1)
    expect(healthy.texts).toEqual([])
    expect(markers.puts).toEqual([])
    expect(h.logs.some(message => message.includes('agent disposed'))).toBe(true)
    agents.set(CONTROLLER, healthy.agent)
    await h.forwarder.poll()
    expect(healthy.texts).toHaveLength(1)
    expect(markers.puts).toEqual([delivery().messageId])
  })

  it('forwards again when the marker write fails, instead of losing the delivery', async () => {
    const { agent, texts } = fakeAgent()
    const markers = markerTable()
    markers.failNextPut(new Error('storage refused'))
    const h = forwarder({
      deliveries: [delivery()],
      agents: new Map([[CONTROLLER, agent]]),
      markers: markers.table,
    })
    await h.forwarder.poll()
    expect(texts).toHaveLength(1)
    expect(markers.puts).toEqual([])
    expect(h.logs.some(message => message.includes('will forward again'))).toBe(true)
    await h.forwarder.poll()
    expect(texts).toHaveLength(2)
  })

  it('bounds the forwarded text through the full path', async () => {
    const { agent, texts } = fakeAgent()
    const h = forwarder({
      deliveries: [delivery({ text: 'word '.repeat(200) })],
      agents: new Map([[CONTROLLER, agent]]),
      maxChars: 60,
    })
    await h.forwarder.poll()
    expect(texts).toHaveLength(1)
    expect(texts[0]).toHaveLength(60)
    expect(texts[0]).toContain('msg-test-1')
  })
})

describe('the delivery-received event path', () => {
  it('forwards the recorded delivery once and lets the next poll skip it', async () => {
    const { agent, texts } = fakeAgent()
    const markers = markerTable()
    const h = forwarder({
      deliveries: [delivery()],
      agents: new Map([[CONTROLLER, agent]]),
      markers: markers.table,
    })
    await h.forwarder.onDeliveryReceived(delivery())
    expect(texts).toEqual(['[Shadow delivery msg-test-1 for workspace ws-test]\nPlease check the gate.'])
    expect(markers.puts).toEqual([delivery().messageId])
    await h.forwarder.poll()
    expect(texts).toHaveLength(1)
    expect(markers.puts).toHaveLength(1)
  })

  it('converges on exactly-once across events, polls, and restarts, in both orders', async () => {
    const { agent, texts } = fakeAgent()
    const markers = markerTable()
    // Event first, then the reconciliation poll.
    const eventFirst = forwarder({
      deliveries: [delivery()],
      agents: new Map([[CONTROLLER, agent]]),
      markers: markers.table,
    })
    await eventFirst.forwarder.onDeliveryReceived(delivery())
    await eventFirst.forwarder.poll()
    expect(texts).toHaveLength(1)
    expect(markers.puts).toEqual([delivery().messageId])
    // Poll first, then the event, on a restarted forwarder over the same marker domain.
    const pollFirst = forwarder({
      deliveries: [delivery()],
      agents: new Map([[CONTROLLER, agent]]),
      markers: markers.table,
    })
    await pollFirst.forwarder.poll()
    await pollFirst.forwarder.onDeliveryReceived(delivery())
    expect(texts).toHaveLength(1)
    expect(markers.puts).toEqual([delivery().messageId])
  })

  it('applies the same gate on the event path', async () => {
    const { agent, texts } = fakeAgent()
    const markers = markerTable()
    const stopped = forwarder({
      deliveries: [delivery()],
      bindings: [binding({ state: 'stopped' })],
      agents: new Map([[CONTROLLER, agent]]),
      markers: markers.table,
    })
    await stopped.forwarder.onDeliveryReceived(delivery())
    const note = forwarder({
      deliveries: [delivery({ mode: 'note', messageId: ShadowMessageId('msg-test-n') })],
      agents: new Map([[CONTROLLER, agent]]),
      markers: markers.table,
    })
    await note.forwarder.onDeliveryReceived(delivery({ mode: 'note', messageId: ShadowMessageId('msg-test-n') }))
    expect(texts).toEqual([])
    expect(markers.puts).toEqual([])
  })

  it('contains a closing initiator scope and leaves the delivery for the safety net', async () => {
    const { agent, texts } = fakeAgent()
    const markers = markerTable()
    const h = forwarder({
      deliveries: [delivery()],
      agents: new Map([[CONTROLLER, agent]]),
      markers: markers.table,
      withoutInitiator: () => { throw new Error('initiator scope disposed') },
    })
    await expect(h.forwarder.onDeliveryReceived(delivery())).resolves.toBeUndefined()
    expect(texts).toEqual([])
    expect(markers.puts).toEqual([])
    expect(h.logs.some(message => message.includes('initiator scope disposed'))).toBe(true)
  })

  it('rejects the reconciliation poll when the initiator boundary is closing, so the loop contains it', async () => {
    const { agent, texts } = fakeAgent()
    const markers = markerTable()
    const h = forwarder({
      deliveries: [delivery()],
      agents: new Map([[CONTROLLER, agent]]),
      markers: markers.table,
      withoutInitiator: () => { throw new Error('initiator scope disposed') },
    })
    await expect(h.forwarder.poll()).rejects.toThrow('initiator scope disposed')
    expect(texts).toEqual([])
    expect(markers.puts).toEqual([])
  })

  it('resolves settle only after the enqueued unit finishes', async () => {
    const { agent, texts } = fakeAgent()
    let release!: () => void
    const gate = new Promise<void>((resolve) => { release = resolve })
    let released = false
    const rows = new Map<string, ShadowBridgeForwardedRecord>()
    const puts: ShadowMessageId[] = []
    const table = {
      keys: () => [].values(),
      put: async (key: ShadowMessageId, value: ShadowBridgeForwardedRecord): Promise<void> => {
        if (!released) await gate
        rows.set(key, value)
        puts.push(key)
      },
    } as unknown as KvTable<ShadowMessageId, ShadowBridgeForwardedRecord>
    const h = forwarder({ deliveries: [delivery()], agents: new Map([[CONTROLLER, agent]]), markers: table })
    const pending = h.forwarder.onDeliveryReceived(delivery())
    const draining = h.forwarder.settle()
    let settled = false
    void draining.then(() => { settled = true })
    // One microtask turn: the unit starts and blocks inside the marker write.
    await Promise.resolve()
    expect(settled).toBe(false)
    released = true
    release()
    await expect(draining).resolves.toBeUndefined()
    await pending
    expect(puts).toEqual([delivery().messageId])
    expect(texts).toHaveLength(1)
  })

  it('resolves settle on an idle chain', async () => {
    const h = forwarder()
    await expect(h.forwarder.settle()).resolves.toBeUndefined()
  })
})

describe('the safety-net loop', () => {
  it('keeps polling until dispose, then stops', async () => {
    let runs = 0
    const loop = new PollLoop({
      intervalMs: 1,
      run: async () => { runs += 1 },
      log: () => {},
    })
    loop.start()
    await vi.waitFor(() => { expect(runs).toBeGreaterThanOrEqual(2) })
    await loop.dispose()
    const settled = runs
    await sleep(25)
    expect(runs).toBe(settled)
  })

  it('contains a rejected poll, logs it, and keeps polling', async () => {
    let runs = 0
    const logs: string[] = []
    const loop = new PollLoop({
      intervalMs: 1,
      run: async () => {
        runs += 1
        if (runs < 3) throw new Error('router unavailable')
      },
      log: (message: string) => { logs.push(message) },
    })
    loop.start()
    await vi.waitFor(() => { expect(runs).toBeGreaterThanOrEqual(3) })
    await loop.dispose()
    expect(logs.some(message => message.includes('router unavailable'))).toBe(true)
  })

  it('disposes to quiescence by awaiting the in-flight poll', async () => {
    let started = false
    let finished = false
    const loop = new PollLoop({
      intervalMs: 1,
      run: async () => {
        started = true
        await sleep(30)
        finished = true
      },
      log: () => {},
    })
    loop.start()
    await vi.waitFor(() => { expect(started).toBe(true) })
    await loop.dispose()
    expect(finished).toBe(true)
  })

  it('disposes cleanly before the first tick', async () => {
    let runs = 0
    const loop = new PollLoop({
      intervalMs: 50,
      run: async () => { runs += 1 },
      log: () => {},
    })
    await loop.dispose()
    await sleep(20)
    expect(runs).toBe(0)
  })

  it('does not start a timer callback that was queued before disposal', async () => {
    const callbacks: Array<() => void> = []
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout').mockImplementation((handler) => {
      if (typeof handler !== 'function') throw new TypeError('test timer callback must be callable')
      callbacks.push(handler)
      return 1 as unknown as ReturnType<typeof setTimeout>
    })
    const clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout').mockImplementation(() => undefined)
    try {
      let runs = 0
      const loop = new PollLoop({
        intervalMs: 1,
        run: async () => { runs += 1 },
        log: () => {},
      })
      loop.start()
      const disposal = loop.dispose()
      callbacks[0]?.()
      await disposal
      expect(runs).toBe(0)
    } finally {
      clearTimeoutSpy.mockRestore()
      setTimeoutSpy.mockRestore()
    }
  })
})
