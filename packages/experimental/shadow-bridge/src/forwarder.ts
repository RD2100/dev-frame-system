/**
 * The delivery forwarder: one poll turns the shadow router's forwardable
 * `received` work deliveries into durable follow-ups on the bound controllers'
 * live agents, then records each forwarded messageId in the `shadow_bridge`
 * domain. The router's rows stay the durable record of delivery state; the
 * marker table only prevents re-forwarding.
 * @module @deepseek-ai/dsh-experimental-shadow-bridge/forwarder
 */

import type { Agent, AgentRegistry } from '@deepseek-ai/dsh-agent'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import type { UserMessage } from '@deepseek-ai/dsh-llm'
import type { KvTable } from '@deepseek-ai/dsh-storage-domain'
import type {
  ShadowBindingRecord,
  ShadowDeliveryRecord,
  ShadowMessageId,
  ShadowRouter,
} from '@deepseek-ai/dsh-experimental-shadow-router'
import type { ShadowBridgeForwardedRecord } from './spec.ts'
import { renderFollowupText } from './text.ts'

/** Collaborators one forwarder needs; all structural, so tests can fake them. */
export interface DeliveryForwarderDeps {
  /**
   * Resolves the mounted router at poll time; `undefined` before it mounts.
   * Reading per poll keeps either mount order working without an injection.
   */
  readonly readRouter: () => ShadowRouter | undefined
  /** The live-agent registry; the only forwarding target surface (v1 forwards to live controllers only). */
  readonly agents: Pick<AgentRegistry, 'get'>
  /** The `forwarded` marker table of the `shadow_bridge` domain. */
  readonly table: KvTable<ShadowMessageId, ShadowBridgeForwardedRecord>
  /** Upper bound in characters on one forwarded follow-up text. */
  readonly maxChars: number
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
 * One serial poller over the router's delivery index. `poll()` forwards every
 * eligible delivery once, in the router's stable (createdAt, messageId) order;
 * the forwarded set restored from the marker table makes every later poll —
 * in this process or after a restart — skip them.
 */
export class DeliveryForwarder {
  private readonly deps: DeliveryForwarderDeps
  /** MessageIds already forwarded, restored from the marker table at construction. */
  private readonly forwarded = new Set<ShadowMessageId>()

  /**
   * @param deps - Collaborators and limits; the marker table's current rows
   *   seed the forwarded set, so a cold start resumes exactly-once forwarding.
   */
  constructor(deps: DeliveryForwarderDeps) {
    this.deps = deps
    for (const key of deps.table.keys()) this.forwarded.add(key)
  }

  /**
   * Run one poll. Every failure is contained per delivery: a follow-up or
   * marker-write failure logs a warning and leaves the delivery unmarked, so
   * a later poll retries it — a visible duplicate beats silently lost input.
   */
  async poll(): Promise<void> {
    const router = this.deps.readRouter()
    if (router === undefined) return
    for (const delivery of router.listDeliveries()) {
      if (delivery.state !== 'received' || delivery.mode !== 'work') continue
      if (this.forwarded.has(delivery.messageId)) continue
      const binding = router.findBinding(delivery.workspaceId)
      if (binding === undefined || !forwardableDelivery(delivery, binding)) continue
      const agent: Agent | undefined = this.deps.agents.get(binding.controllerSessionId)
      // v1 forwards to live controllers only: without a live agent the
      // delivery waits for a later poll; the bridge never creates or resumes one.
      if (agent === undefined) continue
      try {
        agent.followup(followupMessage(delivery, this.deps.maxChars))
      } catch (error: unknown) {
        this.deps.log(`follow-up for "${delivery.messageId}" was rejected; the delivery stays unmarked: ${error instanceof Error ? error.message : String(error)}`)
        continue
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
        // poll forwards the delivery again, and the identical header makes
        // the duplicate recognizable.
        this.deps.log(`forwarding marker for "${delivery.messageId}" could not be persisted; the delivery will forward again: ${error instanceof Error ? error.message : String(error)}`)
        continue
      }
      this.forwarded.add(delivery.messageId)
    }
  }
}
