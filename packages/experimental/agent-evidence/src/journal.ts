/**
 * The honest DevFrame evidence producer: `recordVerification` resolves the
 * stored approved required-checks configuration, executes it exactly through
 * the injected execution face, and appends the real results as one
 * `devframe/verification` record; `recordReview` appends the reviewer decision
 * as one `devframe/review` record. Both records go through the same
 * schema-checked {@link DevFrameSessionJournal} write face — construction wires
 * the reviewer gate, so no bypass path exists. The producer records evidence;
 * completion admission stays with the DevFrame controller.
 * @module @deepseek-ai/dsh-experimental-agent-evidence/journal
 */

import { randomUUID } from 'node:crypto'
import type { GoalResultBinding } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { DevFrameReviewId, DevFrameVerificationId } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import type {
  DevFrameReviewEventData,
  DevFrameReviewFinding,
  DevFrameVerificationEventData,
} from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import type {
  RequiredChecksConfigStore,
  RequiredChecksDigest,
} from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { DevFrameSessionJournal } from '@deepseek-ai/dsh-experimental-devframe/src/session-journal.ts'
import type { DevFrameFlush } from '@deepseek-ai/dsh-experimental-devframe/src/session-journal.ts'
import type { Session, SessionId } from '@deepseek-ai/dsh-session'
import { subprocessRequiredChecksExecution } from './check-runner.ts'
import type { RequiredChecksExecution } from './check-runner.ts'
import { EvidenceReviewGate } from './review-gate.ts'
import type { EvidenceReviewerDirectory } from './review-gate.ts'

/** Construction options of {@link AgentEvidenceJournal}. */
export interface AgentEvidenceJournalOptions {
  /** Native `ctx.sessions.flush`-compatible durability callback. */
  readonly flush: DevFrameFlush
  /** SessionId-keyed reviewer role authority; wired into the journal's review gate. */
  readonly reviewerDirectory: EvidenceReviewerDirectory
  /** Execution face for required checks; defaults to `subprocessRequiredChecksExecution`. */
  readonly execution?: RequiredChecksExecution
}

/** Request accepted by {@link AgentEvidenceJournal.recordVerification}. */
export interface VerificationEvidenceRequest {
  /** Controller Session whose log the devframe projection folds. */
  readonly session: Session
  /** Complete work identity the evidence attributes to (host-resolved). */
  readonly binding: GoalResultBinding
  /** Canonical digest of the approved configuration, registered in the store at approval time. */
  readonly requiredChecksDigest: RequiredChecksDigest
  /** Configuration store resolving the digest to the stored approved checklist. */
  readonly requiredChecksStore: RequiredChecksConfigStore
}

/** Request accepted by {@link AgentEvidenceJournal.recordReview}. */
export interface ReviewEvidenceRequest {
  /** Controller Session whose log the devframe projection folds. */
  readonly session: Session
  /** Complete work identity the evidence attributes to (host-resolved). */
  readonly binding: GoalResultBinding
  /** Exact reviewer Session identity; cross-authorized by the gate before append. */
  readonly reviewerSessionId: SessionId
  /** Role-policy revision active during review. */
  readonly policyVersion: string
  /** Review decision used by completion admission. */
  readonly decision: 'pass' | 'changes_required'
  /** Bounded findings explaining a non-pass decision. */
  readonly findings: readonly DevFrameReviewFinding[]
}

/**
 * Append DevFrame verification and review evidence records to the controller
 * Session log through the DevFrame Session journal, with required checks
 * executed honestly by a real execution face.
 */
export class AgentEvidenceJournal {
  private readonly journal: DevFrameSessionJournal
  private readonly execution: RequiredChecksExecution

  /**
   * @param options - Durability callback, reviewer authority, and the optional
   *   execution face; construction wires the review gate into the journal, so
   *   a journal without a reviewer authority cannot be built.
   */
  constructor(options: AgentEvidenceJournalOptions) {
    this.journal = new DevFrameSessionJournal(options.flush, new EvidenceReviewGate(options.reviewerDirectory))
    this.execution = options.execution ?? subprocessRequiredChecksExecution
  }

  /**
   * Execute the stored approved required checks exactly and record the real
   * results as one `devframe/verification` event on the Session log.
   * @param request - Session, host-resolved binding, registered digest, and
   *   the store resolving that digest to the approved configuration.
   * @returns The accepted verification event data.
   * @throws {@link RequiredChecksError} when the digest has no stored
   *   configuration or the stored bytes fail their schema — before any event
   *   is written.
   * @throws {@link DevFramePersistenceError} when the durability checkpoint
   *   fails or was previously latched for this Session.
   */
  async recordVerification(request: VerificationEvidenceRequest): Promise<DevFrameVerificationEventData> {
    const config = await request.requiredChecksStore.load(request.requiredChecksDigest)
    const checks = await this.execution(config)
    const status = checks.every(check => check.status === 'passed') ? 'passed' as const : 'failed' as const
    const event = await this.journal.append(request.session, 'devframe/verification', {
      version: 1,
      verificationId: DevFrameVerificationId(randomUUID()),
      binding: request.binding,
      snapshotId: request.binding.snapshotId,
      status,
      requiredChecks: { config, digest: request.requiredChecksDigest },
      checks,
    })
    return event.data
  }

  /**
   * Record the reviewer decision as one `devframe/review` event on the
   * Session log; the review gate cross-authorizes the reviewer Session before
   * the event is appended.
   * @param request - Session, host-resolved binding, reviewer identity, policy
   *   revision, decision, and bounded findings.
   * @returns The accepted review event data.
   * @throws {@link AgentEvidenceError} with code
   *   `AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED` when the reviewer Session holds no
   *   reviewer role — the event is not appended and the journal does not latch.
   * @throws {@link DevFramePersistenceError} when the durability checkpoint
   *   fails or was previously latched for this Session.
   */
  async recordReview(request: ReviewEvidenceRequest): Promise<DevFrameReviewEventData> {
    const event = await this.journal.append(request.session, 'devframe/review', {
      version: 1,
      reviewId: DevFrameReviewId(randomUUID()),
      binding: request.binding,
      snapshotId: request.binding.snapshotId,
      reviewerSessionId: request.reviewerSessionId,
      policyVersion: request.policyVersion,
      decision: request.decision,
      findings: request.findings,
    })
    return event.data
  }
}
