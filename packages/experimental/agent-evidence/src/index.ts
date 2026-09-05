/**
 * Package entry for the agent evidence ledger. The default export is the
 * {@link AgentEvidenceLedger} Cordis service the Loader mounts; the named
 * exports carry the receipt shapes, the domain spec, the id factories, and
 * the stable error type. The service registers as `ctx.agentEvidence`.
 * @module @deepseek-ai/dsh-experimental-agent-evidence
 */

export { AgentEvidenceError } from './errors.ts'
export type { AgentEvidenceErrorCode } from './errors.ts'
export { agentEvidenceDomainSpec, submissionReceiptSchema, taskGoalBindingReceiptSchema, verificationSnapshotSchema } from './spec.ts'
export { CommitSha, EvidenceReceiptId } from './ids.ts'
export { AgentEvidenceLedger } from './ledger.ts'
export type { SubmissionRequest, TaskEvidence, TaskGoalBindingRequest, VerificationRequest } from './ledger.ts'
export { AgentEvidenceLedger as default } from './ledger.ts'
