/** Candidate full-chain harness stage 1: the real source CLI boots the
 *  candidate stack (example overlay + DevFrame profile + the loop-closure
 *  fixture overlay) on an isolated home and an OS-assigned port, every
 *  candidate row mounts active through the real --patch, and a controlled
 *  stop followed by a second boot on the SAME home proves the restart face.
 *  Zero model calls: the isolated home carries no credentials and no session
 *  starts. Turn-driving and the real-model round are the next stage; this
 *  file pins the deployment and restart mechanics they will ride.
 */

import type { ChildProcess } from 'node:child_process'
import { spawn } from 'node:child_process'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { mkdir, mkdtemp, readFile, readdir, rename, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { randomUUID } from 'node:crypto'
import { join } from 'node:path'
import { createRequire } from 'node:module'
import { request as httpRequest } from 'node:http'
import { pathToFileURL, fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { load as yamlLoad } from 'js-yaml'
import { startWireReplayServer } from './fixtures/wire-replay-server.ts'
import { approvedChecksFor, expectedDigests, FileRequiredChecksConfigStore, prepareCandidateScenario, writeDigestPatch, writeScenarioFile } from './fixtures/candidate-host.ts'

const REPO_ROOT = fileURLToPath(new URL('../../../..', import.meta.url))
const DSH_SOURCE_BIN = join(REPO_ROOT, 'apps/cli/src/bin.ts')
const TSX_LOADER = pathToFileURL(createRequire(join(REPO_ROOT, 'package.json')).resolve('tsx')).href
const EXAMPLE_OVERLAY = join(REPO_ROOT, 'apps/cli/config/examples/cordis/cordis.yml')
const DEVFRAME_PATCH = join(REPO_ROOT, 'packages/experimental/devframe-profile/cordis.patch.yml')
const CANDIDATE_OVERLAY = fileURLToPath(new URL('./fixtures/candidate-fullchain.overlay.yml', import.meta.url))

/** Every row the three patches must mount active for the candidate chain. */
const CANDIDATE_ROWS = [
  '@deepseek-ai/dsh-tool-cordis',
  '@deepseek-ai/dsh-experimental-session-identity',
  '@deepseek-ai/dsh-experimental-shadow-router',
  '@deepseek-ai/dsh-experimental-project-memory',
  '@deepseek-ai/dsh-experimental-command-goal-binding',
  '@deepseek-ai/dsh-experimental-agent-hierarchy',
  '@deepseek-ai/dsh-experimental-agent-dispatch',
  '@deepseek-ai/dsh-experimental-project-controller',
  '@deepseek-ai/dsh-experimental-devframe/lead-role-landing',
  '@deepseek-ai/dsh-experimental-project-controller/task-consumer',
  '@deepseek-ai/dsh-experimental-project-controller/delivery-consumer',
  '@deepseek-ai/dsh-experimental-project-controller/consumer',
]

interface RunningWeb {
  readonly child: ChildProcess
  readonly pid: number
  readonly launchUrl: string
  readonly output: () => string
}

interface HttpResult {
  readonly status: number
  readonly body: string
}

type JournalEvent = { type?: string; time?: number; data?: Record<string, unknown> }

/** The repository zstd reader: every structurally complete frame decodes. */
const { scanZstdFrames, createZstdFrameDecoder } = await import('../../../session/session-persistence-jsonl/src/zstd.ts')

/** Decode one session log: multi-frame zstd, full plaintext. */
async function decodeSessionLog(path: string): Promise<string> {
  const buffer = await readFile(path)
  const decoder = createZstdFrameDecoder()
  try {
    let plaintext = ''
    for (const frame of decoder.decode(buffer, scanZstdFrames(buffer).frames)) {
      plaintext += Buffer.from(frame).toString('utf8')
    }
    return plaintext
  } finally {
    decoder.close()
  }
}

/** Parse a session log event by event; torn tail lines are skipped. */
function parseLogEvents(text: string): JournalEvent[] {
  return text.split('\n').flatMap((line) => {
    try {
      return [JSON.parse(line) as JournalEvent]
    } catch {
      return []
    }
  })
}

/** Every session log under the isolated home, by path. */
function sessionLogPaths(dshHome: string): string[] {
  const root = join(dshHome, 'sessions')
  // The log root materializes with the first persisted session.
  if (!existsSync(root)) return []
  return readdirSync(root, { withFileTypes: true, recursive: true })
    .filter(entry => entry.isFile() && entry.name === 'session.jsonl.zstd')
    .map(entry => join((entry as unknown as { parentPath: string }).parentPath, entry.name))
}

/** Decode every session log under the isolated home. */
async function decodeSessionLogs(dshHome: string): Promise<{ path: string; text: string }[]> {
  const decoded: { path: string; text: string }[] = []
  for (const path of sessionLogPaths(dshHome)) decoded.push({ path, text: await decodeSessionLog(path) })
  return decoded
}

/**
 * The goal-binding capability evidence the coordinator's ruling requires:
 * the controller session log lands the binding record folded at
 * `admission_open` — runtime proof the composition bound the goal, not a
 * static deployment row.
 * @param events - The parsed controller session events.
 * @param what - The test leg the evidence belongs to, for the message.
 */
function assertGoalBindingAdmissionOpen(events: JournalEvent[], what: string): void {
  const bindings = events.filter(event => event.type === 'devframe/goal-binding')
  expect(bindings.length, `goal-binding records for ${what}`).toBeGreaterThanOrEqual(1)
  for (const binding of bindings) {
    const data = binding.data as { lifecycle?: string; goalId?: string }
    expect(data.goalId, `goal id in ${what}`).toBeTruthy()
    expect(data.lifecycle, `goal-binding lifecycle in ${what}`).toBe('admission_open')
  }
}

function redact(output: string): string {
  return output.replace(/([?&]token=)[^\s)]+/gu, '$1<redacted>')
}

function cleanEnvironment(root: string, dshHome: string, extra: NodeJS.ProcessEnv = {}): NodeJS.ProcessEnv {
  const env = Object.fromEntries(Object.entries(process.env).filter(([name]) =>
    !/(?:KEY|SECRET|TOKEN|PASSWORD)/iu.test(name)))
  return {
    ...env,
    DSH_AGENTS_HOME: join(root, '.agents'),
    DSH_HOME: dshHome,
    DSH_CANDIDATE_HOME: dshHome,
    DSH_TELEMETRY_DISABLED: '1',
    NODE_NO_WARNINGS: '1',
    SSH_CONNECTION: '',
    SSH_TTY: '',
    TSX_TSCONFIG_PATH: join(REPO_ROOT, 'tsconfig.json'),
    ...extra,
  }
}

/** Start the real source CLI with all patches and await readiness. */
async function startCandidateWeb(
  root: string,
  dshHome: string,
  extraEnv: NodeJS.ProcessEnv = {},
  digestPatchPath?: string,
): Promise<RunningWeb> {
  // A source-run CLI writes loader entry wrappers into the profile directory
  // under the temporary home; imports from that directory resolve workspace
  // packages only when the profile carries the production node_modules
  // layout. Mirror it with a junction to the repository's installed
  // workspace so loader-generated imports behave like the shipped app.
  const profileDir = join(dshHome, '.dsh', 'profiles', 'web')
  await mkdir(profileDir, { recursive: true })
  await symlink(join(REPO_ROOT, 'node_modules'), join(profileDir, 'node_modules'), 'junction').catch((error: NodeJS.ErrnoException) => {
    if (error.code !== 'EEXIST') throw error
  })
  const patches = [EXAMPLE_OVERLAY, DEVFRAME_PATCH, CANDIDATE_OVERLAY]
  // The generated digest patch is the last sibling: the deployment's
  // requiredChecksByTask must pin what the shared ledger actually holds,
  // and the file lives in the home so a restarted CLI re-reads it.
  if (digestPatchPath !== undefined) patches.push(digestPatchPath)
  const child = spawn(process.execPath, [
    '--import', TSX_LOADER,
    DSH_SOURCE_BIN,
    '--profile', 'web',
    ...patches.flatMap(patch => ['--patch', patch]),
    '--no-open',
  ], {
    cwd: REPO_ROOT,
    env: cleanEnvironment(root, dshHome, extraEnv),
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  const pid = child.pid ?? -1
  let output = ''
  const launchUrl = await new Promise<string>((resolve, reject) => {
    let settled = false
    const fail = (error: Error): void => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      reject(error)
    }
    const timer = setTimeout(() => {
      fail(new Error(`candidate dsh web did not become ready:\n${redact(output)}`))
    }, 120_000)
    const append = (chunk: Buffer | string): void => {
      output = `${output}${String(chunk)}`.slice(-100_000)
      const match = /dsh web: (http:\/\/[^\s]+)/u.exec(output)
      if (settled || match?.[1] === undefined) return
      settled = true
      clearTimeout(timer)
      resolve(match[1])
    }
    child.stdout?.on('data', append)
    child.stderr?.on('data', append)
    child.once('error', (error) => {
      fail(error)
    })
    child.once('exit', (code) => {
      fail(new Error(`candidate dsh web exited before readiness (${String(code)}):\n${redact(output)}`))
    })
  })
  return { child, pid, launchUrl, output: () => output }
}

/** Controlled teardown: SIGTERM, then SIGKILL after a bounded grace. */
async function stopCandidateWeb(running: RunningWeb): Promise<{ exitCode: number | null; signal: NodeJS.Signals | null }> {
  if (running.child.exitCode !== null) {
    return { exitCode: running.child.exitCode, signal: running.child.signalCode }
  }
  const exited = new Promise<{ exitCode: number | null; signal: NodeJS.Signals | null }>((resolve) => {
    running.child.once('exit', (exitCode, signal) => { resolve({ exitCode, signal }) })
  })
  running.child.kill('SIGTERM')
  const forced = setTimeout(() => { running.child.kill('SIGKILL') }, 10_000)
  forced.unref()
  const result = await exited
  clearTimeout(forced)
  return result
}

/** Exchange the launch URL's boot token for the authenticated cookie. */
async function exchangeLaunchCookie(launchUrl: string): Promise<string> {
  const exchange = await fetch(launchUrl, { redirect: 'manual' })
  expect(exchange.status).toBe(303)
  const setCookie = exchange.headers.get('set-cookie')
  if (setCookie === null) throw new Error('candidate CLI token exchange omitted Set-Cookie')
  return setCookie.split(';', 1)[0]!
}

/** POST one real Remote envelope to the candidate deployment. */
function postRpc(port: number, host: string, cookie: string, method: string, payload: unknown = { args: {} }): Promise<HttpResult> {
  const body = JSON.stringify({
    type: 'client-request',
    rpcId: 'candidate-fullchain',
    method,
    payload,
  })
  return new Promise((resolve, reject) => {
    const req = httpRequest({
      hostname: '127.0.0.1',
      port,
      path: `/api/${method}`,
      method: 'POST',
      headers: {
        host,
        'content-type': 'application/json',
        'content-length': Buffer.byteLength(body),
        cookie,
      },
    }, (res) => {
      const chunks: Uint8Array[] = []
      res.on('data', (chunk: Buffer) => { chunks.push(chunk) })
      res.on('end', () => {
        resolve({ status: res.statusCode ?? 0, body: Buffer.concat(chunks).toString('utf8') })
      })
    })
    req.once('error', reject)
    req.end(body)
  })
}

/** Queue one session prompt through the real RPC face and require acceptance. */
async function promptViaRpc(port: number, host: string, cookie: string, sessionId: string, text: string): Promise<void> {
  const prompted = await postRpc(port, host, cookie, 'session/prompt', { args: {
    request: { requestId: randomUUID(), sessionId, mode: 'queue', content: [{ type: 'text', text }] },
  } })
  expect(prompted.status, `session/prompt status; body=${redact(prompted.body)}`).toBe(200)
  unwrapRpc('session/prompt', prompted.body)
}

/** Assert every candidate row is mounted, enabled, and active. */
async function expectCandidateRowsActive(running: RunningWeb): Promise<void> {
  const url = new URL(running.launchUrl)
  const cookie = await exchangeLaunchCookie(running.launchUrl)
  const response = await postRpc(Number(url.port), url.host, cookie, 'pluginInventory/list')
  expect(response.status).toBe(200)
  const parsed = JSON.parse(response.body) as {
    type: string
    result: { ok: boolean; value: { entries: { moduleName: string; enabled: boolean; fiberPhase: string | null }[] } }
  }
  expect(parsed.type).toBe('server-response')
  expect(parsed.result.ok).toBe(true)
  const mounted = new Map(parsed.result.value.entries.map(entry => [entry.moduleName, entry]))
  for (const moduleName of CANDIDATE_ROWS) {
    const entry = mounted.get(moduleName)
    if (entry === undefined) {
      throw new Error(`candidate row ${moduleName} is not in the loader inventory; mounted=${JSON.stringify([...mounted.keys()])}`)
    }
    // Row enabled-ness is deployment configuration, not capability: the
    // candidate explicitly disables the default launch-directory goal row
    // (the bootstrap mounts its own composition), and the runtime
    // capability evidence is the goal-binding record the bootstrap lands,
    // asserted in the bootstrap and chain legs.
    if (moduleName === '@deepseek-ai/dsh-experimental-command-goal-binding') {
      expect(entry.enabled, `${moduleName} deployment-disabled in the candidate`).toBe(false)
      continue
    }
    expect(entry.enabled, moduleName).toBe(true)
    expect(entry.fiberPhase, moduleName).toBe('active')
  }
}

/** Unwrap one RPC response: HTTP 200 is not success until result.ok says so. */
function unwrapRpc(name: string, body: string): unknown {
  const parsed = JSON.parse(body) as { result?: { ok?: boolean; value?: unknown; error?: { code?: string; message?: string } } }
  const result = parsed.result
  if (result === undefined) throw new Error(`${name} returned no result envelope; body=${redact(body)}`)
  if (result.ok !== true) throw new Error(`${name} refused: ${JSON.stringify(result.error ?? result)}; body=${redact(body)}`)
  return result.value
}

describe('candidate full-chain: real CLI boot, rows, and restart on an isolated home', () => {
  it('boots the candidate stack twice on one home with every row active', { timeout: 420_000 }, async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-candidate-fullchain-'))
    const dshHome = join(root, '.dsh')
    let first: RunningWeb | undefined
    let second: RunningWeb | undefined
    try {
      first = await startCandidateWeb(root, dshHome)
      const url = new URL(first.launchUrl)
      const port = Number(url.port)
      // The candidate owns an OS-assigned port: neither the default 3080 nor
      // the example overlay's pinned 3081, so concurrent runs never collide.
      expect(port).not.toBe(3080)
      expect(port).not.toBe(3081)
      expect(Number.isInteger(port) && port > 0, `readiness URL ${redact(first.launchUrl)}`).toBe(true)
      expect(first.pid).toBeGreaterThan(0)
      await expectCandidateRowsActive(first)

      const stop = await stopCandidateWeb(first)
      first = undefined
      // A graceful stop on Windows reports signal termination (SIGTERM); a
      // POSIX teardown reports the exit code. Either way the process stopped
      // on request: the outcome is recorded, never assumed.
      expect(
        stop.signal === 'SIGTERM' || stop.exitCode === 0 || stop.exitCode === 1,
        `stop outcome ${JSON.stringify(stop)}`,
      ).toBe(true)

      // Second boot on the SAME home: the restart face the chain's controlled
      // restart rides: same home, same patches, fresh process.
      second = await startCandidateWeb(root, dshHome)
      const secondUrl = new URL(second.launchUrl)
      expect(Number(secondUrl.port)).not.toBe(3080)
      expect(Number(secondUrl.port)).not.toBe(3081)
      await expectCandidateRowsActive(second)
    } catch (error) {
      const evidence = second?.output() ?? first?.output()
      throw new Error(`${error instanceof Error ? error.message : String(error)}${evidence === undefined ? '' : `\n${redact(evidence)}`}`, { cause: error })
    } finally {
      if (second !== undefined) await stopCandidateWeb(second)
      if (first !== undefined) await stopCandidateWeb(first)
      await rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })
    }
  })

  // Stage 2a: the session RPC envelope per the smoke-real remoteRpc helper:
  // payload wraps the method args, and args carries { request: {...} }.
  it('drives a session turn over the wire-level replay lane through the real RPC face', { timeout: 420_000 }, async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-candidate-fullchain-drive-'))
    const dshHome = join(root, '.dsh')
    await mkdir(dshHome, { recursive: true })
    // The candidate deployment's contract: the host prepares the scenario
    // before boot — the controller turn reads it from the isolated home,
    // and a missing file errors the turn before any model request.
    const prepared = await prepareCandidateScenario(root, join(dshHome, 'checks-ledger.json'))
    await writeScenarioFile(dshHome, prepared)
    const replay = await startWireReplayServer([
      {
        needle: 'candidate-driving-probe',
        turns: [{ text: 'CANDIDATE_DRIVING_OK' }],
      },
    ])
    let running: RunningWeb | undefined
    try {
      // The provider route points at the local replay server: the model lane
      // is scripted at the wire boundary, every other layer is the real CLI.
      running = await startCandidateWeb(root, dshHome, {
        DEEPSEEK_API_KEY: 'wire-replay-key',
        DEEPSEEK_BASE_URL: replay.baseURL,
      })
      const url = new URL(running.launchUrl)
      const cookie = await exchangeLaunchCookie(running.launchUrl)

      // The request-budget consumer admits only the configured root, its
      // lead, or that lead's scoped worker: the probe session must be the
      // fixed candidate root the deployment selected, or the precharge
      // refuses every send attempt and the turn never reaches the model.
      const created = await postRpc(Number(url.port), url.host, cookie, 'session/create', { args: { request: { sessionId: 'candidate-root-c14' } } })
      expect(created.status, `session/create status; body=${redact(created.body)}`).toBe(200)
      const createdValue = (JSON.parse(created.body) as { result?: { value?: { sessionId?: string } } }).result?.value
      if (createdValue?.sessionId === undefined) {
        throw new Error(`session/create returned no sessionId; body=${redact(created.body)}`)
      }
      const sessionId = createdValue.sessionId

      const prompt = 'candidate-driving-probe: reply with the marker and stop.'
      const prompted = await postRpc(Number(url.port), url.host, cookie, 'session/prompt', { args: {
        request: { requestId: randomUUID(), sessionId, mode: 'queue', content: [{ type: 'text', text: prompt }] },
      } })
      expect(prompted.status, `session/prompt status; body=${redact(prompted.body)}`).toBe(200)

      // The turn is proven by the wire lane: the real CLI session sends the
      // prompt to the replay server, which answers the scripted marker.
      const captured = await Promise.race([
        (async () => {
          for (let tick = 0; tick < 200; tick++) {
            if (replay.requests.length > 0) return replay.requests[0]!
            await new Promise(resolve => setTimeout(resolve, 100))
          }
          throw new Error('wire replay lane received no request in 20s')
        })(),
      ])
      expect(JSON.stringify(captured.body)).toContain(prompt)
      expect(running.child.exitCode).toBeNull()
    } catch (error) {
      // Archive the probe session's own log before the finally deletes the
      // home: turn errors live there, not in the RPC acceptance. Best
      // effort only — the original error still propagates.
      try {
        for (const log of sessionLogPaths(dshHome)) {
          const segment = log.split(/[\\/]/).at(-2) ?? 'unknown-session'
          await writeFile(`.agents/devframe/v14/remaining/drive-${segment}.dump.jsonl`, await decodeSessionLog(log), { flag: 'w' })
        }
      } catch {
        // The archive is diagnostic convenience; the failure evidence below
        // is the primary report.
      }
      const evidence = running?.output()
      throw new Error(`${error instanceof Error ? error.message : String(error)}${evidence === undefined ? '' : `\n${redact(evidence)}`}`, { cause: error })
    } finally {
      await replay.close()
      if (running !== undefined) await stopCandidateWeb(running)
      await rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })
    }
  })

  it('performs the host bootstrap through a replayed turn and re-establishes the same identity after restart', { timeout: 420_000 }, async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-candidate-fullchain-host-'))
    const dshHome = join(root, '.dsh')
    await mkdir(dshHome, { recursive: true })
    // Host preparation per the digest wiring ruling: pre-built real
    // worktrees, sequential digest saves into the shared ledger, the
    // host-owned scenario file, and the approveTaskChecks cross-check.
    const prepared = await prepareCandidateScenario(root, join(dshHome, 'checks-ledger.json'))
    await writeScenarioFile(dshHome, prepared)
    const expected = expectedDigests(prepared)
    for (const task of prepared.tasks) {
      expect(String(task.digest), `digest cross-check for ${task.taskId}`).toBe(expected[task.taskId])
    }

    const hostScript = [{
      needle: 'host-bootstrap-probe',
      turns: [
        { toolCalls: [{ name: 'project_host_start', arguments: {} }] },
        { text: 'HOST_BOOTSTRAP_OK' },
      ],
    }]
    // The restart leg confirms the persisted identity: the current goal
    // resumes, so the leg drives a plain turn — re-invoking the bootstrap
    // would refuse with "a goal is already current", which is the fold's
    // correct behavior, not a recovery path.
    const resumeScript = [{
      needle: 'host-resume-probe',
      turns: [{ text: 'HOST_RESUME_OK' }],
    }]

    /** Extract the host receipt the wire carried in the tool result. */
    function receiptFrom(text: string): { workspaceId: string; worktreeIds: string[]; controllerSessionId?: string } {
      // The receipt rides inside the tool message's string content, so the
      // body serialization escapes its quotes; unescape before matching.
      const flat = text.replaceAll('\\"', '"')
      const workspaceId = /"workspaceId":"([^"]+)"/u.exec(flat)?.[1]
      if (workspaceId === undefined) throw new Error(`no host receipt in wire body: ${redact(flat.slice(0, 600))}`)
      const worktreeIds = [...flat.matchAll(/"worktreeId":"([^"]+)"/gu)].map(match => match[1]!)
      const controllerSessionId = /"controllerSessionId":"([^"]+)"/u.exec(flat)?.[1]
      return { workspaceId, worktreeIds, ...(controllerSessionId !== undefined ? { controllerSessionId } : {}) }
    }

    /**
     * The durable request-budget usage global — the only durable authority
     * for charged request usage, read straight from the domain's single-unit
     * document.
     */
    async function chargedRequestsOf(): Promise<number> {
      try {
        const document = JSON.parse(await readFile(join(dshHome, 'storages', 'project_tasks.json'), 'utf8')) as { global?: { chargedRequests?: number } }
        return document.global?.chargedRequests ?? 0
      } catch {
        // A missing file is the zero state: no charge has been persisted yet.
        return 0
      }
    }

    /** Drive one turn; `requireReceipt` waits for the host receipt too. */
    async function driveHostTurn(
      replay: Awaited<ReturnType<typeof startWireReplayServer>>,
      prompt: string,
      requireReceipt: boolean,
      resumeSessionId?: string,
    ): Promise<{ sessionId: string; receipt?: { workspaceId: string; worktreeIds: string[]; controllerSessionId?: string } }> {
      const running = await startCandidateWeb(root, dshHome, {
        DEEPSEEK_API_KEY: 'wire-replay-key',
        DEEPSEEK_BASE_URL: replay.baseURL,
      })
      try {
        const url = new URL(running.launchUrl)
        const cookie = await exchangeLaunchCookie(running.launchUrl)
        let sessionId = resumeSessionId
        if (sessionId === undefined) {
          // The request-budget consumer admits only the configured root, so
          // the bootstrap session must be the fixed candidate root.
          const created = await postRpc(Number(url.port), url.host, cookie, 'session/create', { args: { request: { sessionId: 'candidate-root-c14' } } })
          sessionId = (unwrapRpc('session/create', created.body) as { sessionId: string }).sessionId
        } else {
          // The restart leg first verifies the persisted session registry
          // still carries the recorded controller identity.
          const listed = await postRpc(Number(url.port), url.host, cookie, 'session/list', { args: { _request: {} } })
          const listValue = JSON.stringify(unwrapRpc('session/list', listed.body))
          expect(listValue, `session/list after restart must carry ${sessionId}`).toContain(sessionId)
        }
        const prompted = await postRpc(Number(url.port), url.host, cookie, 'session/prompt', { args: {
          request: { requestId: randomUUID(), sessionId, mode: 'queue', content: [{ type: 'text', text: prompt }] },
        } })
        expect(prompted.status, `session/prompt status; body=${redact(prompted.body)}`).toBe(200)
        unwrapRpc('session/prompt', prompted.body)
        // The web session also fires a title-generation request through the
        // same lane; scan every captured body for the turn's own request
        // instead of assuming request positions. The resume leg lands here
        // too: the consumer's pre-step resumes the current goal through the
        // public resume lane and releases the model stream, so a real
        // post-restart model request is the acceptance evidence.
        for (let tick = 0; tick < 600; tick++) {
          const bodies = replay.requests.map(request => JSON.stringify(request.body))
          // The receipt lands only after the turn executes project_host_start,
          // so the bootstrap leg keeps polling past its own prompt request.
          const receiptHit = bodies.find(text => text.includes('admission_open'))
          if (receiptHit !== undefined) return { sessionId, receipt: receiptFrom(receiptHit) }
          if (!requireReceipt && bodies.some(text => text.includes(prompt))) return { sessionId }
          await new Promise(resolve => setTimeout(resolve, 100))
        }
        throw new Error(`wire replay lane saw ${replay.requests.length} requests in 60s, none carrying "${prompt}"; tool messages: ${
          redact(replay.requests.map(request => JSON.stringify(request.body)).filter(text => text.includes('"role":"tool"')).map((text) => {
            const at = text.indexOf('"role":"tool"')
            return text.slice(at, at + 400)
          }).join(' | ') || 'none')
        }\n${redact(running.output())}`)
      } finally {
        await stopCandidateWeb(running)
      }
    }

    const first = await startWireReplayServer(hostScript)
    let firstReceipt: { workspaceId: string; worktreeIds: string[] }
    let controllerSessionId: string
    let chargedBeforeResume = 0
    let beforeGoalId = ''
    let beforeRevision = 0
    let beforeBindingCount = 0
    try {
      const driven = await driveHostTurn(first, 'host-bootstrap-probe: start the host.', true)
      controllerSessionId = driven.sessionId
      firstReceipt = driven.receipt!
      expect(firstReceipt.worktreeIds.length, `receipt ${JSON.stringify(firstReceipt)}`).toBe(2)
      // The ruled capability evidence, captured before the restart: the
      // bootstrap bound one goal at one revision, folded at admission_open.
      const controllerLog = sessionLogPaths(dshHome).find(path => path.includes(controllerSessionId))
      expect(controllerLog, 'controller session log after the first bootstrap').toBeDefined()
      const beforeBindings = parseLogEvents(await decodeSessionLog(controllerLog!))
        .filter(event => event.type === 'devframe/goal-binding')
      expect(beforeBindings.length, 'one binding record after the first bootstrap').toBe(1)
      beforeGoalId = String((beforeBindings[0]!.data as { goalId?: unknown }).goalId)
      beforeRevision = Number((beforeBindings[0]!.data as { goalRevision?: unknown }).goalRevision)
      beforeBindingCount = beforeBindings.length
      expect(beforeGoalId, 'the bound goal id').toBeTruthy()
      expect(Number.isFinite(beforeRevision), 'the first binding carries a revision').toBe(true)
      chargedBeforeResume = await chargedRequestsOf()
      expect(chargedBeforeResume, 'the first bootstrap charged the budget').toBeGreaterThanOrEqual(1)
    } catch (error) {
      throw new Error(`${error instanceof Error ? error.message : String(error)}`, { cause: error })
    } finally {
      await first.close()
    }

    // Restart on the SAME home: the SAME controller session id turns again
    // through the consumer's resume lane — the current goal resumes (never a
    // second start), the model stream releases for real, the same
    // goal-binding record stays folded at admission_open, and the durable
    // charged-usage global accumulates across the restart.
    const second = await startWireReplayServer(resumeScript)
    try {
      const driven = await driveHostTurn(second, 'host-resume-probe: confirm the persisted host identity.', false, controllerSessionId)
      expect(driven.sessionId).toBe(controllerSessionId)
      const resumedLog = sessionLogPaths(dshHome).find(path => path.includes(controllerSessionId))
      expect(resumedLog, 'controller session log after the restart leg').toBeDefined()
      // Binding face: the resumed turn belongs to the SAME goal — every
      // record names the identical goal id, the resume landed a new binding
      // record on top of the pre-restart one, and that record advanced the
      // revision.
      const afterEvents = parseLogEvents(await decodeSessionLog(resumedLog!))
      const afterBindings = afterEvents.filter(event => event.type === 'devframe/goal-binding')
      for (const binding of afterBindings) {
        expect(String((binding.data as { goalId?: unknown }).goalId), 'the resume stayed on the same goal').toBe(beforeGoalId)
      }
      expect(afterBindings.length, 'the resume landed a new binding record').toBeGreaterThan(beforeBindingCount)
      const afterRevision = Math.max(...afterBindings.map(binding => Number((binding.data as { goalRevision?: unknown }).goalRevision)))
      expect(afterRevision, 'the resumed binding advanced the revision').toBeGreaterThan(beforeRevision)
      assertGoalBindingAdmissionOpen(afterEvents, 'the restart leg')
      // Project face: the durable charged-usage global accumulated across
      // the restart (the project-level contract, no goal bucketing).
      const chargedAfterResume = await chargedRequestsOf()
      expect(chargedAfterResume, 'the resumed request charged the same durable budget')
        .toBeGreaterThan(chargedBeforeResume)
    } catch (error) {
      // Archive the controller log before the finally deletes the home: the
      // resumed turn's own error lives there. Best effort only.
      try {
        for (const log of sessionLogPaths(dshHome)) {
          const segment = log.split(/[\\/]/).at(-2) ?? 'unknown-session'
          await writeFile(`.agents/devframe/v14/remaining/host-${segment}.dump.jsonl`, await decodeSessionLog(log), { flag: 'w' })
        }
      } catch {
        // The archive is diagnostic convenience; the original error still
        // propagates.
      }
      throw new Error(`${error instanceof Error ? error.message : String(error)}`, { cause: error })
    } finally {
      await second.close()
    }
    await rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })
  })

  it('recovers a failed first bootstrap through the same composition without double charging', { timeout: 420_000 }, async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-candidate-fullchain-retry-'))
    const dshHome = join(root, '.dsh')
    await mkdir(dshHome, { recursive: true })
    const prepared = await prepareCandidateScenario(root, join(dshHome, 'checks-ledger.json'))
    await writeScenarioFile(dshHome, prepared)
    const replay = await startWireReplayServer([
      { needle: 'bootstrap-retry-probe', turns: [{ text: 'BOOTSTRAP_RETRY_OK' }] },
    ])
    let running: RunningWeb | undefined
    try {
      running = await startCandidateWeb(root, dshHome, {
        DEEPSEEK_API_KEY: 'wire-replay-key',
        DEEPSEEK_BASE_URL: replay.baseURL,
      })
      const url = new URL(running.launchUrl)
      const cookie = await exchangeLaunchCookie(running.launchUrl)
      const created = await postRpc(Number(url.port), url.host, cookie, 'session/create', { args: { request: { sessionId: 'candidate-root-c14' } } })
      const sessionId = (unwrapRpc('session/create', created.body) as { sessionId: string }).sessionId
      const promptRoot = (text: string): Promise<void> => {
        // The recovery legs prompt the same fixed root through the one RPC
        // face; the wrapper keeps the failure-reporting helper shared.
        return promptViaRpc(Number(url.port), url.host, cookie, sessionId, text)
      }
      const controllerLogPath = (): string => {
        const log = sessionLogPaths(dshHome).find(path => path.includes(sessionId))
        expect(log, 'controller session log').toBeDefined()
        return log!
      }
      // Round one: the target's git identity is unavailable, so the start
      // gate's source observation throws after the composition mounted — the
      // bootstrap fails loudly and no model stream is released. The session
      // log materializes only once the failing turn is persisted, so the
      // poll tolerates a missing log.
      const hiddenGit = join(prepared.targetWorktreePath, '.git-hidden')
      await rename(join(prepared.targetWorktreePath, '.git'), hiddenGit)
      await promptRoot('bootstrap-retry-probe: start the host.')
      const roundOneLog = (): string | undefined => sessionLogPaths(dshHome).find(path => path.includes(sessionId))
      for (let tick = 0; tick < 300; tick++) {
        const log = roundOneLog()
        if (log !== undefined && (await decodeSessionLog(log)).includes('"kind":"error"')) break
        await new Promise(resolve => setTimeout(resolve, 100))
      }
      const failedLog = roundOneLog()
      expect(failedLog, 'controller session log after the failed round').toBeDefined()
      expect((await decodeSessionLog(failedLog!)).includes('"kind":"error"'), 'the first bootstrap failed loudly').toBe(true)
      expect(replay.requests.length, 'a failed bootstrap releases no model stream').toBe(0)
      // Round two: the same pre-step retries with the SAME mounted
      // composition — the start succeeds and the model stream releases.
      await rename(hiddenGit, join(prepared.targetWorktreePath, '.git'))
      await promptRoot('bootstrap-retry-probe: start the host.')
      for (let tick = 0; tick < 600; tick++) {
        if (replay.requests.some(request => JSON.stringify(request.body).includes('bootstrap-retry-probe'))) break
        await new Promise(resolve => setTimeout(resolve, 100))
      }
      expect(replay.requests.length, 'the recovered bootstrap released the model stream').toBeGreaterThanOrEqual(1)
      // One composition: exactly one successful start landed one binding
      // record — a remount would have registered the face twice.
      const events = parseLogEvents(await decodeSessionLog(controllerLogPath()))
      const bindings = events.filter(event => event.type === 'devframe/goal-binding')
      expect(bindings.length, 'exactly one goal binding after the recovery').toBe(1)
      assertGoalBindingAdmissionOpen(events, 'the recovery leg')
      // No double charging: the failed round charged nothing, so the durable
      // usage equals the admitted streams exactly.
      const document = JSON.parse(await readFile(join(dshHome, 'storages', 'project_tasks.json'), 'utf8')) as { global?: { chargedRequests?: number } }
      expect(document.global?.chargedRequests ?? 0, 'charges match the admitted streams').toBe(replay.requests.length)
      expect(running.child.exitCode).toBeNull()
    } catch (error) {
      // Archive the controller log before the finally deletes the home: the
      // bootstrap's own error lives there. Best effort only.
      try {
        for (const log of sessionLogPaths(dshHome)) {
          const segment = log.split(/[\\/]/).at(-2) ?? 'unknown-session'
          await writeFile(`.agents/devframe/v14/remaining/retry-${segment}.dump.jsonl`, await decodeSessionLog(log), { flag: 'w' })
        }
      } catch {
        // The archive is diagnostic convenience; the original error still
        // propagates.
      }
      throw new Error(`${error instanceof Error ? error.message : String(error)}`, { cause: error })
    } finally {
      await replay.close()
      if (running !== undefined) await stopCandidateWeb(running)
      await rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })
    }
  })

  it('drives the candidate chain over the wire lane: plan, lead dispatch, worker delivery with real checks', { timeout: 600_000 }, async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-candidate-fullchain-chain-'))
    const dshHome = join(root, '.dsh')
    await mkdir(dshHome, { recursive: true })
    const prepared = await prepareCandidateScenario(root, join(dshHome, 'checks-ledger.json'))
    await writeScenarioFile(dshHome, prepared)
    // The final-layer patch pins the per-task digests; the CLI reads it on
    // every boot, so a restarted candidate re-derives the same approvals.
    const digestPatch = await writeDigestPatch(dshHome, prepared)

    /** Pull the prepared worktree ids back out of any wire body. */
    function worktreeIdsFrom(text: string): Record<string, string> {
      const flat = text.replaceAll('\\"', '"')
      const map: Record<string, string> = {}
      for (const match of flat.matchAll(/"taskId":"(task-[ab])","worktreeId":"([^"]+)"/gu)) {
        map[match[1]!] = match[2]!
      }
      const leadWorktreeId = /"leadWorktreeId":"([^"]+)"/u.exec(flat)?.[1]
      if (leadWorktreeId !== undefined) map['lead'] = leadWorktreeId
      return map
    }

    const shell = process.platform === 'win32' ? 'pwsh' : 'bash'
    const commitFor = (taskId: string): string => process.platform === 'win32'
      ? `Set-Content -Path artifact-${taskId}.txt -Value '${taskId} artifact body' -Encoding utf8; git add artifact-${taskId}.txt; git commit -m '${taskId} artifact'`
      : `printf '${taskId} artifact body' > artifact-${taskId}.txt && git add artifact-${taskId}.txt && git commit -m '${taskId} artifact'`

    /**
     * The exact registration state project_task start demands: both worker
     * bindings durably in the identity table. This gates the scripted start
     * turn so the phase can never be consumed before its precondition.
     */
    const registrationsReady = (): boolean => {
      const tablePath = join(dshHome, 'storages', 'session_identity.json')
      if (!existsSync(tablePath)) return false
      try {
        const table = JSON.parse(readFileSync(tablePath, 'utf8')) as {
          tables: { bindings: Record<string, { role: string; taskId?: string }> }
        }
        const tasks = new Set(Object.values(table.tables.bindings)
          .filter(record => record.role === 'worker')
          .map(record => record.taskId))
        return tasks.has('task-a') && tasks.has('task-b')
      } catch {
        // A mid-flush table read races the writer; the next poll retries.
        return false
      }
    }

    const controller = {
      needle: 'controller-chain-c14',
      turns: [
        { toolCalls: [{ name: 'project_host_start', arguments: {} }] },
        // Served on the receipt-carrying request: plan (with pluginId), then
        // dispatch the lead onto its own tree. The dispatch publishes and
        // queues the lead asynchronously — the tasks start only in a later
        // controller turn, after the workers are registered.
        { toolCalls: [
          { name: 'project_task', arguments: { action: 'plan', taskId: 'task-a', pluginId: 'candidate-fullchain', title: 'Candidate task A' } },
          { name: 'project_task', arguments: { action: 'plan', taskId: 'task-b', pluginId: 'candidate-fullchain', title: 'Candidate task B' } },
          { name: 'agent_dispatch', arguments: (body: string) => {
            const ids = worktreeIdsFrom(body)
            return { role: 'lead', taskId: 'task-a', worktreeId: ids['lead'], pluginId: 'candidate-fullchain', childId: 'candidate-fullchain-lead', prompt: `lead-briefing-c14: you are the independent lead. Dispatch one worker per task. RECEIPT_ECHO:${JSON.stringify({ taskId: 'task-a', worktreeId: ids['task-a'] })} RECEIPT_ECHO:${JSON.stringify({ taskId: 'task-b', worktreeId: ids['task-b'] })}` }
          } },
        ] },
        { text: 'CONTROLLER_PHASE1_DONE_C14' },
        // Goal continuation re-prompts the controller; this turn is served
        // only once both worker bindings are durably in the identity table —
        // before that the replay answers a bounded standby without consuming
        // the phase. Start carries the worker briefing (startDevelopment then
        // followup) — the workers' first model request rides this.
        {
          gate: () => registrationsReady(),
          toolCalls: [
            { name: 'project_task', arguments: { action: 'start', taskId: 'task-a', briefing: 'worker-task-a-briefing-c14: create your own artifact file and commit it, then deliver.' } },
            { name: 'project_task', arguments: { action: 'start', taskId: 'task-b', briefing: 'worker-task-b-briefing-c14: create your own artifact file and commit it, then deliver.' } },
          ],
        },
        { text: 'CONTROLLER_CHAIN_DONE_C14' },
      ],
    }
    const lead = {
      needle: 'lead-briefing-c14',
      turns: [
        { toolCalls: [
          { name: 'agent_dispatch', arguments: (body: string) => {
            const ids = worktreeIdsFrom(body)
            // Registration only: no prompt field — the workers receive their
            // briefings through project_task start after the root confirms
            // the registry registrations.
            return { role: 'worker', taskId: 'task-a', worktreeId: ids['task-a'], pluginId: 'candidate-fullchain' }
          } },
          { name: 'agent_dispatch', arguments: (body: string) => {
            const ids = worktreeIdsFrom(body)
            return { role: 'worker', taskId: 'task-b', worktreeId: ids['task-b'], pluginId: 'candidate-fullchain' }
          } },
        ] },
        { text: 'LEAD_DISPATCHED_C14' },
      ],
    }
    const workerA = {
      needle: 'worker-task-a-briefing-c14',
      turns: [
        { toolCalls: [
          { id: 'shell-task-a', name: shell, arguments: { command: commitFor('task-a'), description: 'commit the task artifact' } },
          { id: 'deliver-task-a', name: 'project_deliver', arguments: { taskId: 'task-a' } },
        ] },
        { text: 'WORKER_A_DONE_C14' },
      ],
    }
    const workerB = {
      needle: 'worker-task-b-briefing-c14',
      turns: [
        { toolCalls: [
          { id: 'shell-task-b', name: shell, arguments: { command: commitFor('task-b'), description: 'commit the task artifact' } },
          { id: 'deliver-task-b', name: 'project_deliver', arguments: { taskId: 'task-b' } },
        ] },
        { text: 'WORKER_B_DONE_C14' },
      ],
    }
    const replay = await startWireReplayServer([controller, lead, workerA, workerB])
    let running: RunningWeb | undefined
    try {
      running = await startCandidateWeb(root, dshHome, {
        DEEPSEEK_API_KEY: 'wire-replay-key',
        DEEPSEEK_BASE_URL: replay.baseURL,
      }, digestPatch)
      const url = new URL(running.launchUrl)
      const cookie = await exchangeLaunchCookie(running.launchUrl)
      // The host selects the root identity up front: the same fixed id feeds
      // the budget consumer's config and the create call, and the root
      // session is born inside the controller's target worktree.
      const rootSessionId = 'candidate-root-c14'
      const created = await postRpc(Number(url.port), url.host, cookie, 'session/create', { args: { request: {
        sessionId: rootSessionId,
        cwd: prepared.targetWorktreePath,
      } } })
      const sessionId = (unwrapRpc('session/create', created.body) as { sessionId: string }).sessionId
      expect(sessionId).toBe(rootSessionId)

      const promptSession = (text: string): Promise<void> => promptViaRpc(Number(url.port), url.host, cookie, sessionId, text)
      /** Wait until a predicate holds; the predicate may be async. */
      const waitFor = async (what: string, predicate: () => boolean | Promise<boolean>, ms: number): Promise<void> => {
        for (let tick = 0; tick < Math.ceil(ms / 100); tick++) {
          if (await predicate()) return
          await new Promise(resolve => setTimeout(resolve, 100))
        }
        const toolEvidence = replay.requests.map(request => ({ needle: request.needle, text: JSON.stringify(request.body).replaceAll('\\"', '"') }))
          .filter(entry => entry.text.includes('"role":"tool"'))
          .map((entry) => {
            const results = [...entry.text.matchAll(/"role":"tool","tool_call_id":"([^"]*)","content":"((?:[^"\\]|\\.)*)"/gu)]
              .map(match => `${match[1]}=>${match[2]!.slice(0, 220)}`)
            return `${entry.needle}: ${results.join(' ## ')}`
          })
          .join(' | ')
        throw new Error(`timed out after ${String(ms)}ms waiting for ${what}; captured=${replay.requests.length} requests by needle: ${
          JSON.stringify(replay.requests.reduce<Record<string, number>>((acc, r) => {
            const key = r.needle ?? 'unrouted'
            acc[key] = (acc[key] ?? 0) + 1
            return acc
          }, {}))
        }; tool evidence: ${redact(toolEvidence.slice(0, 3500))}\n${redact(running!.output())}`)
      }
      const bodies = (): string[] => replay.requests.map(request => JSON.stringify(request.body))

      await promptSession('controller-chain-c14: start the host, then plan and dispatch the lead.')
      await waitFor('controller host receipt', () => bodies().some(text => text.includes('admission_open')), 90_000)
      // The real executed-start evidence: decoded session logs, parsed
      // event by event. The root log answers the start-turn evidence and the
      // timeline; the worker logs answer the durable delivery and
      // verification evidence.
      const rootLogPath = (): string | undefined => sessionLogPaths(dshHome)
        .find(path => path.includes('candidate-root-c14'))
      const readRootStartCalls = async (): Promise<{ time: number; task: string }[]> => {
        const rootLog = rootLogPath()
        if (rootLog === undefined) return []
        const startCalls: { time: number; task: string }[] = []
        for (const event of parseLogEvents(await decodeSessionLog(rootLog))) {
          const data = event.data as { name?: string; arguments?: string | { action?: string; taskId?: string } } | undefined
          if (event.type !== 'tool/call' || data?.name !== 'project_task' || event.time === undefined) continue
          const parsed: unknown = typeof data.arguments === 'string'
            ? JSON.parse(data.arguments)
            : data.arguments
          if (parsed === null || typeof parsed !== 'object') continue
          const args = parsed as { action?: string; taskId?: string }
          if (args.action !== 'start' || args.taskId === undefined) continue
          startCalls.push({ time: event.time, task: args.taskId })
        }
        return startCalls
      }

      // The Goal continuation re-prompts the controller on its own; the
      // replay holds the start turn until both worker bindings are durable.
      // The served-turn evidence is the real executed project_task start
      // events in the root session log — never a string match over escaped
      // wire JSON.
      await waitFor('controller start turn served after registration', async () => {
        if (!registrationsReady()) return false
        return await readRootStartCalls().then(calls => calls.length) >= 2
      }, 120_000)
      await waitFor('worker a delivery turn', () => {
        const workerRequests = replay.requests.filter(request => request.needle === 'worker-task-a-briefing-c14')
        return workerRequests.length >= 2 && JSON.stringify(workerRequests[1]!.body).includes('task-a')
      }, 120_000)
      await waitFor('worker b delivery turn', () => {
        const workerRequests = replay.requests.filter(request => request.needle === 'worker-task-b-briefing-c14')
        return workerRequests.length >= 2 && JSON.stringify(workerRequests[1]!.body).includes('task-b')
      }, 120_000)

      // The acceptance timeline reuses the one source of truth: exactly two
      // starts — task-a and task-b — and both stamped after both worker
      // bindings were durably created. The bindings also name each worker's
      // session id, which locates its log by identity — the controller log
      // carries the briefing text too (its own dispatch arguments), so a
      // needle search alone cannot tell the logs apart.
      const identityTable = JSON.parse(await readFile(join(dshHome, 'storages', 'session_identity.json'), 'utf8')) as {
        tables: { bindings: Record<string, { role: string; sessionId: string; taskId?: string; createdAt: string }> }
      }
      const workerBindings = Object.values(identityTable.tables.bindings)
        .filter(record => record.role === 'worker' && record.taskId !== undefined)
      const workerSessionIdByTask = new Map(workerBindings.map(record => [record.taskId!, record.sessionId]))
      const workerCreatedAt = workerBindings.map(record => Date.parse(record.createdAt))
      expect(workerCreatedAt).toHaveLength(2)
      const startCalls = await readRootStartCalls()
      expect(startCalls.map(call => call.task).sort()).toEqual(['task-a', 'task-b'])
      for (const startAt of startCalls) {
        for (const workerAt of workerCreatedAt) {
          expect(startAt.time).toBeGreaterThan(workerAt)
        }
      }
      // The ruled capability evidence on the controller's own log: the
      // bootstrap bound the goal and the record folded at admission_open.
      assertGoalBindingAdmissionOpen(
        parseLogEvents(await decodeSessionLog(rootLogPath()!)), 'the candidate chain controller log')

      // Success = the real tool results on the wire, read back from the
      // captured request objects by the exact tool-call identity (no
      // stringify-and-regex round trip). The wire carries tool results as
      // OpenAI-shaped `role: "tool"` messages keyed by tool_call_id, so the
      // scripted ids tie each result to its call: git shell output can
      // never masquerade as the project_deliver receipt, and the deliver
      // receipt itself must be the exact reviewing-and-passed form — a
      // plain "checks failed" result is not an Error and would otherwise
      // pass any substring check.
      const toolResultById = (needle: string, callId: string): string | undefined => {
        for (const request of replay.requests) {
          if (request.needle !== needle) continue
          const messages = (request.body as { messages?: unknown }).messages
          if (!Array.isArray(messages)) continue
          for (const message of messages) {
            const wire = message as { role?: string; tool_call_id?: string; content?: unknown }
            if (wire.role !== 'tool' || wire.tool_call_id !== callId) continue
            if (typeof wire.content === 'string') return wire.content
            if (Array.isArray(wire.content)) {
              return wire.content.map((part) => {
                const piece = part as { type?: string; text?: string }
                return typeof piece.text === 'string' ? piece.text : ''
              }).join('')
            }
            return JSON.stringify(wire.content)
          }
        }
        return undefined
      }
      // The persisted evidence: the shared ledger resolves each task's
      // digest to the approved checklist (definitions only), the generated
      // patch pins the same digests as real parsed YAML, and the worker's
      // own session log must carry the delivery plus a passed verification
      // bound to the same delivery id, digest, and worktree — the durable
      // proof the checks actually executed and passed.
      const ledgerStore = new FileRequiredChecksConfigStore({ path: join(dshHome, 'checks-ledger.json') })
      const patchText = await readFile(digestPatch, 'utf8')
      const parsedPatch = yamlLoad(patchText.replace(/!!js "[^"]*"/u, '"<ledger-path-expression>"')) as {
        config?: { requiredChecksByTask?: Record<string, string> }
      }[]
      const byTask = parsedPatch[0]?.config?.requiredChecksByTask ?? {}
      const expected = expectedDigests(prepared)
      const decodedLogs = await decodeSessionLogs(dshHome)
      const workerLogEvents = (taskId: string, needle: string): JournalEvent[] => {
        const sessionId = workerSessionIdByTask.get(taskId)
        expect(sessionId, `worker session id for ${taskId}`).toBeTruthy()
        const hit = decodedLogs.find(log => log.path.includes(sessionId!))
        expect(hit, `worker session log for ${taskId} (${sessionId})`).toBeDefined()
        expect(hit!.text.includes(needle), `briefing present in the identity-selected log for ${taskId}`).toBe(true)
        return parseLogEvents(hit!.text)
      }
      for (const task of prepared.tasks) {
        const shellResult = toolResultById(`worker-${task.taskId}-briefing-c14`, `shell-${task.taskId}`)
        expect(shellResult, `shell commit receipt for ${task.taskId}`).toBeDefined()
        expect(shellResult!.startsWith('Error:'), `shell commit must succeed for ${task.taskId}: ${shellResult}`).toBe(false)
        const deliverResult = toolResultById(`worker-${task.taskId}-briefing-c14`, `deliver-${task.taskId}`)
        expect(deliverResult, `real deliver receipt for ${task.taskId}`).toBeDefined()
        expect(deliverResult!.startsWith('Error:'), `delivery must not error for ${task.taskId}: ${deliverResult}`).toBe(false)
        expect(deliverResult, `delivery must reach reviewing with passed checks for ${task.taskId}`)
          .toBe(`Task ${task.taskId}: reviewing; checks passed.`)
        expect(deliverResult).not.toContain('checks failed')
        expect(deliverResult).not.toBe(shellResult)
        expect(await ledgerStore.load(task.digest)).toEqual(approvedChecksFor(task.worktreePath, `artifact-${task.taskId}.txt`))
        expect(byTask[task.taskId]).toBe(expected[task.taskId])
        const events = workerLogEvents(task.taskId, `worker-${task.taskId}-briefing-c14`)
        const deliveries = events.filter(event =>
          event.type === 'devframe/task-delivery' && String((event.data as { taskId?: unknown }).taskId) === task.taskId)
        expect(deliveries.length, `durable delivery event for ${task.taskId}`).toBeGreaterThanOrEqual(1)
        const delivery = deliveries.at(-1)!.data as {
          deliveryId: string
          worktreePath: string
          sourceCommit: string
          binding: { goalId?: string }
          sourceFingerprint?: string
        }
        expect(delivery.deliveryId).toBeTruthy()
        expect(delivery.worktreePath).toBe(task.worktreePath)
        expect(delivery.sourceCommit).toBeTruthy()
        expect(delivery.binding?.goalId).toBeTruthy()
        const verifications = events.filter(event =>
          event.type === 'devframe/verification'
          && (event.data as { deliveryId?: unknown }).deliveryId === delivery.deliveryId)
        expect(verifications.length, `durable verification event for ${task.taskId}`).toBeGreaterThanOrEqual(1)
        for (const verification of verifications) {
          const data = verification.data as { status?: string; requiredChecks?: { digest?: string }; checks?: { status?: string }[] }
          expect(data.requiredChecks?.digest, `verification digest for ${task.taskId}`).toBe(task.digest)
          expect(data.status, `verification status for ${task.taskId}`).toBe('passed')
          for (const check of data.checks ?? []) expect(check.status).toBe('passed')
        }
        const artifact = join(task.worktreePath, `artifact-${task.taskId}.txt`)
        const content = await readFile(artifact, 'utf8')
        expect(content.trim()).toBe(`${task.taskId} artifact body`)
      }
    } catch (error) {
      // Read the root session's own durable log: turn/end and step/end
      // errors live there, not in the RPC acceptance. The log is a
      // multi-frame zstd JSONL under sessions/<cwd>/<id>/session.jsonl.zstd;
      // complete frames decode, a torn active tail is recovered separately,
      // and the full plaintext is archived before the finally deletes the
      // temporary home.
      let logEvidence = ''
      try {
        // The persistence row's root varies by configuration; the physical
        // shape does not: session.jsonl(.zstd) under an encoded session-id
        // directory segment. The repository zstd reader scans every
        // structurally complete frame (a streaming one-shot decode can stop
        // after the first frame and hide the whole turn history), recovers
        // the torn active tail separately, and the raw log plus plaintext
        // are archived before the finally deletes the temporary home.
        const { scanZstdFrames, createZstdFrameDecoder, decompressZstdPrefix } =
          await import('../../../session/session-persistence-jsonl/src/zstd.ts')
        const entries = await readdir(dshHome, { recursive: true, withFileTypes: true })
        const logs = entries.filter(entry => entry.isFile()
          && (entry.name === 'session.jsonl' || entry.name === 'session.jsonl.zstd'))
          .map(entry => join(entry.parentPath, entry.name))
        let lineNo = 0
        for (const log of logs) {
          // One archive per session: the root's forensics keep their names;
          // every other log (lead, workers) lands beside them under its own
          // session segment so a silent child failure is readable.
          const sessionSegment = log.split(/[\\/]/).at(-2) ?? 'unknown-session'
          const dumpName = sessionSegment.includes('candidate-root-c14')
            ? 'root-session-dump.jsonl'
            : `${sessionSegment}.dump.jsonl`
          const buffer = await readFile(log)
          await writeFile(`.agents/devframe/v14/remaining/${sessionSegment}.raw.zstd`, buffer, { flag: 'w' })
          let plaintext = buffer.toString('utf8')
          if (log.endsWith('.zstd')) {
            const { frames, tornStart } = scanZstdFrames(buffer)
            const decoder = createZstdFrameDecoder()
            const parts: Buffer[] = []
            try {
              for (const frame of decoder.decode(buffer, frames)) parts.push(Buffer.from(frame))
            } finally {
              decoder.close()
            }
            if (tornStart !== undefined) {
              try {
                parts.push(await decompressZstdPrefix(buffer.subarray(tornStart)))
              } catch {
                // A structurally incomplete final frame may yield no
                // plaintext; the complete prior frames remain readable.
              }
            }
            plaintext = Buffer.concat(parts).toString('utf8')
          }
          await writeFile(`.agents/devframe/v14/remaining/${dumpName}`, plaintext, { flag: 'w' })
          for (const line of plaintext.split('\n')) {
            lineNo += 1
            if (line.includes('"error"') || line.includes('"kind":"error"')
              || line.includes('"type":"turn/end"') || line.includes('"type":"step/end"')) {
              logEvidence += `\n[line ${lineNo}] ${line.slice(0, 500)}`
            }
          }
        }
        logEvidence = `${logEvidence} [archived root-session-dump.jsonl from ${logs.length} log(s), ${lineNo} lines]`
        // The candidate's own agent/error diagnostics: the original error
        // cause chain per run tag, bound to this run's root id.
        const diags = entries.filter(entry => entry.isFile() && entry.name.startsWith('agent-error-diag-'))
          .map(entry => join(entry.parentPath, entry.name))
        for (const diag of diags) {
          const content = await readFile(diag, 'utf8')
          await writeFile('.agents/devframe/v14/remaining/agent-error-diag-archive.jsonl', content, { flag: 'w' })
          logEvidence += `\n[agent-error-diag ${diag}] ${content.slice(0, 1600)}`
        }
        // The durable identity and worktree tables: project_task start
        // refuses on the bindings these files hold, so the archive shows
        // exactly which rows the authority saw.
        for (const table of ['session_identity.json', 'worktree_registry.json']) {
          const tablePath = join(dshHome, 'storages', table)
          if (!existsSync(tablePath)) continue
          const content = await readFile(tablePath, 'utf8')
          await writeFile(`.agents/devframe/v14/remaining/${table}`, content, { flag: 'w' })
          logEvidence += `\n[${table}] ${content.slice(0, 2400)}`
        }
      } catch (dumpError) {
        logEvidence = `\n[root session dump failed: ${dumpError instanceof Error ? dumpError.message : String(dumpError)}]`
      }
      const evidence = running?.output()
      throw new Error(`${error instanceof Error ? error.message : String(error)}${redact(logEvidence)}${evidence === undefined ? '' : `\n${redact(evidence)}`}`, { cause: error })
    } finally {
      await replay.close()
      if (running !== undefined) await stopCandidateWeb(running)
      await rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })
    }
  })
})
