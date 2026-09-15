/**
 * `team.yml` parsing and pack-level cross validation: the fixed top-level
 * key set, per-phase structure, backward-only `depends_on` references, entry
 * consistency, expert existence, and referenced schema files on disk. Every
 * violation fails loud with a stable `EXPERT_TEAM_*` code, because a mounted
 * pack is the source of truth the whole team runs on.
 * @module @deepseek-ai/dsh-experimental-expert-team/team-yml
 */

import { readFile, stat } from 'node:fs/promises'
import { join, relative, resolve, sep } from 'node:path'
import { load as loadYaml } from 'js-yaml'
import { ExpertTeamError } from './errors.ts'
import {
  MAX_ID_BYTES,
  isPlainRecord,
  requireExactKeys,
  requireKebabId,
  requirePathSegment,
  requireRelativePath,
  requireScalar,
  requireStringList,
} from './validate.ts'
import type { PhaseDef, PhaseGate, PhaseOutput, TeamDef, TeamMode } from './types.ts'

/** Error code for every structural team.yml violation. */
const INVALID = 'EXPERT_TEAM_CATALOG_INVALID'

/** Maximum UTF-8 bytes of the team title. */
const MAX_TITLE_BYTES = 256
/** Maximum UTF-8 bytes of one phase input descriptor. */
const MAX_INPUT_BYTES = 512
/** Maximum UTF-8 bytes of one artifact file name. */
const MAX_ARTIFACT_BYTES = 128
/** Maximum number of phases in one team. */
const MAX_PHASES = 64
/** Maximum depends_on entries of one phase. */
const MAX_DEPENDS = 16

/** Build the fail-loud parse failure for one team.yml file. */
function packInvalid(detail: string, options?: ErrorOptions): ExpertTeamError {
  return new ExpertTeamError(`team.yml ${detail}`, INVALID, options)
}

/**
 * Parse the team mode field.
 * @param value - Raw parsed value.
 * @returns the validated mode.
 */
function parseMode(value: unknown): TeamMode {
  if (value !== 'pipeline' && value !== 'hierarchical') {
    throw packInvalid("mode must be 'pipeline' or 'hierarchical'")
  }
  return value
}

/**
 * Parse the gate field of one phase: the only declared value is
 * `human-review`.
 * @param index - Phase index for the error message.
 * @param value - Raw parsed value.
 * @returns the validated gate.
 */
function parseGate(index: number, value: unknown): PhaseGate {
  if (value !== 'human-review') {
    throw packInvalid(`phases[${index}] gate must be 'human-review', got: ${String(value)}`)
  }
  return value
}

/**
 * Parse the output block of one phase.
 * @param index - Phase index for the error message.
 * @param value - Raw parsed value.
 * @returns the validated output.
 */
function parseOutput(index: number, value: unknown): PhaseOutput {
  const scope = `phases[${index}] output`
  if (!isPlainRecord(value)) {
    throw packInvalid(`${scope} must be a mapping`)
  }
  requireExactKeys(INVALID, scope, value, ['artifact'], ['schema'])
  const artifact = requirePathSegment(INVALID, `${scope} artifact`, value.artifact, MAX_ARTIFACT_BYTES)
  const schema = value.schema === undefined
    ? undefined
    : requireRelativePath(INVALID, `${scope} schema`, value.schema)
  return {
    artifact,
    ...(schema === undefined ? {} : { schema }),
  }
}

/**
 * Parse the phases list: per-phase structure first, then the backward-only
 * rule that makes the dependency graph acyclic by construction.
 * @param value - Raw parsed value.
 * @returns the validated phases.
 */
function parsePhases(value: unknown): readonly PhaseDef[] {
  if (!Array.isArray(value) || value.length === 0) {
    throw packInvalid('phases must be a non-empty array')
  }
  if (value.length > MAX_PHASES) {
    throw packInvalid(`phases exceeds ${MAX_PHASES} entries`)
  }
  const ids = new Set<string>()
  const phases: PhaseDef[] = []
  for (const [index, item] of value.entries()) {
    const scope = `phases[${index}]`
    if (!isPlainRecord(item)) {
      throw packInvalid(`${scope} must be a mapping`)
    }
    requireExactKeys(INVALID, scope, item, ['id', 'expert', 'output'], ['depends_on', 'input', 'gate', 'supersedes'])
    const id = requireKebabId(INVALID, `${scope} id`, item.id)
    if (ids.has(id)) {
      throw packInvalid(`duplicate phase id: ${id}`)
    }
    ids.add(id)
    const expert = requireScalar(INVALID, `${scope} expert`, item.expert, MAX_ID_BYTES)
    const dependsOn = item.depends_on === undefined
      ? []
      : requireStringList(INVALID, `${scope} depends_on`, item.depends_on, MAX_DEPENDS, MAX_ID_BYTES)
    const supersedes = item.supersedes === undefined
      ? []
      : requireStringList(INVALID, `${scope} supersedes`, item.supersedes, MAX_DEPENDS, MAX_ID_BYTES)
    const input = item.input === undefined
      ? undefined
      : requireScalar(INVALID, `${scope} input`, item.input, MAX_INPUT_BYTES)
    const output = parseOutput(index, item.output)
    const gate = item.gate === undefined ? undefined : parseGate(index, item.gate)
    phases.push({
      id,
      expert,
      dependsOn,
      supersedes,
      ...(input === undefined ? {} : { input }),
      output,
      ...(gate === undefined ? {} : { gate }),
    })
  }
  const indexOf = new Map(phases.map((phase, index) => [phase.id, index]))
  for (const [index, phase] of phases.entries()) {
    for (const dep of phase.dependsOn) {
      const depIndex = indexOf.get(dep)
      if (depIndex === undefined || depIndex >= index) {
        throw new ExpertTeamError(
          `team.yml phases[${index}] depends_on must reference an earlier phase, got: ${dep}`,
          'EXPERT_TEAM_PHASE_CYCLE',
        )
      }
    }
    if (phase.supersedes !== undefined) {
      for (const sup of phase.supersedes) {
        const supIndex = indexOf.get(sup)
        if (supIndex === undefined || supIndex >= index) {
          throw new ExpertTeamError(
            `team.yml phases[${index}] supersedes must reference an earlier phase, got: ${sup}`,
            'EXPERT_TEAM_PHASE_CYCLE',
          )
        }
      }
    }
  }
  return phases
}

/**
 * Parse the entry field: a declared phase id whose phase consumes nothing.
 * @param value - Raw parsed value.
 * @param phases - The already validated phases of the same team.
 * @returns the validated entry id.
 */
function parseEntry(value: unknown, phases: readonly PhaseDef[]): string {
  const entry = requireKebabId(INVALID, 'team.yml entry', value)
  const target = phases.find(phase => phase.id === entry)
  if (target === undefined) {
    throw packInvalid(`entry must reference a declared phase, got: ${entry}`)
  }
  if (target.dependsOn.length > 0) {
    throw packInvalid(`entry phase must not declare depends_on: ${entry}`)
  }
  return entry
}

/**
 * Parse one team.yml contents with full structural validation. Filesystem
 * cross checks (expert refs, schema files) belong to {@link loadTeamYml}.
 * @param contents - Full file contents as UTF-8 text.
 * @returns the parsed team definition.
 * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_CATALOG_INVALID`
 *   for any structural violation, or `EXPERT_TEAM_PHASE_CYCLE` when a
 *   depends_on reference is not backward-only.
 */
export function parseTeamYml(contents: string): TeamDef {
  let raw: unknown
  try {
    raw = loadYaml(contents)
  } catch (error: unknown) {
    throw packInvalid('is not valid YAML', { cause: error })
  }
  if (!isPlainRecord(raw)) {
    throw packInvalid('must be a mapping')
  }
  requireExactKeys(INVALID, 'team.yml', raw, ['team', 'title', 'mode', 'entry', 'phases'], [])
  const team = requireKebabId(INVALID, 'team.yml team', raw.team)
  const title = requireScalar(INVALID, 'team.yml title', raw.title, MAX_TITLE_BYTES)
  const mode = parseMode(raw.mode)
  const phases = parsePhases(raw.phases)
  const entry = parseEntry(raw.entry, phases)
  return { team, title, mode, entry, phases }
}

/**
 * Verify one phase's schema reference: a relative path that stays inside the
 * pack and points at an existing file. The file's contents are not parsed
 * here — schema content validation happens when an artifact is checked.
 * @param packDir - Absolute pack directory.
 * @param phaseId - Phase id for the error message.
 * @param schemaPath - Validated pack-relative schema path.
 */
async function requireSchemaFile(packDir: string, phaseId: string, schemaPath: string): Promise<void> {
  const absolute = resolve(packDir, schemaPath)
  const rel = relative(packDir, absolute)
  // `schemaPath` is pre-validated as a relative forward-slash path, so the
  // resolved form can only escape as `..` or via a `..`-prefixed segment.
  if (rel === '' || rel === '..' || rel.startsWith(`..${sep}`)) {
    throw new ExpertTeamError(
      `team.yml phase ${phaseId} schema path escapes the pack: ${schemaPath}`,
      'EXPERT_TEAM_SCHEMA_MISSING',
    )
  }
  const statResult = await stat(absolute).catch((error: unknown) => {
    throw new ExpertTeamError(
      `team.yml phase ${phaseId} schema file does not exist: ${schemaPath}`,
      'EXPERT_TEAM_SCHEMA_MISSING',
      { cause: error },
    )
  })
  if (!statResult.isFile()) {
    throw new ExpertTeamError(
      `team.yml phase ${phaseId} schema path is not a file: ${schemaPath}`,
      'EXPERT_TEAM_SCHEMA_MISSING',
    )
  }
}

/**
 * Load and validate one pack's team.yml against its experts: reads the file,
 * parses it, and checks that every phase references a defined expert and an
 * existing schema file.
 * @param packDir - Absolute pack directory.
 * @param expertIds - Ids of the experts the pack's `experts/` directory defines.
 * @returns the parsed team definition.
 * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_CATALOG_INVALID`
 *   when the file is missing or structurally invalid,
 *   `EXPERT_TEAM_EXPERT_MISSING` when a phase references an unknown expert,
 *   `EXPERT_TEAM_PHASE_CYCLE` for a non-backward depends_on, and
 *   `EXPERT_TEAM_SCHEMA_MISSING` when a referenced schema file is not an
 *   existing file inside the pack.
 */
export async function loadTeamYml(packDir: string, expertIds: readonly string[]): Promise<TeamDef> {
  const contents = await readFile(join(packDir, 'team.yml'), 'utf8').catch((error: unknown) => {
    throw new ExpertTeamError(`pack ${packDir} is missing team.yml`, INVALID, { cause: error })
  })
  const def = parseTeamYml(contents)
  const experts = new Set(expertIds)
  for (const phase of def.phases) {
    if (!experts.has(phase.expert)) {
      throw new ExpertTeamError(
        `team.yml phase ${phase.id} references expert ${phase.expert}, which the pack does not define`,
        'EXPERT_TEAM_EXPERT_MISSING',
      )
    }
    if (phase.output.schema !== undefined) {
      await requireSchemaFile(packDir, phase.id, phase.output.schema)
    }
  }
  return def
}
