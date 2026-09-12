/** Branded cross-boundary identifiers owned by the shadow-routing vocabulary. */

import { brandString, type Branded } from '@deepseek-ai/dsh-brand'
import { ShadowRouterError } from './errors.ts'

/**
 * One caller-issued routing request. The model reuses one stable value across
 * retries of the same logical request; the host keeps it out of the message
 * content. Same id plus identical normalized input replays the prior result;
 * the same id with different input is a `SHADOW_REQUEST_CONFLICT`.
 */
export type ShadowRequestId = Branded<'ShadowRequestId'>

/**
 * One durable cross-root delivery. Derived deterministically from the
 * request id at first persistence (`msg-<requestId>`), so a retried request
 * converges on the same message identity and target-side deduplication keys
 * on the same row.
 */
export type ShadowMessageId = Branded<'ShadowMessageId'>

/**
 * One caller-asserted acceptance association for a delivery. The value is an
 * opaque bounded token; matching it against the workspace's authorized open
 * run is what makes a `work` delivery schedulable and what keeps a previous
 * Goal's message from becoming input to the controller's current Goal.
 */
export type AcceptanceHash = Branded<'AcceptanceHash'>

/** Request ids are bounded URL-safe tokens: 1–128 chars of `[A-Za-z0-9._:-]`, leading alnum. */
const REQUEST_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/

/** Acceptance hashes are bounded printable-ASCII tokens, 8–256 chars. */
const ACCEPTANCE_HASH_PATTERN = /^[\x21-\x7E]{8,256}$/

/**
 * Brand a validated request id.
 * @param value - Raw request id from the tool boundary.
 * @returns the same string, branded at compile time.
 * @throws {@link ShadowRouterError} with code `SHADOW_INVALID_REQUEST` when
 * the value is not a bounded URL-safe token.
 */
export function ShadowRequestId(value: string): ShadowRequestId {
  if (typeof value !== 'string' || !REQUEST_ID_PATTERN.test(value)) {
    throw new ShadowRouterError(
      'requestId must be 1-128 chars of [A-Za-z0-9._:-] with a leading alphanumeric',
      'SHADOW_INVALID_REQUEST',
    )
  }
  return brandString<ShadowRequestId>(value)
}

/**
 * Brand a validated delivery message id.
 * @param value - Raw message id (`msg-<requestId>` as derived by the service).
 * @returns the same string, branded at compile time.
 * @throws {@link ShadowRouterError} with code `SHADOW_INVALID_REQUEST` when
 * the value is not a bounded URL-safe token.
 */
export function ShadowMessageId(value: string): ShadowMessageId {
  if (typeof value !== 'string' || !REQUEST_ID_PATTERN.test(value)) {
    throw new ShadowRouterError(
      'messageId must be 1-128 chars of [A-Za-z0-9._:-] with a leading alphanumeric',
      'SHADOW_INVALID_REQUEST',
    )
  }
  return brandString<ShadowMessageId>(value)
}

/**
 * Brand a validated acceptance hash.
 * @param value - Raw acceptance association token from the tool boundary.
 * @returns the same string, branded at compile time.
 * @throws {@link ShadowRouterError} with code `SHADOW_INVALID_REQUEST` when
 * the value is not a bounded printable-ASCII token.
 */
export function AcceptanceHash(value: string): AcceptanceHash {
  if (typeof value !== 'string' || !ACCEPTANCE_HASH_PATTERN.test(value)) {
    throw new ShadowRouterError(
      'acceptanceHash must be 8-256 printable non-space ASCII chars',
      'SHADOW_INVALID_REQUEST',
    )
  }
  return brandString<AcceptanceHash>(value)
}
