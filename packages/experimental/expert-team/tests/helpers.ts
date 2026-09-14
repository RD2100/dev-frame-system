/**
 * Shared test harness: fixture pack locations, temp copies for
 * mutation-based invalid cases, a config builder, and an error-code
 * assertion helper.
 * @module tests/helpers
 */

import { cp, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect } from 'vitest'
import { ExpertTeamError } from '../src/index.ts'
import type { ExpertTeamConfig, ExpertTeamErrorCode } from '../src/index.ts'

/** Absolute path of one shipped fixture pack under tests/fixtures. */
export function fixturePath(name: string): string {
  return fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url))
}

/**
 * Copy one fixture pack into a fresh temp directory so a test can corrupt
 * individual files.
 * @param name - Fixture directory name under tests/fixtures.
 * @returns the temp pack directory; the caller disposes it via {@link removeDir}.
 */
export async function copyFixturePack(name: string): Promise<string> {
  const target = await mkdtemp(join(tmpdir(), 'dsh-expert-team-'))
  await cp(fixturePath(name), target, { recursive: true })
  return target
}

/** Remove one temp directory tree created by {@link copyFixturePack}. */
export function removeDir(dir: string): Promise<void> {
  return rm(dir, { recursive: true, force: true })
}

/**
 * Build a valid catalog config over the given pack directories.
 * @param packs - Pack directories to mount.
 * @returns the config; artifactsDir points at a throwaway path.
 */
export function makeConfig(packs: readonly string[]): ExpertTeamConfig {
  return { packs: [...packs], artifactsDir: join(tmpdir(), 'dsh-expert-team-artifacts') }
}

/**
 * Assert that one call fails with an {@link ExpertTeamError} carrying
 * exactly the expected stable code.
 * @param run - The call under test; may throw synchronously or reject.
 * @param code - The expected `EXPERT_TEAM_*` code.
 */
export async function expectErrorCode(run: () => unknown, code: ExpertTeamErrorCode): Promise<void> {
  let failed = false
  try {
    await run()
  } catch (error: unknown) {
    failed = true
    expect(error).toBeInstanceOf(ExpertTeamError)
    expect((error as ExpertTeamError).code).toBe(code)
  }
  if (!failed) {
    throw new Error(`expected failure with code ${code}, but the call succeeded`)
  }
}
