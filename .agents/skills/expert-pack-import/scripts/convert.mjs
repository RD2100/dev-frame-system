#!/usr/bin/env node
/**
 * Convert Claude Code subagent definition files into a DSH expert-team pack.
 *
 * Plain Node, no dependencies. Input is one directory of agent `.md` files in
 * the Claude Code subagent format: YAML frontmatter with at least `name` and
 * `description`, an optional `tools` comma list (or sequence, or flow list),
 * and the persona body. An optional `skills/` directory (next to the agent
 * files, or via `--skills`) is copied through verbatim. Output is a pack the
 * `@deepseek-ai/dsh-experimental-expert-team` catalog mounts through its
 * `Config.packs`: `experts/<id>.md`, `team.yml`, and this import's README.
 *
 * Mapping decisions (all restated in the generated README so the human
 * reviewing the pack sees them):
 *
 * - `name` → kebab-case expert id (lowercased, non-[a-z0-9] runs become
 *   single dashes, bounded to the catalog's 64-byte id limit; collisions and
 *   un-kebabizable names fail the conversion). The original `name` is kept
 *   verbatim as the display name; the converter invents nothing.
 * - `description` → `role` is the first sentence, `goal` is the remaining
 *   sentences; a single-sentence description makes both fields identical
 *   (printed as a notice). Sentences split naively on `.!?。！？` followed by
 *   whitespace or end of text, so abbreviations can over-split — the human
 *   reviews `role`/`goal` anyway. Fields are byte-capped at the catalog's
 *   limits (role 256, goal 512); a cap that cuts text prints a warning.
 * - `tools` → lowercased, kept in order, deduplicated (with a warning). This
 *   is an identity mapping, not a translation: the catalog matches allowlist
 *   names against the deployment's mounted tools, and this converter cannot
 *   know that inventory. Names outside the documented Claude Code tool set
 *   stay (lowercased) and are printed as a warning list — they will fail loud
 *   at mount with `EXPERT_TEAM_TOOL_MISSING` unless the deployment mounts
 *   exactly that name; nothing is silently dropped. MCP-style names
 *   (`mcp__server__tool`) get the same treatment plus a case-sensitivity
 *   caveat, because lowercasing can break them.
 * - An agent with NO `tools` frontmatter means "all tools" in Claude Code,
 *   but packs require a non-empty allowlist; the converter defaults it to the
 *   read-only `[read, grep, glob]` and prints a notice. An empty `tools`
 *   value is treated the same way.
 * - Plugin-own tool names (`expert_team_list`, `expert_team_run`,
 *   `expert_team_status`, `expert_team_approve`, `consult_expert`) are
 *   rejected: the conversion exits non-zero and writes nothing, because the
 *   catalog would reject the pack at mount with
 *   `EXPERT_TEAM_TOOL_FORBIDDEN` (an expert that could approve gates or start
 *   runs would widen the pack's authority over the orchestrator).
 * - `skills/` copies through verbatim (files dereferenced and rewritten, so a
 *   standalone copy — no symlinks). Imported packs are standalone copies
 *   because the catalog mounts and validates a real, self-contained
 *   directory per deployment: the source format has no pinned identity to
 *   live-link against, and symlinks would not survive the Windows and
 *   packaging paths a pack travels. Copied skills are never wired into
 *   experts' `skills:` frontmatter — the import cannot know which expert uses
 *   which skill; the human wires that after review.
 * - `team.yml` gets the team id `imported-<source-directory-name>` (kebab,
 *   64-byte capped) and a minimal fabricated graph: one phase per expert in
 *   source file-name order, linear chain, entry first, schema-less
 *   `<id>.md` artifacts. The import does not know the real dependencies; the
 *   generated files say so and the human edits the graph before relying on it.
 * - The persona body copies through verbatim (CRLF normalized, leading blank
 *   lines trimmed, exactly one trailing newline). A missing or blank body
 *   fails the conversion; an oversized one (> 16 KiB) is written with a
 *   warning, because the mount would reject it and the human must trim.
 *
 * Frontmatter parsing is a deliberate YAML subset in the style of the
 * catalog's `expert-md.ts` parser: `key: value` scalars (plain, single- and
 * double-quoted), `- item` sequences, `[a, b]` flow lists, and `|`/`>`
 * block scalars with `+-` chomping. Everything else fails loud naming the
 * file, so a source the subset cannot read is never half-converted.
 *
 * Output is deterministic: no timestamps, no host paths (the generated files
 * record only the source directory's base name), sorted file order. Running
 * the converter twice over the same input produces byte-identical output.
 * An existing output directory is refused without `--force`, which
 * regenerates the generated files and wipes `experts/` and `skills/` while
 * keeping anything else the human added.
 *
 * Usage:
 *   node convert.mjs <source-dir> <output-dir> [--skills <dir>|none] [--force]
 */

import { mkdir, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises'
import { basename, isAbsolute, join, relative, resolve } from 'node:path'
import process from 'node:process'

/** Plugin-own tool names; a pack expert must never declare one. */
const FORBIDDEN_TOOLS = new Set([
  'expert_team_list',
  'expert_team_run',
  'expert_team_status',
  'expert_team_approve',
  'consult_expert',
])

/**
 * Documented Claude Code tool names, lowercased. These map to the deployment
 * by lowercased identity without a warning; anything else warns (kept, but
 * the mount will fail unless the deployment mounts exactly that name).
 */
const KNOWN_CLAUDE_TOOLS = new Set([
  'askuserquestion',
  'bash',
  'bashoutput',
  'edit',
  'exitplanmode',
  'glob',
  'grep',
  'killshell',
  'notebookedit',
  'read',
  'slashcommand',
  'task',
  'todowrite',
  'webfetch',
  'websearch',
  'write',
])

/** Frontmatter keys this converter recognizes but does not import. */
const KNOWN_UNMAPPED_KEYS = new Set(['model'])

/** Read-only default for agents that declare no tools. */
const DEFAULT_TOOLS = Object.freeze(['read', 'grep', 'glob'])

// Bounds mirrored from the catalog's parsers (expert-md.ts, validate.ts) so a
// conversion that fits here also mounts. Oversizes warn rather than fail,
// except where the catalog can never accept the value at all.
const MAX_ID_BYTES = 64
const MAX_NAME_BYTES = 128
const MAX_ROLE_BYTES = 256
const MAX_GOAL_BYTES = 512
const MAX_TITLE_BYTES = 256
const MAX_TOOLS = 32
const MAX_TOOL_BYTES = 64
const MAX_PERSONA_BYTES = 16 * 1024

/** Windows reserved device base names; an expert id must never be one. */
const WINDOWS_RESERVED_DEVICE_NAMES = new Set([
  'aux', 'con', 'prn', 'nul',
  ...['com', 'lpt'].flatMap(prefix => [1, 2, 3, 4, 5, 6, 7, 8, 9].map(digit => `${prefix}${digit}`)),
])

const KEBAB_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

/** A conversion failure: message printed to stderr, exit 1, nothing written. */
class ConvertError extends Error {}

/** Fail loud with a message naming the source file when there is one. */
function fail(message) {
  throw new ConvertError(message)
}

// ---------------------------------------------------------------------------
// Restricted frontmatter parser (a documented YAML subset; anything else
// fails loud). Values come back as strings or arrays of strings.
// ---------------------------------------------------------------------------

/**
 * Parse one `key: value` scalar: plain, single- or double-quoted, or a
 * `[a, b]` flow list. Trailing ` # comment` is stripped from plain scalars.
 */
function parseInlineScalar(text, where, key) {
  if (text.startsWith('"')) return parseDoubleQuoted(text, where, key)
  if (text.startsWith("'")) return parseSingleQuoted(text, where, key)
  if (text.startsWith('[')) return parseFlowList(text, where, key)
  const comment = /\s#/.exec(text)
  return (comment === null ? text : text.slice(0, comment.index)).trim()
}

/** Parse one double-quoted scalar with the short backslash escapes only. */
function parseDoubleQuoted(text, where, key) {
  let out = ''
  let index = 1
  while (index < text.length) {
    const char = text[index]
    if (char === '\\') {
      const escapes = { '"': '"', '\\': '\\', n: '\n', t: '\t', r: '\r', b: '\b', f: '\f', '0': '\0' }
      const replacement = escapes[text[index + 1]]
      if (replacement === undefined) {
        fail(`${where}: unsupported escape in "${key}" (the parser knows \\n \\t \\r \\b \\f \\0 \\" \\\\): ${text.slice(index, index + 2)}`)
      }
      out += replacement
      index += 2
      continue
    }
    if (char === '"') {
      const trailing = text.slice(index + 1).trim()
      if (trailing !== '' && !trailing.startsWith('#')) {
        fail(`${where}: unexpected content after the closing quote of "${key}": ${trailing}`)
      }
      return out
    }
    out += char
    index += 1
  }
  fail(`${where}: unterminated double-quoted value for "${key}"`)
}

/** Parse one single-quoted scalar; `''` is the literal-quote escape. */
function parseSingleQuoted(text, where, key) {
  let out = ''
  let index = 1
  while (index < text.length) {
    const char = text[index]
    if (char === "'") {
      if (text[index + 1] === "'") {
        out += "'"
        index += 2
        continue
      }
      const trailing = text.slice(index + 1).trim()
      if (trailing !== '' && !trailing.startsWith('#')) {
        fail(`${where}: unexpected content after the closing quote of "${key}": ${trailing}`)
      }
      return out
    }
    out += char
    index += 1
  }
  fail(`${where}: unterminated single-quoted value for "${key}"`)
}

/** Parse one `[a, b]` flow list; items go back through the scalar parser. */
function parseFlowList(text, where, key) {
  if (!text.endsWith(']')) {
    fail(`${where}: flow list for "${key}" is not closed: ${text}`)
  }
  const inner = text.slice(1, -1).trim()
  if (inner === '') return []
  return inner.split(',').map(item => {
    const trimmed = item.trim()
    if (trimmed === '') fail(`${where}: empty entry in the flow list for "${key}"`)
    if (trimmed.startsWith('[')) fail(`${where}: nested flow lists are not supported ("${key}")`)
    return parseInlineScalar(trimmed, where, key)
  })
}

/**
 * Parse one `- item` sequence. Items must be plain scalars; nested mappings
 * or deeper indentation fail loud.
 */
function parseSequence(lines, start, indent, where, key) {
  const items = []
  let index = start
  while (index < lines.length) {
    const line = lines[index]
    const trimmed = line.trim()
    if (trimmed === '' || trimmed.startsWith('#')) {
      index += 1
      continue
    }
    const lineIndent = line.length - line.trimStart().length
    if (lineIndent < indent) break
    if (lineIndent > indent) {
      fail(`${where}: unexpected deeper indentation in the "${key}" sequence: ${JSON.stringify(line)}`)
    }
    const item = /^-[ \t]?(.*)$/.exec(line.slice(indent))
    if (item === null) break
    const value = item[1].trim()
    if (value === '') fail(`${where}: empty item in the "${key}" sequence`)
    if (/^[A-Za-z][A-Za-z0-9_-]*:[ \t]/.test(value)) {
      fail(`${where}: sequence items under "${key}" must be plain scalars, not mappings: ${value}`)
    }
    items.push(parseInlineScalar(value, where, key))
    index += 1
  }
  return [items, index]
}

/**
 * Parse one `|` or `>` block scalar (with optional `+`/`-` chomping indicator)
 * introduced on `lines[start]`. Content is every deeper-indented line.
 */
function parseBlockScalar(lines, start, where, key, style, chomp) {
  const headerIndent = lines[start].length - lines[start].trimStart().length
  const contentLines = []
  let index = start + 1
  let contentIndent = -1
  while (index < lines.length) {
    const line = lines[index]
    if (line.trim() === '') {
      contentLines.push('')
      index += 1
      continue
    }
    const lineIndent = line.length - line.trimStart().length
    if (lineIndent <= headerIndent) break
    if (contentIndent === -1) contentIndent = lineIndent
    if (lineIndent < contentIndent) {
      fail(`${where}: inconsistent indentation in the "${key}" block scalar: ${JSON.stringify(line)}`)
    }
    contentLines.push(line.slice(contentIndent))
    index += 1
  }
  while (contentLines.length > 0 && contentLines[contentLines.length - 1] === '') contentLines.pop()
  let text
  if (style === '|') {
    text = contentLines.join('\n')
  } else {
    // `>` folds one paragraph (lines without a blank separator) into one line.
    const paragraphs = []
    let current = []
    for (const line of contentLines) {
      if (line === '') {
        if (current.length > 0) paragraphs.push(current.join(' '))
        current = []
      } else {
        current.push(line)
      }
    }
    if (current.length > 0) paragraphs.push(current.join(' '))
    text = paragraphs.join('\n')
  }
  if (chomp !== '-' && text !== '') text += '\n'
  return [text, index]
}

/**
 * Parse the frontmatter mapping of one agent file. Returns a plain object of
 * string-or-array values; unknown syntax fails loud naming the file.
 */
function parseFrontmatterMapping(metaLines, where) {
  const meta = {}
  let index = 0
  while (index < metaLines.length) {
    const line = metaLines[index]
    const trimmed = line.trim()
    if (trimmed === '' || trimmed.startsWith('#')) {
      index += 1
      continue
    }
    if (/^\t/.test(line)) fail(`${where}: tab indentation is not supported in frontmatter: ${JSON.stringify(line)}`)
    const keyMatch = /^([A-Za-z][A-Za-z0-9_-]*):(?:[ \t]+(.*))?[ \t]*$/.exec(line)
    if (keyMatch === null) {
      fail(`${where}: frontmatter line is not a "key: value" pair: ${JSON.stringify(line)}`)
    }
    const key = keyMatch[1]
    if (key in meta) fail(`${where}: duplicate frontmatter key: ${key}`)
    const rest = (keyMatch[2] ?? '').trim()
    if (rest !== '') {
      meta[key] = parseInlineScalar(rest, where, key)
      index += 1
      continue
    }
    // Empty inline value: a block sequence, a block scalar, or an empty scalar.
    let lookahead = index + 1
    while (lookahead < metaLines.length
      && (metaLines[lookahead].trim() === '' || metaLines[lookahead].trimStart().startsWith('#'))) {
      lookahead += 1
    }
    if (lookahead >= metaLines.length) {
      meta[key] = ''
      break
    }
    const next = metaLines[lookahead]
    const keyIndent = line.length - line.trimStart().length
    const nextIndent = next.length - next.trimStart().length
    if (nextIndent <= keyIndent) {
      meta[key] = ''
      index += 1
      continue
    }
    const blockMatch = /^([ \t]+)([|>])([+-]?)?[ \t]*$/.exec(next)
    if (blockMatch !== null) {
      const [text, nextIndex] = parseBlockScalar(metaLines, lookahead, where, key, blockMatch[2], blockMatch[3] ?? '')
      meta[key] = text
      index = nextIndex
      continue
    }
    if (next.trimStart().startsWith('-')) {
      const [items, nextIndex] = parseSequence(metaLines, lookahead, nextIndent, where, key)
      meta[key] = items
      index = nextIndex
      continue
    }
    fail(`${where}: unsupported frontmatter value under "${key}" (expected a value, a "- item" sequence, or a |/> block scalar): ${JSON.stringify(next)}`)
  }
  return meta
}

// ---------------------------------------------------------------------------
// Mapping helpers.
// ---------------------------------------------------------------------------

/** Normalize one agent file's raw contents to LF and strip a UTF-8 BOM. */
function normalizeSource(contents, notices, where) {
  let text = contents
  if (text.startsWith('\uFEFF')) {
    text = text.slice(1)
    notices.push([where, 'stripped a UTF-8 BOM from the source file'])
  }
  return text.replace(/\r\n/g, '\n')
}

/** Split one normalized single-paragraph text into sentences. */
function splitSentences(text) {
  const sentences = []
  let start = 0
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    // CJK enders are never abbreviation dots and are written without a
    // trailing space, so they always end a sentence; ASCII enders need a
    // following whitespace (or end of text) so "3.5" and "e.g." stay whole.
    const cjkEnder = '。！？'.includes(char)
    const asciiEnder = '.!?'.includes(char)
      && (text[index + 1] === undefined || /\s/.test(text[index + 1]))
    if (cjkEnder || asciiEnder) {
      const sentence = text.slice(start, index + 1).trim()
      if (sentence !== '') sentences.push(sentence)
      start = index + 1
    }
  }
  const tail = text.slice(start).trim()
  if (tail !== '') sentences.push(tail)
  return sentences
}

/**
 * Cut one string to at most `max` UTF-8 bytes without splitting a code point.
 * Returns null when the string already fits.
 */
function cutToBytes(text, max) {
  if (Buffer.byteLength(text, 'utf8') <= max) return null
  let out = Buffer.from(text, 'utf8').subarray(0, max).toString('utf8').replace(/\uFFFD+$/u, '')
  while (out.length > 0 && out.charCodeAt(out.length - 1) >= 0xD800 && out.charCodeAt(out.length - 1) <= 0xDBFF) {
    out = out.slice(0, -1)
  }
  return out.replace(/\s+$/u, '')
}

/** Normalize one free-text field to a single collapsed line. */
function toSingleLine(text) {
  return text.replace(/\s+/gu, ' ').trim()
}

/** Emit one string as a double-quoted YAML scalar (JSON-compatible subset). */
function yamlQuoted(value) {
  return JSON.stringify(value)
}

/**
 * Kebab-normalize one identifier candidate; returns null when nothing
 * survives, which the caller reports as a hard error.
 */
function kebabize(value) {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
}

/**
 * Derive the expert id from one agent's `name`: kebab, within the catalog's
 * id bounds, never a Windows reserved device name (the id becomes a file name
 * on Windows).
 */
function deriveExpertId(name, where, hardErrors) {
  const id = kebabize(name)
  if (!KEBAB_PATTERN.test(id)) {
    hardErrors.push(`${where}: cannot derive a kebab-case expert id from name ${JSON.stringify(name)}; rename the agent with a lowercase [a-z0-9-] name`)
    return null
  }
  if (Buffer.byteLength(id, 'utf8') > MAX_ID_BYTES) {
    hardErrors.push(`${where}: derived expert id exceeds the catalog's ${MAX_ID_BYTES}-byte id limit; shorten the agent name`)
    return null
  }
  if (WINDOWS_RESERVED_DEVICE_NAMES.has(id)) {
    hardErrors.push(`${where}: derived expert id ${id} is a Windows reserved device name and cannot become a file name`)
    return null
  }
  return id
}

// ---------------------------------------------------------------------------
// Agent conversion.
// ---------------------------------------------------------------------------

/**
 * Convert one agent file into an expert definition plus the diagnostics the
 * report will print. Hard failures are collected into `hardErrors` (the
 * conversion writes nothing when any exist) and reported per file; everything
 * recoverable becomes a `[warning]` or `[notice]` entry.
 */
function convertAgentFile(fileName, contents, teamId, hardErrors) {
  const where = fileName
  const notices = []
  const warnings = []
  const text = normalizeSource(contents, notices, where)
  const lines = text.split('\n')
  if (lines[0] !== '---') fail(`${where}: is missing the front matter opening \`---\` (not a Claude Code agent file?)`)
  const close = lines.indexOf('---', 1)
  if (close === -1) fail(`${where}: front matter is not closed with a \`---\` line`)

  const meta = parseFrontmatterMapping(lines.slice(1, close), where)

  if (typeof meta.name !== 'string' || meta.name.trim() === '') {
    fail(`${where}: frontmatter is missing a non-empty "name" (required by the Claude Code subagent format)`)
  }
  if (typeof meta.description !== 'string' || meta.description.trim() === '') {
    fail(`${where}: frontmatter is missing a non-empty "description" (required by the Claude Code subagent format)`)
  }
  const id = deriveExpertId(meta.name, where, hardErrors)
  if (id === null) return null

  let name = toSingleLine(meta.name)
  if (name !== meta.name.trim()) notices.push([where, 'collapsed whitespace in the display name'])

  // description -> role (first sentence) + goal (the rest).
  const description = toSingleLine(meta.description)
  const sentences = splitSentences(description)
  if (sentences.length === 0) fail(`${where}: description is empty after normalization`)
  let role = sentences[0]
  let goal = sentences.slice(1).join(' ')
  if (goal === '') {
    goal = role
    notices.push([where, 'the description is a single sentence, so role and goal are identical; edit them to say who the expert is and what it optimizes for'])
  }
  const cutRole = cutToBytes(role, MAX_ROLE_BYTES)
  if (cutRole !== null) {
    role = cutRole
    warnings.push([where, `role was cut to the catalog's ${MAX_ROLE_BYTES}-byte limit; hand-edit the role line`])
  }
  const cutGoal = cutToBytes(goal, MAX_GOAL_BYTES)
  if (cutGoal !== null) {
    goal = cutGoal
    warnings.push([where, `goal was cut to the catalog's ${MAX_GOAL_BYTES}-byte limit; hand-edit the goal line`])
  }
  const cutName = cutToBytes(name, MAX_NAME_BYTES)
  if (cutName !== null) {
    name = cutName
    warnings.push([where, `display name was cut to the catalog's ${MAX_NAME_BYTES}-byte limit`])
  }

  // tools -> lowercased allowlist, or the read-only default.
  const rawTools = meta.tools
  let defaulted = false
  let tools
  if (rawTools === undefined || (typeof rawTools === 'string' && rawTools.trim() === '')) {
    defaulted = true
    tools = [...DEFAULT_TOOLS]
    warnings.push([where, `no tools frontmatter: Claude Code grants all tools when it is absent, but a pack allowlist must be non-empty — defaulted to the read-only ${tools.join(', ')}`])
  } else {
    const entries = Array.isArray(rawTools)
      ? rawTools
      : typeof rawTools === 'string'
        ? rawTools.split(',')
        : null
    if (entries === null) {
      fail(`${where}: "tools" must be a comma-separated list, a "- item" sequence, or a [a, b] flow list`)
    }
    tools = []
    for (const entry of entries) {
      if (typeof entry !== 'string' || entry.trim() === '') {
        fail(`${where}: empty tool entry in "tools"`)
      }
      const tool = entry.trim().toLowerCase()
      if (FORBIDDEN_TOOLS.has(tool)) {
        hardErrors.push(`${where}: declares tool "${entry.trim()}", which the expert-team plugin itself provides (${tool}); packs must not name the plugin's own tools — the catalog would reject this pack at mount with EXPERT_TEAM_TOOL_FORBIDDEN, because an expert that could approve gates or start runs would widen the pack's authority over the orchestrator. Remove the tool from the source file.`)
        continue
      }
      if (tools.includes(tool)) {
        warnings.push([where, `duplicate tool "${entry.trim()}" was deduplicated`])
        continue
      }
      if (Buffer.byteLength(tool, 'utf8') > MAX_TOOL_BYTES) {
        warnings.push([where, `tool "${tool}" exceeds the catalog's ${MAX_TOOL_BYTES}-byte tool-name limit; the mount will reject it`])
      }
      if (!KNOWN_CLAUDE_TOOLS.has(tool)) {
        const caveat = tool.includes('__')
          ? ' MCP-style names are case-sensitive in some deployments, and this converter lowercased the name — verify it against the mounted tool name.'
          : ` It will fail loud at mount with EXPERT_TEAM_TOOL_MISSING unless the deployment mounts exactly "${tool}".`
        warnings.push([where, `unrecognized tool "${entry.trim()}" (kept, lowercased as "${tool}").${caveat}`])
      }
      tools.push(tool)
    }
    if (tools.length === 0 && hardErrors.length === 0) {
      defaulted = true
      tools = [...DEFAULT_TOOLS]
      warnings.push([where, `tools reduced to nothing (every entry was dropped or forbidden) — defaulted to the read-only ${tools.join(', ')}`])
    }
  }
  if (tools.length > MAX_TOOLS) {
    warnings.push([where, `"tools" exceeds the catalog's ${MAX_TOOLS}-entry limit; the mount will reject it`])
  }

  for (const key of Object.keys(meta)) {
    if (['name', 'description', 'tools'].includes(key)) continue
    if (KNOWN_UNMAPPED_KEYS.has(key)) {
      notices.push([where, `frontmatter "${key}" is not imported (DSH derives expert subagents from the deployment's default model and config)`])
    } else {
      warnings.push([where, `frontmatter "${key}" is not part of the import mapping and was dropped`])
    }
  }

  // Persona body: verbatim after normalization.
  const bodyLines = lines.slice(close + 1)
  while (bodyLines.length > 0 && bodyLines[0] === '') bodyLines.shift()
  const persona = bodyLines.join('\n').trimEnd()
  if (persona.trim().length === 0) {
    fail(`${where}: has no persona body below the front matter; a pack persona must not be blank`)
  }
  if (Buffer.byteLength(persona, 'utf8') > MAX_PERSONA_BYTES) {
    warnings.push([where, `persona body exceeds the catalog's ${MAX_PERSONA_BYTES}-byte limit; the mount will reject it until the body is trimmed`])
  }

  return { id, name, role, goal, tools, defaulted, persona, notices, warnings }
}

// ---------------------------------------------------------------------------
// Output rendering.
// ---------------------------------------------------------------------------

/** Render one expert definition file's contents. */
function renderExpertMd(expert, teamId) {
  const lines = [
    '---',
    `id: ${expert.id}`,
    `team: ${teamId}`,
    `name: ${yamlQuoted(expert.name)}`,
    `role: ${yamlQuoted(expert.role)}`,
    `goal: ${yamlQuoted(expert.goal)}`,
    'tools:',
    ...expert.tools.map(tool => `  - ${tool}`),
    '---',
    '',
    expert.persona,
  ]
  return `${lines.join('\n')}\n`
}

/** Render team.yml: the fabricated minimal linear phase graph. */
function renderTeamYml(experts, teamId, title, sourceLabel) {
  const lines = [
    '# Generated by .agents/skills/expert-pack-import/scripts/convert.mjs from the',
    `# Claude Code subagent directory "${sourceLabel}".`,
    '# The phase order below is fabricated (source file-name order): the import does',
    '# not know the real dependencies between the imported agents. Edit the phases to',
    '# match the actual workflow, or delete phases and consult experts through',
    '# consult_expert instead. Read this pack\'s README before mounting.',
    `team: ${teamId}`,
    `title: ${yamlQuoted(title)}`,
    'mode: pipeline',
    `entry: ${experts[0].id}`,
    'phases:',
  ]
  experts.forEach((expert, index) => {
    lines.push(`  - id: ${expert.id}`)
    lines.push(`    expert: ${expert.id}`)
    if (index === 0) {
      lines.push(`    input: ${yamlQuoted('The run request, as given to expert_team_run')}`)
    } else {
      lines.push('    depends_on:')
      lines.push(`      - ${experts[index - 1].id}`)
      lines.push(`    input: ${yamlQuoted(`The upstream artifact ${experts[index - 1].id}.md`)}`)
    }
    lines.push('    output:')
    lines.push(`      artifact: ${expert.id}.md`)
  })
  return `${lines.join('\n')}\n`
}

/** Render the pack README: provenance, mapping decisions, review checklist. */
function renderReadme(experts, teamId, sourceLabel, skillsCopied) {
  const rows = experts.map(expert => {
    const tools = expert.defaulted
      ? `${expert.tools.join(', ')} (read-only default)`
      : expert.tools.join(', ')
    return `| [${expert.id}](experts/${expert.id}.md) | ${expert.sourceFile} | ${tools} |`
  })
  const singleSentence = experts.filter(expert => expert.role === expert.goal).map(expert => expert.id)
  const lines = [
    `# ${teamId}`,
    '',
    `Imported by \`expert-pack-import\` from the Claude Code subagent directory \`${sourceLabel}\`.`,
    '',
    'This pack is a standalone copy of third-party agent definitions, not a live link:',
    'edits to the source do not propagate, and re-importing (converter `--force`)',
    'overwrites the generated files. The persona bodies are untrusted content — a',
    'human reviewed this pack before it was mounted.',
    '',
    '## What the import mapped',
    '',
    '- `name` became the kebab-case expert id and the file name under `experts/`; the',
    '  original name is kept verbatim as the display name.',
    '- `description` became `role` (first sentence) and `goal` (remaining sentences).',
  ]
  if (singleSentence.length > 0) {
    lines.push(`  The description was one sentence for ${singleSentence.join(', ')}, so role and goal are`,
      '  identical there.')
  }
  lines.push(
    '- `tools` were lowercased and kept; unrecognized names stayed and will fail loud at',
    '  mount (`EXPERT_TEAM_TOOL_MISSING`) unless the deployment mounts exactly that name.',
    '- Agents without a `tools` frontmatter received the read-only default',
    '  `read, grep, glob`, because a pack allowlist must be non-empty.',
    '- The persona body copies through verbatim; the converter never edits it.',
    '',
    '## What the import did not know',
    '',
    '- The `team.yml` phase order is fabricated (source file-name order, one linear',
    '  chain, entry first). Edit the phases to match the real workflow, or delete',
    '  phases and consult experts through `consult_expert` instead.',
    '- `role` and `goal` are mechanical derivations; edit them to say who the expert is',
    '  and what it optimizes for.',
  )
  if (skillsCopied) {
    lines.push('- The `skills/` directory was copied through verbatim but never wired into any',
      '  expert\'s `skills:` frontmatter; add the lists yourself (a declared skill',
      '  without a SKILL.md fails the mount).')
  } else {
    lines.push('- No `skills/` directory was imported; add one and wire it through an expert\'s',
      '  `skills:` frontmatter if needed.')
  }
  lines.push(
    '- No phase result schemas are generated; imported phases stay schema-less.',
    '- The team id is derived from the source directory name and must stay unique',
    '  across all mounted packs; the mount rejects duplicates.',
    '',
    '## Imported experts',
    '',
    '| Expert | Source file | Tools |',
    '|---|---|---|',
    ...rows,
    '',
    '## Review checklist before mounting',
    '',
    '- Read every persona body; the text is third-party content the deployment will',
    '  send to a model as a system prompt.',
    '- Check each expert\'s `tools` allowlist against the deployment\'s mounted tools.',
    '- Rewrite the fabricated `team.yml` phase graph, or delete phases.',
    '- Fix the derived `role` and `goal` lines.',
    '',
    '## Mount and validate',
    '',
    'Point one `packs` entry of the `expert-team` plugin row in `cordis.yml` at this',
    'directory and restart the deployment, then call `expert_team_list` and confirm',
    `the team \`${teamId}\` appears with the experts above. The core validates the pack`,
    'fail-loud at mount; a pack that fails validation never half-mounts.',
    '',
    '```yaml',
    'packs:',
    `  - ./path/to/${teamId}`,
    '```',
  )
  return `${lines.join('\n')}\n`
}

// ---------------------------------------------------------------------------
// Filesystem helpers.
// ---------------------------------------------------------------------------

/** Copy one directory tree, dereferencing through content copies only. */
async function copyTree(source, destination) {
  await mkdir(destination, { recursive: true })
  const entries = await readdir(source, { withFileTypes: true })
  entries.sort((a, b) => (a.name < b.name ? -1 : 1))
  for (const entry of entries) {
    const sourcePath = join(source, entry.name)
    const destinationPath = join(destination, entry.name)
    if (entry.isDirectory()) {
      await copyTree(sourcePath, destinationPath)
    } else if (entry.isFile()) {
      await writeFile(destinationPath, await readFile(sourcePath))
    } else {
      fail(`skills entry is neither a regular file nor a directory (symlinks are not copied; replace it with a real file): ${sourcePath}`)
    }
  }
}

/** List one directory's regular `.md` files in sorted order. */
async function listAgentFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  return entries
    .filter(entry => entry.isFile() && entry.name.endsWith('.md'))
    .map(entry => entry.name)
    .sort()
}

/** True when `child` is `parent` itself or lives inside it. */
function isInside(parent, child) {
  const rel = relative(parent, child)
  return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel))
}

/** Recursively list every file of one tree, sorted, for the self-test diff. */
async function listTree(directory, prefix = '') {
  const out = []
  const entries = await readdir(directory, { withFileTypes: true })
  entries.sort((a, b) => (a.name < b.name ? -1 : 1))
  for (const entry of entries) {
    const path = join(directory, entry.name)
    const rel = prefix === '' ? entry.name : `${prefix}/${entry.name}`
    if (entry.isDirectory()) out.push(...await listTree(path, rel))
    else out.push(rel)
  }
  return out
}

// ---------------------------------------------------------------------------
// Main.
// ---------------------------------------------------------------------------

/** Parse argv; returns null after printing usage for --help. */
function parseArgv(argv) {
  const positional = []
  let skills = undefined
  let force = false
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--force') {
      force = true
    } else if (arg === '--skills' || arg.startsWith('--skills=')) {
      const value = arg === '--skills' ? argv[++index] : arg.slice('--skills='.length)
      if (value === undefined || value === '') fail('usage: --skills requires a directory path or "none"')
      skills = value
    } else if (arg === '--help' || arg === '-h') {
      process.stdout.write('usage: node convert.mjs <source-dir> <output-dir> [--skills <dir>|none] [--force]\n')
      return null
    } else if (arg.startsWith('--')) {
      fail(`unknown option: ${arg}`)
    } else {
      positional.push(arg)
    }
  }
  if (positional.length !== 2) {
    fail('usage: node convert.mjs <source-dir> <output-dir> [--skills <dir>|none] [--force]')
  }
  return { source: resolve(positional[0]), output: resolve(positional[1]), skills, force }
}

async function main() {
  const args = parseArgv(process.argv.slice(2))
  if (args === null) return
  const { source, output, force } = args

  const sourceStat = await stat(source).catch(() => undefined)
  if (sourceStat === undefined || !sourceStat.isDirectory()) {
    fail(`source directory does not exist or is not a directory: ${source}`)
  }
  if (isInside(source, output) || isInside(output, source)) {
    fail('the output directory must be disjoint from the source directory')
  }
  const outputStat = await stat(output).catch(() => undefined)
  if (outputStat !== undefined && !force) {
    fail(`output directory already exists: ${output}; pass --force to regenerate (it overwrites the generated files, wipes experts/ and skills/, and keeps anything else you added)`)
  }

  const fileNames = await listAgentFiles(source)
  if (fileNames.length === 0) {
    fail(`no .md agent files found in: ${source}`)
  }

  // Resolve the skills source: explicit flag, else a "skills" sibling of the
  // agent files, else none.
  let skillsSource = null
  if (args.skills === 'none') {
    skillsSource = null
  } else if (args.skills !== undefined) {
    const resolved = resolve(args.skills)
    const skillsStat = await stat(resolved).catch(() => undefined)
    if (skillsStat === undefined || !skillsStat.isDirectory()) {
      fail(`--skills directory does not exist or is not a directory: ${args.skills}`)
    }
    if (isInside(source, resolved) || isInside(resolved, source)) {
      fail('the --skills directory must be disjoint from the source directory')
    }
    skillsSource = resolved
  } else {
    const candidate = join(source, 'skills')
    const candidateStat = await stat(candidate).catch(() => undefined)
    if (candidateStat !== undefined && candidateStat.isDirectory()) {
      skillsSource = candidate
      process.stdout.write(`expert-pack-import: detected skills directory: skills/\n`)
    }
  }

  // Convert every agent first; hard errors abort the whole run before any
  // output is written, so a rejected source never half-converts.
  const hardErrors = []
  const experts = []
  for (const fileName of fileNames) {
    const contents = await readFile(join(source, fileName), 'utf8')
    try {
      const expert = convertAgentFile(fileName, contents, '', hardErrors)
      if (expert !== null) experts.push({ ...expert, sourceFile: fileName })
    } catch (error) {
      if (!(error instanceof ConvertError)) throw error
      hardErrors.push(error.message)
    }
  }
  if (hardErrors.length === 0) {
    const seen = new Map()
    for (const expert of experts) {
      const previous = seen.get(expert.id)
      if (previous !== undefined) {
        hardErrors.push(`${previous.sourceFile} and ${expert.sourceFile} both map to expert id "${expert.id}"; rename one of the agents`)
      }
      seen.set(expert.id, expert)
    }
  }
  if (hardErrors.length > 0) {
    process.stderr.write(`expert-pack-import: conversion failed with ${hardErrors.length} error(s); no output was written:\n`)
    for (const message of hardErrors) process.stderr.write(`  [error] ${message}\n`)
    process.exitCode = 1
    return
  }

  // Team id and title derive from the source directory's base name only, so
  // the same input converts to identical bytes from any path spelling.
  const sourceLabel = basename(source)
  let teamBase = kebabize(sourceLabel)
  if (teamBase === '') teamBase = 'pack'
  const maxBaseBytes = MAX_ID_BYTES - 'imported-'.length
  const cutBase = cutToBytes(teamBase, maxBaseBytes)
  if (cutBase !== null) teamBase = cutBase
  const teamId = `imported-${teamBase}`
  let title = `Imported team from ${sourceLabel}`
  const cutTitle = cutToBytes(title, MAX_TITLE_BYTES)
  if (cutTitle !== null) {
    title = cutTitle
    process.stderr.write(`  [warning] team title was cut to the catalog's ${MAX_TITLE_BYTES}-byte limit\n`)
  }

  // Write the pack.
  if (outputStat !== undefined) {
    await rm(join(output, 'experts'), { recursive: true, force: true })
    await rm(join(output, 'skills'), { recursive: true, force: true })
  }
  await mkdir(join(output, 'experts'), { recursive: true })
  for (const expert of experts) {
    await writeFile(join(output, 'experts', `${expert.id}.md`), renderExpertMd(expert, teamId))
  }
  await writeFile(join(output, 'team.yml'), renderTeamYml(experts, teamId, title, sourceLabel))
  await writeFile(join(output, 'README.md'), renderReadme(experts, teamId, sourceLabel, skillsSource !== null))
  if (skillsSource !== null) {
    await copyTree(skillsSource, join(output, 'skills'))
  }

  // Report.
  process.stdout.write(`expert-pack-import: converted ${experts.length} agent file(s) from "${sourceLabel}"\n`)
  for (const expert of experts) {
    const tools = expert.defaulted ? `${expert.tools.join(', ')} [defaulted]` : expert.tools.join(', ')
    process.stdout.write(`  ${expert.sourceFile} -> experts/${expert.id}.md (tools: ${tools})\n`)
  }
  process.stdout.write(`wrote pack: ${output} (team.yml, README.md, ${experts.length} expert(s)${skillsSource !== null ? ', skills/ copy' : ''})\n`)
  const diagnostics = experts.flatMap(expert => [
    ...expert.notices.map(([where, message]) => ['notice', where, message]),
    ...expert.warnings.map(([where, message]) => ['warning', where, message]),
  ])
  if (diagnostics.length > 0) {
    process.stderr.write(`diagnostics: ${diagnostics.length} — review before mounting\n`)
    for (const [level, where, message] of diagnostics) {
      process.stderr.write(`  [${level}] ${where}: ${message}\n`)
    }
  }
  process.stdout.write('next: a human must review the generated pack (persona text is untrusted content) before mounting it through Config.packs\n')
}

try {
  await main()
} catch (error) {
  if (error instanceof ConvertError) {
    process.stderr.write(`expert-pack-import: ${error.message}\n`)
    process.exitCode = 1
  } else {
    throw error
  }
}
