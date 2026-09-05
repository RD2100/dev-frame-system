/** The stable error type for shadow-router failures. */

import { HarnessError } from '@deepseek-ai/dsh-llm'

/** Stable, machine-routable failure classifications for Shadow routing. */
export type ShadowRouterErrorCode =
  /** The calling session is not the host-designated Shadow; project tools never serve other roles. */
  | 'SHADOW_CALLER_FORBIDDEN'
  /** A request was malformed: an unsafe id, an unknown mode, or a bounded field outside its range. */
  | 'SHADOW_INVALID_REQUEST'
  /** The requested root directory does not exist or is not a directory; nothing is created implicitly. */
  | 'SHADOW_ROOT_MISSING'
  /** The canonical root is not covered by any host-authorized root. */
  | 'SHADOW_ROOT_UNAUTHORIZED'
  /** The requested root physically nests an already-open project root, or vice versa. */
  | 'SHADOW_ROOTS_OVERLAP'
  /** An existing binding pins a different controller profile than the deployment currently serves. */
  | 'SHADOW_PROFILE_CONFLICT'
  /** No controller binding exists for the requested workspace. */
  | 'SHADOW_WORKSPACE_UNKNOWN'
  /** The request carried an obsolete bindingRevision; the host re-reads status and retries. */
  | 'SHADOW_STALE_REVISION'
  /** project_open met a binding that is stopping or stopped; restart follows the host recovery policy. */
  | 'SHADOW_PROJECT_STOPPED'
  /** The receiving project is not admitting deliveries: stopping, stopped, or its controller is not live. */
  | 'SHADOW_RECEIVER_CLOSED'
  /** The workspace records no authorized open run, so no work or note can be delivered against one. */
  | 'SHADOW_GOAL_NOT_AUTHORIZED'
  /** The message's Goal or acceptance hash does not match the authorized open run. */
  | 'SHADOW_GOAL_STALE'
  /** The receiving project's pending-delivery queue is at its configured limit. */
  | 'SHADOW_QUEUE_FULL'
  /** The bounded message text exceeded the configured message size. */
  | 'SHADOW_MESSAGE_TOO_LARGE'
  /** The same requestId was replayed with different normalized input. */
  | 'SHADOW_REQUEST_CONFLICT'
  /** The workspace binding is marked needs_attention; its durable failure reason explains why. */
  | 'SHADOW_NEEDS_ATTENTION'
  /** A config value is outside its serviceable range or its authorized roots are missing or nested. */
  | 'SHADOW_INVALID_CONFIG'
  /** The storage domain refused a write, or a record on disk failed its schema. */
  | 'SHADOW_PERSISTENCE'

/**
 * Structured failure from binding, delivery, or tool dispatch, so host
 * admission and diagnostics can route on the code alone. Extends the harness
 * error so tool dispatch carries `{ name, code }` in the failure info.
 */
export class ShadowRouterError extends HarnessError {
  /** Stable machine-routable failure classification. */
  declare readonly code: ShadowRouterErrorCode

  /**
   * @param message - Human-readable rejection reason.
   * @param code - Stable failure classification.
   * @param options - Original storage or filesystem failure, when one exists.
   */
  constructor(message: string, code: ShadowRouterErrorCode, options?: ErrorOptions) {
    super(message, code, options)
    this.name = 'ShadowRouterError'
  }
}
