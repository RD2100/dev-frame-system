/** Client-safe expert-team status vocabulary used by the Web Remote surface. */

import type { ExpertTeamRunView, ExpertTeamView } from './orchestrate.ts'
import type { GateDecision, TeamRun } from './types.ts'

/** Snapshot consumed by the expert-team sidebar entry. */
export interface ExpertTeamSnapshot {
  /** Mounted teams and their phase/expert declarations. */
  readonly teams: readonly ExpertTeamView[]
  /** Live-process run history, newest updates last. */
  readonly runs: readonly ExpertTeamRunView[]
}

/** Start one pipeline or hierarchical run from the UI. */
export interface ExpertTeamStartRunRequest {
  /** Mounted team id. */
  readonly teamId: string
  /** Free-form run request text (for example, the research topic). */
  readonly input: string
}

/** Consult one expert outside any pipeline from the UI. */
export interface ExpertTeamConsultRequest {
  /** Mounted team id. */
  readonly teamId: string
  /** Expert id within the team's pack. */
  readonly expertId: string
  /** The caller's question. */
  readonly question: string
}

/** Record a human gate decision from the UI. */
export interface ExpertTeamApproveRequest {
  /** Raw run id the UI row displayed. */
  readonly runId: string
  /** The recorded decision. */
  readonly decision: GateDecision
  /** Optional reviewer comment; a rejection comment is the revision guidance. */
  readonly comment?: string
}

/** Read one live run's full snapshot from the UI. */
export interface ExpertTeamRunRequest {
  /** Raw run id the UI row displayed. */
  readonly runId: string
}

/** Full client-safe detail of one run, including per-phase gate state. */
export type ExpertTeamRunDetail = TeamRun

/** Result of a single-expert consultation. */
export interface ExpertTeamConsultResult {
  /** The answer text. */
  readonly answer: string
  /** Whether the answer was truncated at the bounded output ceiling. */
  readonly truncated: boolean
}

export type { ExpertTeamRunView, ExpertTeamView } from './orchestrate.ts'
export type { ArtifactRef, GateDecision, GateReview, PhaseState, TeamRun } from './types.ts'
