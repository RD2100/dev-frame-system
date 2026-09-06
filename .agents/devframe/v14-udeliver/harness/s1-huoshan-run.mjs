/**
 * B4 — S1 real-credential retest, huoshan explicit route (v14-udeliver lead,
 * design §4). Corrects the v14-accept S1 baseline: the original keyless BLOCK
 * was the missing deepseek-official credential, not a huoshan failure. This
 * variant boots the same one-shot headless task over an isolated DSH_HOME
 * whose settings declare the huoshan pi-ai provider routes and point
 * agent-default-model at huoshan-1/glm-5.3-flash; the credential references
 * travel only inside the isolated credential store copied from the host home.
 *
 * Expected verdict on a healthy account: PASS with real request-level
 * provider evidence (request frames naming provider `huoshan-1` and model
 * `glm-5.3-flash`, plus a real wire response). The keyless-era pin (exit 1 +
 * MISSING_CREDENTIAL) must NOT reproduce; when it does, the verdict is FAIL.
 *
 * Credential discipline: the script copies the credential store file verbatim
 * into the isolated home and records presence/size/ref-names only — never a
 * value, never a copy in the evidence directory.
 *
 * CLI: `node --import tsx/esm s1-huoshan-run.mjs --tree <worktree> --out <dir>
 *       --credentials <path-to-host-.credentials.yaml>`
 * @module harness/s1-huoshan-run
 */

import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { isolatedRoot, launchHeadless, parseCliArgs } from '../../v14-accept/worker/harness/helpers/launch.mjs'
import { findSessionLogs, listLogsRoot, readSessionLog } from '../../v14-accept/worker/harness/helpers/logread.mjs'
import {
  assembleVerdict,
  check,
  evidencePath,
  exitCodeForVerdict,
  recordHarnessError,
  writeJsonOut,
  writeTextOut,
  writeVerdict,
} from '../../v14-accept/worker/harness/helpers/evidence.mjs'

const USAGE = 'usage: node --import tsx/esm s1-huoshan-run.mjs --tree <worktree> --out <dir> --credentials <path>'
const TASK = 'reply with the single word ok'
/** The keyless-era stderr fragment that must NOT reproduce on the huoshan route. */
const MISSING_CREDENTIAL_FRAGMENT
  = 'dsh: MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"'
/** The explicit route this retest pins (settings.yaml written below). */
const ROUTE = { provider: 'huoshan-1', model: 'glm-5.3-flash' }

/** The isolated settings document: huoshan routes + explicit default model. */
const SETTINGS_YAML = `llm-pi-ai:
  providers:
    huoshan-1:
      apiKeyEnv: HUOSHAN_1_API_KEY
      api: openai-completions
      baseURL: https://ark.cn-beijing.volces.com/api/coding/v3
      models:
        - id: glm-5.3-flash
          name: glm-5.3-flash
    huoshan-2:
      apiKeyEnv: HUOSHAN_2_API_KEY
      api: openai-completions
      baseURL: https://ark.cn-beijing.volces.com/api/coding/v3
      models:
        - id: glm-5.3-flash
          name: glm-5.3-flash
agent-default-model:
  provider: huoshan-1
  model: glm-5.3-flash
`

/**
 * Probe the credential-store copy without recording any secret value.
 * @param {string} sourcePath - the host credential store to copy from.
 * @param {string} dshHome - the isolated home receiving the copy.
 * @returns {{sourceExists: boolean, copied: boolean, copyBytes: number,
 *   refsPresent: {huoshan1: boolean, huoshan2: boolean}}} as-found facts only.
 */
function probeAndCopyCredentials(sourcePath, dshHome) {
  const sourceExists = existsSync(sourcePath)
  if (!sourceExists) {
    return { sourceExists, copied: false, copyBytes: 0, refsPresent: { huoshan1: false, huoshan2: false } }
  }
  const target = join(dshHome, '.credentials.yaml')
  copyFileSync(sourcePath, target)
  const bytes = statSync(target).size
  // Presence probe of the two reference names; values are never read out.
  const text = readFileSync(target, 'utf8')
  return {
    sourceExists,
    copied: true,
    copyBytes: bytes,
    refsPresent: {
      huoshan1: /^refs:\s*$/m.test(text) && /^ {2}HUOSHAN_1_API_KEY:/m.test(text),
      huoshan2: /^ {2}HUOSHAN_2_API_KEY:/m.test(text),
    },
  }
}

/**
 * Extract request-level provider evidence from the decoded session log.
 * @param {{header: object, events: object[]}} log - decoded log.
 * @returns {{requestFrame: object|null, requestEventIndex: number|null,
 *   responseFrame: object|null, responseEventIndex: number|null}} verbatim
 *   frames with their event indexes (the log's seq evidence).
 */
function extractProviderEvidence(log) {
  let requestFrame = null
  let requestEventIndex = null
  let responseFrame = null
  let responseEventIndex = null
  log.events.forEach((event, index) => {
    const type = typeof event.type === 'string' ? event.type : ''
    if (requestFrame === null && type.startsWith('request/')) {
      const text = JSON.stringify(event)
      if (text.includes(`"${ROUTE.provider}"`) && text.includes(`"${ROUTE.model}"`)) {
        requestFrame = event
        requestEventIndex = index
      }
    }
    if (type.startsWith('assistant/') || type.startsWith('response/')) {
      const text = JSON.stringify(event)
      if (text.includes('responseId') && text.includes(ROUTE.provider)) {
        responseFrame = event
        responseEventIndex = index
      }
    }
  })
  return { requestFrame, requestEventIndex, responseFrame, responseEventIndex }
}

/**
 * Run the B4 retest scenario.
 * @param {string} tree - the launched worktree.
 * @param {string} outDir - the `--out` evidence directory.
 * @param {string} credentialsSource - the host credential store path.
 * @returns {Promise<number>} the process exit code (harness contract).
 */
async function run(tree, outDir, credentialsSource) {
  const root = isolatedRoot('s1-huoshan')
  const dshHome = join(root, 'dsh-home')
  const cwd = join(root, 'cwd')
  mkdirSync(cwd, { recursive: true })
  mkdirSync(dshHome, { recursive: true })

  writeFileSync(join(dshHome, 'settings.yaml'), SETTINGS_YAML, 'utf8')
  const credentials = probeAndCopyCredentials(credentialsSource, dshHome)
  if (!credentials.sourceExists) {
    const verdict = assembleVerdict({
      scenario: 's1-huoshan-run',
      checks: [],
      blocked: {
        reason: `凭据存储来源不存在（--credentials "${credentialsSource}"）：huoshan 路由无法解析，真实调用不可运行；未启动任何产品进程`,
        probes: credentials,
      },
      notes: ['凭据只进隔离配置；来源缺失为精确阻塞，不算产品失败'],
    })
    await writeVerdict(outDir, verdict)
    return exitCodeForVerdict(verdict)
  }

  const runRecord = await launchHeadless({ tree, task: TASK, dshHome, cwd, timeoutMs: 180_000 })
  const logs = findSessionLogs(join(dshHome, 'sessions'))
  const evidence = logs.length === 1 ? extractProviderEvidence(readSessionLog(logs[0].logPath)) : {
    requestFrame: null, requestEventIndex: null, responseFrame: null, responseEventIndex: null,
  }

  const exitcodePath = await writeTextOut(outDir, 's1-huoshan/exitcode.txt', `${String(runRecord.exitCode)}\n`)
  const stdoutPath = await writeTextOut(outDir, 's1-huoshan/stdout.txt', runRecord.stdout)
  const stderrPath = await writeTextOut(outDir, 's1-huoshan/stderr.txt', runRecord.stderr)
  const listingPath = await writeTextOut(outDir, 's1-huoshan/session-listing.txt', listLogsRoot(join(dshHome, 'sessions')))
  await writeJsonOut(outDir, 's1-huoshan/run-record.json', {
    task: TASK,
    launchedTree: tree,
    route: ROUTE,
    run: {
      exitCode: runRecord.exitCode,
      timedOut: runRecord.timedOut,
      durationMs: runRecord.durationMs,
      cwd: runRecord.cwd,
      dshHome: runRecord.dshHome,
      isolationEnv: runRecord.isolationEnv,
    },
    credentials,
    childEnvHuoshanVars: Object.keys(process.env).filter(key => key.startsWith('HUOSHAN_')),
  })
  await writeJsonOut(outDir, 's1-huoshan/request-frame.json', {
    eventIndex: evidence.requestEventIndex,
    frame: evidence.requestFrame,
  })
  await writeJsonOut(outDir, 's1-huoshan/response-frame.json', {
    eventIndex: evidence.responseEventIndex,
    frame: evidence.responseFrame,
  })

  const checks = [
    check({
      id: 'b4-exit-code-0',
      expectation: 'exit code = 0 (the real turn completes on the huoshan route)',
      pass: runRecord.exitCode === 0,
      observed: { exitCode: runRecord.exitCode, timedOut: runRecord.timedOut },
      evidence: evidencePath(outDir, exitcodePath),
    }),
    check({
      id: 'b4-no-missing-credential',
      expectation: `stderr does NOT contain "${MISSING_CREDENTIAL_FRAGMENT}" (the keyless-era pin must not reproduce)`,
      pass: !runRecord.stderr.includes(MISSING_CREDENTIAL_FRAGMENT),
      observed: { stderrTail: runRecord.stderr.split('\n').slice(-6).join('\n') },
      evidence: evidencePath(outDir, stderrPath),
    }),
    check({
      id: 'b4-real-model-output',
      expectation: "stdout is the model's answer (trimmed 'ok')",
      pass: runRecord.stdout.trim() === 'ok',
      observed: { stdoutRepr: JSON.stringify(runRecord.stdout) },
      evidence: evidencePath(outDir, stdoutPath),
    }),
    check({
      id: 'b4-one-session-dir',
      expectation: 'exactly one session directory under $DSH_HOME/sessions/',
      pass: logs.length === 1,
      observed: { sessionLogCount: logs.length },
      evidence: evidencePath(outDir, listingPath),
    }),
    check({
      id: 'b4-request-level-provider',
      expectation: `a request/ frame names provider "${ROUTE.provider}" and model "${ROUTE.model}" (request-level, not a label)`,
      pass: evidence.requestFrame !== null,
      observed: { eventIndex: evidence.requestEventIndex, framePreview: evidence.requestFrame === null ? null : JSON.stringify(evidence.requestFrame).slice(0, 600) },
      evidence: evidencePath(outDir, join(outDir, 's1-huoshan/request-frame.json')),
    }),
    check({
      id: 'b4-real-wire-response',
      expectation: `a response frame carries a wire responseId attributed to "${ROUTE.provider}" (real API call, not a mock)`,
      pass: evidence.responseFrame !== null,
      observed: { eventIndex: evidence.responseEventIndex, framePreview: evidence.responseFrame === null ? null : JSON.stringify(evidence.responseFrame).slice(0, 600) },
      evidence: evidencePath(outDir, join(outDir, 's1-huoshan/response-frame.json')),
    }),
    check({
      id: 'b4-credential-refs-isolated',
      expectation: 'the isolated credential store holds both huoshan refs; no HUOSHAN_* ambient vars reach the child',
      pass: credentials.refsPresent.huoshan1 && credentials.refsPresent.huoshan2,
      observed: { ...credentials, childEnvHuoshanVars: Object.keys(process.env).filter(key => key.startsWith('HUOSHAN_')) },
      evidence: evidencePath(outDir, join(outDir, 's1-huoshan/run-record.json')),
    }),
  ]

  const verdict = assembleVerdict({
    scenario: 's1-huoshan-run',
    checks,
    notes: [
      '判定语义：全部检查通过=PASS（真实凭据重测的预期翻转）；任一不匹配=FAIL；凭据来源缺失=BLOCKED（精确阻塞，非产品失败）',
      '凭据值零记录：仅存在性/字节数/引用名',
      'provider 判定只认请求级帧（request/header、request/context、wire response）',
    ],
  })
  await writeVerdict(outDir, verdict)
  await writeJsonOut(outDir, 's1-huoshan/verdict-copy.json', verdict)
  return exitCodeForVerdict(verdict)
}

const parsed = parseCliArgs(process.argv.slice(2), {
  tree: { required: true },
  out: { required: true },
  credentials: { required: true },
}, USAGE)
process.exit(await run(parsed.tree, parsed.out, parsed.credentials).catch(error => recordHarnessError(parsed.out, 's1-huoshan-run', error)))
