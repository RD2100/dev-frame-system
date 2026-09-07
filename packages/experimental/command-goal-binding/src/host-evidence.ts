/**
 * Composition-owned host evidence wiring for the DevFrame command surface:
 * the native flush closure, the projection-derived live role authority, the
 * composition-owned DevFrame Session journal, and the landing helpers that
 * put role-policy and goal-binding records on the controller Session log in
 * the fold-required order. The host collects every fact here; model input
 * never writes evidence (s4 rule 4).
 * @module @deepseek-ai/dsh-experimental-command-goal-binding/host-evidence
 */

import type { Context } from '@deepseek-ai/cordis'
import { createHash } from 'node:crypto'
import { EvidenceReviewGate } from '@deepseek-ai/dsh-experimental-agent-evidence'
import type { EvidenceReviewerDirectory } from '@deepseek-ai/dsh-experimental-agent-evidence'
import type {
  DevFrameRolePolicyEventData,
} from '@deepseek-ai/dsh-experimental-devframe'
import type { DevFrameRequiredChecksConfig } from '@deepseek-ai/dsh-experimental-devframe'
import { DevFrameSessionJournal } from '@deepseek-ai/dsh-experimental-devframe'
import type { DevFrameFlush } from '@deepseek-ai/dsh-experimental-devframe'
import type { DevFrameProjectionState } from '@deepseek-ai/dsh-experimental-devframe'
import type {
  GoalBinding,
  GoalResultBinding,
} from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type { Session, SessionId } from '@deepseek-ai/dsh-session'
import { AcceptanceHash } from '@deepseek-ai/dsh-experimental-devframe/shared'
import type { WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'

/**
 * Build the native durability callback the DevFrame journals flush through:
 * every appended DevFrame record is checkpointed with the Session store's
 * THE flush entry, so a failed checkpoint latches the writer instead of
 * leaving unverified state on disk.
 * @param ctx - the plugin fiber's context carrying `sessions`.
 * @returns a `ctx.sessions.flush`-compatible `DevFrameFlush`.
 */
export function sessionFlush(ctx: Context): DevFrameFlush {
  return session => ctx.sessions.flush(session)
}

/**
 * Assemble the composition-owned DevFrame Session journal: schema-checked,
 * per-Session serialized DevFrame writes whose review events are
 * cross-authorized through the projection-derived role directory. This
 * journal lands the role-policy and goal-binding records; the
 * `AgentEvidenceJournal` keeps its own internal journal instance for
 * verification records (the dual-journal latch window is a registered
 * limitation).
 * @param flush - the native durability callback from {@link sessionFlush}.
 * @param reviewerDirectory - the live SessionId-keyed role authority.
 * @returns the composition-owned journal wired to both faces.
 */
export function compositionDevFrameJournal(
  flush: DevFrameFlush,
  reviewerDirectory: EvidenceReviewerDirectory,
): DevFrameSessionJournal {
  return new DevFrameSessionJournal(flush, new EvidenceReviewGate(reviewerDirectory))
}

/**
 * Live reviewer role authority derived from the session log: `roleOf`
 * resolves the Session in the store, reads its devframe projection, and
 * returns the role the latest recorded role-policy snapshot assigns to that
 * Session — fail-closed on any miss (no Session, no projection state, no
 * policy, no assignment all mean "no role"). The authority is the log's own
 * record, not a host-memory side ledger.
 */
export class ProjectionEvidenceReviewerDirectory implements EvidenceReviewerDirectory {
  /**
   * @param ctx - the plugin fiber's context carrying `sessions` and
   *   `sessionProjections`.
   */
  constructor(private readonly ctx: Context) {}

  /**
   * Resolve one Session's deployed role from the recorded role policy.
   * @param sessionId - Session identity carried by the review payload.
   * @returns The assigned role, or undefined when the Session is unbound.
   */
  roleOf(sessionId: SessionId): 'controller' | 'lead' | 'worker' | 'reviewer' | undefined {
    const session = this.ctx.sessions.get(sessionId)
    if (session === undefined) return undefined
    const state = this.ctx.sessionProjections.stateOf(session, 'devframe')
    if (state === undefined) return undefined
    return state.rolePolicy?.assignments.find(assignment => assignment.sessionId === sessionId)?.role
  }
}

/**
 * Read the devframe projection state of one controller Session. The
 * composition registers the devframe projection unit in its constructor, so
 * the key cannot be absent while its own command runs.
 * @param ctx - the plugin fiber's context carrying `sessionProjections`.
 * @param session - the controller Session whose state is read.
 * @returns the folded projection state.
 */
export function devFrameStateOf(ctx: Context, session: Session): DevFrameProjectionState {
  const state = ctx.sessionProjections.stateOf(session, 'devframe')
  /* v8 ignore next 1 -- this composition registers the devframe unit, so the key cannot be absent while its own command runs */
  if (state === undefined) throw new TypeError('devframe projection state is unavailable for the controller session')
  return state
}

/**
 * The controller-only role-policy snapshot this composition lands when the
 * projection holds none: deterministic policy version, empty tool policies
 * for every role, and the owning Session as the controller. No reviewer is
 * assigned, so any review submission stays unauthorized until a review
 * production wave lands one.
 * @param workspaceId - the configured workspace identity.
 * @param controllerSessionId - the Session that owns the policy record.
 * @returns the role-policy event payload.
 */
export function compositionRolePolicy(
  workspaceId: WorkspaceId,
  controllerSessionId: SessionId,
): DevFrameRolePolicyEventData {
  const emptyPolicy = { inheritedTools: [] as string[], denyScopedTools: [] as string[] }
  return {
    version: 1,
    workspaceId,
    controllerSessionId,
    policyVersion: `policy-${workspaceId}-v1`,
    config: {
      controller: { ...emptyPolicy },
      worker: { ...emptyPolicy },
      reviewer: { ...emptyPolicy },
    },
    assignments: [{ role: 'controller', sessionId: controllerSessionId }],
  }
}

/**
 * Land the role-policy record unless the projection already holds one. The
 * record is idempotent by construction: a repeated identical snapshot under
 * the same deterministic policy version would be folded as "recorded twice",
 * so the projection check is what makes a second start on the same Session
 * safe.
 * @param ctx - the plugin fiber's context carrying `sessionProjections`.
 * @param journal - the composition-owned DevFrame Session journal.
 * @param session - the controller Session that owns the record.
 * @param workspaceId - the configured workspace identity.
 * @returns Nothing; a persistence failure propagates as
 *   `DevFramePersistenceError`.
 */
export async function landRolePolicyIfAbsent(
  ctx: Context,
  journal: DevFrameSessionJournal,
  session: Session,
  workspaceId: WorkspaceId,
): Promise<void> {
  if (devFrameStateOf(ctx, session).rolePolicy !== null) return
  await journal.append(session, 'devframe/role-policy', compositionRolePolicy(workspaceId, session.id))
}

/**
 * Land one goal-binding record on the controller Session log. The binding is
 * the event payload verbatim; the first record folds legally at
 * `admission_open`, and a resume lands the revision-advanced binding as a
 * legal monotonic replacement.
 * @param journal - the composition-owned DevFrame Session journal.
 * @param session - the controller Session that owns the record.
 * @param binding - the admitted binding to record.
 * @returns Nothing; a persistence failure propagates as
 *   `DevFramePersistenceError`.
 */
export async function landGoalBinding(
  journal: DevFrameSessionJournal,
  session: Session,
  binding: GoalBinding,
): Promise<void> {
  await journal.append(session, 'devframe/goal-binding', binding)
}

/**
 * Project one admitted binding onto the result tuple evidence records
 * attribute to: the eight-field work identity the verification and review
 * payloads carry.
 * @param binding - the admitted binding whose tuple is projected.
 * @returns the detached result binding tuple.
 */
export function resultTupleOf(binding: GoalBinding): GoalResultBinding {
  return {
    controllerSessionId: binding.controllerSessionId,
    goalId: binding.goalId,
    goalRevision: binding.goalRevision,
    taskIds: [...binding.taskIds],
    acceptanceHash: binding.acceptanceHash,
    workspaceId: binding.workspaceId,
    sourceFingerprint: binding.sourceFingerprint,
    snapshotId: binding.snapshotId,
  }
}

/**
 * Compose the host-computed acceptance digest of one human-approved start:
 * sha256 over a canonical JSON whose fields serialize in a fixed explicit
 * order (objective, approved checklist version, then every check's
 * checkId/executable/arguments/cwd in declaration order), lowercase hex. The
 * command invocation itself is the human approval act and stays auditable in
 * the command/run log.
 * @param objective - the approved objective from the command line.
 * @param checks - the approved required-checks configuration from the config.
 * @returns the branded acceptance hash.
 */
export function acceptanceHashOf(
  objective: string,
  checks: DevFrameRequiredChecksConfig,
): AcceptanceHash {
  const canonical = JSON.stringify({
    objective,
    version: checks.version,
    checks: checks.checks.map(check => ({
      checkId: check.checkId,
      executable: check.executable,
      arguments: [...check.arguments],
      cwd: check.cwd,
    })),
  })
  return AcceptanceHash(createHash('sha256').update(canonical, 'utf8').digest('hex'))
}
