import { execa, type ResultPromise } from 'execa'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { afterEach, describe, expect, it } from 'vitest'
import { createZstdFrameDecoder, scanZstdFrames } from '../../../packages/session/session-persistence-jsonl/src/zstd.ts'

interface ControllerIdentity {
  readonly schemaVersion: 1
  readonly role: 'global'
  readonly sessionId: string
  readonly profileId: string
  readonly cwd: string
}

interface ControllerLog {
  readonly path: string
  readonly headerId: string
  readonly identities: readonly ControllerIdentity[]
}

function readSessionText(path: string): string {
  const bytes = readFileSync(path)
  if (!path.endsWith('.zstd')) return bytes.toString('utf8')
  const { frames } = scanZstdFrames(bytes)
  const decoder = createZstdFrameDecoder()
  try {
    const chunks: Buffer[] = []
    for (const chunk of decoder.decode(bytes, frames)) chunks.push(Buffer.from(chunk))
    return Buffer.concat(chunks).toString('utf8')
  } finally {
    decoder.close()
  }
}

const roots: string[] = []
type Child = ResultPromise
const running = new Set<Child>()
const output = new WeakMap<Child, { stdout: string; stderr: string }>()
const requireBuiltArtifacts = process.env.DSH_REQUIRE_BUILT_CLI_SMOKE === '1'
const cliEntry = fileURLToPath(new URL(requireBuiltArtifacts ? '../lib/bin.js' : '../src/bin.ts', import.meta.url))
const tsxLoader = pathToFileURL(fileURLToPath(new URL('../../../node_modules/tsx/dist/esm/index.mjs', import.meta.url))).href

function collectSessionLogs(root: string): ControllerLog[] {
  if (!existsSync(root)) return []
  const logs: ControllerLog[] = []
  const visit = (directory: string): void => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name)
      if (entry.isDirectory()) {
        visit(path)
        continue
      }
      if (entry.name !== 'session.jsonl' && entry.name !== 'session.jsonl.zstd') continue
      let lines: string[]
      try {
        lines = readSessionText(path).trimEnd().split('\n').filter(Boolean)
      } catch {
        continue
      }
      const header = lines[0] === undefined ? undefined : JSON.parse(lines[0]) as { id?: unknown }
      if (typeof header?.id !== 'string') continue
      const identities: ControllerIdentity[] = []
      for (const line of lines.slice(1)) {
        let record: unknown
        try {
          record = JSON.parse(line)
        } catch {
          continue
        }
        if (typeof record !== 'object' || record === null || !('type' in record) || !('data' in record)) continue
        const value = record as { type?: unknown; data?: unknown }
        if (value.type !== 'controller/identity' || typeof value.data !== 'object' || value.data === null) continue
        const identity = value.data as Partial<ControllerIdentity>
        if (identity.role === 'global' && identity.schemaVersion === 1
          && typeof identity.sessionId === 'string' && typeof identity.profileId === 'string'
          && typeof identity.cwd === 'string') {
          identities.push(identity as ControllerIdentity)
        }
      }
      if (identities.length > 0) logs.push({ path, headerId: header.id, identities })
    }
  }
  visit(root)
  return logs
}

async function waitForControllerLog(home: string, child: Child): Promise<ControllerLog> {
  const deadline = Date.now() + 60_000
  while (Date.now() < deadline) {
    const log = collectSessionLogs(join(home, 'sessions')).find(value => value.identities.length > 0)
    if (log !== undefined) return log
    await delay(50)
  }
  const captured = output.get(child)
  throw new Error(`timed out waiting for Global Controller JSONL under ${join(home, 'sessions')}\nstdout:\n${captured?.stdout ?? ''}\nstderr:\n${captured?.stderr ?? ''}`)
}

function startProfile(home: string, cwd: string): Child {
  const child = execa(process.execPath, [
    ...(requireBuiltArtifacts ? [] : ['--import', tsxLoader]),
    cliEntry,
    '--profile',
    'devframe',
    '--host',
    '127.0.0.1',
    '--port',
    '0',
  ], {
    cwd,
    env: {
      ...process.env,
      DSH_HOME: home,
      DSH_TELEMETRY_DISABLED: '1',
    },
    reject: false,
  }) as Child
  const captured = { stdout: '', stderr: '' }
  output.set(child, captured)
  child.stdout?.on('data', (chunk: string) => { captured.stdout += chunk })
  child.stderr?.on('data', (chunk: string) => { captured.stderr += chunk })
  running.add(child)
  void child.finally(() => running.delete(child))
  return child
}

async function stopProfile(child: Child): Promise<void> {
  child.kill('SIGTERM')
  const result = await child
  // Windows reports a signal-terminated child without a numeric exit code;
  // the persistence assertions above are the lifecycle contract under test.
  expect(result.exitCode === 0 || result.signal === 'SIGTERM').toBe(true)
}

afterEach(async () => {
  for (const child of running) child.kill('SIGKILL')
  await Promise.all([...running].map(child => child.catch(() => undefined)))
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

describe.skipIf(!requireBuiltArtifacts)('real dsh devframe profile bootstrap', () => {
  it('opens and resumes one Global Controller through the CLI and JSONL persistence', async () => {
    const home = mkdtempSync(join(tmpdir(), 'dsh-devframe-profile-'))
    roots.push(home)
    const firstCwd = mkdtempSync(join(tmpdir(), 'dsh-devframe-cwd-a-'))
    const secondCwd = mkdtempSync(join(tmpdir(), 'dsh-devframe-cwd-b-'))
    roots.push(firstCwd, secondCwd)

    const first = startProfile(home, firstCwd)
    const initial = await waitForControllerLog(home, first)
    expect(initial.headerId).toBe(initial.identities[0]?.sessionId)
    expect(initial.identities).toHaveLength(1)
    expect(initial.identities[0]).toMatchObject({ role: 'global', schemaVersion: 1 })
    expect(initial.identities[0]?.sessionId).toMatch(/^devframe-global:/u)
    expect(initial.identities[0]?.cwd).toContain('devframe-control')
    await stopProfile(first)

    const second = startProfile(home, secondCwd)
    const resumed = await waitForControllerLog(home, second)
    expect(resumed.path).toBe(initial.path)
    expect(resumed.headerId).toBe(initial.headerId)
    expect(resumed.identities).toEqual(initial.identities)
    await stopProfile(second)
  }, 150_000)
})
