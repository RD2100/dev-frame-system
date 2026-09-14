/**
 * Config unit behavior: `validateExpertTeamConfig` enforces the loader
 * contract — packs is a non-empty array of clean path strings,
 * artifactsDir is a clean path string — and fails loud with
 * `EXPERT_TEAM_CONFIG_INVALID` on every violation.
 */

import { describe, expect, it } from 'vitest'
import { validateExpertTeamConfig } from '../src/index.ts'
import type { ExpertTeamConfig } from '../src/index.ts'
import { expectErrorCode } from './helpers.ts'

/** The tab as a real control character for violation cases. */
const TAB = String.fromCharCode(9)

describe('valid config', () => {
  it('returns a defensive copy for a clean config', () => {
    const config: ExpertTeamConfig = { packs: ['packs/paper'], artifactsDir: 'artifacts' }
    const validated = validateExpertTeamConfig(config)
    expect(validated).toEqual(config)
    expect(validated).not.toBe(config)
    expect(validated.packs).not.toBe(config.packs)
  })
})

describe('invalid packs', () => {
  it('rejects a missing, non-array, and empty packs field', async () => {
    await expectErrorCode(
      () => validateExpertTeamConfig({ artifactsDir: 'artifacts' } as unknown as ExpertTeamConfig),
      'EXPERT_TEAM_CONFIG_INVALID',
    )
    await expectErrorCode(
      () => validateExpertTeamConfig({ packs: 'packs/paper', artifactsDir: 'artifacts' } as unknown as ExpertTeamConfig),
      'EXPERT_TEAM_CONFIG_INVALID',
    )
    await expectErrorCode(
      () => validateExpertTeamConfig({ packs: [], artifactsDir: 'artifacts' }),
      'EXPERT_TEAM_CONFIG_INVALID',
    )
  })

  it('rejects pack entries that are not clean path strings', async () => {
    await expectErrorCode(
      () => validateExpertTeamConfig({ packs: [5], artifactsDir: 'artifacts' } as unknown as ExpertTeamConfig),
      'EXPERT_TEAM_CONFIG_INVALID',
    )
    await expectErrorCode(
      () => validateExpertTeamConfig({ packs: ['   '], artifactsDir: 'artifacts' }),
      'EXPERT_TEAM_CONFIG_INVALID',
    )
    await expectErrorCode(
      () => validateExpertTeamConfig({ packs: [' padded'], artifactsDir: 'artifacts' }),
      'EXPERT_TEAM_CONFIG_INVALID',
    )
    await expectErrorCode(
      () => validateExpertTeamConfig({ packs: [`with${TAB}tab`], artifactsDir: 'artifacts' }),
      'EXPERT_TEAM_CONFIG_INVALID',
    )
  })
})

describe('invalid artifactsDir', () => {
  it('rejects a missing, blank, padded, or control-bearing artifactsDir', async () => {
    await expectErrorCode(
      () => validateExpertTeamConfig({ packs: ['packs/paper'] } as unknown as ExpertTeamConfig),
      'EXPERT_TEAM_CONFIG_INVALID',
    )
    await expectErrorCode(
      () => validateExpertTeamConfig({ packs: ['packs/paper'], artifactsDir: '   ' }),
      'EXPERT_TEAM_CONFIG_INVALID',
    )
    await expectErrorCode(
      () => validateExpertTeamConfig({ packs: ['packs/paper'], artifactsDir: ' padded' }),
      'EXPERT_TEAM_CONFIG_INVALID',
    )
    await expectErrorCode(
      () => validateExpertTeamConfig({ packs: ['packs/paper'], artifactsDir: `with${TAB}tab` }),
      'EXPERT_TEAM_CONFIG_INVALID',
    )
  })
})
