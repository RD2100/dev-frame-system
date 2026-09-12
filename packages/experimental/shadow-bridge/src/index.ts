/**
 * Package entry for the shadow delivery bridge. The named exports carry the
 * function-plugin face (`name`/`inject`/`Config`/`apply`, no default export):
 * an event-driven forwarder that turns the shadow router's forwardable
 * `received` work deliveries into durable follow-ups on the bound controllers'
 * live agents, exactly once per delivery across restarts. The router's
 * `shadow/delivery-received` event is the primary trigger; a mount-time and a
 * loader-settled full reconciliation poll plus a low-frequency safety-net
 * timer cover deliveries that entered `received` outside the listener's
 * window. The plugin registers no tools, no prompt sections, and no session
 * events; `ctx.shadowBridge` is deliberately absent — the bridge is a
 * background host service with no programmatic face beyond its composition
 * row.
 * @module @deepseek-ai/dsh-experimental-shadow-bridge
 */

import type { Context } from '@deepseek-ai/cordis'
// Empty type import carries the loader Context merge so `ctx.get('loader')`
// is typed for the post-settlement reconciliation await.
import type {} from '@deepseek-ai/cordis-plugin-loader'
import z from '@deepseek-ai/schemastery'
import { shadowBridgeDomainSpec } from './spec.ts'
import { DeliveryForwarder } from './forwarder.ts'
import { PollLoop } from './loop.ts'

/**
 * Plugin config. Both fields are required with no defaults — a composition
 * row without them fails the load (`misconfiguration fails loud`), and the
 * schemastery schema owns every constraint (positive safe integers).
 */
export interface ShadowBridgeConfig {
  /**
   * Positive safe integer: milliseconds between two safety-net reconciliation
   * polls. The `shadow/delivery-received` event carries live transitions, so
   * this bounds only how long a delivery the event path missed may wait.
   */
  intervalMs: number
  /** Positive safe integer: upper bound in characters on one forwarded follow-up text. */
  followupMaxChars: number
}

/** Cordis plugin name. */
export const name = 'shadow-bridge'

/** Required host services; the bridge cannot forward or persist without them. */
export const inject = ['agents', 'storageDomain']

/**
 * Validated deployment settings; both fields are required and bounded, so an
 * absent or out-of-range value fails the load before `apply` runs.
 */
export const Config: z<ShadowBridgeConfig> = z.object({
  intervalMs: z.number().step(1).min(1).required(),
  followupMaxChars: z.number().step(1).min(1).required(),
})

/**
 * Register the delivery bridge: open the `shadow_bridge` marker domain,
 * restore the forwarded set from it, subscribe to the router's
 * `shadow/delivery-received` event as the primary trigger, reconcile once at
 * mount and once after the composition settles, and arm the low-frequency
 * safety-net poll loop.
 * @param ctx - Host context carrying the agents registry, the storage domain
 *   facility, and — at any point before a productive forward — the shadow
 *   router.
 * @param config - Schema-validated composition settings.
 */
export async function apply(ctx: Context, config: ShadowBridgeConfig): Promise<void> {
  const domain = await ctx.storageDomain.open(shadowBridgeDomainSpec)
  ctx.effect(() => () => domain.close(), 'shadow-bridge.domainClose')
  const log = (message: string): void => { ctx.logger.warn(`shadow-bridge: ${message}`) }
  const forwarder = new DeliveryForwarder({
    readRouter: () => ctx.get('shadowRouter'),
    agents: ctx.agents,
    table: domain.table('forwarded'),
    maxChars: config.followupMaxChars,
    withoutInitiator: operation => ctx.agents.withoutInitiator(operation),
    log,
  })
  // The primary channel. `ctx.on` registers the listener as an effect of this
  // plugin's fiber, so disposal removes it with the plugin; the forwarder
  // contains every failure, so nothing escapes into the router's emit path.
  ctx.on('shadow/delivery-received', (_workspaceId, delivery) => {
    void forwarder.onDeliveryReceived(delivery)
  })
  // Startup reconciliation: two full polls cover deliveries that entered
  // `received` before this listener existed — before mount, in a previous
  // process, or while the composition was still settling.
  const reconcile = (when: string): void => {
    void forwarder.poll().catch((error: unknown) => {
      log(`${when} reconciliation poll failed: ${error instanceof Error ? error.message : String(error)}`)
    })
  }
  reconcile('mount')
  const loader = ctx.get('loader')
  if (loader !== undefined) {
    void loader.await().then(
      () => { reconcile('post-settlement') },
      (error: unknown) => { log(`composition settlement failed; skipping the post-settlement reconciliation: ${error instanceof Error ? error.message : String(error)}`) },
    )
  }
  // Safety net: the timer exists only for work the event and reconciliation
  // paths missed, so disposal drains both it and the event-fed chain.
  const loop = new PollLoop({
    intervalMs: config.intervalMs,
    run: () => forwarder.poll(),
    log,
  })
  ctx.effect(() => {
    loop.start()
    return async () => {
      await loop.dispose()
      await forwarder.settle()
    }
  }, 'shadow-bridge.pollLoop')
}
