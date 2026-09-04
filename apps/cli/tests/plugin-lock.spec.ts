import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { delimiter, join } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { ensureProfileIdentity } from '@deepseek-ai/dsh-app-boot'
import { execa } from 'execa'
import { afterEach, describe, expect, it } from 'vitest'

const roots: string[] = []

function tempDir(prefix: string): string {
  const dir = mkdtempSync(join(tmpdir(), prefix))
  roots.push(dir)
  return dir
}

function writeFakePnpm(binDir: string): void {
  const script = join(binDir, 'fake-pnpm.mjs')
  writeFileSync(script, `
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { setTimeout as delay } from 'node:timers/promises'

const manifestPath = process.env.DSH_TEST_PLUGIN_MANIFEST
const packageName = process.env.DSH_TEST_PLUGIN_PACKAGE
if (manifestPath === undefined || packageName === undefined) throw new Error('missing fake-pnpm inputs')
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
manifest.dependencies = { ...manifest.dependencies, [packageName]: '1.0.0' }
writeFileSync(manifestPath, JSON.stringify(manifest, undefined, 2) + '\\n')
const entered = process.env.DSH_TEST_PLUGIN_ENTERED
const release = process.env.DSH_TEST_PLUGIN_RELEASE
if (entered !== undefined && release !== undefined) {
  writeFileSync(entered, 'entered\\n')
  const deadline = Date.now() + 5_000
  while (!existsSync(release)) {
    if (Date.now() >= deadline) throw new Error('fake pnpm timed out waiting for release')
    await delay(10)
  }
}
process.exit(Number(process.env.DSH_TEST_PLUGIN_EXIT ?? '0'))
`)
  const executable = join(binDir, 'pnpm')
  writeFileSync(executable, '#!/bin/sh\nexec node "$(dirname "$0")/fake-pnpm.mjs" "$@"\n')
  chmodSync(executable, 0o755)
  writeFileSync(join(binDir, 'pnpm.cmd'), `@echo off\r\n"${process.execPath}" "%~dp0fake-pnpm.mjs" %*\r\n`)
}

function createProfile(home: string, name: string, packageName: string): string {
  const profileDir = join(home, 'profiles', name)
  mkdirSync(join(profileDir, 'node_modules', packageName), { recursive: true })
  writeFileSync(join(profileDir, 'package.json'), JSON.stringify({
    name: `dsh-profile-${name}`,
    private: true,
    dependencies: {},
    dsh: { profile: { bundles: ['@deepseek-ai/dsh-base'] } },
  }, undefined, 2) + '\n')
  writeFileSync(join(profileDir, 'node_modules', packageName, 'package.json'), JSON.stringify({
    name: packageName,
    version: '1.0.0',
    dsh: { bundle: { patch: './cordis.patch.yml' } },
  }))
  return profileDir
}

function runPluginProcess(options: {
  home: string
  profile: string
  packageName: string
  binDir: string
  entered?: string
  release?: string
  exitCode?: number
}) {
  return execa(process.execPath, [
    '--import',
    'tsx/esm',
    'apps/cli/src/bin.ts',
    'plugin',
    '--profile',
    options.profile,
    'add',
    options.packageName,
  ], {
    cwd: process.cwd(),
    reject: false,
    env: {
      DSH_HOME: options.home,
      DSH_TEST_PLUGIN_MANIFEST: join(options.home, 'profiles', options.profile, 'package.json'),
      DSH_TEST_PLUGIN_PACKAGE: options.packageName,
      DSH_TEST_PLUGIN_EXIT: String(options.exitCode ?? 0),
      ...options.entered === undefined ? {} : { DSH_TEST_PLUGIN_ENTERED: options.entered },
      ...options.release === undefined ? {} : { DSH_TEST_PLUGIN_RELEASE: options.release },
      PATH: `${options.binDir}${delimiter}${process.env.PATH ?? ''}`,
    },
  })
}

async function waitForFile(filename: string): Promise<void> {
  const deadline = Date.now() + 5_000
  while (!existsSync(filename)) {
    if (Date.now() >= deadline) throw new Error(`timed out waiting for ${filename}`)
    await delay(10)
  }
}

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

describe('plugin manifest writer lock', () => {
  it('serializes pnpm and bundle reconciliation with profile UUID migration', async () => {
    const home = tempDir('dsh-plugin-lock-home-')
    const binDir = tempDir('dsh-plugin-lock-bin-')
    const packageName = 'locked-bundle'
    const profileDir = createProfile(home, 'locked', packageName)
    const entered = join(home, 'pnpm-entered')
    const release = join(home, 'pnpm-release')
    writeFakePnpm(binDir)

    const plugin = runPluginProcess({ home, profile: 'locked', packageName, binDir, entered, release })
    await waitForFile(entered)
    expect(existsSync(`${join(profileDir, 'package.json')}.lock`)).toBe(true)
    let identitySettled = false
    const identityResult = ensureProfileIdentity('dsh', 'locked', home)
      .finally(() => { identitySettled = true })
    await delay(200)
    const waitedForPluginWriter = !identitySettled
    writeFileSync(release, 'release\n')

    const [result, identity] = await Promise.all([plugin, identityResult])
    expect(waitedForPluginWriter).toBe(true)
    expect(result.exitCode).toBe(0)
    const manifest = JSON.parse(readFileSync(join(profileDir, 'package.json'), 'utf8')) as {
      dependencies: Record<string, string>
      dsh: { profile: { id?: string; bundles: string[] } }
    }
    expect(manifest.dsh.profile.id).toBe(identity.id)
    expect(manifest.dependencies).toEqual({ [packageName]: '1.0.0' })
    expect(manifest.dsh.profile.bundles).toEqual(['@deepseek-ai/dsh-base', packageName])
    expect(existsSync(`${join(profileDir, 'package.json')}.lock`)).toBe(false)
  }, 15_000)

  it('returns a failed pnpm code without reconciling bundle layers', async () => {
    const home = tempDir('dsh-plugin-failure-home-')
    const binDir = tempDir('dsh-plugin-failure-bin-')
    const packageName = 'failed-bundle'
    const profileDir = createProfile(home, 'failed', packageName)
    writeFakePnpm(binDir)

    const result = await runPluginProcess({
      home,
      profile: 'failed',
      packageName,
      binDir,
      exitCode: 23,
    })

    expect(result.exitCode).toBe(23)
    expect(result.stderr).toContain(`dsh: pnpm failed in profile directory ${profileDir}`)
    const manifest = JSON.parse(readFileSync(join(profileDir, 'package.json'), 'utf8')) as {
      dependencies: Record<string, string>
      dsh: { profile: { bundles: string[] } }
    }
    expect(manifest.dependencies).toEqual({ [packageName]: '1.0.0' })
    expect(manifest.dsh.profile.bundles).toEqual(['@deepseek-ai/dsh-base'])
    expect(existsSync(`${join(profileDir, 'package.json')}.lock`)).toBe(false)
  }, 15_000)
})
