/**
 * Wire receipts of the shadow project write faces: the vocabulary that
 * crosses the typert Remote boundary between the host bridge and the
 * controller's public remotes.
 * @module @deepseek-ai/dsh-experimental-shadow-router/types
 */

import type { SessionId } from '@deepseek-ai/dsh-session'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type { ShadowMessageId } from './ids.ts'
import type { ShadowBindingState } from './spec.ts'

/** The receipt `project_open` returns: one workspace's controller association. */
export interface ProjectOpenResult {
  /** The workspace registry's stable project identity. */
  readonly workspaceId: WorkspaceId
  /** The reserved (then actual) controller root session. */
  readonly controllerSessionId: SessionId
  /** Association version after the open. */
  readonly bindingRevision: number
  /** Provisioning state at return; `ready` is the usable one. */
  readonly state: ShadowBindingState
  /** Canonical root the registry recorded. */
  readonly canonicalPath: string
}

/**
 * The receipt `project_send` returns. `status` is `received`: durable target
 * acceptance of the input — never a claim that the work ran or succeeded.
 */
export interface ProjectSendResult {
  /** Stable delivery identity, derived from the request id. */
  readonly messageId: ShadowMessageId
  /** Receiving project. */
  readonly workspaceId: WorkspaceId
  /** The durable receipt state; always `received` at send time. */
  readonly status: 'received'
}

/** The receipt `project_stop` returns for one project's stop. */
export interface ProjectStopResult {
  /** The stopped project. */
  readonly workspaceId: WorkspaceId
  /** `stopping` until the host confirms quiescence, then `stopped`. */
  readonly status: 'stopping' | 'stopped'
  /** Pending deliveries cancelled by this stop; they stay visible, never dropped. */
  readonly cancelledDeliveries: number
  /** Association version after the stop. */
  readonly bindingRevision: number
}
