/**
 * The expert catalog: mounts every configured pack directory, parses its
 * experts and team.yml with fail-loud validation, and serves immutable
 * team/expert lookups to the orchestration half and the model tools.
 * @module @deepseek-ai/dsh-experimental-expert-team/catalog
 */

import { readdir, readFile, stat } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { type ExpertTeamConfig, validateExpertTeamConfig } from './config.ts'
import { ExpertTeamError } from './errors.ts'
import { parseExpertMd } from './expert-md.ts'
import { loadTeamYml } from './team-yml.ts'
import { EXPERT_TEAM_TOOL_NAMES } from './tools.ts'
import type { ExpertDef, TeamDef } from './types.ts'

/** One mounted pack: its directory, the parsed team definition, and its experts. */
export interface LoadedTeam {
  /** Absolute pack directory the team was loaded from. */
  readonly packDir: string
  /** The parsed `team.yml`. */
  readonly def: TeamDef
  /** The pack's experts, in file-name order. Treat as immutable. */
  readonly experts: readonly ExpertDef[]
}

/**
 * Immutable catalog of the mounted expert packs. Build once with
 * {@link ExpertCatalog.load}; every pack problem fails loud there, so the
 * lookups afterwards only fail on unknown ids. The orchestration half's
 * plugin provides one instance per process as a Cordis service.
 */
export class ExpertCatalog {
  private constructor(private readonly teams: ReadonlyMap<string, LoadedTeam>) {}

  /**
   * Mount and validate every configured pack. Duplicate pack directories and
   * duplicate team ids are rejected, so each team has exactly one source
   * pack per process.
   * @param config - Loader config; validated here too, so a direct `load`
   *   call fails as loud as the plugin path.
   * @returns the loaded catalog.
   * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_CONFIG_INVALID`
   *   when the config is malformed, `EXPERT_TEAM_CATALOG_INVALID` when a
   *   pack directory, its experts directory, its team.yml, or the
   *   pack/team pairing is invalid, `EXPERT_TEAM_EXPERT_INVALID` when an
   *   expert md file fails its parse, `EXPERT_TEAM_EXPERT_MISSING` when a
   *   phase references an unknown expert, `EXPERT_TEAM_SKILL_MISSING` when a
   *   declared skill has no `SKILL.md` in the pack, `EXPERT_TEAM_PHASE_CYCLE`
   *   when a depends_on is not backward-only, `EXPERT_TEAM_TOOL_FORBIDDEN`
   *   when an expert allowlist names one of the plugin's own tools, and
   *   `EXPERT_TEAM_SCHEMA_MISSING` when a referenced schema file is not an
   *   existing file in the pack.
   */
  static async load(config: ExpertTeamConfig): Promise<ExpertCatalog> {
    const spec = validateExpertTeamConfig(config)
    const teams = new Map<string, LoadedTeam>()
    const mountedDirs = new Set<string>()
    for (const pack of spec.packs) {
      const packDir = resolve(pack)
      if (mountedDirs.has(packDir)) {
        throw new ExpertTeamError(`pack directory is mounted twice: ${pack}`, 'EXPERT_TEAM_CATALOG_INVALID')
      }
      mountedDirs.add(packDir)
      const dirStat = await stat(packDir).catch(() => undefined)
      // A failed stat means "not an existing directory"; the check below
      // turns that into the fail-loud catalog error.
      if (dirStat === undefined || !dirStat.isDirectory()) {
        throw new ExpertTeamError(
          `pack directory does not exist or is not a directory: ${pack}`,
          'EXPERT_TEAM_CATALOG_INVALID',
        )
      }
      const experts = await loadExperts(packDir)
      const def = await loadTeamYml(packDir, experts.map(expert => expert.id))
      for (const expert of experts) {
        if (expert.team !== def.team) {
          throw new ExpertTeamError(
            `expert ${expert.id} declares team ${expert.team}, but the pack team is ${def.team}`,
            'EXPERT_TEAM_CATALOG_INVALID',
          )
        }
        // A data pack must not name the plugin's own tools: an expert that
        // could approve gates or start runs would widen the pack's authority
        // over the orchestrator itself.
        for (const tool of expert.tools) {
          if (EXPERT_TEAM_TOOL_NAMES.includes(tool)) {
            throw new ExpertTeamError(
              `expert ${expert.id} declares tool "${tool}", which the expert-team plugin itself provides; packs must not name the plugin's own tools`,
              'EXPERT_TEAM_TOOL_FORBIDDEN',
            )
          }
        }
        // A declared skill is a persona-referenced contract; a missing
        // SKILL.md must fail the mount instead of composing a phase that
        // cannot keep its own promise.
        for (const skill of expert.skills ?? []) {
          const skillStat = await stat(join(packDir, 'skills', skill, 'SKILL.md')).catch(() => undefined)
          if (skillStat === undefined || !skillStat.isFile()) {
            throw new ExpertTeamError(
              `expert ${expert.id} declares skill ${skill}, which the pack does not provide with a SKILL.md`,
              'EXPERT_TEAM_SKILL_MISSING',
            )
          }
        }
      }
      const existing = teams.get(def.team)
      if (existing !== undefined) {
        throw new ExpertTeamError(
          `team id ${def.team} is mounted from two pack directories: ${existing.packDir} and ${packDir}`,
          'EXPERT_TEAM_CATALOG_INVALID',
        )
      }
      teams.set(def.team, { packDir, def, experts })
    }
    return new ExpertCatalog(teams)
  }

  /**
   * List every mounted team in pack configuration order.
   * @returns the loaded teams; treat as immutable.
   */
  listTeams(): readonly LoadedTeam[] {
    return [...this.teams.values()]
  }

  /**
   * Look up one mounted team.
   * @param teamId - Kebab-case team id from a pack's `team.yml`.
   * @returns the loaded team.
   * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_TEAM_MISSING`
   *   when the id is not mounted.
   */
  getTeam(teamId: string): LoadedTeam {
    const team = this.teams.get(teamId)
    if (team === undefined) {
      throw new ExpertTeamError(`unknown team: ${teamId}`, 'EXPERT_TEAM_TEAM_MISSING')
    }
    return team
  }

  /**
   * Look up one expert of a mounted team.
   * @param teamId - Team id, resolved through {@link getTeam}.
   * @param expertId - Kebab-case expert id from the team's pack.
   * @returns the parsed expert definition.
   * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_TEAM_MISSING`
   *   when the team is not mounted, or `EXPERT_TEAM_EXPERT_MISSING` when the
   *   team's pack does not define the expert.
   */
  getExpert(teamId: string, expertId: string): ExpertDef {
    const team = this.getTeam(teamId)
    const expert = team.experts.find(candidate => candidate.id === expertId)
    if (expert === undefined) {
      throw new ExpertTeamError(`team ${teamId} does not define expert: ${expertId}`, 'EXPERT_TEAM_EXPERT_MISSING')
    }
    return expert
  }
}

/**
 * Parse every `*.md` file of one pack's `experts/` directory.
 * @param packDir - Absolute pack directory.
 * @returns the experts in file-name order.
 * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_CATALOG_INVALID`
 *   when the directory is missing or unreadable, or
 *   `EXPERT_TEAM_EXPERT_INVALID` when a file is unreadable or fails its parse.
 */
async function loadExperts(packDir: string): Promise<ExpertDef[]> {
  const expertsDir = join(packDir, 'experts')
  const entries = await readdir(expertsDir, { withFileTypes: true }).catch((error: unknown) => {
    throw new ExpertTeamError(`pack ${packDir} has no readable experts directory`, 'EXPERT_TEAM_CATALOG_INVALID', {
      cause: error,
    })
  })
  const fileNames = entries
    .filter(entry => entry.isFile() && entry.name.endsWith('.md'))
    .map(entry => entry.name)
    .sort()
  const experts: ExpertDef[] = []
  for (const fileName of fileNames) {
    const contents = await readFile(join(expertsDir, fileName), 'utf8').catch(
      // Reachable only when the entry changes state between readdir and read,
      // or an OS-level denial blocks the read; neither is portably
      // reproducible in a test, and the failure must still carry a stable code.
      // v8 ignore next 4 -- unreachable failure mapping, reason above.
      (error: unknown) => {
        throw new ExpertTeamError(`expert file ${fileName} is not readable as UTF-8 text`, 'EXPERT_TEAM_EXPERT_INVALID', { cause: error })
      },
    )
    experts.push(parseExpertMd(fileName, contents))
  }
  return experts
}
