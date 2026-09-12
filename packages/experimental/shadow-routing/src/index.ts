/**
 * Package entry for the shadow routing Service Definition. The default export
 * is the abstract {@link ShadowRouter} the Loader never mounts directly; the
 * named exports carry the contract vocabulary (branded ids, binding/delivery
 * records, request/receipt shapes, the stable error type, and the router
 * config type). The Service Provider is
 * `@deepseek-ai/dsh-experimental-shadow-router`.
 * @module @deepseek-ai/dsh-experimental-shadow-routing
 */

export { ShadowRouterError } from './errors.ts'
export type { ShadowRouterErrorCode } from './errors.ts'
export { AcceptanceHash, ShadowMessageId, ShadowRequestId } from './ids.ts'
export { ShadowRouter } from './service.ts'
export type {
  ProjectDeliverySummary,
  ProjectOpenRequest,
  ProjectOpenResult,
  ProjectSendRequest,
  ProjectSendResult,
  ProjectStatusEntry,
  ProjectStatusResult,
  ProjectStopRequest,
  ProjectStopResult,
  ShadowBindingRecord,
  ShadowBindingState,
  ShadowDeliveryMode,
  ShadowDeliveryRecord,
  ShadowDeliveryState,
  ShadowRequestKind,
  ShadowRequestRecord,
  ShadowRouterStatus,
  ShadowStatusBinding,
} from './types.ts'
export { ShadowRouter as default } from './service.ts'
