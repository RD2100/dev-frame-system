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
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { randomUUID } from 'node:crypto'
import { join } from 'node:path'
import { createRequire } from 'node:module'
import { request as httpRequest } from 'node:http'
import { pathToFileURL, fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { startWireReplayServer } from './fixtures/wire-replay-server.ts'

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

/** Start the real source CLI with all three patches and await readiness. */
async function startCandidateWeb(root: string, dshHome: string, extraEnv: NodeJS.ProcessEnv = {}): Promise<RunningWeb> {
  const child = spawn(process.execPath, [
    '--import', TSX_LOADER,
    DSH_SOURCE_BIN,
    '--profile', 'web',
    '--patch', EXAMPLE_OVERLAY,
    '--patch', DEVFRAME_PATCH,
    '--patch', CANDIDATE_OVERLAY,
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

/** Assert every candidate row is mounted, enabled, and active. */
async function expectCandidateRowsActive(running: RunningWeb): Promise<void> {
  const url = new URL(running.launchUrl)
  const cookie = await exchangeLaunchCookie(running.launchUrl)
  const response = await postRpc(url.port, url.host, cookie, 'pluginInventory/list')
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
    expect(entry.enabled, moduleName).toBe(true)
    expect(entry.fiberPhase, moduleName).toBe('active')
  }
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
      // on request — the outcome is recorded, never assumed.
      expect(
        stop.signal === 'SIGTERM' || stop.exitCode === 0 || stop.exitCode === 1,
        `stop outcome ${JSON.stringify(stop)}`,
      ).toBe(true)

      // Second boot on the SAME home: the restart face the chain's controlled
      // restart rides — same home, same patches, fresh process.
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

  // Stage 2a: the session RPC envelope per the smoke-real remoteRpc helper —
  // payload wraps the method args, and args carries { request: {...} }.
  it('drives a session turn over the wire-level replay lane through the real RPC face', { timeout: 420_000 }, async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-candidate-fullchain-drive-'))
    const dshHome = join(root, '.dsh')
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

      const created = await postRpc(url.port, url.host, cookie, 'session/create', { args: { request: {} } })
      expect(created.status, `session/create status; body=${redact(created.body)}`).toBe(200)
      const createdValue = (JSON.parse(created.body) as { result?: { value?: { sessionId?: string } } }).result?.value
      if (createdValue?.sessionId === undefined) {
        throw new Error(`session/create returned no sessionId; body=${redact(created.body)}`)
      }
      const sessionId = createdValue.sessionId

      const prompt = 'candidate-driving-probe: reply with the marker and stop.'
      const prompted = await postRpc(url.port, url.host, cookie, 'session/prompt', { args: {
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
      const evidence = running?.output()
      throw new Error(`${error instanceof Error ? error.message : String(error)}${evidence === undefined ? '' : `\n${redact(evidence)}`}`, { cause: error })
    } finally {
      await replay.close()
      if (running !== undefined) await stopCandidateWeb(running)
      await rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })
    }
  })
})
