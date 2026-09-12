/**
 * The delivery forwarder: turns the shadow router's forwardable `received`
 * work deliveries into durable follow-ups on the bound controllers' live
 * agents, then records each forwarded messageId in the `shadow_bridge`
 * domain. The router's `shadow/delivery-received` event feeds one unit per
 * real transition into `received`; the full reconciliation polls
 * ({@link DeliveryForwarder.poll}) cover deliveries that entered `received`
 * outside this listener's window — before mount, in a previous process, or
 * through the router's recovery. Every unit, event-fed or polled, runs
 * serialized on one chain, so the two channels can never overlap on one
 * delivery. The router's rows stay the durable record of delivery state; the
 * marker table only prevents re-forwarding.
 * @module @deepseek-ai/dsh-experimental-shadow-bridge/forwarder
 */

import type { Agent, AgentRegistry } from '@deepseek-ai/dsh-agent'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import type { UserMessage } from '@deepseek-ai/dsh-llm'
import type { KvTable } from '@deepseek-ai/dsh-storage-domain'
import type { ShadowRouter } from '@deepseek-ai/dsh-experimental-shadow-routing'
import type {
  ShadowBindingRecord,
  ShadowDeliveryRecord,
  ShadowMessageId,
} from '@deepseek-ai/dsh-experimental-shadow-routing'
import type { ShadowBridgeForwardedRecord } from './spec.ts'
import { renderFollowupText } from './text.ts'

/** Collaborators one forwarder needs; all structural, so tests can fake them. */
export interface DeliveryForwarderDeps {
  /**
   * Resolves the mounted router at forward time; `undefined` before it
   * mounts. Reading per unit keeps either mount order working without an
   * injection.
   */
  readonly readRouter: () => ShadowRouter | undefined
  /** The live-agent registry; the only forwarding target surface (v1 forwards to live controllers only). */
  readonly agents: Pick<AgentRegistry, 'get'>
  /** The `forwarded` marker table of the `shadow_bridge` domain. */
  readonly table: KvTable<ShadowMessageId, ShadowBridgeForwardedRecord>
  /** Upper bound in characters on one forwarded follow-up text. */
  readonly maxChars: number
  /** The agents registry's initiator-clearing boundary; no forwarding unit inherits an ambient initiator. */
  readonly withoutInitiator: Pick<AgentRegistry, 'withoutInitiator'>['withoutInitiator']
  /** Process-local warning sink for contained failures. */
  readonly log: (message: string) => void
}

/**
 * Whether one delivery may be forwarded onto its binding's controller, per
 * the detailed design's delivery gate: only a `work` message whose Goal and
 * acceptance binding match an authorized open run schedules a follow-up, and
 * a `stopping` or `stopped` receiver schedules none. The match is checked
 * against the binding's CURRENT run, so a Goal switch after receipt keeps the
 * previous Goal's message out of the controller's current Goal.
 * @param delivery - The router delivery row in `received` state.
 * @param binding - The controller binding of the delivery's workspace.
 * @returns true when the delivery is forwardable.
 */
export function forwardableDelivery(delivery: ShadowDeliveryRecord, binding: ShadowBindingRecord): boolean {
  if (binding.state === 'stopping' || binding.state === 'stopped') return false
  if (binding.activeGoalId === undefined || binding.activeAcceptanceHash === undefined) return false
  return delivery.goalId === binding.activeGoalId
    && delivery.acceptanceHash === binding.activeAcceptanceHash
}

/** Render one not-yet-forwarded delivery as an identified user-role relay message. */
function followupMessage(delivery: ShadowDeliveryRecord, maxChars: number): UserMessage {
  return createUserMessage({
    content: [{ type: 'text', text: renderFollowupText(delivery, maxChars) }],
    source: { kind: 'plugin', plugin: 'shadow-bridge', form: 'relay' },
  })
}

/**
 * One serialized forwarder. Every forwarding unit — one
 * `shadow/delivery-received` event or one polled delivery — passes the
 * delivery gate, forwards onto the live agent the binding resolves to, and
 * marks the messageId; the forwarded set restored from the marker table makes
 * every later unit — in this process or after a restart — skip it.
 */
export class DeliveryForwarder {
  private readonly deps: DeliveryForwarderDeps
  /** MessageIds already forwarded, restored from the marker table at construction. */
  private readonly forwarded = new Set<ShadowMessageId>()
  /** Tail of the forwarding chain; never rejects, so the chain survives every unit failure. */
  private queue: Promise<void> = Promise.resolve()

  /**
   * @param deps - Collaborators and limits; the marker table's current rows
   *   seed the forwarded set, so a cold start resumes exactly-once forwarding.
   */
  constructor(deps: DeliveryForwarderDeps) {
    this.deps = deps
    for (const key of deps.table.keys()) this.forwarded.add(key)
  }

  /**
   * Handle one `shadow/delivery-received` event: gate, forward, and mark the
   * recorded delivery once, serialized behind every other unit. Never
   * rejects — the event is observe-only, so any failure, including a closing
   * initiator scope, logs a warning and leaves the delivery for the
   * reconciliation and safety-net polls.
   * @param delivery - The frozen delivery record snapshot as it entered `received`.
   * @returns resolution once the delivery's unit settled.
   */
  onDeliveryReceived(delivery: ShadowDeliveryRecord): Promise<void> {
    return this.serialize(delivery).catch((error: unknown) => {
      this.deps.log(`delivery-received handling for "${delivery.messageId}" failed; the delivery stays unmarked: ${error instanceof Error ? error.message : String(error)}`)
    })
  }

  /**
   * Run one full reconciliation pass over the router's delivery index,
   * forwarding every eligible delivery once in the router's stable
   * (createdAt, messageId) order. Failures inside a unit are contained per
   * delivery; a failure of the pass itself, such as a closing initiator
   * scope, rejects to the caller.
   * @returns resolution once every pass unit has settled.
   */
  async poll(): Promise<void> {
    const router = this.deps.readRouter()
    if (router === undefined) return
    for (const delivery of router.listDeliveries()) {
      if (delivery.state !== 'received' || delivery.mode !== 'work') continue
      await this.serialize(delivery)
    }
  }

  /**
   * Resolve once every enqueued unit has settled, however it settled. A unit
   * enqueued while draining extends the wait, so the disposal path can await
   * this without stranding a half-forwarded delivery.
   * @returns resolution at forwarding quiescence.
   */
  async settle(): Promise<void> {
    while (true) {
      const tail = this.queue
      await tail
      if (this.queue === tail) return
    }
  }

  /**
   * Run one forwarding unit behind the previous one and outside any inherited
   * agent-initiator boundary. The returned promise carries the unit's
   * outcome; the chain itself always continues.
   * @param delivery - The delivery row or event snapshot to forward.
   * @returns the unit's outcome.
   */
  private serialize(delivery: ShadowDeliveryRecord): Promise<void> {
    const run = this.queue.then(() => this.deps.withoutInitiator(() => this.forwardOne(delivery)))
    this.queue = run.then(() => {}, () => {})
    return run
  }

  /**
   * Gate, forward, and mark one delivery — the one per-delivery path shared
   * by the event and the polls. Every expected failure is contained with a
   * warning that leaves the delivery unmarked, so a later unit retries it —
   * a visible duplicate beats silently lost input.
   * @param delivery - The delivery row or event snapshot to forward.
   */
  private async forwardOne(delivery: ShadowDeliveryRecord): Promise<void> {
    if (delivery.state !== 'received' || delivery.mode !== 'work') return
    if (this.forwarded.has(delivery.messageId)) return
    const router = this.deps.readRouter()
    if (router === undefined) return
    const binding = router.findBinding(delivery.workspaceId)
    if (binding === undefined || !forwardableDelivery(delivery, binding)) return
    const agent: Agent | undefined = this.deps.agents.get(binding.controllerSessionId)
    // v1 forwards to live controllers only: without a live agent the
    // delivery waits for a later unit; the bridge never creates or resumes one.
    if (agent === undefined) return
    try {
      agent.followup(followupMessage(delivery, this.deps.maxChars))
    } catch (error: unknown) {
      this.deps.log(`follow-up for "${delivery.messageId}" was rejected; the delivery stays unmarked: ${error instanceof Error ? error.message : String(error)}`)
      return
    }
    try {
      await this.deps.table.put(delivery.messageId, {
        messageId: delivery.messageId,
        workspaceId: delivery.workspaceId,
        controllerSessionId: binding.controllerSessionId,
        forwardedAt: new Date().toISOString(),
      })
    } catch (error: unknown) {
      // The marker failed after the follow-up entered the inbox: the next
      // unit forwards the delivery again, and the identical header makes
      // the duplicate recognizable.
      this.deps.log(`forwarding marker for "${delivery.messageId}" could not be persisted; the delivery will forward again: ${error instanceof Error ? error.message : String(error)}`)
      return
    }
    this.forwarded.add(delivery.messageId)
  }
}
