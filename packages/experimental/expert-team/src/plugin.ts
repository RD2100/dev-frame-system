/**
 * Cordis plugin wiring for the expert-team core: one loadable row that mounts
 * the configured packs fail-loud at load, provides `ctx.expertTeam`, and
 * registers the five model tools on `ctx.tools`. Misconfiguration (packs
 * below the minimum, a pack that fails validation) fails the load — a
 * half-mounted expert team is worse than an absent one.
 * @module @deepseek-ai/dsh-experimental-expert-team/plugin
 */

import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { resolve, isAbsolute } from 'node:path'
import { ExpertCatalog } from './catalog.ts'
import { validateExpertTeamConfig } from './config.ts'
import { TeamOrchestrator } from './orchestrate.ts'
import { ExpertRuntime } from './runtime.ts'
import { createExpertTeamTools } from './tools.ts'

/** Cordis plugin name. */
export const name = 'expert-team'

/** Required host services; the runtime derives expert subagents through them. */
export const inject = ['tools', 'systemPrompt', 'agents', 'agentLoop']

/**
 * The static usage guidance the plugin registers on the global prompt layer.
 * Text is pinned: it teaches when to list, run, approve, and consult — never
 * a deployment tunable.
 */
export const EXPERT_TEAM_USAGE_SECTION = `This deployment mounts expert teams: human-gated expert pipelines over pack-defined personas.

- Call expert_team_list once when a task could be a team run, and pick the team by its phases and gates.
- expert_team_run drives the whole pipeline phase by phase and returns when the run parks — a human gate (waiting-approval), completion, or a failure. Report the parked state honestly; do not paraphrase a gate as finished.
- When a run is waiting-approval, the human decision is the reviewer's, not yours: ask the reviewer, then expert_team_approve with their decision and their own words as the comment. A rejection returns the artifact to the phase expert for revision.
- consult_expert answers one question outside any run; prefer it when a full pipeline is not wanted.
- Artifacts are files under the run directory; reference them by path instead of restating their content.`

/** Loader configuration for the expert-team plugin; both fields required. */
export interface Config {
  /** Directories of team packs to mount; at least one. */
  readonly packs: string[]
  /** Runtime artifacts root; a run writes under `<artifactsDir>/<runId>/`. */
  readonly artifactsDir: string
}

/**
 * Loader schema; the explicit content checks (non-empty packs, clean paths)
 * run in {@link apply} through `validateExpertTeamConfig`.
 */
export const Config: z<Config> = z.object({
  packs: z.array(z.string()).required(),
  artifactsDir: z.string().required(),
})

declare module '@deepseek-ai/cordis' {
  interface Context {
    /** The expert-team orchestrator over the mounted packs. */
    expertTeam: TeamOrchestrator
  }
}

/**
 * Mount the expert-team plugin: validate config, load the pack catalog (every
 * pack problem fails the load), construct the runtime and orchestrator,
 * provide `ctx.expertTeam`, register the five tools, and register the static
 * usage section. Disposal removes the tools, the section, the service, and
 * every agent session the orchestrator derived.
 * @param ctx - The mounting context.
 * @param config - Schema-validated loader config.
 */
export async function apply(ctx: Context, config: Config): Promise<void> {
  const spec = validateExpertTeamConfig(config)
  const catalog = await ExpertCatalog.load(spec)
  const runtime = new ExpertRuntime(ctx, catalog)
  const orchestrator = new TeamOrchestrator(catalog, runtime, resolveArtifactsRoot(spec.artifactsDir))
  const disposers: Array<{ readonly label: string; readonly dispose: () => unknown }> = [
    { label: 'expertTeam service', dispose: ctx.provide('expertTeam', orchestrator) },
    { label: 'usage prompt section', dispose: ctx.systemPrompt.section({ name: 'expert-team:usage', order: 45, text: EXPERT_TEAM_USAGE_SECTION }) },
    {
      label: 'derived session disposal',
      dispose: ctx.effect(() => () => {
        // Registry contributions unwind with the fiber; the derived sessions
        // are the one async resource this plugin owns, so disposal awaits them.
        return orchestrator.dispose()
      }, 'expert-team.sessions'),
    },
  ]
  try {
    for (const definition of createExpertTeamTools(orchestrator)) {
      disposers.push({ label: `tool ${definition.name}`, dispose: ctx.tools.register(definition) })
    }
  } catch (error: unknown) {
    // Roll back everything that mounted, naming any disposer that failed so a
    // partial unmount stays diagnosable; the original load error remains the
    // loud failure.
    const rollback = [...disposers].reverse()
    // The promise wrapper routes a synchronously-throwing disposer into
    // allSettled too; a bare `map(entry => entry.dispose())` would let its
    // throw escape the map and replace the original load error.
    const settled = await Promise.allSettled(rollback.map(entry => Promise.resolve().then(() => entry.dispose())))
    for (const [index, outcome] of settled.entries()) {
      if (outcome.status === 'rejected') {
        const label = rollback[index]?.label ?? 'an unnamed contribution'
        const detail = outcome.reason instanceof Error ? outcome.reason.message : String(outcome.reason)
        console.warn(`[expert-team] mount rollback: disposal of ${label} failed: ${detail}`)
      }
    }
    throw error
  }
}

/**
 * Resolve the artifacts root to an absolute path. The config accepts repo-
 * relative deployment paths; every downstream consumer (run directories,
 * session cwds, briefing references) needs the absolute form.
 */
function resolveArtifactsRoot(artifactsDir: string): string {
  if (isAbsolute(artifactsDir)) return artifactsDir
  return resolve(process.cwd(), artifactsDir)
}
