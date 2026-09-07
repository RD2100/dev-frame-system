/** Candidate-command harness for the shipped opt-in Cordis example overlay
 *  plus its private DevFrame profile layer: the real source CLI booted with
 *  two explicit root-level `--patch`es (the example overlay for the pinned
 *  3081 webserver and tool-cordis, then
 *  `packages/experimental/devframe-profile/cordis.patch.yml` for the six-row
 *  hierarchy stack) over an isolated harness home, its readiness line
 *  observed on the overlay's own pinned 3081 port, and a controlled teardown.
 *  The 总控 boundary governs what this harness may claim: these are opt-in
 *  overlays, not the web default bundle, so a run here never speaks for the
 *  default 3080 deployment, and a scaffold composeEntries run never
 *  substitutes for this candidate-command path.
 *  The dry-run test verifies the harness mechanism (boot, readiness,
 *  teardown); the full-candidate test additionally asserts every row from
 *  both patches mounted active through the real --patch (plugin-inventory
 *  RPC), including the hierarchy and dispatch rows. Zero model calls: the
 *  isolated home carries no credentials and no session starts.
 */

import type { ChildProcess } from 'node:child_process'
import { spawn } from 'node:child_process'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createRequire } from 'node:module'
import { request as httpRequest } from 'node:http'
import { pathToFileURL, fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const REPO_ROOT = fileURLToPath(new URL('../../..', import.meta.url))
const DSH_SOURCE_BIN = join(REPO_ROOT, 'apps/cli/src/bin.ts')
const TSX_LOADER = pathToFileURL(createRequire(join(REPO_ROOT, 'package.json')).resolve('tsx')).href
const EXAMPLE_OVERLAY = join(REPO_ROOT, 'apps/cli/config/examples/cordis/cordis.yml')
const DEVFRAME_PATCH = join(REPO_ROOT, 'packages/experimental/devframe-profile/cordis.patch.yml')
// The example overlay's own webserver row pins this port; the harness passes
// no --port so the readiness URL proves the overlay actually rode.
const OVERLAY_PORT = 3081
// Every row the two patches insert; the full candidate verification asserts
// each mounted enabled and active through the real --patch.
const OVERLAY_ROWS = [
  '@deepseek-ai/dsh-tool-cordis',
  '@deepseek-ai/dsh-experimental-session-identity',
  '@deepseek-ai/dsh-experimental-shadow-router',
  '@deepseek-ai/dsh-experimental-project-memory',
  '@deepseek-ai/dsh-experimental-command-goal-binding',
  '@deepseek-ai/dsh-experimental-agent-hierarchy',
  '@deepseek-ai/dsh-experimental-agent-dispatch',
]

interface RunningWeb {
  readonly child: ChildProcess
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

function cleanEnvironment(root: string, dshHome: string): NodeJS.ProcessEnv {
  const env = Object.fromEntries(Object.entries(process.env).filter(([name]) =>
    !/(?:KEY|SECRET|TOKEN|PASSWORD)/iu.test(name)))
  return {
    ...env,
    DSH_AGENTS_HOME: join(root, '.agents'),
    DSH_HOME: dshHome,
    DSH_TELEMETRY_DISABLED: '1',
    NODE_NO_WARNINGS: '1',
    SSH_CONNECTION: '',
    SSH_TTY: '',
    TSX_TSCONFIG_PATH: join(REPO_ROOT, 'tsconfig.json'),
  }
}

/** Start the real source CLI with both patches and await readiness. */
async function startCandidateWeb(root: string, dshHome: string): Promise<RunningWeb> {
  const child = spawn(process.execPath, [
    '--import', TSX_LOADER,
    DSH_SOURCE_BIN,
    '--profile', 'web',
    '--patch', EXAMPLE_OVERLAY,
    '--patch', DEVFRAME_PATCH,
    '--no-open',
  ], {
    cwd: REPO_ROOT,
    env: cleanEnvironment(root, dshHome),
    stdio: ['ignore', 'pipe', 'pipe'],
  })
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
    }, 90_000)
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
  return { child, launchUrl, output: () => output }
}

/** Controlled teardown: SIGTERM, then SIGKILL after a bounded grace. */
async function stopCandidateWeb(running: RunningWeb): Promise<void> {
  if (running.child.exitCode !== null) return
  const exited = new Promise<void>((resolve) => { running.child.once('exit', () => { resolve() }) })
  running.child.kill('SIGTERM')
  const forced = setTimeout(() => { running.child.kill('SIGKILL') }, 10_000)
  forced.unref()
  await exited
  clearTimeout(forced)
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
function postRpc(port: number, host: string, cookie: string, method: string): Promise<HttpResult> {
  const body = JSON.stringify({
    type: 'client-request',
    rpcId: 'cordis-example-candidate',
    method,
    payload: { args: {} },
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

describe('candidate command: shipped opt-in Cordis example overlay', () => {
  it('dry run: boots to readiness on the overlay-pinned 3081 and tears down clean', { timeout: 180_000 }, async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-cordis-example-candidate-'))
    const dshHome = join(root, '.dsh')
    let running: RunningWeb | undefined
    try {
      running = await startCandidateWeb(root, dshHome)
      const url = new URL(running.launchUrl)
      expect(url.origin).toBe(`http://127.0.0.1:${String(OVERLAY_PORT)}`)
      expect(url.pathname).toBe('/')
    } catch (error) {
      const evidence = running?.output()
      throw new Error(`${error instanceof Error ? error.message : String(error)}${evidence === undefined ? '' : `\n${redact(evidence)}`}`, { cause: error })
    } finally {
      if (running !== undefined) await stopCandidateWeb(running)
      await rm(root, { recursive: true, force: true })
    }
  })

  it('full candidate: the overlay rows mount active through the real --patch', { timeout: 180_000 }, async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-cordis-example-candidate-'))
    const dshHome = join(root, '.dsh')
    let running: RunningWeb | undefined
    try {
      running = await startCandidateWeb(root, dshHome)
      const url = new URL(running.launchUrl)
      expect(url.origin).toBe(`http://127.0.0.1:${String(OVERLAY_PORT)}`)
      const cookie = await exchangeLaunchCookie(running.launchUrl)
      const response = await postRpc(OVERLAY_PORT, url.host, cookie, 'pluginInventory/list')
      expect(response.status).toBe(200)
      const parsed = JSON.parse(response.body) as {
        type: string
        result: { ok: boolean; value: { entries: { moduleName: string; enabled: boolean; fiberPhase: string | null }[] } }
      }
      expect(parsed.type).toBe('server-response')
      expect(parsed.result.ok).toBe(true)
      const mounted = new Map(parsed.result.value.entries.map(entry => [entry.moduleName, entry]))
      for (const moduleName of OVERLAY_ROWS) {
        const entry = mounted.get(moduleName)
        if (entry === undefined) {
          throw new Error(`overlay row ${moduleName} is not in the loader inventory; mounted=${JSON.stringify([...mounted.keys()])}`)
        }
        expect(entry.enabled, moduleName).toBe(true)
        expect(entry.fiberPhase, moduleName).toBe('active')
      }
    } catch (error) {
      const evidence = running?.output()
      throw new Error(`${error instanceof Error ? error.message : String(error)}${evidence === undefined ? '' : `\n${redact(evidence)}`}`, { cause: error })
    } finally {
      if (running !== undefined) await stopCandidateWeb(running)
      await rm(root, { recursive: true, force: true })
    }
  })
})
