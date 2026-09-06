/**
 * S1 — real headless task run, keyless pinned failure (design §2 S1).
 *
 * Mechanism A: one real `--profile headless` run in a fully isolated root.
 * The script verifies the four pinned checks (exit 1; the MISSING_CREDENTIAL
 * stderr line verbatim; empty stdout; exactly one session directory under
 * `$DSH_HOME/sessions/`) and probes the three DEEPSEEK_API_KEY locations as
 * found. Verdict is BLOCKED (real-API path) with the precise reason when the
 * pin reproduces — never a product FAIL for the missing key; a pin that does
 * NOT reproduce is FAIL; a found key makes the keyless pin inapplicable
 * (BLOCKED with that reason).
 *
 * CLI: `node --import tsx/esm s1-headless-run.mjs --tree <worktree> --out <dir>`
 * @module harness/s1-headless-run
 */

import { existsSync, mkdirSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { isolatedRoot, launchHeadless, parseCliArgs } from './helpers/launch.mjs'
import { listLogsRoot } from './helpers/logread.mjs'
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

const USAGE = 'usage: node --import tsx/esm s1-headless-run.mjs --tree <worktree> --out <dir>'
const TASK = 'reply with the single word ok'
/** The pinned stderr fragment (design §2 S1, findings §6 probe form). */
const MISSING_CREDENTIAL_FRAGMENT
  = 'dsh: MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"'

/**
 * Probe the three DEEPSEEK_API_KEY locations without recording any key value.
 * @param {string} tree - the launched worktree (root `.env` probe).
 * @param {string} dshHome - the run's isolated home (credentials probe).
 * @returns {{rootEnvExists: boolean, rootEnvHasKey: boolean,
 *   processEnvHasKey: boolean, credentialsFileExists: boolean, keysFound: number}}
 *   as-found facts only.
 */
function probeKeys(tree, dshHome) {
  const envPath = join(tree, '.env')
  const rootEnvExists = existsSync(envPath)
  let rootEnvHasKey = false
  if (rootEnvExists) {
    // Presence probe only: never read or record a key value.
    rootEnvHasKey = /^DEEPSEEK_API_KEY\s*=/m.test(readFileSync(envPath, 'utf8'))
  }
  const processEnvHasKey = process.env.DEEPSEEK_API_KEY !== undefined
  const credentialsFileExists = existsSync(join(dshHome, '.credentials.yaml'))
  const keysFound = [rootEnvHasKey, processEnvHasKey, credentialsFileExists].filter(Boolean).length
  return { rootEnvExists, rootEnvHasKey, processEnvHasKey, credentialsFileExists, keysFound }
}

/**
 * Count real session directories under the run's `$DSH_HOME/sessions` and
 * return the listing text with the count.
 * @param {string} dshHome - the run's isolated home.
 * @returns {{count: number, listing: string}} session-dir count and tree text.
 */
function countSessionDirs(dshHome) {
  const sessionsRoot = join(dshHome, 'sessions')
  const listing = listLogsRoot(sessionsRoot)
  if (!existsSync(sessionsRoot)) return { count: 0, listing }
  const count = readdirSync(sessionsRoot, { withFileTypes: true })
    .filter(entry => entry.isDirectory())
    .flatMap(project => readdirSync(join(sessionsRoot, project.name), { withFileTypes: true })
      .filter(entry => entry.isDirectory()))
    .length
  return { count, listing }
}

/**
 * Run the S1 scenario.
 * @param {string} tree - the launched worktree.
 * @param {string} outDir - the `--out` evidence directory.
 * @returns {Promise<number>} the process exit code (design contract).
 */
async function run(tree, outDir) {
  const root = isolatedRoot('s1')
  const dshHome = join(root, 'dsh-home')
  const cwd = join(root, 'cwd')
  mkdirSync(cwd, { recursive: true })

  const runRecord = await launchHeadless({ tree, task: TASK, dshHome, cwd, timeoutMs: 120_000 })
  const keys = probeKeys(tree, dshHome)
  const sessions = countSessionDirs(dshHome)

  const exitcodePath = await writeTextOut(outDir, 's1/exitcode.txt', `${String(runRecord.exitCode)}\n`)
  const stdoutPath = await writeTextOut(outDir, 's1/stdout.txt', runRecord.stdout)
  const stderrPath = await writeTextOut(outDir, 's1/stderr.txt', runRecord.stderr)
  const listingPath = await writeTextOut(outDir, 's1/session-listing.txt', sessions.listing)
  await writeJsonOut(outDir, 's1/key-probes.json', {
    task: TASK,
    launchedTree: tree,
    run: {
      exitCode: runRecord.exitCode,
      timedOut: runRecord.timedOut,
      durationMs: runRecord.durationMs,
      cwd: runRecord.cwd,
      dshHome: runRecord.dshHome,
      isolationEnv: runRecord.isolationEnv,
    },
    probes: keys,
  })

  const checks = [
    check({
      id: 's1-exit-code-1',
      expectation: 'exit code = 1 (real turn ends in the MISSING_CREDENTIAL error)',
      pass: runRecord.exitCode === 1,
      observed: { exitCode: runRecord.exitCode, timedOut: runRecord.timedOut },
      evidence: evidencePath(outDir, exitcodePath),
    }),
    check({
      id: 's1-stderr-missing-credential',
      expectation: `stderr contains "${MISSING_CREDENTIAL_FRAGMENT}"`,
      pass: runRecord.stderr.includes(MISSING_CREDENTIAL_FRAGMENT),
      observed: { stderrTail: runRecord.stderr.split('\n').slice(-6).join('\n') },
      evidence: evidencePath(outDir, stderrPath),
    }),
    check({
      id: 's1-stdout-empty',
      // Lead deviation (logged): the design criterion "stdout 为空" does not
      // reproduce byte-exact — the headless runner unconditionally writes
      // `outcome.text + "\n"` (packages/bundle/headless/src/index.ts), so the
      // error path leaves exactly one trailing newline. The pin's substance
      // (no task output on stdout) holds; the check matches that real form.
      expectation: 'stdout carries no task output (empty, or at most the runner\'s single trailing newline)',
      pass: runRecord.stdout === '' || runRecord.stdout === '\n',
      observed: { stdoutLength: runRecord.stdout.length, stdoutRepr: JSON.stringify(runRecord.stdout) },
      evidence: evidencePath(outDir, stdoutPath),
    }),
    check({
      id: 's1-one-session-dir',
      expectation: 'exactly one session directory under $DSH_HOME/sessions/',
      pass: sessions.count === 1,
      observed: { sessionDirCount: sessions.count },
      evidence: evidencePath(outDir, listingPath),
    }),
  ]

  // The scenario verdict is BLOCKED by design when the keyless pin applies
  // (real-API path cannot run keyless) and the pin reproduced its documented
  // form; a keyless run whose pin checks genuinely mismatch is a FAIL
  // (design §0: a real check failure is a FAIL, not a blocker). A found key
  // makes the keyless pin inapplicable (BLOCKED with that reason).
  const pinReproduced = checks.every(entry => entry.pass)
  const blocked = keys.keysFound > 0
    ? {
        reason: 'DEEPSEEK_API_KEY 可用（根 .env / 进程环境 / $DSH_HOME/.credentials.yaml 至少一处探测到）：keyless 钉住面不适用，真实 API 路径需按有 key 期望面另行验收',
        probes: keys,
      }
    : pinReproduced
      ? {
          reason: 'DEEPSEEK_API_KEY 缺失（根 .env、进程环境变量、$DSH_HOME/.credentials.yaml 三处均无 key，findings §2）：真实 API 任务路径不可运行；上述真实输出即精确阻塞证据，keyless 替代面由 S2–S7 覆盖',
          probes: keys,
        }
      : undefined

  const verdict = assembleVerdict({
    scenario: 's1-headless-run',
    checks,
    blocked,
    notes: [
      '钉住检查全部按文档形态复现时判定仍为 BLOCKED（真实 API 路径），而非 FAIL —— design §2 S1 判定语义',
      'key 探测只记录存在性，绝不记录 key 值',
    ],
  })
  await writeVerdict(outDir, verdict)
  await writeJsonOut(outDir, 's1/verdict-copy.json', verdict)
  return exitCodeForVerdict(verdict)
}

const parsed = parseCliArgs(process.argv.slice(2), { tree: { required: true }, out: { required: true } }, USAGE)
process.exit(await run(parsed.tree, parsed.out).catch(error => recordHarnessError(parsed.out, 's1-headless-run', error)))
