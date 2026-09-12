/**
 * Package entry for the shadow router Service Provider. The default export is
 * the concrete {@link ShadowRouter} Cordis service the Loader mounts; the
 * named exports carry the request/receipt shapes, the domain spec, the stable
 * error type, and the Shadow tool whitelist seam. The service registers as
 * `ctx.shadowRouter` under the contract declared by
 * `@deepseek-ai/dsh-experimental-shadow-routing`, whose vocabulary is
 * re-exported here so existing family consumers keep one import root.
 * @module @deepseek-ai/dsh-experimental-shadow-router
 */

export { ShadowRouterError } from '@deepseek-ai/dsh-experimental-shadow-routing'
export type { ShadowRouterErrorCode } from '@deepseek-ai/dsh-experimental-shadow-routing'
export { AcceptanceHash, ShadowMessageId, ShadowRequestId } from '@deepseek-ai/dsh-experimental-shadow-routing'
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
} from '@deepseek-ai/dsh-experimental-shadow-routing'
export type { ShadowRouterConfig } from './service.ts'
export {
  shadowBindingRecordSchema,
  shadowDeliveryRecordSchema,
  shadowRequestRecordSchema,
  shadowRouterDomainSpec,
} from './spec.ts'
export { ShadowRouter } from './service.ts'
export { SHADOW_TOOL_NAMES, installShadowTools } from './tools.ts'
export { ShadowRouter as default } from './service.ts'
