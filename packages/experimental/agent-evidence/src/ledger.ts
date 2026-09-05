/**
 * The agent evidence ledger (`ctx.agentEvidence`): the Cordis service that
 * records and serves the append-only provenance trail of agent work —
 * task/Goal binding receipts, submission receipts, and verification
 * snapshots — over the `agent_evidence` storage domain.
 *
 * The ledger stores provenance only: it holds no acceptance verdict and
 * judges no verification result. Acceptance stays with the Goal binding
 * (DevFrame goal-binding) and task states (project-controller); every
 * receipt here resolves to that work through the same identity tuple the
 * DevFrame goal-result binding carries. Receipts are append-only facts and
 * are restored verbatim on start.
 *
 * @module @deepseek-ai/dsh-experimental-agent-evidence/ledger
 */

import { randomUUID } from 'node:crypto'
import { Service, type Context } from '@deepseek-ai/cordis'
import type { KvTable } from '@deepseek-ai/dsh-storage-domain'
import type { GoalId } from '@deepseek-ai/dsh-goal/types'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { AgentEvidenceError } from './errors.ts'
import type {
  EvidenceReceiptId,
  SubmissionReceipt,
  TaskGoalBindingReceipt,
  VerificationSnapshot,
} from './types.ts'
import {
  agentEvidenceDomainSpec,
  submissionReceiptSchema,
  taskGoalBindingReceiptSchema,
  verificationSnapshotSchema,
} from './spec.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    agentEvidence: AgentEvidenceLedger
  }
}

/** Request for one task/Goal binding receipt. */
export interface TaskGoalBindingRequest {
  /** The task whose work serves the Goal. */
  readonly taskId: TaskId
  /** Controller Session that owns the Goal. */
  readonly controllerSessionId: ControllerSessionId
  /** Native Goal the work serves. */
  readonly goalId: GoalId
  /** Goal revision captured when the binding is recorded. */
  readonly goalRevision: number
  /** Host-owned workspace the work runs in. */
  readonly workspaceId: string
  /** Fingerprint of the approved acceptance configuration. */
  readonly acceptanceHash: string
  /** Fingerprint of the source inputs the work started from. */
  readonly sourceFingerprint: string
}

/** Request for one submission receipt. */
export interface SubmissionRequest {
  /** The task whose work was submitted. */
  readonly taskId: TaskId
  /** Session that produced the commit. */
  readonly submittedBy: SessionId
  /** The commit object name, 40 or 64 lowercase hex digits. */
  readonly commit: string
  /** Paths the commit changed, as reported by the submitter. */
  readonly changedPaths: readonly string[]
  /** Digest of the source inputs the work started from. */
  readonly inputDigest: string
}

/** Request for one verification snapshot. */
export interface VerificationRequest {
  /** The task the verification ran for. */
  readonly taskId: TaskId
  /** The verification command, verbatim. */
  readonly command: string
  /** The process exit code. */
  readonly exitCode: number
  /** Paths of the artifacts the command produced. */
  readonly artifactPaths: readonly string[]
}

/** The three receipt trails of one task, in recorded order. */
export interface TaskEvidence {
  /** Task/Goal binding receipts recorded for the task. */
  readonly bindings: readonly TaskGoalBindingReceipt[]
  /** Submission receipts recorded for the task. */
  readonly submissions: readonly SubmissionReceipt[]
  /** Verification snapshots recorded for the task. */
  readonly verifications: readonly VerificationSnapshot[]
}

/** Sort receipts into stable recorded order. */
function byRecorded<V extends { readonly recordedAt: string }>(left: V, right: V): number {
  return left.recordedAt.localeCompare(right.recordedAt)
}

/** The agent evidence ledger: append-only provenance per task and Goal. */
export class AgentEvidenceLedger extends Service {
  static inject = ['storageDomain']

  private bindingsTable?: KvTable<EvidenceReceiptId, TaskGoalBindingReceipt>
  private submissionsTable?: KvTable<EvidenceReceiptId, SubmissionReceipt>
  private verificationsTable?: KvTable<EvidenceReceiptId, VerificationSnapshot>
  private readonly bindings = new Map<EvidenceReceiptId, TaskGoalBindingReceipt>()
  private readonly submissions = new Map<EvidenceReceiptId, SubmissionReceipt>()
  private readonly verifications = new Map<EvidenceReceiptId, VerificationSnapshot>()

  constructor(ctx: Context) {
    super(ctx, 'agentEvidence')
  }

  protected async [Service.init](): Promise<void> {
    const domain = await this.ctx.storageDomain.open(agentEvidenceDomainSpec)
    this.ctx.effect(() => () => domain.close(), 'agent-evidence.domainClose')
    // Cold restore: every receipt trail comes back verbatim. The maps hold
    // detached frozen copies so the durable rows stay untouched.
    this.bindingsTable = domain.table('bindings')
    this.submissionsTable = domain.table('submissions')
    this.verificationsTable = domain.table('verifications')
    for (const [id, record] of this.bindingsTable.entries()) this.bindings.set(id, Object.freeze({ ...record }))
    for (const [id, record] of this.submissionsTable.entries()) this.submissions.set(id, Object.freeze({ ...record }))
    for (const [id, record] of this.verificationsTable.entries()) this.verifications.set(id, Object.freeze({ ...record }))
  }

  /**
   * Record one task/Goal binding receipt tying a task to the Goal that owns
   * its work. Re-recording under a new Goal revision adds a receipt; the
   * trail keeps them all.
   * @param request - The work identity to bind, in DevFrame goal-binding vocabulary.
   * @returns the recorded receipt.
   */
  async recordTaskGoalBinding(request: TaskGoalBindingRequest): Promise<TaskGoalBindingReceipt> {
    return await this.putReceipt(
      taskGoalBindingReceiptSchema,
      this.requireBindingsTable(),
      this.bindings,
      {
        receiptId: randomUUID(),
        taskId: request.taskId,
        controllerSessionId: request.controllerSessionId,
        goalId: request.goalId,
        goalRevision: request.goalRevision,
        workspaceId: request.workspaceId,
        acceptanceHash: request.acceptanceHash,
        sourceFingerprint: request.sourceFingerprint,
      },
    )
  }

  /**
   * Record one submission receipt: the commit, the changed paths, and the
   * digest of the inputs the work started from.
   * @param request - The submission facts.
   * @returns the recorded receipt.
   */
  async recordSubmission(request: SubmissionRequest): Promise<SubmissionReceipt> {
    return await this.putReceipt(
      submissionReceiptSchema,
      this.requireSubmissionsTable(),
      this.submissions,
      {
        receiptId: randomUUID(),
        taskId: request.taskId,
        submittedBy: request.submittedBy,
        commit: request.commit,
        changedPaths: [...request.changedPaths],
        inputDigest: request.inputDigest,
      },
    )
  }

  /**
   * Record one verification snapshot: command, exit code, and artifact
   * paths. A non-zero exit code is recorded as-is — the ledger does not
   * judge verification outcomes.
   * @param request - The verification facts.
   * @returns the recorded snapshot.
   */
  async recordVerification(request: VerificationRequest): Promise<VerificationSnapshot> {
    return await this.putReceipt(
      verificationSnapshotSchema,
      this.requireVerificationsTable(),
      this.verifications,
      {
        receiptId: randomUUID(),
        taskId: request.taskId,
        command: request.command,
        exitCode: request.exitCode,
        artifactPaths: [...request.artifactPaths],
      },
    )
  }

  /**
   * Read one task's complete evidence trail.
   * @param taskId - Task selecting the receipts.
   * @returns the three trails, each in recorded order.
   */
  byTask(taskId: TaskId): TaskEvidence {
    return {
      bindings: [...this.bindings.values()].filter(r => r.taskId === taskId).sort(byRecorded),
      submissions: [...this.submissions.values()].filter(r => r.taskId === taskId).sort(byRecorded),
      verifications: [...this.verifications.values()].filter(r => r.taskId === taskId).sort(byRecorded),
    }
  }

  /**
   * Read the binding receipts of one Goal on one controller session.
   * @param controllerSessionId - Controller Session that owns the Goal.
   * @param goalId - Goal whose bindings are queried.
   * @returns the matching binding receipts in recorded order.
   */
  bindingsByGoal(controllerSessionId: ControllerSessionId, goalId: GoalId): readonly TaskGoalBindingReceipt[] {
    return [...this.bindings.values()]
      .filter(r => r.controllerSessionId === controllerSessionId && r.goalId === goalId)
      .sort(byRecorded)
  }

  /**
   * Validate one receipt through its durable schema (which applies the
   * brands and stamps nothing — the caller passes `recordedAt`-less raw
   * fields and the schema owns the shapes), write it through to the domain
   * table, and mirror a frozen copy into the query map.
   */
  private async putReceipt<V extends { readonly receiptId: EvidenceReceiptId }>(
    schema: { parse(value: object): V },
    table: KvTable<EvidenceReceiptId, V>,
    mirror: Map<EvidenceReceiptId, V>,
    raw: object,
  ): Promise<V> {
    let parsed: V
    try {
      parsed = schema.parse({ ...raw, recordedAt: new Date().toISOString() })
    } catch (error: unknown) {
      throw new AgentEvidenceError('receipt failed its schema validation', 'AGENT_EVIDENCE_INVALID_RECEIPT', { cause: error })
    }
    try {
      await table.put(parsed.receiptId, parsed)
    } catch (error: unknown) {
      throw new AgentEvidenceError(
        `receipt "${String(parsed.receiptId)}" could not be persisted`,
        'AGENT_EVIDENCE_PERSISTENCE',
        { cause: error },
      )
    }
    const frozen = Object.freeze({ ...parsed })
    mirror.set(parsed.receiptId, frozen)
    return frozen
  }

  /** The opened bindings table; absent only before Service.init completed. */
  private requireBindingsTable(): KvTable<EvidenceReceiptId, TaskGoalBindingReceipt> {
    if (this.bindingsTable === undefined) {
      throw new AgentEvidenceError('the agent_evidence domain is not open yet', 'AGENT_EVIDENCE_PERSISTENCE')
    }
    return this.bindingsTable
  }

  /** The opened submissions table; absent only before Service.init completed. */
  private requireSubmissionsTable(): KvTable<EvidenceReceiptId, SubmissionReceipt> {
    if (this.submissionsTable === undefined) {
      throw new AgentEvidenceError('the agent_evidence domain is not open yet', 'AGENT_EVIDENCE_PERSISTENCE')
    }
    return this.submissionsTable
  }

  /** The opened verifications table; absent only before Service.init completed. */
  private requireVerificationsTable(): KvTable<EvidenceReceiptId, VerificationSnapshot> {
    if (this.verificationsTable === undefined) {
      throw new AgentEvidenceError('the agent_evidence domain is not open yet', 'AGENT_EVIDENCE_PERSISTENCE')
    }
    return this.verificationsTable
  }
}
