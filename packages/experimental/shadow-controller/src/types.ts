/**
 * Client-safe status vocabulary of the `shadow` Remote namespace.
 * @module @deepseek-ai/dsh-experimental-shadow-controller/types
 */

import type { ShadowRouterStatus } from '@deepseek-ai/dsh-experimental-shadow-router'

export type { ShadowRouterStatus } from '@deepseek-ai/dsh-experimental-shadow-router'

/** The status vocabulary a Client reads: the router snapshot plus mount presence. */
export interface ShadowStatusView extends ShadowRouterStatus {
  /** Whether the deployment mounts a shadow router at all. */
  readonly mounted: boolean
}
