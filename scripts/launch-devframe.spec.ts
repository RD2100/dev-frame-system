import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs'
import { spawn } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const launcher = await import(new URL('./launch-devframe.mjs', import.meta.url).href) as {
  buildDevFrameCliArgs: (forwarded: readonly string[], options?: { cli?: string; port?: string }) => string[]
}
const repoRoot = resolve(fileURLToPath(new URL('..', import.meta.url)))
const dshBin = join(repoRoot, 'apps', 'cli', 'lib', 'bin.js')
const launcherPath = join(repoRoot, 'scripts', 'launch-devframe.mjs')

interface ProcessProbeResult {
  stdout: string
  stderr: string
  code: number | null
}

/** Run one Node entrypoint until it prints its loopback URL, then stop it. */
async function runNodeUntilWebUrl(
  entrypoint: string,
  args: readonly string[],
  env: Record<string, string>,
): Promise<ProcessProbeResult> {
  const child = spawn(process.execPath, [entrypoint, ...args], {
    cwd: repoRoot,
    env: { ...process.env, ...env },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  let stdout = ''
  let stderr = ''
  let stopped = false
  let timer: ReturnType<typeof setTimeout> | undefined
  const stop = (): void => {
    if (stopped) return
    stopped = true
    child.kill('SIGTERM')
    timer = setTimeout(() => {
      if (child.exitCode === null) child.kill('SIGKILL')
    }, 3_000)
  }
  return await new Promise<ProcessProbeResult>((resolveProbe, rejectProbe) => {
    const deadline = setTimeout(() => {
      stop()
      rejectProbe(new Error(`built DevFrame profile did not print a Web URL. stdout:\n${stdout}\nstderr:\n${stderr}`))
    }, 20_000)
    child.stdout.on('data', (chunk: Buffer) => {
      stdout += String(chunk)
      if (/dsh web: http:\/\/127\.0\.0\.1:\d+/.test(stdout)) stop()
    })
    child.stderr.on('data', (chunk: Buffer) => { stderr += String(chunk) })
    child.on('error', (error) => {
      clearTimeout(deadline)
      if (timer !== undefined) clearTimeout(timer)
      rejectProbe(error)
    })
    child.on('exit', (code) => {
      clearTimeout(deadline)
      if (timer !== undefined) clearTimeout(timer)
      resolveProbe({ stdout, stderr, code })
    })
  })
}

/** Run the built profile until it prints its loopback URL, then stop it. */
async function runBuiltUntilWebUrl(args: readonly string[], env: Record<string, string>): Promise<ProcessProbeResult> {
  return await runNodeUntilWebUrl(dshBin, args, env)
}

/** Run the desktop launcher until its built child prints the loopback URL. */
async function runDesktopUntilWebUrl(args: readonly string[], env: Record<string, string>): Promise<ProcessProbeResult> {
  return await runNodeUntilWebUrl(launcherPath, args, env)
}

/** Run a bounded built invocation to completion and retain both output streams. */
async function runBuiltToExit(args: readonly string[], env: Record<string, string>): Promise<ProcessProbeResult> {
  const child = spawn(process.execPath, [dshBin, ...args], {
    cwd: repoRoot,
    env: { ...process.env, ...env },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  let stdout = ''
  let stderr = ''
  return await new Promise<ProcessProbeResult>((resolveProbe, rejectProbe) => {
    const deadline = setTimeout(() => {
      child.kill('SIGKILL')
      rejectProbe(new Error(`built DevFrame invocation did not exit. stdout:\n${stdout}\nstderr:\n${stderr}`))
    }, 20_000)
    child.stdout.on('data', (chunk: Buffer) => { stdout += String(chunk) })
    child.stderr.on('data', (chunk: Buffer) => { stderr += String(chunk) })
    child.on('error', (error) => {
      clearTimeout(deadline)
      rejectProbe(error)
    })
    child.on('exit', (code) => {
      clearTimeout(deadline)
      resolveProbe({ stdout, stderr, code })
    })
  })
}

function filesUnder(root: string, relative = ''): string[] {
  const current = join(root, relative)
  return readdirSync(current, { withFileTypes: true }).flatMap((entry) => {
    const next = join(relative, entry.name)
    return entry.isDirectory() ? filesUnder(root, next) : [next]
  })
}

describe('DevFrame desktop launcher argv', () => {
  it('boots the formal devframe profile without the deprecated web patch alias', () => {
    expect(launcher.buildDevFrameCliArgs([], { cli: 'apps/cli/lib/bin.js', port: '3088' })).toEqual([
      'apps/cli/lib/bin.js',
      '--profile', 'devframe',
      '--port', '3088',
    ])
  })

  it('passes ordinary Web arguments after the launcher-owned flags', () => {
    expect(launcher.buildDevFrameCliArgs(['--host', '127.0.0.1'], { cli: 'dsh', port: '0' })).toEqual([
      'dsh',
      '--profile', 'devframe',
      '--port', '0',
      '--host', '127.0.0.1',
    ])
  })

  it('forwards an explicit profile unchanged and does not inject devframe', () => {
    expect(launcher.buildDevFrameCliArgs(['--profile', 'web'], { cli: 'dsh', port: '0' })).toEqual([
      'dsh',
      '--profile', 'web',
      '--port', '0',
    ])
  })
})

describe.skipIf(!existsSync(dshBin))('DevFrame built profile real path', () => {
  it('accepts ordinary Web --port through the formal profile and reaches a URL', async () => {
    const home = mkdtempSync(join(tmpdir(), 'dsh-devframe-web-probe-'))
    try {
      const result = await runBuiltUntilWebUrl(['--profile', 'devframe', '--port', '0'], {
        DSH_HOME: home,
        DSH_TELEMETRY_DISABLED: '1',
      })
      const firstIdentity = (JSON.parse(readFileSync(join(home, 'profiles', 'devframe', 'package.json'), 'utf8')) as {
        dsh?: { profile?: { id?: string } }
      }).dsh?.profile?.id
      const restart = await runDesktopUntilWebUrl(['--port', '0'], {
        DSH_HOME: home,
        DSH_TELEMETRY_DISABLED: '1',
        DSH_DESKTOP_SKIP_BROWSER: '1',
      })
      const secondIdentity = (JSON.parse(readFileSync(join(home, 'profiles', 'devframe', 'package.json'), 'utf8')) as {
        dsh?: { profile?: { id?: string } }
      }).dsh?.profile?.id
      expect(result.stdout).toMatch(/dsh web: http:\/\/127\.0\.0\.1:\d+/)
      expect(restart.stdout).toMatch(/dsh web: http:\/\/127\.0\.0\.1:\d+/)
      expect(restart.stdout).not.toContain('unknown option --port')
      expect(restart.stderr).not.toContain('unknown option --port')
      expect(firstIdentity).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u)
      expect(secondIdentity).toBe(firstIdentity)
      expect(result.stdout).not.toContain('unknown option --port')
      expect(result.stderr).not.toContain('unknown option --port')
    } finally {
      rmSync(home, { recursive: true, force: true })
    }
  }, 30_000)

  it('rejects the default task before creating a task Session or writing the project', async () => {
    const home = mkdtempSync(join(tmpdir(), 'dsh-devframe-task-gate-'))
    const project = mkdtempSync(join(tmpdir(), 'dsh-devframe-task-project-'))
    try {
      const result = await runBuiltToExit([
        '--profile', 'devframe',
        'task',
        '--project', project,
        '--objective', 'inspect',
      ], {
        DSH_HOME: home,
        DSH_TELEMETRY_DISABLED: '1',
        DSH_DEVFRAME_EXPERIMENTAL_TASKS: '',
      })
      expect(result.code).toBe(1)
      expect(result.stderr).toContain('DSH_DEVFRAME_EXPERIMENTAL_TASKS=1')
      expect(filesUnder(project)).toEqual([])
      const durableSessionFiles = filesUnder(home).filter(file =>
        /(^|[\\/])(session|sessions)([\\/]|$)|\.(jsonl|sqlite(?:-shm|-wal)?)$/iu.test(file))
      expect(durableSessionFiles).toEqual([])
    } finally {
      rmSync(home, { recursive: true, force: true })
      rmSync(project, { recursive: true, force: true })
    }
  }, 30_000)
})
