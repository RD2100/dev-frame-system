# Expert teams

English | [中文](expert-team.zh.md)

The expert-team subsystem runs human-gated expert pipelines over persona packs: a pack's `team.yml` declares the phases, their expert personas, their dependencies, artifacts, and human-review gates, and the orchestrator executes the phases in declaration order through persona-scoped subagents derived from the agent registry. Each phase expert answers with its artifact as the reply body plus a fenced-JSON result object; the runtime is the single writer — it validates the result against the declared artifact name and the pack's JSON Schema, writes the body atomically, and re-drives the same session within a bounded retry on a contract failure. A gated phase parks the run until a human decision arrives: an approval resumes the pipeline, a rejection returns the artifact to the same session with the reviewer's comment as revision guidance. Artifacts land as files under `<artifactsDir>/<runId>/` and never re-enter prompts as content. The [package README](../../packages/experimental/expert-team/README.md) owns the mount configuration, the pack contract, and the model experience.

## Service surface

`ctx.expertTeam` is the orchestrator the five model tools dispatch through: `listTeams` serves `expert_team_list`, `startRun` and `getRun` serve `expert_team_run` and `expert_team_status`, `approve` records the human gate decision for `expert_team_approve`, and `consult` answers `consult_expert` outside any run. Concurrent decisions on one run serialize through a per-run gate.

## Contracts

Every failure carries a stable `EXPERT_TEAM_*` code on `ExpertTeamError`: mount-time codes (`EXPERT_TEAM_CONFIG_INVALID`, `EXPERT_TEAM_CATALOG_INVALID`, `EXPERT_TEAM_EXPERT_INVALID`, `EXPERT_TEAM_EXPERT_MISSING`, `EXPERT_TEAM_SKILL_MISSING`, `EXPERT_TEAM_SCHEMA_MISSING`, `EXPERT_TEAM_PHASE_CYCLE`) fail the load, and run-time codes (`EXPERT_TEAM_TEAM_MISSING`, `EXPERT_TEAM_TOOL_MISSING`, `EXPERT_TEAM_MODEL_MISSING`, `EXPERT_TEAM_RUN_UNKNOWN`, `EXPERT_TEAM_GATE_PENDING`, `EXPERT_TEAM_RESULT_INVALID`, `EXPERT_TEAM_MODE_UNSUPPORTED`) surface on the tool result. Run and phase state move through `pending` → `running` → (`gate-pending`) → `done` or `failed`, and the run status reports `waiting-approval` while a gate parks it. A failed phase has no accepted artifact to pass downstream, so approval is refused while a rejection re-opens it as a guided revision.

## Boundaries

The five tools join the [tools](tools.md) registry through the loader plugin, and phase subagents derive through the agent registry's scoped-create face rather than the [agent-hierarchy](agent-hierarchy.md) dispatch engine — a phase session is a bounded persona, not a role-bound worker. Run state mirrors to `<artifactsDir>/<runId>/run-state.json` at every commit point, but a run does not resume in a new process. Recording artifacts into project-memory is delegated to the packs' tool allowlists; the orchestrator never calls memory itself.

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxexpertteam--teamorchestrator"></a>

### `ctx.expertTeam` — `TeamOrchestrator`

Orchestrates expert-team runs over the mounted catalog. One instance per mounted plugin, published as `ctx.expertTeam`; the model tools are its only consumers.

```ts cordis-catalog
/**
 * List every mounted team, in pack configuration order.
 * @returns the team views shaped for `expert_team_list`, in configuration order.
 */
listTeams(): readonly ExpertTeamView[]

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
async startRun(teamId: string, input: string): Promise<TeamRun>

/**
 * Read one run's snapshot; serves `expert_team_status` after a run parks.
 * @param runId - Raw run id as the model supplied it.
 * @returns the frozen run snapshot.
 * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_RUN_UNKNOWN` when
 *   the id is malformed or not a live run of this process.
 */
getRun(runId: string): TeamRun

/**
 * Record the human gate decision on a run's single parked phase and resume.
 * An approval marks the gated phase done and executes the remaining
 * pipeline to the next park point; a rejection re-drives the phase session
 * with the reviewer's comment before parking again. The whole span is
 * serialized against concurrent decisions.
 * @param runId - Raw run id as the model supplied it.
 * @param decision - The recorded decision.
 * @param comment - Optional reviewer comment; a rejection comment is the
 *   revision guidance the phase expert receives.
 * @returns the run snapshot after the decision took effect.
 * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_RUN_UNKNOWN` when
 *   the run is not live, or `EXPERT_TEAM_GATE_PENDING` when no gate awaits
 *   a decision or an approval targets a failed phase. An infrastructure
 *   failure while re-driving the phase (agent derivation, model selection,
 *   session creation) settles the run failed and propagates.
 */
async approve(runId: string, decision: GateDecision, comment?: string | undefined): Promise<TeamRun>

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
async consult(teamId: string, expertId: string, question: string): Promise<{ readonly answer: string; readonly truncated: boolean }>

/** Dispose every derived agent session this orchestrator still owns. */
async dispose(): Promise<void>
```

Types: [ExpertTeamView](../../packages/experimental/expert-team/README.md) · [GateDecision](../../packages/experimental/expert-team/README.md) · [TeamRun](../../packages/experimental/expert-team/README.md)

Source: [`packages/experimental/expert-team/src/orchestrate.ts`](../../packages/experimental/expert-team/src/orchestrate.ts)
<!-- END GENERATED cordis-surface -->
