/** Branded identifiers owned by the evidence ledger. */

import { brandString, type Branded } from '@deepseek-ai/dsh-brand'
import { AgentEvidenceError } from './errors.ts'

/** Identifies one evidence receipt across the ledger. */
export type EvidenceReceiptId = Branded<'EvidenceReceiptId'>

/** A git commit object name (SHA-1 or SHA-256, lowercase hex). */
export type CommitSha = Branded<'GitCommitSha'>

/** A git commit object name: 40 (SHA-1) or 64 (SHA-256) lowercase hex digits. */
const COMMIT_SHA_RE = /^[0-9a-f]{40}$|^[0-9a-f]{64}$/

/**
 * Brand a receipt identifier minted by the ledger.
 * @param value - Non-empty, untrimmed-free receipt identifier.
 * @returns the same string, branded at compile time.
 * @throws {@link AgentEvidenceError} with code `AGENT_EVIDENCE_INVALID_RECEIPT`
 * when the value is empty, whitespace-only, or padded.
 */
export function EvidenceReceiptId(value: string): EvidenceReceiptId {
  return brandString<EvidenceReceiptId>(requireId(value, 'receiptId'))
}

/**
 * Brand a validated git commit object name.
 * @param value - 40 or 64 lowercase hex digits.
 * @returns the same string, branded at compile time.
 * @throws {@link AgentEvidenceError} with code `AGENT_EVIDENCE_INVALID_RECEIPT`
 * when the value is not a lowercase hex commit name.
 */
export function CommitSha(value: string): CommitSha {
  if (typeof value !== 'string' || !COMMIT_SHA_RE.test(value)) {
    throw new AgentEvidenceError(
      'commit must be a 40 or 64 character lowercase hex object name',
      'AGENT_EVIDENCE_INVALID_RECEIPT',
    )
  }
  return brandString<CommitSha>(value)
}

/** Validate one identifier before applying its compile-time brand. */
function requireId(value: string, field: string): string {
  if (typeof value !== 'string' || value.length === 0 || value.trim().length === 0 || value !== value.trim()) {
    throw new AgentEvidenceError(
      `${field} must be a non-empty trimmed string`,
      'AGENT_EVIDENCE_INVALID_RECEIPT',
    )
  }
  return value
}
