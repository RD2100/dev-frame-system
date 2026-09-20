/**
 * Strict parsing of one expert definition file (`<pack>/experts/<id>.md`):
 * a fixed-key YAML front matter block plus the persona body. The front
 * matter keys are exactly the pack format's; anything unknown, missing,
 * oversized, or self-inconsistent fails loud, because a mounted pack is the
 * source of truth the whole team runs on.
 * @module @deepseek-ai/dsh-experimental-expert-team/expert-md
 */

import { load as loadYaml } from 'js-yaml'
import { ExpertTeamError } from './errors.ts'
import {
  FRONT_MATTER_DELIMITER,
  isPlainRecord,
  requireExactKeys,
  requireKebabId,
  requireScalar,
  requireStringList,
} from './validate.ts'
import type { ExpertDef } from './types.ts'

/** Fail-loud parse failure for one expert md file. */
function expertInvalid(detail: string, options?: ErrorOptions): ExpertTeamError {
  return new ExpertTeamError(`expert md ${detail}`, 'EXPERT_TEAM_EXPERT_INVALID', options)
}

/** Maximum UTF-8 bytes of the persona body. */
const MAX_PERSONA_BYTES = 16 * 1024
/** Maximum entries of the tools allowlist. */
const MAX_TOOLS = 32
/** Maximum UTF-8 bytes of one tool name. */
const MAX_TOOL_BYTES = 64
/** Maximum entries of the skills list. */
const MAX_SKILLS = 16
/** Maximum UTF-8 bytes of one skill directory name. */
const MAX_SKILL_BYTES = 64
/** Maximum entries of the handoff-check list. */
const MAX_CHECKS = 16
/** Maximum UTF-8 bytes of one handoff check. */
const MAX_CHECK_BYTES = 256
/** Maximum UTF-8 bytes of the display name. */
const MAX_NAME_BYTES = 128
/** Maximum UTF-8 bytes of the role line. */
const MAX_ROLE_BYTES = 256
/** Maximum UTF-8 bytes of the goal line. */
const MAX_GOAL_BYTES = 512
/** Maximum UTF-8 bytes of the hierarchy role value. */
const MAX_HIERARCHY_ROLE_BYTES = 32

/**
 * Parse one expert definition file strictly.
 * @param fileName - Base name of the file inside the pack's `experts/`
 *   directory; the front matter id must equal its name stem.
 * @param contents - Full file contents as UTF-8 text. CRLF line endings are
 *   normalized to LF before parsing.
 * @returns the parsed expert definition, with the md body as `persona`.
 * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_EXPERT_INVALID` when
 *   the front matter structure, key set, field shapes or bounds, id/file-name
 *   match, or body bounds are violated.
 */
export function parseExpertMd(fileName: string, contents: string): ExpertDef {
  if (!fileName.endsWith('.md')) {
    throw expertInvalid(`file name must end with .md: ${fileName}`)
  }
  const normalized = contents.replace(/\r\n/g, '\n')
  const lines = normalized.split('\n')
  if (lines[0] !== FRONT_MATTER_DELIMITER) {
    throw expertInvalid('is missing the front matter opening `---`')
  }
  let close = -1
  for (let index = 1; index < lines.length; index += 1) {
    if (lines[index] === FRONT_MATTER_DELIMITER) {
      close = index
      break
    }
  }
  if (close === -1) {
    throw expertInvalid('is missing the front matter closing `---`')
  }
  let meta: unknown
  try {
    meta = loadYaml(lines.slice(1, close).join('\n'))
  } catch (error: unknown) {
    throw expertInvalid('front matter is not valid YAML', { cause: error })
  }
  if (!isPlainRecord(meta)) {
    throw expertInvalid('front matter must be a mapping')
  }
  requireExactKeys(
    'EXPERT_TEAM_EXPERT_INVALID',
    'front matter',
    meta,
    ['id', 'team', 'name', 'role', 'goal', 'tools'],
    ['hierarchy-role', 'skills', 'handoff-checks'],
  )
  const id = requireKebabId('EXPERT_TEAM_EXPERT_INVALID', 'front matter id', meta.id)
  const stem = fileName.slice(0, -3)
  if (id !== stem) {
    throw expertInvalid(`id must match the file name stem: ${fileName}`)
  }
  const team = requireKebabId('EXPERT_TEAM_EXPERT_INVALID', 'front matter team', meta.team)
  const name = requireScalar('EXPERT_TEAM_EXPERT_INVALID', 'front matter name', meta.name, MAX_NAME_BYTES)
  const role = requireScalar('EXPERT_TEAM_EXPERT_INVALID', 'front matter role', meta.role, MAX_ROLE_BYTES)
  const goal = requireScalar('EXPERT_TEAM_EXPERT_INVALID', 'front matter goal', meta.goal, MAX_GOAL_BYTES)
  const tools = requireStringList('EXPERT_TEAM_EXPERT_INVALID', 'front matter tools', meta.tools, MAX_TOOLS, MAX_TOOL_BYTES)
  if (tools.length === 0) {
    throw expertInvalid('front matter tools must declare at least one tool; an expert with none cannot act')
  }
  const skills = meta.skills === undefined
    ? undefined
    : requireStringList('EXPERT_TEAM_EXPERT_INVALID', 'front matter skills', meta.skills, MAX_SKILLS, MAX_SKILL_BYTES)
  const handoffChecks = meta['handoff-checks'] === undefined
    ? undefined
    : requireStringList('EXPERT_TEAM_EXPERT_INVALID', 'front matter handoff-checks', meta['handoff-checks'], MAX_CHECKS, MAX_CHECK_BYTES)
  const hierarchyRole = meta['hierarchy-role'] === undefined
    ? undefined
    : (() => {
      const raw = requireScalar('EXPERT_TEAM_EXPERT_INVALID', 'front matter hierarchy-role', meta['hierarchy-role'], MAX_HIERARCHY_ROLE_BYTES)
      if (raw !== 'controller' && raw !== 'lead' && raw !== 'worker') {
        throw expertInvalid(`front matter hierarchy-role must be 'controller', 'lead', or 'worker', got: ${raw}`)
      }
      return raw
    })()
  const bodyLines = lines.slice(close + 1)
  // One blank line separates the front matter from the body; tolerate its
  // absence so a body starting immediately after `---` still parses.
  if (bodyLines[0] === '') bodyLines.shift()
  const persona = bodyLines.join('\n')
  if (persona.trim().length === 0) {
    throw expertInvalid('persona body must not be blank')
  }
  if (Buffer.byteLength(persona, 'utf8') > MAX_PERSONA_BYTES) {
    throw expertInvalid(`persona body exceeds ${MAX_PERSONA_BYTES} UTF-8 bytes`)
  }
  return {
    id,
    team,
    name,
    role,
    goal,
    tools,
    ...(hierarchyRole === undefined ? {} : { hierarchyRole }),
    ...(skills === undefined ? {} : { skills }),
    ...(handoffChecks === undefined ? {} : { handoffChecks }),
    persona,
  }
}
