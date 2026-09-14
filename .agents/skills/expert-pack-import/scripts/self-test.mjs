#!/usr/bin/env node
/**
 * Self-test for the expert-pack-import converter. Plain Node, no
 * dependencies, no network, no workspace packages — it cannot run the real
 * expert-team catalog (mounting belongs to the core package), so it verifies
 * converter behavior and re-checks the pack contract rules the catalog
 * enforces, with an independent mini-parser, over the converter's output:
 *
 * 1. The fixtures convert byte-identically to fixtures/expected.
 * 2. The converted pack satisfies the pack contract: exact frontmatter key
 *    sets, kebab ids matching file stems, team consistency, single-line
 *    bounded name/role/goal, non-empty lowercase unique allowlists without
 *    plugin-own tools, non-blank bounded personas, exact team.yml keys,
 *    entry/depends-on consistency, existing expert references, safe artifact
 *    names, schema-less phases.
 * 3. Converting twice — and via different path spellings — produces
 *    byte-identical output.
 * 4. An existing output directory is refused without --force and regenerated
 *    with it.
 * 5. Negative fixtures: a plugin-own tool name fails the whole conversion
 *    (exit 1, nothing written); an unrecognized tool name converts with a
 *    warning, stays in the allowlist lowercased, and the resulting pack still
 *    validates.
 *
 * Usage: node self-test.mjs
 */

import { spawnSync } from 'node:child_process'
import { mkdtempSync, readdirSync, readFileSync, existsSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import process from 'node:process'

const skillRoot = resolve(fileURLToPath(new URL('..', import.meta.url)))
const convertScript = join(skillRoot, 'scripts', 'convert.mjs')
const fixturesAgents = join(skillRoot, 'fixtures', 'agents')
const fixturesExpected = join(skillRoot, 'fixtures', 'expected')
const fixturesForbidden = join(skillRoot, 'fixtures', 'negative', 'forbidden-tool')
const fixturesUnknown = join(skillRoot, 'fixtures', 'negative', 'unknown-tool')

/** Plugin-own tool names; a pack expert must never declare one. */
const FORBIDDEN_TOOLS = new Set([
  'expert_team_list',
  'expert_team_run',
  'expert_team_status',
  'expert_team_approve',
  'consult_expert',
])
const KEBAB_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

let failures = 0
let checks = 0

/** Record one check result. */
function check(name, condition, detail = '') {
  checks += 1
  if (condition) {
    process.stdout.write(`  ok   ${name}\n`)
  } else {
    failures += 1
    process.stderr.write(`  FAIL ${name}${detail === '' ? '' : `: ${detail}`}\n`)
  }
}

/** Run the converter; returns { status, stdout, stderr }. */
function runConvert(args) {
  const result = spawnSync(process.execPath, [convertScript, ...args], { encoding: 'utf8' })
  if (result.error !== undefined) throw result.error
  return { status: result.status, stdout: result.stdout ?? '', stderr: result.stderr ?? '' }
}

/** Recursively list every file of one tree as sorted forward-slash paths. */
function listTree(directory, prefix = '') {
  const out = []
  for (const entry of readdirSync(directory, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1))) {
    const relative = prefix === '' ? entry.name : `${prefix}/${entry.name}`
    if (entry.isDirectory()) out.push(...listTree(join(directory, entry.name), relative))
    else out.push(relative)
  }
  return out
}

/** Byte-compare two trees; returns a list of differences. */
function diffTrees(expectedRoot, actualRoot) {
  const diffs = []
  const expectedFiles = listTree(expectedRoot)
  const actualFiles = listTree(actualRoot)
  for (const file of expectedFiles) {
    if (!actualFiles.includes(file)) {
      diffs.push(`missing in output: ${file}`)
    } else if (!readFileSync(join(expectedRoot, file)).equals(readFileSync(join(actualRoot, file)))) {
      diffs.push(`differs from expected: ${file}`)
    }
  }
  for (const file of actualFiles) {
    if (!expectedFiles.includes(file)) diffs.push(`unexpected in output: ${file}`)
  }
  return diffs
}

// ---------------------------------------------------------------------------
// Independent mini-parser for the generated YAML shape (mappings, sequences of
// scalars, sequences of mappings, nested maps). Anything else fails the check.
// ---------------------------------------------------------------------------

/** Parse one scalar: strip quotes, keep everything else as a string. */
function miniScalar(text) {
  if (text.startsWith('"') && text.endsWith('"') && text.length >= 2) return text.slice(1, -1)
  if (text.startsWith("'") && text.endsWith("'") && text.length >= 2) return text.slice(1, -1)
  if (text.includes(' #')) return text.slice(0, text.indexOf(' #')).trim()
  return text
}

/**
 * Parse the restricted YAML shape the converter emits; generated files only —
 * anything the converter did not produce fails the check naming the file.
 */
function parseMiniYaml(text, label) {
  const lines = []
  for (const [index, raw] of text.split('\n').entries()) {
    const trimmed = raw.trim()
    if (trimmed === '' || trimmed.startsWith('#')) continue
    lines.push({ indent: raw.length - raw.trimStart().length, text: trimmed, line: index + 1 })
  }
  let position = 0

  function fail(detail) {
    throw new Error(`${label}: ${detail}`)
  }

  function parseBlock(indent) {
    const line = lines[position]
    if (line.text.startsWith('- ') || line.text === '-') return parseSequence(line.indent)
    return parseMapping(line.indent)
  }

  function parseSequence(indent) {
    const items = []
    while (position < lines.length) {
      const line = lines[position]
      if (line.indent < indent) break
      if (line.indent !== indent || !(line.text.startsWith('- ') || line.text === '-')) {
        fail(`malformed sequence at line ${line.line}: ${line.text}`)
      }
      const rest = line.text === '-' ? '' : line.text.slice(2).trim()
      position += 1
      if (rest === '') fail(`empty sequence item at line ${line.line}`)
      if (/^[A-Za-z][A-Za-z0-9_-]*:(?:[ \t].*)?$/.test(rest)) {
        // A mapping item: its first key continues on the item line.
        lines.splice(position, 0, { indent: indent + 2, text: rest, line: line.line })
        items.push(parseMapping(indent + 2))
      } else {
        items.push(miniScalar(rest))
      }
    }
    return items
  }

  function parseMapping(indent) {
    const map = {}
    while (position < lines.length) {
      const line = lines[position]
      if (line.indent < indent) break
      if (line.indent > indent) fail(`unexpected indent at line ${line.line}: ${line.text}`)
      const keyMatch = /^([A-Za-z][A-Za-z0-9_-]*):(?:[ \t]*(.*))?$/.exec(line.text)
      if (keyMatch === null) fail(`not a "key: value" line at line ${line.line}: ${line.text}`)
      const key = keyMatch[1]
      if (key in map) fail(`duplicate key ${key} at line ${line.line}`)
      const rest = (keyMatch[2] ?? '').trim()
      position += 1
      if (rest !== '') {
        map[key] = miniScalar(rest)
      } else if (position < lines.length && lines[position].indent > indent) {
        map[key] = parseBlock(lines[position].indent)
      } else {
        map[key] = ''
      }
    }
    return map
  }

  if (lines.length === 0) fail('is empty')
  return parseBlock(lines[0].indent)
}

/** Parse one generated expert md file into { meta, persona }. */
function parseExpertFile(path) {
  const contents = readFileSync(path, 'utf8')
  const lines = contents.split('\n')
  if (lines[0] !== '---') throw new Error(`${path}: missing front matter opening`)
  const close = lines.indexOf('---', 1)
  if (close === -1) throw new Error(`${path}: front matter not closed`)
  return { meta: parseMiniYaml(lines.slice(1, close).join('\n'), path), persona: lines.slice(close + 1).join('\n') }
}

/** One single-line bounded scalar check against the catalog's rules. */
function checkScalar(label, name, value, maxBytes) {
  check(`${label} ${name} is a non-empty single line`, typeof value === 'string' && value.trim() !== '' && !value.includes('\n'))
  check(`${label} ${name} fits ${maxBytes} bytes`, typeof value === 'string' && Buffer.byteLength(value, 'utf8') <= maxBytes)
}

/**
 * Validate one converted pack against the contract rules of the catalog's
 * parsers (expert-md.ts, validate.ts, team-yml.ts, catalog.ts).
 */
function validatePack(packDir) {
  const team = parseMiniYaml(readFileSync(join(packDir, 'team.yml'), 'utf8'), join(packDir, 'team.yml'))

  check('team.yml has exactly the contract keys', JSON.stringify(Object.keys(team).sort()) === JSON.stringify(['entry', 'mode', 'phases', 'team', 'title']), Object.keys(team).join(','))
  check('team id is kebab-case', typeof team.team === 'string' && KEBAB_PATTERN.test(team.team))
  check('mode is pipeline or hierarchical', team.mode === 'pipeline' || team.mode === 'hierarchical')
  checkScalar('team.yml', 'title', team.title, 256)

  const expertFiles = readdirSync(join(packDir, 'experts')).filter(name => name.endsWith('.md')).sort()
  check('experts directory is non-empty', expertFiles.length > 0)
  const expertIds = new Set()
  for (const fileName of expertFiles) {
    const label = `expert ${fileName}`
    let expert
    try {
      expert = parseExpertFile(join(packDir, 'experts', fileName))
    } catch (error) {
      check(`${label} parses`, false, error.message)
      continue
    }
    const { meta, persona } = expert
    const stem = fileName.slice(0, -3)
    check(`${label} has exactly the contract keys`, JSON.stringify(Object.keys(meta).sort()) === JSON.stringify(['goal', 'id', 'name', 'role', 'team', 'tools']), Object.keys(meta).join(','))
    check(`${label} id matches the file stem`, meta.id === stem)
    check(`${label} id is kebab-case`, KEBAB_PATTERN.test(String(meta.id)))
    check(`${label} team equals the pack team`, meta.team === team.team)
    checkScalar(label, 'name', meta.name, 128)
    checkScalar(label, 'role', meta.role, 256)
    checkScalar(label, 'goal', meta.goal, 512)
    const tools = meta.tools
    check(`${label} tools is a non-empty array (an expert with none cannot act)`, Array.isArray(tools) && tools.length > 0)
    if (Array.isArray(tools)) {
      check(`${label} has at most 32 tools`, tools.length <= 32)
      check(`${label} tool names are unique`, new Set(tools).size === tools.length)
      check(`${label} tool names are lowercase single words within 64 bytes (identity mapping)`, tools.every(tool => /^[a-z0-9_-]+$/.test(tool) && Buffer.byteLength(tool, 'utf8') <= 64))
      check(`${label} names no plugin-own tool (EXPERT_TEAM_TOOL_FORBIDDEN)`, tools.every(tool => !FORBIDDEN_TOOLS.has(tool)))
    }
    check(`${label} persona is not blank`, persona.replace(/^\n+/, '').trim() !== '')
    check(`${label} persona fits 16 KiB`, Buffer.byteLength(persona, 'utf8') <= 16 * 1024)
    expertIds.add(meta.id)
  }

  const phases = team.phases
  check('team.yml phases is a non-empty array', Array.isArray(phases) && phases.length > 0)
  if (!Array.isArray(phases)) return
  const seen = new Set()
  for (const [index, phase] of phases.entries()) {
    const label = `phase ${index} (${phase.id})`
    const keys = Object.keys(phase)
    check(`${label} has only contract keys`, keys.every(key => ['id', 'expert', 'output', 'depends_on', 'input', 'gate'].includes(key)) && ['id', 'expert', 'output'].every(key => keys.includes(key)), keys.join(','))
    check(`${label} id is kebab-case`, KEBAB_PATTERN.test(String(phase.id)))
    check(`${label} id is unique`, !seen.has(phase.id))
    seen.add(phase.id)
    check(`${label} references a defined expert`, expertIds.has(phase.expert), String(phase.expert))
    const deps = phase.depends_on ?? []
    check(`${label} depends_on references earlier phases only`, deps.every(dep => seen.has(dep)), deps.join(','))
    const artifact = phase.output?.artifact
    check(`${label} artifact is a single safe segment`, typeof artifact === 'string' && artifact !== '.' && artifact !== '..' && !/[/\\:]/.test(artifact) && !artifact.endsWith('.') && !artifact.endsWith(' '), String(artifact))
    check(`${label} is schema-less (imports generate no schemas)`, phase.output?.schema === undefined)
  }
  check('entry references a declared phase', phases.some(phase => phase.id === team.entry))
  const entry = phases.find(phase => phase.id === team.entry)
  if (entry !== undefined) {
    check('entry phase declares no depends_on', (entry.depends_on ?? []).length === 0)
  }
}

// ---------------------------------------------------------------------------
// Suites.
// ---------------------------------------------------------------------------

const scratch = mkdtempSync(join(tmpdir(), 'expert-pack-import-selftest-'))
try {
  process.stdout.write('1. golden diff: fixtures/agents converts byte-identically to fixtures/expected\n')
  const goldenOut = join(scratch, 'golden')
  const golden = runConvert([fixturesAgents, goldenOut])
  check('converter exits 0 over the fixtures', golden.status === 0, `exit ${golden.status}; stderr: ${golden.stderr}`)
  const goldenDiffs = diffTrees(fixturesExpected, goldenOut)
  check('converted output is byte-identical to fixtures/expected', goldenDiffs.length === 0, goldenDiffs.join('; '))

  process.stdout.write('2. contract validation of the converted pack\n')
  try {
    validatePack(goldenOut)
  } catch (error) {
    check('contract validation runs to completion', false, error.message)
  }

  process.stdout.write('3. idempotency and path-spelling independence\n')
  const secondOut = join(scratch, 'second')
  runConvert([fixturesAgents, secondOut])
  const repeatDiffs = diffTrees(goldenOut, secondOut)
  check('two conversions are byte-identical', repeatDiffs.length === 0, repeatDiffs.join('; '))
  const spellingOut = join(scratch, 'spelling')
  runConvert([join(fixturesAgents), spellingOut])
  const spellingDiffs = diffTrees(goldenOut, spellingOut)
  check('absolute and relative source paths convert identically', spellingDiffs.length === 0, spellingDiffs.join('; '))

  process.stdout.write('4. overwrite refusal and --force regeneration\n')
  const refused = runConvert([fixturesAgents, goldenOut])
  check('existing output directory is refused without --force', refused.status === 1 && /already exists/.test(refused.stderr), `exit ${refused.status}`)
  check('the refused run changed nothing', diffTrees(fixturesExpected, goldenOut).length === 0)
  const forced = runConvert([fixturesAgents, goldenOut, '--force'])
  check('--force regenerates the pack byte-identically', forced.status === 0 && diffTrees(fixturesExpected, goldenOut).length === 0)

  process.stdout.write('5. negative fixtures\n')
  const forbiddenOut = join(scratch, 'forbidden')
  const forbidden = runConvert([fixturesForbidden, forbiddenOut])
  check('a plugin-own tool fails the conversion (exit 1)', forbidden.status === 1, `exit ${forbidden.status}`)
  check('the failure names the tool and the catalog code', /expert_team_list/.test(forbidden.stderr) && /EXPERT_TEAM_TOOL_FORBIDDEN/.test(forbidden.stderr), forbidden.stderr.slice(0, 200))
  check('a failed conversion writes no output directory', !existsSync(forbiddenOut))

  const unknownOut = join(scratch, 'unknown')
  const unknown = runConvert([fixturesUnknown, unknownOut])
  check('an unrecognized tool converts with exit 0', unknown.status === 0, `exit ${unknown.status}; stderr: ${unknown.stderr}`)
  check('the unrecognized tool is warned about', /Foo_Bar99/.test(unknown.stderr) && /EXPERT_TEAM_TOOL_MISSING/.test(unknown.stderr), unknown.stderr.slice(0, 300))
  const unknownExpert = readFileSync(join(unknownOut, 'experts', 'unknown-tool-checker.md'), 'utf8')
  check('the unrecognized tool stays in the allowlist, lowercased', /^  - foo_bar99$/m.test(unknownExpert))
  try {
    validatePack(unknownOut)
  } catch (error) {
    check('the unknown-tool pack validates', false, error.message)
  }

  process.stdout.write(`\n${checks} checks, ${failures} failure(s)\n`)
  process.exitCode = failures === 0 ? 0 : 1
} finally {
  rmSync(scratch, { recursive: true, force: true })
}
