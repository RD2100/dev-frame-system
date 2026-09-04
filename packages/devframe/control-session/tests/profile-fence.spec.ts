import { fork, type ChildProcess } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { hostname, tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { afterEach, describe, expect, it, vi } from 'vitest'

const fsFault = vi.hoisted(() => ({ failRenameCall: 0, renameCalls: 0 }))

vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>()
  return {
    ...actual,
    renameSync: (...args: Parameters<typeof actual.renameSync>) => {
      fsFault.renameCalls += 1
      if (fsFault.failRenameCall === fsFault.renameCalls) {
        throw Object.assign(new Error('transition busy'), { code: 'EACCES' })
      }
      actual.renameSync(...args)
    },
  }
})

import {
  acquireProfileHostFence,
  ProfileHostFenceError,
  profileHostFencePath,
} from '../src/profile-fence.ts'

const roots: string[] = []
const children = new Set<ChildProcess>()

function tempHome(): string {
  const home = mkdtempSync(join(tmpdir(), 'dsh-profile-host-fence-'))
  roots.push(home)
  return home
}

function ownerRecord(overrides: Partial<{
  version: number
  token: string
  pid: number
  hostname: string
  startedAt: string
}> = {}): string {
  return `${JSON.stringify({
    version: 1,
    token: randomUUID(),
    pid: process.pid,
    hostname: hostname().trim().toLowerCase(),
    startedAt: new Date().toISOString(),
    ...overrides,
  })}\n`
}

function writeFence(home: string, contents: string): string {
  const path = profileHostFencePath(home)
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, contents, { mode: 0o600 })
  return path
}

function waitForMessage(child: ChildProcess, type: string): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const onMessage = (message: unknown): void => {
      if (typeof message !== 'object' || message === null || !('type' in message)
        || (message as { type?: unknown }).type !== type) return
      cleanup()
      resolve(message)
    }
    const onError = (failure: Error): void => {
      cleanup()
      reject(failure)
    }
    const onExit = (code: number | null, signal: NodeJS.Signals | null): void => {
      cleanup()
      reject(new Error(`profile-fence child exited before ${type}: ${String(code)}/${String(signal)}`))
    }
    const cleanup = (): void => {
      child.off('message', onMessage)
      child.off('error', onError)
      child.off('exit', onExit)
    }
    child.on('message', onMessage)
    child.on('error', onError)
    child.on('exit', onExit)
  })
}

async function startHolder(home: string): Promise<ChildProcess> {
  const child = fork(join(import.meta.dirname, 'profile-fence-child.ts'), [home], {
    cwd: process.cwd(),
    execArgv: ['--import', 'tsx/esm'],
    silent: true,
  })
  children.add(child)
  child.once('exit', () => children.delete(child))
  await waitForMessage(child, 'ready')
  return child
}

function waitForExit(child: ChildProcess): Promise<void> {
  return new Promise((resolve, reject) => {
    if (child.exitCode !== null || child.signalCode !== null) {
      resolve()
      return
    }
    child.once('error', reject)
    child.once('exit', () => { resolve() })
  })
}

afterEach(async () => {
  vi.restoreAllMocks()
  const exits: Promise<void>[] = []
  for (const child of children) {
    exits.push(waitForExit(child))
    child.kill('SIGKILL')
  }
  await Promise.all(exits)
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

describe('Profile Host lifecycle fence', () => {
  it('rejects a second process while the same-host owner is alive', async () => {
    const home = tempHome()
    await startHolder(home)

    await expect(acquireProfileHostFence(home)).rejects.toMatchObject({ code: 'ACTIVE' })
  })

  it('allows a new owner after a normal release', async () => {
    const home = tempHome()
    const first = await acquireProfileHostFence(home)
    await first.release()

    const second = await acquireProfileHostFence(home)
    expect(second.owner.pid).toBe(process.pid)
    await second.release()
    expect(existsSync(profileHostFencePath(home))).toBe(false)
  })

  it('takes over only after the prior same-host process is dead', async () => {
    const home = tempHome()
    const child = await startHolder(home)
    const exit = waitForExit(child)
    child.kill('SIGKILL')
    await exit

    const recovered = await acquireProfileHostFence(home)
    expect(recovered.owner.pid).toBe(process.pid)
    await recovered.release()
  })

  it('fails closed for malformed and foreign-host owner records', async () => {
    const malformedHome = tempHome()
    const malformedPath = writeFence(malformedHome, '{"pid":1}\n')
    await expect(acquireProfileHostFence(malformedHome)).rejects.toMatchObject({ code: 'INVALID_RECORD' })
    expect(readFileSync(malformedPath, 'utf8')).toBe('{"pid":1}\n')

    const foreignHome = tempHome()
    const foreignPath = writeFence(foreignHome, ownerRecord({ hostname: 'remote-host.invalid' }))
    await expect(acquireProfileHostFence(foreignHome)).rejects.toMatchObject({ code: 'FOREIGN_HOST' })
    expect(readFileSync(foreignPath, 'utf8')).toContain('remote-host.invalid')
  })

  it('treats EPERM as a live owner instead of reclaiming it', async () => {
    const home = tempHome()
    const path = writeFence(home, ownerRecord({ pid: 424_242 }))
    vi.spyOn(process, 'kill').mockImplementation(() => {
      throw Object.assign(new Error('denied'), { code: 'EPERM' })
    })

    await expect(acquireProfileHostFence(home)).rejects.toMatchObject({ code: 'ACTIVE' })
    expect(existsSync(path)).toBe(true)
  })

  it('never removes a record whose ownership token changed', async () => {
    const home = tempHome()
    const fence = await acquireProfileHostFence(home)
    const replacement = ownerRecord()
    writeFileSync(profileHostFencePath(home), replacement, { mode: 0o600 })

    await expect(fence.release()).rejects.toBeInstanceOf(ProfileHostFenceError)
    await expect(fence.release()).rejects.toMatchObject({ code: 'NOT_OWNER' })
    expect(readFileSync(profileHostFencePath(home), 'utf8')).toBe(replacement)
  })

  it('can finish transition cleanup after a transient release failure', async () => {
    const home = tempHome()
    const fence = await acquireProfileHostFence(home)
    fsFault.renameCalls = 0
    fsFault.failRenameCall = 2

    await expect(fence.release()).rejects.toMatchObject({ code: 'FILESYSTEM' })
    await expect(fence.release()).rejects.toMatchObject({ code: 'NOT_OWNER' })
    expect(existsSync(profileHostFencePath(home))).toBe(false)

    fsFault.failRenameCall = 0
    const second = await acquireProfileHostFence(home)
    await second.release()
  })
})
