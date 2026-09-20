/**
 * Host Remote owner for the expert-team status and execution surface. The
 * model tools remain the mutation boundary for in-session use; this gateway
 * additionally exposes the write operations the expert center needs — start a
 * pipeline run, consult one expert, record a human gate decision, and read a
 * full run snapshot — to the Web UI.
 *
 * @module @deepseek-ai/dsh-experimental-expert-team/gateway
 */

import type { Context } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import type { TeamOrchestrator } from './orchestrate.ts'
import type {
  ExpertTeamApproveRequest,
  ExpertTeamConsultRequest,
  ExpertTeamConsultResult,
  ExpertTeamRunRequest,
  ExpertTeamRunDetail,
  ExpertTeamSnapshot,
  ExpertTeamStartRunRequest,
} from './client.ts'

/** Host service backing the generated `ctx.remote.expertTeam` namespace. */
export class ExpertTeamGateway extends TypertRemoteService {
  /**
   * @param ctx - Host context that owns the Remote service registration.
   * @param orchestrator - The already-mounted expert-team orchestrator.
   */
  constructor(ctx: Context, private readonly orchestrator: TeamOrchestrator) {
    super(ctx, 'expertTeamGateway', { namespace: 'expertTeam' })
  }

  /**
   * Read the current catalog and live-process run index.
   * @returns the mounted team metadata and detached run-history rows.
   */
  @Remote('view')
  view(): ExpertTeamSnapshot {
    return {
      teams: this.orchestrator.listTeams(),
      runs: this.orchestrator.listRuns(),
    }
  }

  /**
   * Start one pipeline or hierarchical run from the UI.
   * @param request - Team id and run input text.
   * @returns the run snapshot at its first park point.
   * @throws {@link ExpertTeamError} with the same codes as
   *   {@link TeamOrchestrator.startRun}.
   */
  @Remote('startRun')
  async startRun(request: ExpertTeamStartRunRequest): Promise<ExpertTeamRunDetail> {
    return await this.orchestrator.startRun(request.teamId, request.input)
  }

  /**
   * Consult one expert outside any pipeline from the UI.
   * @param request - Team id, expert id, and the caller's question.
   * @returns the answer text and its truncation flag.
   * @throws {@link ExpertTeamError} with `EXPERT_TEAM_TEAM_MISSING` /
   *   `EXPERT_TEAM_EXPERT_MISSING` codes from the catalog lookups.
   */
  @Remote('consult')
  async consult(request: ExpertTeamConsultRequest): Promise<ExpertTeamConsultResult> {
    return await this.orchestrator.consult(request.teamId, request.expertId, request.question)
  }

  /**
   * Record the human gate decision on a run's single parked phase and resume.
   * @param request - Run id, the recorded decision, and an optional comment.
   * @returns the run snapshot after the decision took effect.
   * @throws {@link ExpertTeamError} with the same codes as
   *   {@link TeamOrchestrator.approve}.
   */
  @Remote('approve')
  async approve(request: ExpertTeamApproveRequest): Promise<ExpertTeamRunDetail> {
    return await this.orchestrator.approve(request.runId, request.decision, request.comment)
  }

  /**
   * Read one live run's full snapshot, including per-phase gate state.
   * @param request - Raw run id as the UI row displayed it.
   * @returns the frozen run snapshot.
   * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_RUN_UNKNOWN` when
   *   the id is malformed or not a live run of this process.
   */
  @Remote('getRun')
  getRun(request: ExpertTeamRunRequest): ExpertTeamRunDetail {
    return this.orchestrator.getRun(request.runId)
  }
}
