/**
 * Package entry for the shadow delivery bridge. The named exports carry the
 * function-plugin face (`name`/`inject`/`Config`/`apply`, no default export):
 * a background poller that turns the shadow router's forwardable `received`
 * work deliveries into durable follow-ups on the bound controllers' live
 * agents, exactly once per delivery across restarts. The plugin registers no
 * tools, no prompt sections, and no session events; `ctx.shadowBridge` is
 * deliberately absent — the bridge is a background host service with no
 * programmatic face beyond its composition row.
 * @module @deepseek-ai/dsh-experimental-shadow-bridge
 */

import type { Context } from '@deepseek-ai/cordis'
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
  /** Positive safe integer: milliseconds between one delivery poll and the next. */
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
 * restore the forwarded set from it, and arm the self-rescheduling poll loop
 * over the mounted router's public read face.
 * @param ctx - Host context carrying the agents registry, the storage domain
 *   facility, and — at any point before a productive poll — the shadow router.
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
    log,
  })
  const loop = new PollLoop({
    intervalMs: config.intervalMs,
    run: () => forwarder.poll(),
    withoutInitiator: operation => ctx.agents.withoutInitiator(operation),
    log,
  })
  ctx.effect(() => {
    loop.start()
    return () => loop.dispose()
  }, 'shadow-bridge.pollLoop')
}
