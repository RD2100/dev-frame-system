export {
  createTerminalAttachmentController,
  type TerminalAttachmentController
} from "./attachmentController.ts";
export {
  closeTerminalSession,
  type CloseTerminalSessionInput,
  type TerminalCloseConfirmation,
  type TerminalCloseResult
} from "./closeFlow.ts";
export {
  createTerminalNodeFeature,
  defaultTerminalNodeLimits,
  type CreateTerminalNodeFeatureInput,
  type TerminalNodeFeature
} from "./feature.ts";
export {
  createBufferedTerminalInputQueue,
  writeQueuedTerminalInput,
  type BufferedTerminalInputQueue,
  type QueuedTerminalInput
} from "./inputQueue.ts";
export {
  detectTerminalFileLinks,
  toTerminalLinkTarget,
  type DetectedTerminalFileLink
} from "./linkDetection.ts";
export {
  resolveInitialTerminalDimensions,
  type TerminalScreenDimensions,
  type TerminalScreenDimensionsLike
} from "./dimensions.ts";
export {
  applyTerminalSessionStatusProjection,
  applyTerminalSessionTitleProjection,
  createTerminalSessionExitProjection,
  createTerminalSessionFailedProjection,
  isTerminalSessionEndedStatus,
  terminalSessionLostMessage,
  type TerminalSessionStatusProjection
} from "./sessionProjection.ts";
export {
  createTerminalScreenStateCache,
  type CachedTerminalScreenState,
  type TerminalScreenStateCache
} from "./screenStateCache.ts";
export {
  defaultMaxTerminalScrollbackChars,
  mergeTerminalScrollbackSnapshots,
  resolveTerminalScrollbackDelta,
  truncateTerminalScrollback,
  type TerminalScrollbackOptions
} from "./scrollback.ts";
export { resolveSuffixPrefixOverlap } from "./stringOverlap.ts";
