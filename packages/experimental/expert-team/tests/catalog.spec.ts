/**
 * Catalog unit behavior: fixture packs mount with complete lookups in
 * configuration order, and every mount-time problem — duplicate directories,
 * duplicate team ids, missing files, cross-file inconsistencies — fails loud
 * with its stable code.
 */

import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ExpertCatalog } from '../src/index.ts'
import { copyFixturePack, expectErrorCode, fixturePath, makeConfig, removeDir } from './helpers.ts'

describe('mounted catalog', () => {
  it('mounts both fixture packs and serves lookups in configuration order', async () => {
    const catalog = await ExpertCatalog.load(makeConfig([
      fixturePath('fixture-pack'),
      fixturePath('fixture-pack-hierarchical'),
    ]))
    const teams = catalog.listTeams()
    expect(teams.map(team => team.def.team)).toEqual(['paper-research', 'code-builders'])
    expect(teams[0]?.experts.map(expert => expert.id)).toEqual(['literature-reviewer', 'topic-scout'])

    const pipeline = catalog.getTeam('paper-research')
    expect(pipeline.def.mode).toBe('pipeline')
    expect(pipeline.def.entry).toBe('perspective-discovery')
    expect(pipeline.packDir).toBe(fixturePath('fixture-pack'))
    expect(pipeline.def.phases[1]?.gate).toBe('human-review')

    const hierarchical = catalog.getTeam('code-builders')
    expect(hierarchical.def.mode).toBe('hierarchical')
    expect(hierarchical.def.phases[1]?.dependsOn).toEqual(['plan'])

    const expert = catalog.getExpert('paper-research', 'topic-scout')
    expect(expert.role).toBe('从研究主题中发掘多样的研究视角')
    expect(expert.tools).toEqual(['web_search', 'read_file'])
  })
})

describe('mount-time failures', () => {
  it('rejects a config without packs through the catalog boundary', async () => {
    await expectErrorCode(
      () => ExpertCatalog.load({ packs: [], artifactsDir: 'artifacts' }),
      'EXPERT_TEAM_CONFIG_INVALID',
    )
  })

  it('rejects a pack directory mounted twice', async () => {
    const pack = fixturePath('fixture-pack')
    await expectErrorCode(() => ExpertCatalog.load(makeConfig([pack, pack])), 'EXPERT_TEAM_CATALOG_INVALID')
  })

  it('rejects a team id mounted from two directories', async () => {
    const copy = await copyFixturePack('fixture-pack')
    try {
      await expectErrorCode(
        () => ExpertCatalog.load(makeConfig([fixturePath('fixture-pack'), copy])),
        'EXPERT_TEAM_CATALOG_INVALID',
      )
    } finally {
      await removeDir(copy)
    }
  })

  it('rejects a pack directory that does not exist or is not a directory', async () => {
    const missing = join(tmpdir(), 'dsh-expert-team-missing-pack')
    await expectErrorCode(() => ExpertCatalog.load(makeConfig([missing])), 'EXPERT_TEAM_CATALOG_INVALID')

    const fileParent = await mkdtemp(join(tmpdir(), 'dsh-expert-team-'))
    try {
      const filePath = join(fileParent, 'pack-as-file')
      await writeFile(filePath, 'not a directory')
      await expectErrorCode(() => ExpertCatalog.load(makeConfig([filePath])), 'EXPERT_TEAM_CATALOG_INVALID')
    } finally {
      await removeDir(fileParent)
    }
  })

  it('rejects a pack without team.yml and a pack without experts', async () => {
    const noYml = await copyFixturePack('fixture-pack')
    try {
      await rm(join(noYml, 'team.yml'))
      await expectErrorCode(() => ExpertCatalog.load(makeConfig([noYml])), 'EXPERT_TEAM_CATALOG_INVALID')
    } finally {
      await removeDir(noYml)
    }

    const noExperts = await copyFixturePack('fixture-pack')
    try {
      await rm(join(noExperts, 'experts'), { recursive: true })
      await expectErrorCode(() => ExpertCatalog.load(makeConfig([noExperts])), 'EXPERT_TEAM_CATALOG_INVALID')
    } finally {
      await removeDir(noExperts)
    }
  })

  it('rejects an expert whose team field contradicts the pack team', async () => {
    const dir = await copyFixturePack('fixture-pack')
    try {
      const expertPath = join(dir, 'experts', 'topic-scout.md')
      const contents = await readFile(expertPath, 'utf8')
      await writeFile(expertPath, contents.replace('team: paper-research', 'team: other-team'))
      await expectErrorCode(() => ExpertCatalog.load(makeConfig([dir])), 'EXPERT_TEAM_CATALOG_INVALID')
    } finally {
      await removeDir(dir)
    }
  })

  it('rejects a declared skill whose SKILL.md is missing at mount time', async () => {
    const dir = await copyFixturePack('fixture-pack')
    try {
      await rm(join(dir, 'skills', 'topic-scout', 'SKILL.md'))
      await expectErrorCode(() => ExpertCatalog.load(makeConfig([dir])), 'EXPERT_TEAM_SKILL_MISSING')
    } finally {
      await removeDir(dir)
    }
  })

  it("rejects an expert allowlist that names one of the plugin's own tools", async () => {
    await expectErrorCode(
      () => ExpertCatalog.load(makeConfig([fixturePath('fixture-pack-own-tools')])),
      'EXPERT_TEAM_TOOL_FORBIDDEN',
    )
  })

  it('ignores non-md files while loading experts', async () => {
    const dir = await copyFixturePack('fixture-pack')
    try {
      await writeFile(join(dir, 'experts', 'notes.txt'), 'not an expert')
      const catalog = await ExpertCatalog.load(makeConfig([dir]))
      expect(catalog.getTeam('paper-research').experts).toHaveLength(2)
    } finally {
      await removeDir(dir)
    }
  })
})

describe('lookups on a mounted catalog', () => {
  it('fails loud on unknown teams and unknown experts', async () => {
    const catalog = await ExpertCatalog.load(makeConfig([fixturePath('fixture-pack')]))
    await expectErrorCode(() => catalog.getTeam('ghost-team'), 'EXPERT_TEAM_TEAM_MISSING')
    await expectErrorCode(() => catalog.getExpert('paper-research', 'ghost-expert'), 'EXPERT_TEAM_EXPERT_MISSING')
    // An expert id that exists in another team is still missing here.
    await expectErrorCode(() => catalog.getExpert('code-builders', 'topic-scout'), 'EXPERT_TEAM_TEAM_MISSING')
  })
})
