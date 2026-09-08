/** Keyless built-launch SDK transport for delayed native Goal activation. */
import { createServer, type Server } from 'node:http'
import { existsSync } from 'node:fs'
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { expect, it, vi } from 'vitest'
import { DeepSeekHarness, JsonRpcResponseError } from '../src/index.ts'
import type { HarnessNotification, NotificationSubscription } from '../src/index.ts'

const repo = fileURLToPath(new URL('../../../../', import.meta.url))

/** Read this test's single durable session, preserving event payloads verbatim. */
async function durableGoalEvents(directory: string): Promise<unknown[]> {
  const logs = (await readdir(directory, { recursive: true })).filter(path => path.endsWith('.jsonl'))
  expect(logs).toHaveLength(1)
  const text = await readFile(join(directory, logs[0] as string), 'utf8')
  return text.trim().split('\n').map(line => JSON.parse(line) as { type: string; data: unknown })
    .filter(event => event.type === 'goal/change').map(event => event.data)
}

/** Bound all waits below the outer test budget so failures execute owned cleanup. */
async function bounded<T>(work: Promise<T>, label: string, deadline: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([work, new Promise<never>((_resolve, reject) => {
      timer = setTimeout(() => { reject(new Error(label + ' timed out')) }, Math.max(1, Math.min(20_000, deadline - Date.now())))
    })])
  } finally { clearTimeout(timer) }
}

/** Observe the OS after SDK-owned termination, without sending a termination signal. */
function processPresent(pid: number): boolean {
  try { process.kill(pid, 0); return true } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ESRCH') return false
    throw error
  }
}

/** Run one public-client lifecycle, retaining cleanup on setup and pre-barrier failures. */
async function probeResume(rejectBeforeHeld = false): Promise<void> {
  const root = await mkdtemp(join(tmpdir(), 'dsh-sdk-goal-resume-'))
  const deadline = Date.now() + 60_000
  const sessions = join(root, 'home', 'sessions')
  let server: Server | undefined
  let harness: DeepSeekHarness | undefined
  let subscription: NotificationSubscription | undefined
  let pid: number | undefined
  const entered = Promise.withResolvers<Record<string, unknown>>()
  const release = Promise.withResolvers<undefined>()
  const requests: unknown[] = []
  let durable = false
  let held = false
  let serverError: unknown
  try {
    server = createServer((request, response) => {
      void (async () => {
        let body = ''
        for await (const chunk of request) body += String(chunk)
        if (request.url === '/held') {
          held = true
          entered.resolve(JSON.parse(body) as Record<string, unknown>)
          await release.promise
          response.end('released')
        } else if (request.url === '/durable') {
          const events = await durableGoalEvents(sessions)
          expect(events.at(-1)).toMatchObject({ operation: 'resume', goal: { phase: 'active', revision: 3 } })
          durable = true
          response.end('durable')
        } else if (request.url === '/chat/completions') {
          requests.push(JSON.parse(body) as unknown)
          if (requests.length > 1) expect(durable).toBe(true)
          response.setHeader('content-type', 'text/event-stream')
          response.end('data: '+JSON.stringify({ choices: [{ delta: { role: 'assistant', content: 'resume transport ok' } }] })+'\n\n'
          +'data: '+JSON.stringify({ choices: [{ delta: {}, finish_reason: 'stop' }], usage: { prompt_tokens: 1, completion_tokens: 1 } })+'\n\n'
          +'data: [DONE]\n\n')
        } else { response.statusCode = 404; response.end() }
      })().catch((error: unknown) => { serverError = error; response.statusCode = 500; response.end('probe failed') })
    })
    const ownedServer = server
    await bounded(new Promise<void>((resolve, reject) => {
      ownedServer.once('error', reject)
      ownedServer.listen(0, '127.0.0.1', resolve)
    }), 'HTTP listener', deadline)
    const address = server.address()
    if (address === null || typeof address === 'string') throw new Error('test server did not bind TCP')
    const url = `http://127.0.0.1:${address.port}`
    const patch = join(root, 'resume.patch.json')
    await writeFile(patch, JSON.stringify([
      { id: 'session-persistence-jsonl', config: { root: sessions, compression: 'none' } },
      { id: 'session-telemetry-otel', disabled: true },
      { insert: [{ id: 'sdk-resume-probe', name: pathToFileURL(join(repo, 'scripts/fixtures/python-sdk-task-delivery.mjs')).href,
        config: { resumeBarrierUrl: url } }] },
    ]))
    harness = new DeepSeekHarness({
      dshBin: join(repo, 'apps/cli/lib/bin.js'), profile: 'sdk', patches: [patch],
      cwd: root, processCwd: root, dshHome: join(root, 'home'),
      provider: 'deepseek-official', model: 'smoke-model', requestTimeoutMs: 60_000,
      env: { ...process.env, DSH_HOME: join(root, 'home'), DSH_TELEMETRY_DISABLED: '1',
        DSH_PERMISSION_MODE: 'danger-full-access', DEEPSEEK_API_KEY: 'sk-keyless-smoke', DEEPSEEK_BASE_URL: url },
    })
    subscription = harness.client.subscribe()
    const notifications: HarnessNotification[] = []
    const first = await bounded(harness.run('Prepare a paused transport goal.', { sessionId: 'sdk-goal-resume' }), 'initial SDK run', deadline)
    pid = Number(await readFile(join(root, 'resume-probe.pid'), 'utf8'))
    expect(first.finalResponse).toBe('resume transport ok')
    expect(requests).toHaveLength(1)
    expect(first.events.filter(event => event.type === 'goal/change').map(event => event.data))
      .toEqual(await durableGoalEvents(sessions))
    const resuming = harness.run(rejectBeforeHeld ? [{ type: 'image', data: 'invalid-base64!', mimeType: 'image/png' }] : 'Resume the paused transport goal.', { sessionId: first.sessionId })
    const endedBeforeHeld = resuming.then(() => { throw new Error('Resume settled before its held barrier') })
    const barrier = bounded(Promise.race([entered.promise, endedBeforeHeld]), 'resume held barrier', deadline)
    if (rejectBeforeHeld) {
      await expect(barrier).rejects.toBeInstanceOf(JsonRpcResponseError)
      await expect(barrier).rejects.toHaveProperty('message', 'Image upload is not canonical base64.')
      expect(held).toBe(false)
      expect(durable).toBe(false)
      expect(requests).toHaveLength(1)
      return
    }
    expect(await barrier).toMatchObject({ phase: 'active', activation: 'disarmed', revision: 3 })
    expect(requests).toHaveLength(1)
    expect(durable).toBe(false)
    release.resolve(undefined)
    await bounded(resuming, 'resume SDK run', deadline)
    const activeSubscription = subscription
    await bounded((async () => {
      let finished = false
      while (!finished) {
        const note = await activeSubscription.next()
        notifications.push(note)
        if (note.method === 'session.event') {
          const event = note.params.event as { type?: string; data?: { operation?: string } }
          finished = event.type === 'goal/change' && event.data?.operation === 'block'
        }
      }
    })(), 'terminal Goal notification', deadline)
    await harness.close()
    expect(serverError).toBeUndefined()
    expect(durable).toBe(true)
    expect(requests).toHaveLength(2)
    const streamed = notifications.filter(note => note.method === 'session.event')
      .map(note => note.params.event as { type: string; data: unknown })
      .filter(event => event.type === 'goal/change').map(event => event.data)
    expect(streamed).toEqual(await durableGoalEvents(sessions))
    expect(streamed).toMatchObject([
      { operation: 'create', goal: { phase: 'active', revision: 1 } },
      { operation: 'pause', goal: { phase: 'paused', revision: 2 } },
      { operation: 'resume', goal: { phase: 'active', revision: 3 } },
      { operation: 'block', goal: { phase: 'blocked', revision: 4 } },
    ])
  } finally {
    release.resolve(undefined)
    subscription?.close()
    try { await harness?.close() } finally {
      try {
        if (server !== undefined) {
          server.closeAllConnections()
          const ownedServer = server
          if (ownedServer.listening) await new Promise<void>((resolve, reject) => {
            ownedServer.close((error) => { if (error) reject(error); else resolve() })
          })
          expect(ownedServer.listening).toBe(false)
        }
        if (pid !== undefined) {
          const ownedPid = pid
          await vi.waitFor(() => { expect(processPresent(ownedPid)).toBe(false) }, { timeout: 5_000 })
        }
      } finally {
        await rm(root, { recursive: true, force: true })
        expect(existsSync(root)).toBe(false)
      }
    }
  }
}

it('carries paused and durable deferred resume through the public SDK before one continuation', { timeout: 90_000 }, async () => {
  await probeResume()
})

it('closes the CLI and HTTP listener when resume rejects before the held barrier', { timeout: 90_000 }, async () => {
  await probeResume(true)
})
