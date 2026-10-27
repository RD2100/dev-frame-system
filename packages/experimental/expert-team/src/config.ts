/**
 * Explicit config validation for the expert-team plugin boundary. The
 * orchestration half's plugin builds its loader `Config` from these fields;
 * the catalog refuses to mount anything until the config validates.
 * @module @deepseek-ai/dsh-experimental-expert-team/config
 */

import { createRequire } from 'node:module'
import { dirname } from 'node:path'
import { ExpertTeamError } from './errors.ts'
import { hasControlChar } from './validate.ts'

const require = createRequire(import.meta.url)

/**
 * Loader config of the expert-team plugin. Pack entries accept either a
 * filesystem path or an installed pack package name. Package references are
 * resolved from this plugin's installation, so a profile bundle does not
 * depend on the caller's working directory.
 */
export interface ExpertTeamConfig {
  /** Team-pack directories or installed package names; at least one. */
  readonly packs: readonly string[]
  /** Runtime artifacts root; a run writes under `<artifactsDir>/<runId>/`. */
  readonly artifactsDir: string
}

/**
 * Validate one config path field: a non-empty, unpadded, control-free string
 * usable as a path.
 * @param field - Field label used in error messages.
 * @param value - Raw field value from the config.
 * @returns the validated value.
 * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_CONFIG_INVALID` when
 *   the value is not a clean path string.
 */
function requireConfigPath(field: string, value: unknown): string {
  if (typeof value !== 'string') {
    throw new ExpertTeamError(`${field} must be a string`, 'EXPERT_TEAM_CONFIG_INVALID')
  }
  if (value.trim().length === 0) {
    throw new ExpertTeamError(`${field} must be a non-empty path`, 'EXPERT_TEAM_CONFIG_INVALID')
  }
  if (value !== value.trim()) {
    throw new ExpertTeamError(`${field} must not be padded with whitespace`, 'EXPERT_TEAM_CONFIG_INVALID')
  }
  if (hasControlChar(value)) {
    throw new ExpertTeamError(`${field} must not contain control characters`, 'EXPERT_TEAM_CONFIG_INVALID')
  }
  return value
}

/** Resolve a package reference to its installed directory while preserving paths. */
function resolvePackReference(value: string): string {
  if (value.startsWith('.') || value.startsWith('/') || value.includes('\\')
    || (value.includes('/') && !value.startsWith('@')) || /^[A-Za-z]:[\\/]/u.test(value)) return value
  try {
    return dirname(require.resolve(`${value}/package.json`))
  } catch (error) {
    throw new ExpertTeamError(
      `pack package ${JSON.stringify(value)} could not be resolved from the expert-team installation`,
      'EXPERT_TEAM_CONFIG_INVALID',
      { cause: error },
    )
  }
}

/**
 * Validate the plugin config explicitly at the package boundary. Packs are
 * validated in order, so a failing entry is named as `packs[<index>]`.
 * @param config - Raw config values as the loader supplies them.
 * @returns a defensive copy with every field validated.
 * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_CONFIG_INVALID`
 *   when `packs` is not a non-empty array of clean path strings or
 *   `artifactsDir` is not a clean path string.
 */
export function validateExpertTeamConfig(config: ExpertTeamConfig): ExpertTeamConfig {
  if (!Array.isArray(config.packs) || config.packs.length === 0) {
    throw new ExpertTeamError(
      'packs must be a non-empty array of team pack directories (at least one)',
      'EXPERT_TEAM_CONFIG_INVALID',
    )
  }
  return {
    packs: config.packs.map((pack, index) => resolvePackReference(requireConfigPath(`packs[${index}]`, pack))),
    artifactsDir: requireConfigPath('artifactsDir', config.artifactsDir),
  }
}
