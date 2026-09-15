/**
 * The expert-team vocabulary: expert and team definitions parsed from pack
 * files, the run/phase/artifact shapes the orchestration half builds on, and
 * the stable `EXPERT_TEAM_*` error-code union. Types only — parsing,
 * validation, and filesystem behavior live in `./expert-md.ts`,
 * `./team-yml.ts`, and `./catalog.ts`.
 * @module @deepseek-ai/dsh-experimental-expert-team/types
 */

import type { RunId } from './ids.ts'

/** The two orchestration modes of a team. */
export type TeamMode =
  /** Phases execute in declaration (DAG topological) order. */
  | 'pipeline'
  /** Phases map onto the agent-dispatch hierarchy and its completion gates. */
  | 'hierarchical'

/** The only gate a phase may declare: the artifact waits for human approval. */
export type PhaseGate = 'human-review'

/**
 * One expert persona parsed from `<pack>/experts/<id>.md`. Ids are
 * author-assigned kebab-case names validated at pack load — they are file
 * names inside a pack, not opaque host-issued ids.
 */
export interface ExpertDef {
  /** Kebab-case expert id, identical to the defining file's name stem. */
  readonly id: string
  /** Team id the expert belongs to; must equal the pack's `team.yml` team id. */
  readonly team: string
  /** Display name, one line. */
  readonly name: string
  /** One-line role statement: who the expert is. */
  readonly role: string
  /** One-line goal statement: what the expert optimizes for. */
  readonly goal: string
  /**
   * Tool-name allowlist. The delegation layer must not expose any tool
   * outside it to a subagent running this expert.
   */
  readonly tools: readonly string[]
  /** Optional skill directory names inside the same pack. */
  readonly skills?: readonly string[]
  /** Optional acceptance checks the expert restates when handing off its artifact. */
  readonly handoffChecks?: readonly string[]
  /** The persona text — the md body below the front matter. */
  readonly persona: string
}

/** The declared artifact of one phase. */
export interface PhaseOutput {
  /** Artifact file name written under the run directory; a single path segment. */
  readonly artifact: string
  /**
   * Pack-relative path of the JSON Schema file the artifact must satisfy;
   * validated to exist at pack load.
   */
  readonly schema?: string
}

/** One phase of a team, as declared in `team.yml`. */
export interface PhaseDef {
  /** Kebab-case phase id, unique within the team. */
  readonly id: string
  /** Expert id that executes the phase; must be defined by the same pack. */
  readonly expert: string
  /**
   * Ids of the phases this phase consumes, each referencing a phase declared
   * earlier in the list. Backward-only references make the graph acyclic by
   * construction.
   */
  readonly dependsOn: readonly string[]
  /**
   * Optional phase ids this phase supersedes: when any superseded phase has
   * run, this phase's artifact replaces it downstream and the superseded
   * phase's open questions are forwarded. Used for revision phases that
   * rewrite an earlier artifact in place.
   */
  readonly supersedes?: readonly string[]
  /** Optional version label distinguishing iterations of the same phase id across runs. */
  readonly version?: string
  /** Optional free-form input descriptor for the phase. */
  readonly input?: string
  /** The artifact the phase must produce. */
  readonly output: PhaseOutput
  /** Optional human gate: the phase waits for a review after writing its artifact. */
  readonly gate?: PhaseGate
}

/** A team definition parsed from `<pack>/team.yml`. */
export interface TeamDef {
  /** Kebab-case team id, unique across all mounted packs. */
  readonly team: string
  /** Human-readable title. */
  readonly title: string
  /** Orchestration mode. */
  readonly mode: TeamMode
  /** The starting phase id; must reference a phase that declares no `dependsOn`. */
  readonly entry: string
  /** Phases in declaration order; `dependsOn` may only reference earlier entries. */
  readonly phases: readonly PhaseDef[]
}

/** Review decision a human gate records for one phase. */
export type GateDecision = 'approved' | 'rejected'

/** One human gate review recorded on a phase. */
export interface GateReview {
  /** The decision. */
  readonly decision: GateDecision
  /** Optional reviewer comment; a rejection comment feeds the upstream revision. */
  readonly comment?: string
  /** ISO-8601 instant the review was recorded. */
  readonly at: string
}

/** Reference to one phase artifact written under the run directory. */
export interface ArtifactRef {
  /** The phase that produced the artifact. */
  readonly phaseId: string
  /** Artifact file name, as declared by the phase output. */
  readonly artifact: string
  /** Path of the stored artifact relative to `<artifactsDir>/<runId>/`. */
  readonly relativePath: string
  /** Pack-relative schema path the artifact was validated against, when declared. */
  readonly schema?: string
}

/** Lifecycle status of one phase inside a run. */
export type PhaseStatus =
  /** Upstream phases have not delivered its inputs yet. */
  | 'pending'
  /** A subagent delegation for the phase is in flight. */
  | 'running'
  /** The artifact is written and the phase's human gate awaits a review. */
  | 'gate-pending'
  /** The artifact passed its gate (or the phase declares none); downstream may consume it. */
  | 'done'
  /** The phase failed after its bounded retries; `error` names the reason. */
  | 'failed'

/** Lifecycle status of one run. */
export type TeamRunStatus =
  /** No gate blocks the run and at least one phase is runnable or running. */
  | 'running'
  /** A gated phase's artifact awaits human review. */
  | 'waiting-approval'
  /** Every phase is done. */
  | 'completed'
  /** A phase failed terminally. */
  | 'failed'

/** State of one phase inside a run. */
export interface PhaseState {
  /** The phase this state belongs to. */
  readonly phaseId: string
  /** Current lifecycle status. */
  readonly status: PhaseStatus
  /** Delegation attempts so far, including schema-validation retries; starts at 0. */
  readonly attempts: number
  /** The written artifact, once the phase produced one. */
  readonly artifact?: ArtifactRef
  /** Failure detail when the status is `failed`. */
  readonly error?: string
  /** Open questions carried forward from superseded phases that this phase consumed. */
  readonly openQuestions?: readonly string[]
  /** Questions a human reviewer needs to answer when the phase is gate-pending; absent otherwise. */
  readonly userQuestions?: readonly string[]
  /** Human gate reviews recorded so far, in order. */
  readonly reviews?: readonly GateReview[]
}

/** One expert-team run over a mounted team. */
export interface TeamRun {
  /** Opaque run id, minted by the orchestrator; also names the run directory. */
  readonly runId: RunId
  /** The team the run executes. */
  readonly teamId: string
  /** Orchestration mode, copied from the team definition. */
  readonly mode: TeamMode
  /** Current run status. */
  readonly status: TeamRunStatus
  /** ISO-8601 instant the run started. */
  readonly createdAt: string
  /** Per-phase state, in the team's declaration order. */
  readonly phases: readonly PhaseState[]
  /** Monotonically advancing run version; incremented after each park point. */
  readonly version?: number
}

/**
 * Stable, machine-routable failure classifications for the expert-team
 * packages. Catalog and config failures fail loud at mount time; the run,
 * gate, and result codes belong to the orchestration half.
 */
export type ExpertTeamErrorCode =
  /** Plugin config failed validation (packs below minimum, blank path, missing artifactsDir). */
  | 'EXPERT_TEAM_CONFIG_INVALID'
  /** A pack directory or its team.yml is missing, malformed, duplicated, or self-inconsistent. */
  | 'EXPERT_TEAM_CATALOG_INVALID'
  /** An expert md file failed its structural or bound validation. */
  | 'EXPERT_TEAM_EXPERT_INVALID'
  /** A phase references an expert id that the team's pack does not define. */
  | 'EXPERT_TEAM_EXPERT_MISSING'
  /** The requested team id is not mounted in the catalog. */
  | 'EXPERT_TEAM_TEAM_MISSING'
  /** A phase's depends_on references a non-earlier (forward, self, or unknown) phase id. */
  | 'EXPERT_TEAM_PHASE_CYCLE'
  /** A phase's referenced JSON Schema file escapes the pack, is missing, or is not a file. */
  | 'EXPERT_TEAM_SCHEMA_MISSING'
  /** A pack expert declares a skill directory the pack does not provide with a SKILL.md. */
  | 'EXPERT_TEAM_SKILL_MISSING'
  /** An expert's tool allowlist names a tool this deployment does not mount. */
  | 'EXPERT_TEAM_TOOL_MISSING'
  /** An expert's tool allowlist names one of the expert-team plugin's own tools. */
  | 'EXPERT_TEAM_TOOL_FORBIDDEN'
  /** The deployment provides no default model selection to derive expert subagents with. */
  | 'EXPERT_TEAM_MODEL_MISSING'
  /** The requested run id does not match a live or recorded run. */
  | 'EXPERT_TEAM_RUN_UNKNOWN'
  /** The operation needs a gate decision the human has not recorded yet. */
  | 'EXPERT_TEAM_GATE_PENDING'
  /** A phase reply failed the phase result contract (fenced JSON tail, required fields, schema). */
  | 'EXPERT_TEAM_RESULT_INVALID'
  /** The team's orchestration mode is not implemented by this runtime. */
  | 'EXPERT_TEAM_MODE_UNSUPPORTED'
