/**
 * S3 — cwd resolution and recording of a real task run (design §2 S3).
 *
 * Mechanism A: one real headless run in a dedicated temp cwd whose directory
 * name carries a recognizable uuid. The session log's first record (the
 * header) must record that cwd; the mapping between the encoded session
 * directory under `$DSH_HOME/sessions/` and the cwd is recorded alongside.
 * Paths compare equal after realpath + case normalization (Windows).
 *
 * CLI: `node --import tsx/esm s3-cwd.mjs --tree <worktree> --out <dir>`
 * @module harness/s3-cwd
 */

import { mkdirSync, realpathSync } from 'node:fs'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { isolatedRoot, launchHeadless, parseCliArgs } from './helpers/launch.mjs'
import { findSessionLogs, readSessionLog } from './helpers/logread.mjs'
import {
  assembleVerdict,
  check,
  evidencePath,
  exitCodeForVerdict,
  recordHarnessError,
  writeJsonOut,
  writeTextOut,
  writeVerdict,
} from './helpers/evidence.mjs'

const USAGE = 'usage: node --import tsx/esm s3-cwd.mjs --tree <worktree> --out <dir>'
const TASK = 'reply with the single word ok'

/**
 * Normalize a path for equality: realpath + lowercase on case-insensitive
 * platforms (the same comparison shape the product's own `samePath` uses).
 * @param {string} path - the path to normalize.
 * @returns {string} the normalized absolute path.
 */
function normalizePath(path) {
  const real = realpathSync(path)
  return process.platform === 'win32' ? real.toLowerCase() : real
}

/**
 * Run the S3 scenario.
 * @param {string} tree - the launched worktree.
 * @param {string} outDir - the `--out` evidence directory.
 * @returns {Promise<number>} the process exit code (design contract).
 */
async function run(tree, outDir) {
  const root = isolatedRoot('s3')
  const dshHome = join(root, 'dsh-home')
  // Recognizable uuid right in the directory name.
  const cwd = join(root, `cwd-accept-${randomUUID()}`)
  mkdirSync(cwd, { recursive: true })

  const runRecord = await launchHeadless({ tree, task: TASK, dshHome, cwd, timeoutMs: 120_000 })
  const stderrPath = await writeTextOut(outDir, 's3/stderr.txt', runRecord.stderr)
  await writeTextOut(outDir, 's3/stdout.txt', runRecord.stdout)
  await writeTextOut(outDir, 's3/exitcode.txt', `${String(runRecord.exitCode)}\n`)

  const logs = findSessionLogs(join(dshHome, 'sessions'))
  let header = undefined
  let logReadError = undefined
  if (logs.length === 1) {
    try {
      header = readSessionLog(logs[0].logPath).header
    } catch (error) {
      logReadError = error instanceof Error ? error.message : String(error)
    }
  }
  const headerPath = await writeJsonOut(outDir, 's3/header.json', {
    header,
    ...(logReadError !== undefined ? { logReadError } : {}),
    sessionLogs: logs.map(log => log.logPath),
  })

  const sessionPathText = logs.length === 1
    ? `${logs[0].sessionDir}\n${logs[0].logPath}\ncwd: ${cwd}\n`
    : `${logs.map(log => log.sessionDir).join('\n') || '<none>'}\ncwd: ${cwd}\n`
  const sessionPathFile = await writeTextOut(outDir, 's3/session-path.txt', sessionPathText)

  const normalizedSpawnCwd = normalizePath(cwd)
  const observedHeaderCwd = header?.cwd
  const normalizedHeaderCwd = observedHeaderCwd !== undefined && typeof observedHeaderCwd === 'string'
    ? normalizePath(observedHeaderCwd)
    : undefined

  const checks = [
    check({
      id: 's3-header-cwd-equals-spawn-cwd',
      expectation: 'session header cwd equals the spawn cwd after realpath + case normalization',
      pass: normalizedHeaderCwd !== undefined && normalizedHeaderCwd === normalizedSpawnCwd,
      observed: {
        spawnCwd: cwd,
        spawnCwdNormalized: normalizedSpawnCwd,
        headerCwd: observedHeaderCwd,
        headerCwdNormalized: normalizedHeaderCwd,
      },
      evidence: evidencePath(outDir, headerPath),
    }),
    check({
      id: 's3-session-dir-maps-to-cwd',
      expectation: 'exactly one session directory under $DSH_HOME/sessions/ corresponds to the run cwd',
      pass: logs.length === 1 && logReadError === undefined,
      observed: { sessionLogCount: logs.length, sessionDirs: logs.map(log => log.sessionDir) },
      evidence: evidencePath(outDir, sessionPathFile),
    }),
  ]

  const verdict = assembleVerdict({
    scenario: 's3-cwd',
    checks,
    notes: [
      'headless runner 以 meta.cwd = process.cwd() 建 session（findings §4），header.cwd 即 JSONL 首记录的 cwd 字段',
      '本次运行同样以 keyless 结束（exit 非 0），S3 判据只针对 header cwd 的解析与记录，不以退出码为判据（design §2 S3）',
      'stdout.txt / stderr.txt / exitcode.txt 为附加证据（design 产物行之外）',
    ],
  })
  await writeVerdict(outDir, verdict)
  return exitCodeForVerdict(verdict)
}

const parsed = parseCliArgs(process.argv.slice(2), { tree: { required: true }, out: { required: true } }, USAGE)
process.exit(await run(parsed.tree, parsed.out).catch(error => recordHarnessError(parsed.out, 's3-cwd', error)))
