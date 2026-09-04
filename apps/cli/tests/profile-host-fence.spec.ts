import { randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { execa, type ResultPromise } from 'execa'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import { acquireProfileHostFence, profileHostFencePath } from '@deepseek-ai/dsh-devframe-control-session'
import { resolveTaskModePatches } from '../src/profile-boot.ts'

const roots: string[] = []
type Child = ResultPromise
const running = new Set<Child>()
const cliEntry = fileURLToPath(new URL('../src/bin.ts', import.meta.url))
const tsxLoader = pathToFileURL(fileURLToPath(new URL('../../../node_modules/tsx/dist/esm/index.mjs', import.meta.url))).href

interface Fixture {
  home: string
  profile: string
  interrupt: string
  releaseOrder: string
  releaseVisibility: string
}

function createProfile(home: string, profile: string, devframe: boolean): void {
  const profileDir = join(home, 'profiles', profile)
  const bundleDir = join(profileDir, 'node_modules', 'profile-fence-fixture')
  mkdirSync(bundleDir, { recursive: true })
  writeFileSync(join(profileDir, 'package.json'), `${JSON.stringify({
    name: 'dsh-profile-fenced',
    private: true,
    dependencies: { 'profile-fence-fixture': '1.0.0' },
    dsh: { profile: { id: randomUUID(), bundles: ['profile-fence-fixture'] } },
  }, undefined, 2)}\n`)
  writeFileSync(join(profileDir, 'cordis.patch.yml'), '[]\n')
  writeFileSync(join(bundleDir, 'package.json'), `${JSON.stringify({
    name: 'profile-fence-fixture',
    version: '1.0.0',
    type: 'module',
    dsh: { bundle: { patch: './cordis.patch.yml' } },
  }, undefined, 2)}\n`)
  writeFileSync(join(bundleDir, 'cordis.patch.yml'), [
    '- insert:',
    `    - id: ${devframe ? 'devframe-control-session' : 'ordinary-lifecycle'}`,
    '      name: ./lifecycle.mjs',
    '',
  ].join('\n'))
  writeFileSync(join(profileDir, 'lifecycle.mjs'), [
    'import { existsSync, writeFileSync } from \'node:fs\'',
    'import { join } from \'node:path\'',
    'export function apply(ctx) {',
    '  const loaded = process.env.DSH_TEST_PROFILE_HOST_LOADED',
    '  if (loaded !== undefined) writeFileSync(loaded, \'loaded\\n\')',
    '  const releaseVisibility = process.env.DSH_TEST_PROFILE_HOST_RELEASE_VISIBILITY',
    '  if (releaseVisibility !== undefined) writeFileSync(releaseVisibility, String(typeof ctx.get(\'profileHostFence\')?.release))',
    '  const timer = setInterval(() => {',
    '    const interrupt = process.env.DSH_TEST_PROFILE_HOST_INTERRUPT',
    '    if (interrupt === undefined || !existsSync(interrupt)) return',
    '    clearInterval(timer)',
    '    if (process.platform === \'win32\') process.emit(\'SIGTERM\')',
    '    else process.kill(process.pid, \'SIGTERM\')',
    '  }, 10)',
    '  ctx.effect(() => async () => {',
    '    clearInterval(timer)',
    '    const home = process.env.DSH_HOME',
    '    const order = process.env.DSH_TEST_PROFILE_HOST_RELEASE_ORDER',
    '    if (home !== undefined && order !== undefined) writeFileSync(order, existsSync(join(home, \'devframe\', \'host-lease.json\')) ? \'lease-held\\n\' : \'lease-missing\\n\')',
    '  })',
    '}',
    '',
  ].join('\n'))
}

function createFixture(): Fixture {
  const home = mkdtempSync(join(tmpdir(), 'dsh-cli-profile-fence-'))
  roots.push(home)
  const profile = 'fenced-a'
  const interrupt = join(home, 'interrupt')
  const releaseOrder = join(home, 'release-order')
  const releaseVisibility = join(home, 'release-visibility')
  createProfile(home, profile, true)
  return { home, profile, interrupt, releaseOrder, releaseVisibility }
}

function startProfile(fixture: Fixture, loaded: string, profile = fixture.profile): Child {
  const child = execa(process.execPath, [
    '--import',
    tsxLoader,
    cliEntry,
    '--profile',
    profile,
  ], {
    cwd: process.cwd(),
    reject: false,
    env: {
      DSH_HOME: fixture.home,
      DSH_TEST_PROFILE_HOST_LOADED: loaded,
      DSH_TEST_PROFILE_HOST_INTERRUPT: fixture.interrupt,
      DSH_TEST_PROFILE_HOST_RELEASE_ORDER: fixture.releaseOrder,
      DSH_TEST_PROFILE_HOST_RELEASE_VISIBILITY: fixture.releaseVisibility,
    },
  }) as Child
  running.add(child)
  void child.finally(() => running.delete(child))
  return child
}

async function waitForFile(path: string): Promise<void> {
  const deadline = Date.now() + 10_000
  while (!existsSync(path)) {
    if (Date.now() >= deadline) throw new Error(`timed out waiting for ${path}`)
    await delay(10)
  }
}

afterEach(async () => {
  for (const child of running) child.kill('SIGKILL')
  await Promise.all([...running].map(child => child.catch(() => undefined)))
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

describe('CLI Profile Host fence', () => {
  it('disables the Web-only rows for the headless task command without disabling DevFrame control', () => {
    expect(resolveTaskModePatches([])).toEqual([])
    const taskPatches = resolveTaskModePatches(['task'])
    const disabled = new Set(taskPatches.filter(patch => patch.disabled).map(patch => patch.id))
    const byId = new Map(taskPatches.map(patch => [patch.id, patch]))
    expect(disabled.has('web-startup')).toBe(true)
    expect(disabled.has('webserver')).toBe(true)
    expect(disabled.has('client-ui-devframe-control-session')).toBe(true)
    expect(disabled.has('devframe-control-session')).toBe(false)
    expect(byId.get('tool-fs')?.disabled).toBe(false)
    expect(byId.get('tool-fs-search')?.disabled).toBe(false)
    expect(byId.get('tool-str-replace-editor')?.disabled).toBe(false)
  })

  it('blocks a second Host before its configuration plugin loads and releases after plugin teardown', async () => {
    const fixture = createFixture()
    const secondProfile = 'fenced-b'
    createProfile(fixture.home, secondProfile, true)
    const firstLoaded = join(fixture.home, 'first-loaded')
    const secondLoaded = join(fixture.home, 'second-loaded')
    const first = startProfile(fixture, firstLoaded)
    await waitForFile(firstLoaded)
    await waitForFile(fixture.releaseVisibility)
    expect(readFileSync(fixture.releaseVisibility, 'utf8')).toBe('undefined')

    const second = await startProfile(fixture, secondLoaded, secondProfile)
    expect(second.exitCode).not.toBe(0)
    expect(second.stderr).toContain('Profile Host blocked: ACTIVE')
    expect(existsSync(secondLoaded)).toBe(false)

    writeFileSync(fixture.interrupt, 'stop\n')
    const firstResult = await first
    expect(firstResult.exitCode).toBe(0)
    expect(readFileSync(fixture.releaseOrder, 'utf8')).toBe('lease-held\n')
    expect(existsSync(profileHostFencePath(fixture.home))).toBe(false)

    const reacquired = await acquireProfileHostFence(fixture.home)
    await reacquired.release()
  }, 30_000)

  it('does not fence a profile whose composed tree has no DevFrame Host row', async () => {
    const fixture = createFixture()
    const profile = 'ordinary'
    createProfile(fixture.home, profile, false)
    const loaded = join(fixture.home, 'ordinary-loaded')
    const child = startProfile(fixture, loaded, profile)
    await waitForFile(loaded)

    expect(existsSync(profileHostFencePath(fixture.home))).toBe(false)
    writeFileSync(fixture.interrupt, 'stop\n')
    const result = await child
    expect(result.exitCode).toBe(0)
    expect(readFileSync(fixture.releaseOrder, 'utf8')).toBe('lease-missing\n')
  }, 30_000)
})
