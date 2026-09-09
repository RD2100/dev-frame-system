/**
 * Package entry for the shadow router. The default export is the
 * {@link ShadowRouter} Cordis service the Loader mounts; the named exports
 * carry the request/receipt shapes, the domain spec, the stable error type,
 * and the Shadow tool whitelist seam. The service registers as
 * `ctx.shadowRouter`.
 * @module @deepseek-ai/dsh-experimental-shadow-router
 */

export { ShadowRouterError } from './errors.ts'
export type { ShadowRouterErrorCode } from './errors.ts'
export { AcceptanceHash, ShadowMessageId, ShadowRequestId } from './ids.ts'
export {
  shadowBindingRecordSchema,
  shadowDeliveryRecordSchema,
  shadowRequestRecordSchema,
  shadowRouterDomainSpec,
} from './spec.ts'
export type {
  ShadowBindingRecord,
  ShadowBindingState,
  ShadowDeliveryMode,
  ShadowDeliveryRecord,
  ShadowDeliveryState,
  ShadowRequestKind,
  ShadowRequestRecord,
} from './spec.ts'
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
  ShadowRouterConfig,
  ShadowRouterStatus,
  ShadowStatusBinding,
} from './service.ts'
export { SHADOW_TOOL_NAMES, installShadowTools } from './tools.ts'
export { ShadowRouter as default } from './service.ts'
