import { createHash } from 'node:crypto'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  DESKTOP_PACKAGES_DIR,
  DESKTOP_PACKAGE_SET_FILE,
  desktopCorePackageOverrides,
  desktopDshPackageSpec,
  DESKTOP_DEVFRAME_PROFILE_PACKAGE,
  parseDesktopCorePackageSet,
  verifyDesktopCoreLockfile,
  verifyDesktopCorePackageSet,
  type DesktopCorePackageRecord,
} from '../src/core-package-set.ts'

const roots: string[] = []

function record(name: string, file: string, body: Buffer, version = '1.2.3'): DesktopCorePackageRecord {
  return {
    name,
    version,
    file,
    bytes: body.byteLength,
    integrity: `sha512-${createHash('sha512').update(body).digest('base64')}`,
  }
}

function packageSetProject(): {
  root: string
  dsh: DesktopCorePackageRecord
  base: DesktopCorePackageRecord
  host: DesktopCorePackageRecord
  profile: DesktopCorePackageRecord
} {
  const root = mkdtempSync(join(tmpdir(), 'dsh-desktop-package-set-'))
  roots.push(root)
  const packageDir = join(root, DESKTOP_PACKAGES_DIR)
  mkdirSync(packageDir)
  const dshBody = Buffer.from('dsh')
  const baseBody = Buffer.from('base')
  const hostBody = Buffer.from('host')
  const profileBody = Buffer.from('devframe-profile')
  const dsh = record('@deepseek-ai/dsh', 'dsh.tgz', dshBody)
  const base = record('@deepseek-ai/dsh-base', 'dsh-base.tgz', baseBody)
  const host = record('@deepseek-ai/dsh-desktop-host', 'dsh-desktop-host.tgz', hostBody)
  const profile = record(DESKTOP_DEVFRAME_PROFILE_PACKAGE, 'dsh-experimental-devframe-profile.tgz', profileBody)
  writeFileSync(join(packageDir, dsh.file), dshBody)
  writeFileSync(join(packageDir, base.file), baseBody)
  writeFileSync(join(packageDir, host.file), hostBody)
  writeFileSync(join(packageDir, profile.file), profileBody)
  writeFileSync(join(root, DESKTOP_PACKAGE_SET_FILE), `${JSON.stringify({
    schemaVersion: 1,
    packages: [dsh, base, host, profile].sort((left, right) => left.name.localeCompare(right.name)),
  })}\n`)
  return { root, dsh, base, host, profile }
}

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

describe('desktop core package set', () => {
  it('pins the direct dsh dependency and every internal package to local tarballs', () => {
    const { root } = packageSetProject()
    const packageSet = verifyDesktopCorePackageSet(root, '1.2.3')
    expect(desktopDshPackageSpec(packageSet)).toBe('file:./desktop-packages/dsh.tgz')
    expect(desktopCorePackageOverrides(packageSet)).toEqual({
      '@deepseek-ai/dsh': 'file:./desktop-packages/dsh.tgz',
      '@deepseek-ai/dsh-base': 'file:./desktop-packages/dsh-base.tgz',
      '@deepseek-ai/dsh-desktop-host': 'file:./desktop-packages/dsh-desktop-host.tgz',
      '@deepseek-ai/dsh-experimental-devframe-profile': 'file:./desktop-packages/dsh-experimental-devframe-profile.tgz',
    })
  })

  it('rejects version drift, descriptor disorder, corruption, and extra files', () => {
    const { root, dsh, base, host, profile } = packageSetProject()
    expect(() => verifyDesktopCorePackageSet(root, '2.0.0')).toThrow(/does not match Desktop/u)
    expect(() => parseDesktopCorePackageSet({
      schemaVersion: 1,
      packages: [dsh, base, profile, { ...host, version: '2.0.0' }].sort((left, right) => left.name.localeCompare(right.name)),
    }, '1.2.3')).toThrow(/dsh-desktop-host@2\.0\.0 does not match Desktop 1\.2\.3/u)
    expect(() => parseDesktopCorePackageSet({ schemaVersion: 1, packages: [base, dsh, host, profile] }))
      .toThrow(/sorted by name/u)
    writeFileSync(join(root, DESKTOP_PACKAGES_DIR, dsh.file), 'changed')
    expect(() => verifyDesktopCorePackageSet(root, '1.2.3')).toThrow(/integrity check failed/u)
    writeFileSync(join(root, DESKTOP_PACKAGES_DIR, 'extra.tgz'), '')
    expect(() => verifyDesktopCorePackageSet(root, '1.2.3')).toThrow(/does not match its descriptor/u)
  })

  it('rejects registry resolutions for names supplied by the local package set', () => {
    const dsh = record('@deepseek-ai/dsh', 'dsh.tgz', Buffer.from('dsh'))
    const host = record('@deepseek-ai/dsh-desktop-host', 'host.tgz', Buffer.from('host'))
    const profile = record(DESKTOP_DEVFRAME_PROFILE_PACKAGE, 'profile.tgz', Buffer.from('profile'))
    const packageSet = parseDesktopCorePackageSet({
      schemaVersion: 1,
      packages: [dsh, host, profile].sort((left, right) => left.name.localeCompare(right.name)),
    })
    expect(() => {
      verifyDesktopCoreLockfile(
        "packages:\n  '@deepseek-ai/dsh@file:desktop-packages/dsh.tgz':\n    resolution: {}\n",
        packageSet,
      )
    }).not.toThrow()
    expect(() => {
      verifyDesktopCoreLockfile(
        "packages:\n  '@deepseek-ai/dsh@1.2.3':\n    resolution: {integrity: sha512-registry}\n",
        packageSet,
      )
    }).toThrow(/outside the local package set/u)
  })
})
