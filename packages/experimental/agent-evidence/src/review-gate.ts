/**
 * Reviewer authorization gate for DevFrame review recording. The gate is the
 * AT1-05 wrong-reviewer rejection: it consumes a host-wired SessionId-keyed
 * role directory and refuses any review submission whose Session the deployed
 * role policy has not made reviewer-eligible — the reviewer role, or the
 * hierarchy-authorized lead tier the host recorded — with the stable
 * `AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED` code.
 *
 * The gate structurally satisfies the DevFrame journal's `DevFrameReviewGate`
 * seam, so a composition wires it into `DevFrameSessionJournal` without either
 * package importing the other.
 *
 * @module @deepseek-ai/dsh-experimental-agent-evidence/review-gate
 */

import type { SessionId } from '@deepseek-ai/dsh-session'
import { AgentEvidenceError } from './errors.ts'

/** The role values that make a Session reviewer-eligible. */
const REVIEWER_ELIGIBLE_ROLES: ReadonlySet<string> = new Set(['reviewer', 'lead'])

/**
 * SessionId-keyed role read face the gate authorizes against. Hosts wire it to
 * whichever deployed authority owns the reviewer role vocabulary — for example
 * the DevFrame role policy's SessionId read face or the durable role-policy
 * assignments — because the hierarchy `AgentRole` vocabulary has no reviewer.
 */
export interface EvidenceReviewerDirectory {
  /**
   * Resolve one Session's deployed role.
   * @param sessionId - Session identity carried by the review payload.
   * @returns The assigned role, or undefined when the Session is unbound.
   */
  roleOf(sessionId: SessionId): 'controller' | 'lead' | 'worker' | 'reviewer' | undefined
}

/**
 * Reject reviews submitted by Sessions without recorded reviewer authority.
 * Wired as the required review gate of the DevFrame Session journal, so a
 * review event whose `reviewerSessionId` resolves to neither the reviewer
 * role nor a hierarchy-authorized lead never reaches the Session log.
 */
export class EvidenceReviewGate {
  private readonly directory: EvidenceReviewerDirectory

  /**
   * @param directory - SessionId-keyed role authority deployed by the host.
   */
  constructor(directory: EvidenceReviewerDirectory) {
    this.directory = directory
  }

  /**
   * Reject a review submission whose Session holds no reviewer-eligible role.
   * @param sessionId - Reviewer Session identity carried by the review payload.
   * @returns Nothing; a rejection throws before the event is appended.
   * @throws {@link AgentEvidenceError} with code
   * `AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED` when the Session lacks the role.
   */
  requireReviewer(sessionId: SessionId): void {
    const role = this.directory.roleOf(sessionId)
    if (role === undefined || !REVIEWER_ELIGIBLE_ROLES.has(role)) {
      throw new AgentEvidenceError(
        `review Session "${sessionId}" holds no reviewer-eligible role`,
        'AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED',
      )
    }
  }
}
