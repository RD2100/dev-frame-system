/**
 * The five model tools of the expert-team plugin, bound to one
 * {@link TeamOrchestrator}. The schemas are authored in the tool-schema DSL
 * (`defineTool` compiles them into the enforced JSON-Schema subset; required
 * properties are marked on the property, never in a sibling `required`
 * array), and every result is rendered as canonical JSON: the run snapshots
 * the tools return are the same frozen shapes the orchestrator mirrors into
 * each run's `run-state.json`.
 * @module @deepseek-ai/dsh-experimental-expert-team/tools
 */

import { defineTool } from '@deepseek-ai/dsh-tools'
import type { ToolDefinition, ValueSchemaSpec } from '@deepseek-ai/dsh-tools'
import type { TeamOrchestrator } from './orchestrate.ts'
import type { GateDecision, GateReview, PhaseState, PhaseStatus, TeamMode, TeamRun, TeamRunStatus } from './types.ts'

/**
 * The tool names this plugin itself registers. A data pack's expert allowlist
 * must never name one of them: a phase expert that could approve gates or
 * start runs would widen the pack's authority over the orchestrator itself.
 */
export const EXPERT_TEAM_TOOL_NAMES: readonly string[] = [
  'expert_team_list',
  'expert_team_run',
  'expert_team_status',
  'expert_team_approve',
  'consult_expert',
]

/** One recorded gate review, projected for the tool output. */
interface ReviewDto {
  readonly decision: GateDecision
  readonly at: string
  readonly comment?: string
}

/** One written artifact, projected for the tool output. */
interface ArtifactDto {
  readonly phaseId: string
  readonly artifact: string
  readonly relativePath: string
  readonly schema?: string
}

/** One phase state, projected for the tool output. */
interface PhaseDto {
  readonly phaseId: string
  readonly status: PhaseStatus
  readonly attempts: number
  readonly artifact?: ArtifactDto
  readonly error?: string
  readonly reviews?: ReviewDto[]
}

/** One run snapshot, projected for the tool output. */
interface RunDto {
  readonly runId: string
  readonly teamId: string
  readonly mode: TeamMode
  readonly status: TeamRunStatus
  readonly createdAt: string
  readonly phases: PhaseDto[]
}

/** Project one gate review into the lossless-JSON DTO the output schema declares. */
function reviewDto(review: GateReview): ReviewDto {
  return {
    decision: review.decision,
    at: review.at,
    ...(review.comment === undefined ? {} : { comment: review.comment }),
  }
}

/** Project one phase state into the lossless-JSON DTO the output schema declares. */
function phaseDto(state: PhaseState): PhaseDto {
  return {
    phaseId: state.phaseId,
    status: state.status,
    attempts: state.attempts,
    ...(state.artifact === undefined ? {} : {
      artifact: {
        phaseId: state.artifact.phaseId,
        artifact: state.artifact.artifact,
        relativePath: state.artifact.relativePath,
        ...(state.artifact.schema === undefined ? {} : { schema: state.artifact.schema }),
      },
    }),
    ...(state.error === undefined ? {} : { error: state.error }),
    ...(state.reviews === undefined ? {} : { reviews: state.reviews.map(reviewDto) }),
  }
}

/** Project one run snapshot into the lossless-JSON DTO the output schema declares. */
function runDto(run: TeamRun): RunDto {
  return {
    runId: String(run.runId),
    teamId: run.teamId,
    mode: run.mode,
    status: run.status,
    createdAt: run.createdAt,
    phases: run.phases.map(phaseDto),
  }
}

/**
 * The run-snapshot output schema shared by `expert_team_run`,
 * `expert_team_status`, and `expert_team_approve`. `as const` keeps the
 * literal types so `defineTool` infers the exact result shape; `satisfies`
 * proves the DSL contract.
 */
const RUN_OUTPUT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    runId: { type: 'string', required: true, description: 'Opaque run id; pass it back to expert_team_status and expert_team_approve.' },
    teamId: { type: 'string', required: true },
    mode: { type: 'string', required: true, enum: ['pipeline', 'hierarchical'] },
    status: { type: 'string', required: true, enum: ['running', 'waiting-approval', 'completed', 'failed'], description: "'waiting-approval' means a human gate is parked; expert_team_approve records the decision." },
    createdAt: { type: 'string', required: true },
    phases: {
      type: 'array',
      required: true,
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          phaseId: { type: 'string', required: true },
          status: { type: 'string', required: true, enum: ['pending', 'running', 'gate-pending', 'done', 'failed'] },
          attempts: { type: 'integer', required: true, description: 'Delegation attempts so far, including result-contract retries.' },
          artifact: {
            type: 'object',
            additionalProperties: false,
            properties: {
              phaseId: { type: 'string', required: true },
              artifact: { type: 'string', required: true },
              relativePath: { type: 'string', required: true, description: 'Artifact path relative to the run directory <artifactsDir>/<runId>/.' },
              schema: { type: 'string' },
            },
          },
          error: { type: 'string', description: 'Failure detail when the phase status is failed.' },
          reviews: {
            type: 'array',
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                decision: { type: 'string', required: true, enum: ['approved', 'rejected'] },
                comment: { type: 'string' },
                at: { type: 'string', required: true },
              },
            },
          },
        },
      },
    },
  },
} as const satisfies ValueSchemaSpec

/** Render one canonical value as the tool result's text payload. */
function renderJson(_args: unknown, value: unknown): { readonly type: 'text'; readonly text: string }[] {
  return [{ type: 'text', text: JSON.stringify(value) }]
}

/**
 * Build the five expert-team tool definitions bound to one orchestrator.
 * @param orchestrator - The mounted orchestrator the tools dispatch to.
 * @returns the registry-ready tool definitions.
 */
export function createExpertTeamTools(orchestrator: TeamOrchestrator): ToolDefinition[] {
  return [
    defineTool({
      name: 'expert_team_list',
      description: 'List the mounted expert teams: every phase with its dependencies, artifact, and human gate, and every expert with its role. Read this before running a team or consulting an expert.',
      parameters: {},
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            teams: {
              type: 'array',
              required: true,
              items: {
                type: 'object',
                additionalProperties: false,
                properties: {
                  team: { type: 'string', required: true },
                  title: { type: 'string', required: true },
                  mode: { type: 'string', required: true, enum: ['pipeline', 'hierarchical'] },
                  entry: { type: 'string', required: true },
                  experts: {
                    type: 'array',
                    required: true,
                    items: {
                      type: 'object',
                      additionalProperties: false,
                      properties: {
                        id: { type: 'string', required: true },
                        name: { type: 'string', required: true },
                        role: { type: 'string', required: true },
                        tools: { type: 'array', required: true, items: { type: 'string' } },
                      },
                    },
                  },
                  phases: {
                    type: 'array',
                    required: true,
                    items: {
                      type: 'object',
                      additionalProperties: false,
                      properties: {
                        id: { type: 'string', required: true },
                        expert: { type: 'string', required: true },
                        dependsOn: { type: 'array', required: true, items: { type: 'string' } },
                        artifact: { type: 'string', required: true },
                        gate: { type: 'string', description: "Present when the phase parks for human review ('human-review')." },
                      },
                    },
                  },
                },
              },
            },
          },
        },
        render: renderJson,
      },
      isConcurrencySafe: () => true,
      async execute() {
        return {
          teams: orchestrator.listTeams().map(team => ({
            team: team.team,
            title: team.title,
            mode: team.mode,
            entry: team.entry,
            experts: team.experts.map(expert => ({ id: expert.id, name: expert.name, role: expert.role, tools: expert.tools })),
            phases: team.phases.map(phase => ({
              id: phase.id,
              expert: phase.expert,
              dependsOn: phase.dependsOn,
              artifact: phase.artifact,
              ...(phase.gate === undefined ? {} : { gate: phase.gate }),
            })),
          })),
        }
      },
    }),
    defineTool({
      name: 'expert_team_run',
      description: 'Start one expert-team run: the pipeline executes phase by phase, deriving a subagent per phase, and returns when the run parks — at a human gate (waiting-approval), on completion, or on a failure. The input is the run request, for example the research topic.',
      parameters: {
        team: { type: 'string', required: true, description: 'Team id from expert_team_list.' },
        input: { type: 'string', required: true, description: 'The free-form run request the entry phase starts from.' },
      },
      output: { schema: RUN_OUTPUT_SCHEMA, render: renderJson },
      isConcurrencySafe: () => false,
      async execute(args) {
        return runDto(await orchestrator.startRun(args.team, args.input))
      },
    }),
    defineTool({
      name: 'expert_team_status',
      description: 'Read one expert-team run: its status, per-phase states with artifacts and attempts, and the recorded gate reviews. Use it after a run parks to see exactly where it stands.',
      parameters: {
        run_id: { type: 'string', required: true, description: 'Run id returned by expert_team_run.' },
      },
      output: { schema: RUN_OUTPUT_SCHEMA, render: renderJson },
      isConcurrencySafe: () => true,
      async execute(args) {
        return runDto(orchestrator.getRun(args.run_id))
      },
    }),
    defineTool({
      name: 'expert_team_approve',
      description: 'Record the human decision on a parked run gate. approved marks the gated phase done and resumes the pipeline to the next park point; rejected returns the artifact to the phase expert with the comment as revision guidance and parks the re-armed gate again. Convey the human reviewer\'s own words as the comment.',
      parameters: {
        run_id: { type: 'string', required: true, description: 'Run id returned by expert_team_run.' },
        decision: { type: 'string', required: true, enum: ['approved', 'rejected'], description: 'The human reviewer\'s decision.' },
        comment: { type: 'string', description: 'The reviewer\'s comment; on rejection it becomes the revision guidance.' },
      },
      output: { schema: RUN_OUTPUT_SCHEMA, render: renderJson },
      isConcurrencySafe: () => false,
      async execute(args) {
        return runDto(await orchestrator.approve(args.run_id, args.decision, args.comment))
      },
    }),
    defineTool({
      name: 'consult_expert',
      description: 'Consult one expert of a mounted team outside any pipeline: one bounded answer to one question, with the expert\'s persona and tool allowlist and no artifacts, no run state, no phase side effects. Use it for a single expert opinion when a full run is not wanted.',
      parameters: {
        team: { type: 'string', required: true, description: 'Team id from expert_team_list.' },
        expert: { type: 'string', required: true, description: 'Expert id of that team.' },
        question: { type: 'string', required: true, description: 'The question, delivered verbatim to the expert.' },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            answer: { type: 'string', required: true },
            truncated: { type: 'boolean', required: true, description: 'True when the answer was cut to the return byte bound.' },
          },
        },
        render: renderJson,
      },
      isConcurrencySafe: () => false,
      async execute(args) {
        return await orchestrator.consult(args.team, args.expert, args.question)
      },
    }),
  ]
}
