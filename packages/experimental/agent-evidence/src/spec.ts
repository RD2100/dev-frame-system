/** The agent-evidence domain declaration: receipt schemas and the `defineDomain` spec. */

import { z } from 'zod'
import { brandString } from '@deepseek-ai/dsh-brand'
import { GoalId } from '@deepseek-ai/dsh-goal'
import type { SessionId } from '@deepseek-ai/dsh-session'
import { defineDomain, domainTable } from '@deepseek-ai/dsh-storage-domain'
import { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { AcceptanceHash, SourceFingerprint, WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type {
  SubmissionReceipt,
  TaskGoalBindingReceipt,
  VerificationSnapshot,
} from './types.ts'
import { CommitSha, EvidenceReceiptId } from './ids.ts'

/** Receipt identity schema; validation owns the brand factory. */
const receiptId = z.string().min(1).transform(value => EvidenceReceiptId(value))

/** Task identity schema; validation owns the brand factory. */
const taskId = z.string().min(1).transform(value => TaskId(value))

/** Session identity schema at the durable boundary; the id is opaque here. */
const sessionId = z.string().min(1).transform(value => brandString<SessionId>(value))

/** Goal identity schema at the durable boundary; the id is opaque here. */
const goalId = z.string().min(1).transform(value => GoalId(value))

/** Controller session schema; the DevFrame factory owns validation. */
const controllerSessionId = z.string().min(1).transform(value => ControllerSessionId(value))

/** Workspace identity schema; the DevFrame factory owns the brand. */
const workspaceId = z.string().min(1).transform(value => WorkspaceId(value))

/** Acceptance digest schema; the DevFrame factory owns the brand. */
const acceptanceHash = z.string().min(1).transform(value => AcceptanceHash(value))

/** Source-input digest schema; the DevFrame factory owns the brand. */
const sourceFingerprint = z.string().min(1).transform(value => SourceFingerprint(value))

/** Commit object name schema; validation enforces the lowercase hex shape. */
const commitSha = z.string().regex(/^[0-9a-f]{40}$|^[0-9a-f]{64}$/).transform(value => CommitSha(value))

/** Path list schema: every entry must be a non-empty trimmed string. */
const pathList = z.array(z.string().refine(value => value.length > 0 && value === value.trim(), {
  message: 'paths must be non-empty trimmed strings',
}))

/**
 * Durable shape of one task/Goal binding receipt, cast onto the shared
 * {@link TaskGoalBindingReceipt} contract so shape drift fails to compile.
 */
export const taskGoalBindingReceiptSchema = z.object({
  receiptId,
  taskId,
  controllerSessionId,
  goalId,
  goalRevision: z.number().int().nonnegative(),
  workspaceId,
  acceptanceHash,
  sourceFingerprint,
  recordedAt: z.string().min(1),
}) as z.ZodType<TaskGoalBindingReceipt>

/** Durable shape of one submission receipt. */
export const submissionReceiptSchema = z.object({
  receiptId,
  taskId,
  submittedBy: sessionId,
  commit: commitSha,
  changedPaths: pathList,
  inputDigest: sourceFingerprint,
  recordedAt: z.string().min(1),
}) as z.ZodType<SubmissionReceipt>

/** Durable shape of one verification snapshot. */
export const verificationSnapshotSchema = z.object({
  receiptId,
  taskId,
  command: z.string().min(1).refine(value => value === value.trim(), { message: 'command must be trimmed' }),
  exitCode: z.number().int(),
  artifactPaths: pathList,
  recordedAt: z.string().min(1),
}) as z.ZodType<VerificationSnapshot>

/**
 * The agent-evidence domain spec: three append-only receipt tables keyed by
 * receipt id. Records are written through on every receipt and rebuilt from
 * these tables on start, so the tables are the only durable authority.
 */
export const agentEvidenceDomainSpec = defineDomain({
  name: 'agent_evidence',
  version: 1,
  tables: {
    bindings: domainTable<EvidenceReceiptId, TaskGoalBindingReceipt>(taskGoalBindingReceiptSchema),
    submissions: domainTable<EvidenceReceiptId, SubmissionReceipt>(submissionReceiptSchema),
    verifications: domainTable<EvidenceReceiptId, VerificationSnapshot>(verificationSnapshotSchema),
  },
})
