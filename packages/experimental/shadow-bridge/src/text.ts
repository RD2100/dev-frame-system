/**
 * Deterministic follow-up text for one forwarded delivery: the fixed header
 * naming the delivery's identity plus the verbatim delivery text, bounded by
 * the configured character limit.
 * @module @deepseek-ai/dsh-experimental-shadow-bridge/text
 */

import type { ShadowDeliveryRecord, ShadowMessageId } from '@deepseek-ai/dsh-experimental-shadow-router'
import type { WorkspaceId } from '@deepseek-ai/dsh-workspace'

/**
 * Render the fixed header of one forwarded delivery. The header is stable for
 * a given delivery: the controller can correlate a repeated forward across a
 * crash window by its identical `messageId`.
 * @param messageId - The router delivery identity.
 * @param workspaceId - The project the delivery belongs to.
 * @returns the bracketed one-line header.
 */
export function deliveryHeader(messageId: ShadowMessageId, workspaceId: WorkspaceId): string {
  return `[Shadow delivery ${messageId} for workspace ${workspaceId}]`
}

/**
 * Render one delivery's follow-up text: the fixed header, one newline, then
 * the verbatim delivery text. When the combined text exceeds `maxChars`, the
 * tail is cut silently to the exact limit — the header and the delivery's
 * leading text survive, and the result is deterministic for a given delivery
 * and limit.
 * @param delivery - The delivery row whose identity and text to render.
 * @param maxChars - Upper bound in characters on the complete result.
 * @returns the complete follow-up text of at most `maxChars` characters.
 */
export function renderFollowupText(
  delivery: Pick<ShadowDeliveryRecord, 'messageId' | 'workspaceId' | 'text'>,
  maxChars: number,
): string {
  const full = `${deliveryHeader(delivery.messageId, delivery.workspaceId)}\n${delivery.text}`
  return full.length <= maxChars ? full : full.slice(0, maxChars)
}
