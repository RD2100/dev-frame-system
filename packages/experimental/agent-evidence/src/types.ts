/**
 * The receipt vocabulary of the evidence ledger. Identity fields reuse the
 * experimental DevFrame work-binding types ({@link GoalId},
 * {@link ControllerSessionId}, {@link AcceptanceHash},
 * {@link SourceFingerprint}, {@link WorkspaceId}) so evidence is tied to the
 * same work identity dispatch, verification, and completion already carry —
 * the ledger stores provenance only and holds no acceptance verdict.
 * @module @deepseek-ai/dsh-experimental-agent-evidence/types
 */

import type { Branded } from '@deepseek-ai/dsh-brand'
import type { GoalId } from '@deepseek-ai/dsh-goal/types'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type { AcceptanceHash, SourceFingerprint, WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'

/** Identifies one evidence receipt across the ledger. */
export type EvidenceReceiptId = Branded<'EvidenceReceiptId'>

/** A git commit object name (SHA-1 or SHA-256, lowercase hex). */
export type CommitSha = Branded<'GitCommitSha'>

/**
 * Ties one task's evidence trail to the Goal binding that owns the work:
 * the identity tuple mirrors the DevFrame goal-result binding for a single
 * task, so every later receipt resolves to one Goal through this record.
 */
export interface TaskGoalBindingReceipt {
  /** Stable receipt identity. */
  readonly receiptId: EvidenceReceiptId
  /** The task whose work serves the Goal. */
  readonly taskId: TaskId
  /** Controller Session that owns the Goal. */
  readonly controllerSessionId: ControllerSessionId
  /** Native Goal the work serves. */
  readonly goalId: GoalId
  /** Goal revision captured when the binding was recorded. */
  readonly goalRevision: number
  /** Host-owned workspace the work runs in. */
  readonly workspaceId: WorkspaceId
  /** Fingerprint of the approved acceptance configuration. */
  readonly acceptanceHash: AcceptanceHash
  /** Fingerprint of the source inputs the work started from. */
  readonly sourceFingerprint: SourceFingerprint
  /** ISO-8601 recording instant. */
  readonly recordedAt: string
}

/**
 * One submission receipt: what was committed, which paths changed, and the
 * digest of the inputs the work was based on. Append-only — a re-submission
 * adds a receipt, it never rewrites one.
 */
export interface SubmissionReceipt {
  /** Stable receipt identity. */
  readonly receiptId: EvidenceReceiptId
  /** The task whose work was submitted. */
  readonly taskId: TaskId
  /** Session that produced the commit. */
  readonly submittedBy: SessionId
  /** The commit object name, validated lowercase hex. */
  readonly commit: CommitSha
  /** Paths the commit changed, as reported by the submitter. */
  readonly changedPaths: readonly string[]
  /** Digest of the source inputs the work started from. */
  readonly inputDigest: SourceFingerprint
  /** ISO-8601 recording instant. */
  readonly recordedAt: string
}

/**
 * One verification snapshot: the command that ran, the exit code it settled
 * with, and the artifacts it produced. A non-zero exit code is evidence too
 * — recording a failure is the ledger's job, judging it is not.
 */
export interface VerificationSnapshot {
  /** Stable receipt identity. */
  readonly receiptId: EvidenceReceiptId
  /** The task the verification ran for. */
  readonly taskId: TaskId
  /** The verification command, verbatim. */
  readonly command: string
  /** The process exit code. */
  readonly exitCode: number
  /** Paths of the artifacts the command produced. */
  readonly artifactPaths: readonly string[]
  /** ISO-8601 recording instant. */
  readonly recordedAt: string
}
