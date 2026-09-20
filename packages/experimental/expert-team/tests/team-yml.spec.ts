/**
 * team.yml unit behavior: the strict key and phase contract parses valid
 * team definitions in both modes, every structural violation fails loud with
 * `EXPERT_TEAM_CATALOG_INVALID`, non-backward `depends_on` references fail
 * with `EXPERT_TEAM_PHASE_CYCLE`, and pack cross checks (expert refs, schema
 * files) fail with their own codes.
 */

import { mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { loadTeamYml, parseTeamYml } from '../src/index.ts'
import type { TeamDef } from '../src/index.ts'
import { copyFixturePack, expectErrorCode, fixturePath, removeDir } from './helpers.ts'

/** Valid phase list covering depends_on, input, schema, and gate. */
const PHASES = [
  '  - id: perspective-discovery',
  '    expert: topic-scout',
  '    input: 研究主题与已有材料笔记',
  '    output:',
  '      artifact: perspectives.md',
  '      schema: schemas/perspectives.schema.json',
  '  - id: literature-review',
  '    expert: literature-reviewer',
  '    depends_on:',
  '      - perspective-discovery',
  '    output:',
  '      artifact: survey.md',
  '    gate: human-review',
].join('\n')

/** Buildable team.yml fields; `phases` carries raw YAML item lines. */
interface YmlFields {
  readonly team?: string
  readonly title?: string
  readonly mode?: string
  readonly entry?: string
  readonly phases?: string
}

/** Build one valid pipeline team.yml with every field overridable. */
function teamYml(fields: YmlFields = {}): string {
  const f = {
    team: 'paper-research',
    title: '论文研究专家团',
    mode: 'pipeline',
    entry: 'perspective-discovery',
    phases: PHASES,
    ...fields,
  }
  return [
    `team: ${f.team}`,
    `title: ${f.title}`,
    `mode: ${f.mode}`,
    `entry: ${f.entry}`,
    'phases:',
    f.phases,
  ].join('\n')
}

/** Parse with a mode-preserving cast for invalid raw modes. */
function parse(contents: string): TeamDef {
  return parseTeamYml(contents)
}

describe('valid team.yml', () => {
  it('parses the pipeline shape with phase details intact', () => {
    const def = parse(teamYml())
    expect(def.team).toBe('paper-research')
    expect(def.title).toBe('论文研究专家团')
    expect(def.mode).toBe('pipeline')
    expect(def.entry).toBe('perspective-discovery')
    expect(def.phases).toHaveLength(2)
    expect(def.phases[1]?.dependsOn).toEqual(['perspective-discovery'])
    expect(def.phases[0]?.output.schema).toBe('schemas/perspectives.schema.json')
    expect(def.phases[0]?.input).toBe('研究主题与已有材料笔记')
    expect(def.phases[1]?.gate).toBe('human-review')
  })

  it('parses the hierarchical mode', () => {
    const def = parse(teamYml({ team: 'code-builders', mode: 'hierarchical', entry: 'plan', phases: [
      '  - id: plan',
      '    expert: planner',
      '    output:',
      '      artifact: plan.md',
    ].join('\n') }))
    expect(def.mode).toBe('hierarchical')
    expect(def.phases[0]?.dependsOn).toEqual([])
    expect(def.phases[0]?.gate).toBeUndefined()
  })
})

describe('invalid team.yml structure', () => {
  it('rejects malformed YAML', async () => {
    await expectErrorCode(() => parse('team: [unclosed'), 'EXPERT_TEAM_CATALOG_INVALID')
  })

  it('rejects non-mapping documents', async () => {
    await expectErrorCode(() => parse('- a\n- b'), 'EXPERT_TEAM_CATALOG_INVALID')
  })

  it('rejects unknown and missing top-level keys', async () => {
    await expectErrorCode(() => parse(teamYml().replace('title:', 'ttl:')), 'EXPERT_TEAM_CATALOG_INVALID')
    await expectErrorCode(() => parse(teamYml().replace(/title: .*\n/u, '')), 'EXPERT_TEAM_CATALOG_INVALID')
  })

  it('rejects a bad team id, title, and mode', async () => {
    await expectErrorCode(() => parse(teamYml({ team: 'Paper_Research' })), 'EXPERT_TEAM_CATALOG_INVALID')
    await expectErrorCode(() => parse(teamYml({ title: '""' })), 'EXPERT_TEAM_CATALOG_INVALID')
    await expectErrorCode(() => parse(teamYml({ mode: 'serial' })), 'EXPERT_TEAM_CATALOG_INVALID')
  })
})

describe('invalid phases', () => {
  it('rejects missing, non-array, empty, and oversized phase lists', async () => {
    await expectErrorCode(() => parse(teamYml().replace(/phases:\n[\s\S]*/u, 'phases:')), 'EXPERT_TEAM_CATALOG_INVALID')
    await expectErrorCode(() => parse(teamYml({ phases: 'phases-text' })), 'EXPERT_TEAM_CATALOG_INVALID')
    const emptyList = teamYml().replace(PHASES, '  []')
    await expectErrorCode(() => parse(emptyList), 'EXPERT_TEAM_CATALOG_INVALID')
    const oversized = Array.from({ length: 65 }, (_, i) => [
      `  - id: phase-${i}`,
      '    expert: topic-scout',
      '    output:',
      '      artifact: a.md',
    ].join('\n')).join('\n')
    await expectErrorCode(() => parse(teamYml({ phases: oversized })), 'EXPERT_TEAM_CATALOG_INVALID')
  })

  it('rejects non-mapping phases and unknown or missing phase keys', async () => {
    await expectErrorCode(() => parse(teamYml({ phases: '  - phase-as-text' })), 'EXPERT_TEAM_CATALOG_INVALID')
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('    input:', '    inputs:') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    const missingOutput = PHASES.replace('    output:\n      artifact: perspectives.md\n      schema: schemas/perspectives.schema.json', '')
    await expectErrorCode(() => parse(teamYml({ phases: missingOutput })), 'EXPERT_TEAM_CATALOG_INVALID')
  })

  it('rejects duplicate, non-kebab, and missing phase ids', async () => {
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('literature-review', 'perspective-discovery') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('perspective-discovery', 'Perspective Discovery') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('  - id: perspective-discovery', '  - expert-only: no') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
  })

  it('rejects malformed expert and input fields', async () => {
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('expert: topic-scout', 'expert: 5') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('input: 研究主题与已有材料笔记', 'input: ""') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
  })

  it('rejects malformed depends_on lists', async () => {
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('depends_on:\n      - perspective-discovery', 'depends_on: perspective-discovery') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('- perspective-discovery', '- 5') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('- perspective-discovery', '  - perspective-discovery\n      - perspective-discovery') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
  })

  it('rejects non-backward depends_on references with EXPERT_TEAM_PHASE_CYCLE', async () => {
    // Self reference.
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('depends_on:\n      - perspective-discovery', 'depends_on:\n      - literature-review') })),
      'EXPERT_TEAM_PHASE_CYCLE',
    )
    // Forward reference to a later phase.
    const forward = [
      '  - id: second',
      '    expert: topic-scout',
      '    depends_on:',
      '      - first',
      '    output:',
      '      artifact: a.md',
      '  - id: first',
      '    expert: topic-scout',
      '    output:',
      '      artifact: b.md',
    ].join('\n')
    await expectErrorCode(() => parse(teamYml({ phases: forward, entry: 'second' })), 'EXPERT_TEAM_PHASE_CYCLE')
    // Unknown phase id.
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('- perspective-discovery', '- ghost-phase') })),
      'EXPERT_TEAM_PHASE_CYCLE',
    )
  })

  it('rejects malformed output blocks', async () => {
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('      artifact: perspectives.md', '      artifact: 5') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('      artifact: survey.md', '') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('      artifact: perspectives.md', '      artifact: nested/dir.md') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('      artifact: perspectives.md', "      artifact: '..'") })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('artifact: perspectives.md', "artifact: '.'") })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('artifact: perspectives.md', 'artifact: back\\\\slash.md') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('      schema: schemas/perspectives.schema.json', '      schema: 5') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('      schema: schemas/perspectives.schema.json', '      schema: /abs/schema.json') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('      schema: schemas/perspectives.schema.json', '      schema: win\\\\path.json') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('      schema: schemas/perspectives.schema.json', '      schema: C:drive.json') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
  })

  it('rejects Windows name hazards in artifact names', async () => {
    // NTFS alternate data stream separator.
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('artifact: perspectives.md', 'artifact: perspectives.md:ads') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    // Reserved device base names, with an extension and bare, in any case.
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('artifact: perspectives.md', 'artifact: aux.md') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('artifact: perspectives.md', "artifact: 'CON'") })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('artifact: perspectives.md', 'artifact: com1.json') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    // Trailing dot and trailing space, which Windows normalization drops.
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('artifact: perspectives.md', "artifact: 'survey.md.'") })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('artifact: perspectives.md', "artifact: 'survey.md '") })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
  })

  it('rejects gate values other than human-review', async () => {
    await expectErrorCode(
      () => parse(teamYml({ phases: PHASES.replace('gate: human-review', 'gate: auto-approve') })),
      'EXPERT_TEAM_CATALOG_INVALID',
    )
  })
})

describe('entry consistency', () => {
  it('rejects an entry that references no declared phase', async () => {
    await expectErrorCode(() => parse(teamYml({ entry: 'ghost-phase' })), 'EXPERT_TEAM_CATALOG_INVALID')
  })

  it('rejects an entry phase that declares depends_on', async () => {
    await expectErrorCode(() => parse(teamYml({ entry: 'literature-review' })), 'EXPERT_TEAM_CATALOG_INVALID')
  })
})

describe('pack cross validation via loadTeamYml', () => {
  it('loads the shipped pipeline fixture', async () => {
    const def = await loadTeamYml(fixturePath('fixture-pack'), ['topic-scout', 'literature-reviewer'])
    expect(def.team).toBe('paper-research')
    expect(def.phases).toHaveLength(2)
  })

  it('rejects a missing team.yml', async () => {
    const dir = await copyFixturePack('fixture-pack')
    try {
      await rm(join(dir, 'team.yml'))
      await expectErrorCode(() => loadTeamYml(dir, ['topic-scout', 'literature-reviewer']), 'EXPERT_TEAM_CATALOG_INVALID')
    } finally {
      await removeDir(dir)
    }
  })

  it('rejects a phase referencing an expert the pack does not define', async () => {
    const dir = await copyFixturePack('fixture-pack')
    try {
      await expectErrorCode(() => loadTeamYml(dir, ['topic-scout']), 'EXPERT_TEAM_EXPERT_MISSING')
    } finally {
      await removeDir(dir)
    }
  })

  it('rejects two controller phases even when they name the same expert', async () => {
    const dir = await copyFixturePack('fixture-pack')
    try {
      const contents = await readFile(join(dir, 'team.yml'), 'utf8')
      const hierarchical = contents
        .replace('mode: pipeline', 'mode: hierarchical')
        .replace('expert: topic-scout', 'expert: topic-scout\n    hierarchy-role: controller')
        .replace('expert: literature-reviewer', 'expert: topic-scout\n    hierarchy-role: controller')
      await writeFile(join(dir, 'team.yml'), hierarchical)
      await expectErrorCode(() => loadTeamYml(dir, ['topic-scout', 'literature-reviewer']), 'EXPERT_TEAM_CATALOG_INVALID')
    } finally {
      await removeDir(dir)
    }
  })

  it('rejects missing, non-file, and escaping schema references', async () => {
    const dir = await copyFixturePack('fixture-pack')
    try {
      await rm(join(dir, 'schemas', 'perspectives.schema.json'))
      await expectErrorCode(() => loadTeamYml(dir, ['topic-scout', 'literature-reviewer']), 'EXPERT_TEAM_SCHEMA_MISSING')
    } finally {
      await removeDir(dir)
    }

    const dirFile = await copyFixturePack('fixture-pack')
    try {
      await rm(join(dirFile, 'schemas', 'perspectives.schema.json'))
      await mkdir(join(dirFile, 'schemas', 'perspectives.schema.json'))
      await expectErrorCode(() => loadTeamYml(dirFile, ['topic-scout', 'literature-reviewer']), 'EXPERT_TEAM_SCHEMA_MISSING')
    } finally {
      await removeDir(dirFile)
    }

    const dirEscape = await copyFixturePack('fixture-pack')
    try {
      const contents = await readFile(join(dirEscape, 'team.yml'), 'utf8')
      await writeFile(
        join(dirEscape, 'team.yml'),
        contents.replace('schema: schemas/perspectives.schema.json', 'schema: ../outside.json'),
      )
      await expectErrorCode(() => loadTeamYml(dirEscape, ['topic-scout', 'literature-reviewer']), 'EXPERT_TEAM_SCHEMA_MISSING')
    } finally {
      await removeDir(dirEscape)
    }

    const dirParent = await copyFixturePack('fixture-pack')
    try {
      const contents = await readFile(join(dirParent, 'team.yml'), 'utf8')
      await writeFile(
        join(dirParent, 'team.yml'),
        contents.replace('schema: schemas/perspectives.schema.json', "schema: '..'"),
      )
      await expectErrorCode(() => loadTeamYml(dirParent, ['topic-scout', 'literature-reviewer']), 'EXPERT_TEAM_SCHEMA_MISSING')
    } finally {
      await removeDir(dirParent)
    }
  })

  it('rejects schema references that resolve to the pack root itself', async () => {
    const dir = await copyFixturePack('fixture-pack')
    try {
      const contents = await readFile(join(dir, 'team.yml'), 'utf8')
      await writeFile(join(dir, 'team.yml'), contents.replace('schema: schemas/perspectives.schema.json', "schema: '.'"))
      await expectErrorCode(() => loadTeamYml(dir, ['topic-scout', 'literature-reviewer']), 'EXPERT_TEAM_SCHEMA_MISSING')
    } finally {
      await removeDir(dir)
    }
  })
})
