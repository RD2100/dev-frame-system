/**
 * Host Remote owner of the read-only `shadow` status namespace. One method:
 * the aggregate {@link ShadowRouterStatus} snapshot host status surfaces (the
 * Web Shadow card) display. The controller stays registered when the
 * deployment mounts no shadow router and answers `mounted: false`, so a
 * status surface renders the honest disabled state instead of a transport
 * failure. The read carries no Shadow-caller gate: the caller is the host
 * composition itself, never a model scope.
 *
 * @module @deepseek-ai/dsh-experimental-shadow-controller
 */

import type { Context } from '@deepseek-ai/cordis'
import type { ShadowStatusView } from './types.ts'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'

export type { ShadowRouterStatus, ShadowStatusView } from './types.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    /** Host owner of the `shadow` Remote namespace. */
    shadowController: ShadowController
  }
}

/**
 * Host service backing the generated `ctx.remote.shadow` namespace. The read
 * never mutates router state and never wakes a model.
 */
export class ShadowController extends TypertRemoteService {
  /**
   * Register the `shadow` namespace.
   * @param ctx - Host context whose optional `shadowRouter` owns the snapshot.
   */
  constructor(ctx: Context) {
    super(ctx, 'shadowController', { namespace: 'shadow' })
  }

  /**
   * Read the aggregate Shadow status: mount presence, designation, controller
   * liveness, authorized roots, and binding rows.
   * @returns the router's snapshot, or the honest `mounted: false` answer when
   *   this deployment composes no shadow router.
   */
  @Remote
  readStatus(): ShadowStatusView {
    const router = this.ctx.get('shadowRouter')
    if (router === undefined) {
      return {
        mounted: false,
        shadowLive: false,
        authorizedRoots: [],
        bindings: [],
      }
    }
    return { mounted: true, ...router.readStatus() }
  }
}

export default ShadowController
