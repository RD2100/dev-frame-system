/**
 * Public entry of `@deepseek-ai/dsh-experimental-expert-team`: the expert-team
 * plugin — strict pack file parsing and mounting (the expert catalog half)
 * plus the orchestration half (phase subagent derivation, pipeline execution
 * with human gates, run state) and the four model tools, all wired by the
 * loader plugin in `./plugin.ts`.
 * @module @deepseek-ai/dsh-experimental-expert-team
 */

export { ExpertTeamError } from './errors.ts'
export { type ExpertTeamConfig, validateExpertTeamConfig } from './config.ts'
export { parseExpertMd } from './expert-md.ts'
export { loadTeamYml, parseTeamYml } from './team-yml.ts'
export { ExpertCatalog, type LoadedTeam } from './catalog.ts'
export { mintRunId, parseRunId } from './ids.ts'
export type { RunId } from './ids.ts'
export { splitPhaseReply, parsePhaseResult, parseConsultAnswer, RESULT_FENCE_OPEN, MAX_ARTIFACT_BYTES } from './result-protocol.ts'
export type { PhaseResult, SplitPhaseReply } from './result-protocol.ts'
export { composePhaseBriefing, composeRevisionMessage, composeConsultMessage, composeGateAcceptanceMessage } from './briefing.ts'
export type { RevisionReason } from './briefing.ts'
export { ExpertRuntime, type PhaseExecutionOutcome, type PhaseExecutionRequest } from './runtime.ts'
export { TeamOrchestrator } from './orchestrate.ts'
export { ExpertTeamGateway } from './gateway.ts'
export type { ExpertTeamRunView, ExpertTeamSnapshot } from './client.ts'
export type { ExpertTeamView } from './client.ts'
export { createExpertTeamTools } from './tools.ts'
// The Cordis loader resolves the package name to this entry and reads the
// plugin-protocol exports `name`, `inject`, `Config`, and `apply` by their
// exact names; `createExpertTeamTools` is the testable tool factory behind them.
export { apply, Config, EXPERT_TEAM_USAGE_SECTION, inject, name } from './plugin.ts'
export type {
  ArtifactRef,
  ExpertDef,
  ExpertTeamErrorCode,
  GateDecision,
  GateReview,
  PhaseDef,
  PhaseGate,
  PhaseOutput,
  PhaseState,
  PhaseStatus,
  TeamDef,
  TeamMode,
  TeamRun,
  TeamRunStatus,
} from './types.ts'
