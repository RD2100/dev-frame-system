/**
 * The team orchestrator: mints runs, executes a pipeline team's phases in
 * declaration (topological) order through the {@link ExpertRuntime}, parks at
 * declared human gates, and records every phase's artifact and run state.
 * Run state is authoritative in memory for the live process and is mirrored
 * to `<artifactsDir>/<runId>/run-state.json` at every commit point, so the
 * files on disk tell the whole run story; a run does not resume in a new
 * process (an M1 scope limit, recorded in the package README).
 *
 * A gate is the trust anchor of the design: expert output is observed data.
 * `approve` records the human decision — an approval marks the gated phase
 * done and resumes the pipeline; a rejection re-drives the SAME phase session
 * with the reviewer's comment so the expert revises its own artifact in
 * context. A phase that exhausted its result-contract retries parks the run
 * at its gate (when it declares one) with the failure reported: the human
 * cannot approve a failed phase (nothing accepted exists to pass downstream),
 * but a rejection with a comment re-opens it as a guided revision.
 * @module @deepseek-ai/dsh-experimental-expert-team/orchestrate
 */

import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { writeFileAtomic } from '@deepseek-ai/dsh-atomic-write'
import type { LoadedTeam } from './catalog.ts'
import type { ExpertCatalog } from './catalog.ts'
import type { RevisionReason } from './briefing.ts'
import { ExpertTeamError } from './errors.ts'
import type { RunId } from './ids.ts'
import { mintRunId, parseRunId } from './ids.ts'
import type { ExpertRuntime } from './runtime.ts'
import type { ArtifactRef, GateDecision, GateReview, PhaseDef, PhaseState, PhaseStatus, TeamMode, TeamRun, TeamRunStatus } from './types.ts'

/** The run-state file name inside every run directory. */
const RUN_STATE_FILE = 'run-state.json'

/** One orchestrator-owned view of a mounted team, shaped for `expert_team_list`. */
export interface ExpertTeamView {
  /** Team id. */
  readonly team: string
  /** Human-readable title. */
  readonly title: string
  /** Orchestration mode. */
  readonly mode: TeamMode
  /** Entry phase id. */
  readonly entry: string
  /** The team's experts, in file-name order. */
  readonly experts: readonly {
    readonly id: string
    readonly name: string
    readonly role: string
    readonly tools: string[]
  }[]
  /** The team's phases, in declaration order. */
  readonly phases: readonly {
    readonly id: string
    readonly expert: string
    readonly dependsOn: string[]
    readonly artifact: string
    readonly gate?: string
  }[]
}

/** Mutable per-phase run state; {@link TeamOrchestrator.snapshot} is the published, frozen form. */
interface MutablePhaseState {
  phaseId: string
  status: PhaseStatus
  attempts: number
  artifact?: ArtifactRef | undefined
  error?: string | undefined
  openQuestions?: readonly string[] | undefined
  userQuestions?: readonly string[] | undefined
  reviews?: GateReview[] | undefined
}

/** One live run: its definition, mutable state, and serialization gate. */
interface RunRecord {
  runId: RunId
  team: LoadedTeam
  runDir: string
  input: string
  status: TeamRunStatus
  createdAt: string
  version: number
  states: MutablePhaseState[]
  /** Serializes every mutating span on this run; see {@link TeamOrchestrator.withRunGate}. */
  gate: Promise<unknown>
}

/**
 * Orchestrates expert-team runs over the mounted catalog. One instance per
 * mounted plugin, published as `ctx.expertTeam`; the model tools are its only
 * consumers.
 */
export class TeamOrchestrator {
  /** Live runs of this process, keyed by run id string. */
  private readonly runs = new Map<string, RunRecord>()

  constructor(
    private readonly catalog: ExpertCatalog,
    private readonly runtime: ExpertRuntime,
    /** Absolute artifacts root from the validated plugin config. */
    private readonly artifactsDir: string,
  ) {}

  /**
   * List every mounted team, in pack configuration order.
   * @returns the team views shaped for `expert_team_list`, in configuration order.
   */
  listTeams(): readonly ExpertTeamView[] {
    return this.catalog.listTeams().map(team => ({
      team: team.def.team,
      title: team.def.title,
      mode: team.def.mode,
      entry: team.def.entry,
      experts: team.experts.map(expert => ({
        id: expert.id,
        name: expert.name,
        role: expert.role,
        tools: [...expert.tools],
      })),
      phases: team.def.phases.map(phase => ({
        id: phase.id,
        expert: phase.expert,
        dependsOn: [...phase.dependsOn],
        artifact: phase.output.artifact,
        ...(phase.gate === undefined ? {} : { gate: phase.gate }),
      })),
    }))
  }

  /**
   * Start one run over a mounted pipeline team: mint the run id, create the
   * run directory, and execute phases to the first park point (a gate, a
   * terminal failure, or completion). Every phase expert's tool allowlist is
   * proven mounted before anything is created, so a pack naming an unmounted
   * tool fails without leaving a run behind.
   * @param teamId - Mounted team id.
   * @param input - Free-form run request text (for example, the research topic).
   * @returns the run snapshot at its first park point.
   * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_TEAM_MISSING`
   *   when the team is not mounted, `EXPERT_TEAM_MODE_UNSUPPORTED` when the
   *   team is not a pipeline, or `EXPERT_TEAM_TOOL_MISSING` when a phase
   *   expert names an unmounted tool.
   */
  async startRun(teamId: string, input: string): Promise<TeamRun> {
    const team = this.catalog.getTeam(teamId)
    if (team.def.mode !== 'pipeline') {
      throw new ExpertTeamError(
        `team ${teamId} declares mode "${team.def.mode}", which this runtime does not orchestrate yet`,
        'EXPERT_TEAM_MODE_UNSUPPORTED',
      )
    }
    for (const phase of team.def.phases) {
      this.runtime.requireMountedTools(this.catalog.getExpert(team.def.team, phase.expert))
    }
    if (input.trim().length === 0) {
      throw new ExpertTeamError('run input must be a non-empty string', 'EXPERT_TEAM_CONFIG_INVALID')
    }
    const runId = mintRunId()
    const runDir = join(this.artifactsDir, String(runId))
    await mkdir(runDir, { recursive: true, mode: 0o700 })
    const record: RunRecord = {
      runId,
      team,
      runDir,
      input,
      status: 'running',
      createdAt: new Date().toISOString(),
      version: 0,
      states: team.def.phases.map(phase => ({ phaseId: phase.id, status: 'pending', attempts: 0 })),
      gate: Promise.resolve(),
    }
    this.runs.set(String(runId), record)
    await this.persist(record)
    await this.withRunGate(record, () => this.advance(record))
    return this.snapshot(record)
  }

  /**
   * Read one run's snapshot; serves `expert_team_status` after a run parks.
   * @param runId - Raw run id as the model supplied it.
   * @returns the frozen run snapshot.
   * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_RUN_UNKNOWN` when
   *   the id is malformed or not a live run of this process.
   */
  getRun(runId: string): TeamRun {
    return this.snapshot(this.requireRun(runId))
  }

  /**
   * Record the human gate decision on a run's single parked phase and resume.
   * An approval marks the gated phase done and executes the remaining
   * pipeline to the next park point, and delivers a best-effort post-approval
   * follow-up to the gated phase session so the persona's post-acceptance
   * steps can fire in a real turn (a failed delivery is logged, never fatal);
   * a rejection re-drives the phase session with the reviewer's comment
   * before parking again and sends no follow-up. The whole span is
   * serialized against concurrent decisions.
   * @param runId - Raw run id as the model supplied it.
   * @param decision - The recorded decision.
   * @param comment - Optional reviewer comment; a rejection comment is the
   *   revision guidance the phase expert receives, and an approval comment
   *   rides the acceptance follow-up.
   * @returns the run snapshot after the decision took effect.
   * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_RUN_UNKNOWN` when
   *   the run is not live, or `EXPERT_TEAM_GATE_PENDING` when no gate awaits
   *   a decision or an approval targets a failed phase (no review is
   *   recorded then). An infrastructure failure while re-driving the phase
   *   (agent derivation, model selection, session creation) settles the run
   *   failed and propagates.
   */
  async approve(runId: string, decision: GateDecision, comment?: string | undefined): Promise<TeamRun> {
    const record = this.requireRun(runId)
    return await this.withRunGate(record, async () => {
      const parked = this.findParkedGate(record)
      if (parked === undefined) {
        throw new ExpertTeamError(
          `run ${String(record.runId)} has no gate awaiting a decision (status ${record.status})`,
          'EXPERT_TEAM_GATE_PENDING',
        )
      }
      const { state, phase } = parked
      // Validate before recording: a refused approval (a failed phase has no
      // accepted artifact to approve) must not persist a review that never
      // took effect.
      if (decision === 'approved' && state.status === 'failed') {
        throw new ExpertTeamError(
          `phase ${phase.id} failed and has no accepted artifact to pass downstream; reject it with a comment to request a revision`,
          'EXPERT_TEAM_GATE_PENDING',
        )
      }
      state.reviews = [...state.reviews ?? [], {
        decision,
        ...(comment === undefined ? {} : { comment }),
        at: new Date().toISOString(),
      }]
      if (decision === 'approved') {
        state.status = 'done'
        state.error = undefined
        await this.persist(record)
        // Best-effort post-approval follow-up: the gated phase session learns
        // its artifact was accepted (reviewer comment included) so the
        // persona's post-acceptance steps can fire in a real turn. Advancing
        // must not block on it, so the delivery floats with a named catch.
        void this.runtime.notifyGateAccepted(record.runId, phase, comment).catch((error: unknown) => {
          const detail = error instanceof Error ? error.message : String(error)
          console.warn(
            `[expert-team] post-approval follow-up to phase ${phase.id} of run ${String(record.runId)} failed: ${detail}`,
          )
        })
        await this.advance(record)
        return this.snapshot(record)
      }
      try {
        await this.drivePhase(record, record.team.def.phases.indexOf(phase), phase, {
          kind: 'gate-rejection',
          ...(comment === undefined ? {} : { comment }),
        })
      } catch (error: unknown) {
        await this.settleInfraFailure(record, error)
      }
      record.status = this.parkRun(state, phase, record)
      await this.persist(record)
      return this.snapshot(record)
    })
  }

  /**
   * Consult one expert outside any pipeline: a single bounded turn with the
   * expert persona and allowlist, no artifacts, no run state.
   * @param teamId - Mounted team id.
   * @param expertId - Expert id within the team's pack.
   * @param question - The caller's question.
   * @returns the answer text and its truncation flag.
   * @throws {@link ExpertTeamError} with `EXPERT_TEAM_TEAM_MISSING` /
   *   `EXPERT_TEAM_EXPERT_MISSING` codes from the catalog lookups.
   */
  async consult(teamId: string, expertId: string, question: string): Promise<{ readonly answer: string; readonly truncated: boolean }> {
    const team = this.catalog.getTeam(teamId)
    const expert = this.catalog.getExpert(teamId, expertId)
    return await this.runtime.consult(team, expert, question)
  }

  /** Dispose every derived agent session this orchestrator still owns. */
  async dispose(): Promise<void> {
    await this.runtime.dispose()
  }

  /**
   * Execute the run's phases in declaration order to the next park point.
   * Declaration order is a topological order because depends_on references
   * only earlier phases; each phase drives only after its predecessors'
   * artifacts are committed. Parallel DAG (concurrent phases with independent
   * dependencies) is deferred to a future milestone.
   */
  private async advance(record: RunRecord): Promise<void> {
    try {
      const phases = record.team.def.phases
      for (const [index, phase] of phases.entries()) {
        const state = record.states[index]
        if (state === undefined) {
          throw new ExpertTeamError(`run state missing for phase ${phase.id}`, 'EXPERT_TEAM_CATALOG_INVALID')
        }
        if (state.status === 'done') continue
        if (state.status === 'gate-pending' || state.status === 'failed') {
          record.status = this.parkRun(state, phase, record)
          await this.persist(record)
          return
        }
        await this.drivePhase(record, index, phase)
        record.status = this.parkRun(state, phase, record)
        if (record.status !== 'running') {
          await this.persist(record)
          return
        }
      }
      record.status = 'completed'
      await this.runtime.retireRun(record.runId)
      await this.persist(record)
    } catch (error: unknown) {
      await this.settleInfraFailure(record, error)
    }
  }

  /**
   * Collect open questions from the run's done phases whose ids appear in
   * any of the given phase's `supersedes` list, returning a deduplicated
   * array preserving the order the superseded phases appear in the team
   * declaration.
   */
  private collectSupersededOpenQuestions(record: RunRecord, phase: PhaseDef): string[] {
    const seen = new Set<string>()
    const questions: string[] = []
    for (const supersededId of phase.supersedes ?? []) {
      const stateIndex = record.states.findIndex(s => s.phaseId === supersededId)
      if (stateIndex < 0) continue
      const state = record.states[stateIndex]
      const phaseDef = record.team.def.phases[stateIndex]
      if (state === undefined || phaseDef === undefined || state.artifact === undefined || phaseDef.supersedes === undefined) continue
      for (const q of state.openQuestions ?? []) {
        if (seen.has(q)) continue
        seen.add(q)
        questions.push(q)
      }
    }
    return questions
  }

  /**
   * Drive one phase through the runtime: verify dependencies are satisfied,
   * mark it running, collect upstream artifacts, forward open questions from
   * superseded phases, and record the outcome on the phase state.
   */
  private async drivePhase(record: RunRecord, index: number, phase: PhaseDef, revision?: RevisionReason): Promise<void> {
    const state = record.states[index]
    if (state === undefined) {
      throw new ExpertTeamError(`run state missing for phase ${phase.id}`, 'EXPERT_TEAM_CATALOG_INVALID')
    }
    if (state.status === 'done') return // superseded phase already replaced
    state.status = 'running'
    state.openQuestions = undefined
    state.userQuestions = undefined
    await this.persist(record)
    const upstream: ArtifactRef[] = []
    const upstreamPaths = new Map<string, string>()
    for (const depId of phase.dependsOn) {
      const dep = record.states.find(candidate => candidate.phaseId === depId)
      if (dep?.artifact === undefined) {
        throw new ExpertTeamError(
          `phase ${phase.id} depends on ${depId}, which has no artifact yet`,
          'EXPERT_TEAM_CATALOG_INVALID',
        )
      }
      upstream.push(dep.artifact)
      upstreamPaths.set(depId, join(record.runDir, dep.artifact.artifact))
    }
    const supersededOpenQuestions = this.collectSupersededOpenQuestions(record, phase)
    const outcome = await this.runtime.executePhase({
      team: record.team,
      phase,
      upstream,
      upstreamPaths,
      input: record.input,
      runId: record.runId,
      runDir: record.runDir,
      supersededOpenQuestions,
      ...(revision === undefined ? {} : { revision }),
    })
    state.attempts += outcome.attempts
    if (!outcome.ok) {
      state.status = 'failed'
      state.error = outcome.detail
      await this.persist(record)
      return
    }
    state.status = phase.gate === undefined ? 'done' : 'gate-pending'
    state.error = undefined
    state.artifact = {
      phaseId: phase.id,
      artifact: phase.output.artifact,
      relativePath: phase.output.artifact,
      ...(phase.output.schema === undefined ? {} : { schema: phase.output.schema }),
    }
    // Forward open questions from the result for downstream consumption.
    if (outcome.result.openQuestions !== undefined && outcome.result.openQuestions.length > 0) {
      state.openQuestions = [...outcome.result.openQuestions]
    }
    // When the phase declares a gate, surface the artifact summary as the
    // human reviewer's entry question.
    if (phase.gate !== undefined) {
      state.userQuestions = [`请审阅 ${phase.output.artifact} 并给出 approve 或 reject 决定。`]
    }
    await this.persist(record)
  }

  /** The run status implied by one phase's settled state. */
  private parkRun(state: MutablePhaseState, phase: PhaseDef, record: RunRecord): TeamRunStatus {
    record.version += 1
    if (state.status === 'gate-pending') return 'waiting-approval'
    if (state.status === 'failed') return phase.gate !== undefined ? 'waiting-approval' : 'failed'
    return 'running'
  }

  /**
   * Settle one infrastructure failure (agent derivation, model selection,
   * session creation): every running phase and the run itself settle to
   * failed, the state mirrors to disk, and the error stays loud. A run must
   * never keep claiming active work it no longer has.
   */
  private async settleInfraFailure(record: RunRecord, error: unknown): Promise<never> {
    const detail = error instanceof Error ? error.message : String(error)
    for (const state of record.states) {
      if (state.status === 'running') {
        state.status = 'failed'
        state.error = detail
      }
    }
    record.status = 'failed'
    await this.persist(record)
    throw error
  }

  /** The first parked phase of a run, or `undefined` when none is parked. */
  private findParkedGate(record: RunRecord): { readonly state: MutablePhaseState; readonly phase: PhaseDef } | undefined {
    for (const [index, phase] of record.team.def.phases.entries()) {
      const state = record.states[index]
      if (state === undefined) continue
      if (state.status === 'gate-pending' || (state.status === 'failed' && phase.gate !== undefined)) {
        return { state, phase }
      }
    }
    return undefined
  }

  /** The live run for one raw id, or the stable unknown-run failure. */
  private requireRun(runId: string): RunRecord {
    let parsed: RunId
    try {
      parsed = parseRunId(runId)
    } catch {
      throw new ExpertTeamError(`run id is malformed: ${JSON.stringify(runId)}`, 'EXPERT_TEAM_RUN_UNKNOWN')
    }
    const record = this.runs.get(String(parsed))
    if (record === undefined) {
      throw new ExpertTeamError(`unknown run: ${String(parsed)}`, 'EXPERT_TEAM_RUN_UNKNOWN')
    }
    return record
  }

  /** The frozen published snapshot of one run. */
  private snapshot(record: RunRecord): TeamRun {
    const phases: PhaseState[] = record.states.map(state => ({
      phaseId: state.phaseId,
      status: state.status,
      attempts: state.attempts,
      ...(state.artifact === undefined ? {} : { artifact: state.artifact }),
      ...(state.error === undefined ? {} : { error: state.error }),
      ...(state.openQuestions === undefined || state.openQuestions.length === 0 ? {} : { openQuestions: [...state.openQuestions] }),
      ...(state.userQuestions === undefined || state.userQuestions.length === 0 ? {} : { userQuestions: [...state.userQuestions] }),
      ...(state.reviews === undefined ? {} : { reviews: [...state.reviews] }),
    }))
    return {
      runId: record.runId,
      teamId: record.team.def.team,
      mode: record.team.def.mode,
      status: record.status,
      createdAt: record.createdAt,
      phases,
      ...(record.version === 0 ? {} : { version: record.version }),
    }
  }

  /** Mirror the run state to `<runDir>/run-state.json` at one commit point. */
  private async persist(record: RunRecord): Promise<void> {
    const body = `${JSON.stringify(this.snapshot(record), null, 2)}\n`
    await writeFileAtomic(join(record.runDir, RUN_STATE_FILE), body, { mode: 0o600 })
  }

  /**
   * Serialize one mutating span on a run. Concurrent `expert_team_approve`
   * calls must not interleave state transitions or drive the same phase
   * session twice; the chain makes each span observe the settled state of the
   * previous one.
   */
  private async withRunGate<T>(record: RunRecord, run: () => Promise<T>): Promise<T> {
    const previous = record.gate
    const result = previous.then(run, run)
    const tail = result.then(() => undefined, () => undefined)
    record.gate = tail
    return await result
  }
}
