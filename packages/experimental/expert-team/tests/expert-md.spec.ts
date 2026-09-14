/**
 * Expert md unit behavior: the strict front matter contract parses valid
 * pack files into complete expert definitions, and every structural,
 * charset, or bound violation fails loud with `EXPERT_TEAM_EXPERT_INVALID`.
 */

import { readFile } from 'node:fs/promises'
import { describe, expect, it } from 'vitest'
import { parseExpertMd } from '../src/index.ts'
import type { ExpertDef } from '../src/index.ts'
import { expectErrorCode, fixturePath } from './helpers.ts'

/** Raw YAML fragments for the list-valued front matter keys. */
const TOOLS = '  - web_search\n  - read_file'
const SKILLS = '  - topic-scout'
const CHECKS = '  - 每个视角都说明为什么值得研究\n  - 视角之间没有重复'

/** Buildable expert md fields; list keys carry raw YAML item lines. */
interface MdFields {
  readonly id?: string
  readonly team?: string
  readonly name?: string
  readonly role?: string
  readonly goal?: string
  readonly tools?: string
  readonly skills?: string
  readonly handoffChecks?: string
  readonly persona?: string
}

/**
 * Build one valid expert md, with every field overridable (list keys take
 * raw YAML item lines, so tests can inject arbitrary YAML shapes).
 */
function expertMd(fields: MdFields = {}): string {
  const f = {
    id: 'topic-scout',
    team: 'paper-research',
    name: '选题侦察员',
    role: '发掘研究视角',
    goal: '产出研究视角清单',
    tools: TOOLS,
    persona: '你是选题侦察员。',
    ...fields,
  }
  const lines = [
    '---',
    `id: ${f.id}`,
    `team: ${f.team}`,
    `name: ${f.name}`,
    `role: ${f.role}`,
    `goal: ${f.goal}`,
    `tools:\n${f.tools}`,
  ]
  if (f.skills !== undefined) lines.push(`skills:\n${f.skills}`)
  if (f.handoffChecks !== undefined) lines.push(`handoff-checks:\n${f.handoffChecks}`)
  lines.push('---', '', f.persona)
  return lines.join('\n')
}

/** Parse under the file name the builder's default id matches. */
function parse(md: string): ExpertDef {
  return parseExpertMd('topic-scout.md', md)
}

describe('valid expert md', () => {
  it('parses every front matter field and the persona body', () => {
    const expert = parse(expertMd({
      skills: SKILLS,
      handoffChecks: CHECKS,
      persona: '你是选题侦察员。\n多行正文保持原样。',
    }))
    expect(expert.id).toBe('topic-scout')
    expect(expert.team).toBe('paper-research')
    expect(expert.name).toBe('选题侦察员')
    expect(expert.role).toBe('发掘研究视角')
    expect(expert.goal).toBe('产出研究视角清单')
    expect(expert.tools).toEqual(['web_search', 'read_file'])
    expect(expert.skills).toEqual(['topic-scout'])
    expect(expert.handoffChecks).toEqual(['每个视角都说明为什么值得研究', '视角之间没有重复'])
    expect(expert.persona).toBe('你是选题侦察员。\n多行正文保持原样。')
  })

  it('leaves optional keys absent when not declared', () => {
    const expert = parse(expertMd())
    expect(expert.skills).toBeUndefined()
    expect(expert.handoffChecks).toBeUndefined()
  })

  it('parses a body that starts immediately after the closing delimiter', () => {
    const md = [
      '---',
      'id: topic-scout',
      'team: paper-research',
      'name: 选题侦察员',
      'role: 发掘研究视角',
      'goal: 产出研究视角清单',
      'tools:',
      '  - web_search',
      '---',
      '紧贴分隔符的正文',
    ].join('\n')
    expect(parse(md).persona).toBe('紧贴分隔符的正文')
  })

  it('normalizes CRLF line endings before parsing', () => {
    const expert = parse(expertMd().replace(/\n/g, '\r\n'))
    expect(expert.id).toBe('topic-scout')
    expect(expert.persona).toBe('你是选题侦察员。')
  })

  it('parses the shipped fixture expert end to end', async () => {
    const contents = await readFile(fixturePath('fixture-pack/experts/topic-scout.md'), 'utf8')
    const expert = parseExpertMd('topic-scout.md', contents)
    expect(expert.team).toBe('paper-research')
    expect(expert.skills).toEqual(['topic-scout'])
    expect(expert.handoffChecks).toHaveLength(2)
    expect(expert.persona).toContain('选题侦察员')
  })
})

describe('invalid expert md structure', () => {
  it('rejects a file name without the .md suffix', async () => {
    await expectErrorCode(() => parseExpertMd('topic-scout.txt', expertMd()), 'EXPERT_TEAM_EXPERT_INVALID')
  })

  it('rejects a missing front matter opening', async () => {
    await expectErrorCode(() => parse(expertMd().replace(/^---\n/u, '')), 'EXPERT_TEAM_EXPERT_INVALID')
  })

  it('rejects a missing front matter closing', async () => {
    const md = expertMd().replace(/\n---\n/u, '\n')
    await expectErrorCode(() => parse(md), 'EXPERT_TEAM_EXPERT_INVALID')
  })

  it('rejects malformed YAML front matter', async () => {
    await expectErrorCode(() => parse('---\nid: [unclosed\n---\n正文'), 'EXPERT_TEAM_EXPERT_INVALID')
  })

  it('rejects list, null, and scalar front matter', async () => {
    await expectErrorCode(() => parse('---\n- a\n- b\n---\n正文'), 'EXPERT_TEAM_EXPERT_INVALID')
    await expectErrorCode(() => parse('---\nnull\n---\n正文'), 'EXPERT_TEAM_EXPERT_INVALID')
    await expectErrorCode(() => parse('---\nscalar\n---\n正文'), 'EXPERT_TEAM_EXPERT_INVALID')
  })

  it('rejects unknown and missing keys', async () => {
    await expectErrorCode(
      () => parse(expertMd({ handoffChecks: CHECKS }).replace('handoff-checks:', 'handoffs:')),
      'EXPERT_TEAM_EXPERT_INVALID',
    )
    const missingTools = [
      '---',
      'id: topic-scout',
      'team: paper-research',
      'name: 选题侦察员',
      'role: 发掘研究视角',
      'goal: 产出研究视角清单',
      '---',
      '',
      '正文',
    ].join('\n')
    await expectErrorCode(() => parse(missingTools), 'EXPERT_TEAM_EXPERT_INVALID')
  })
})

describe('invalid expert md fields', () => {
  it('rejects ids and team names that are not kebab-case', async () => {
    await expectErrorCode(() => parse(expertMd({ id: 'Topic_Scout' })), 'EXPERT_TEAM_EXPERT_INVALID')
    await expectErrorCode(() => parse(expertMd({ team: 'paper research' })), 'EXPERT_TEAM_EXPERT_INVALID')
    await expectErrorCode(() => parse(expertMd({ id: 'a'.repeat(65) })), 'EXPERT_TEAM_EXPERT_INVALID')
  })

  it('rejects an id that does not match the file name stem', async () => {
    await expectErrorCode(() => parse(expertMd({ id: 'other-name' })), 'EXPERT_TEAM_EXPERT_INVALID')
  })

  it('rejects blank, non-string, and multi-line scalars', async () => {
    await expectErrorCode(() => parse(expertMd({ name: "''" })), 'EXPERT_TEAM_EXPERT_INVALID')
    await expectErrorCode(() => parse('---\nid: topic-scout\nteam: t\nname: 5\nrole: r\ngoal: g\ntools:\n  - x\n---\n\n正文'), 'EXPERT_TEAM_EXPERT_INVALID')
    await expectErrorCode(
      () => parse('---\nid: topic-scout\nteam: t\nname: n\nrole: |-\n  第一行\n  第二行\ngoal: g\ntools:\n  - x\n---\n\n正文'),
      'EXPERT_TEAM_EXPERT_INVALID',
    )
  })

  it('rejects control characters in scalars', async () => {
    await expectErrorCode(() => parse(expertMd({ goal: '"含\t制表符"' })), 'EXPERT_TEAM_EXPERT_INVALID')
  })

  it('rejects byte-bound overruns on scalars and the persona body', async () => {
    await expectErrorCode(() => parse(expertMd({ name: '字'.repeat(64) })), 'EXPERT_TEAM_EXPERT_INVALID') // 192 bytes > 128
    await expectErrorCode(() => parse(expertMd({ role: '字'.repeat(128) })), 'EXPERT_TEAM_EXPERT_INVALID') // 256+ bytes
    await expectErrorCode(() => parse(expertMd({ goal: '字'.repeat(256) })), 'EXPERT_TEAM_EXPERT_INVALID') // 512+ bytes
    await expectErrorCode(() => parse(expertMd({ persona: '字'.repeat(8193) })), 'EXPERT_TEAM_EXPERT_INVALID') // 16 KiB+
  })

  it('rejects a blank persona body', async () => {
    await expectErrorCode(() => parse(expertMd({ persona: '   ' })), 'EXPERT_TEAM_EXPERT_INVALID')
  })

  it('rejects malformed tools lists', async () => {
    await expectErrorCode(() => parse(expertMd({ tools: '' })), 'EXPERT_TEAM_EXPERT_INVALID') // key without value -> null
    await expectErrorCode(() => parse(expertMd({ tools: '  web_search' })), 'EXPERT_TEAM_EXPERT_INVALID') // scalar, not list
    await expectErrorCode(() => parse(expertMd({ tools: '  []' })), 'EXPERT_TEAM_EXPERT_INVALID') // empty list: an expert with no tools cannot act
    await expectErrorCode(() => parse(expertMd({ tools: '  - web_search\n  - web_search' })), 'EXPERT_TEAM_EXPERT_INVALID')
    await expectErrorCode(() => parse(expertMd({ tools: `  - ${'t'.repeat(65)}` })), 'EXPERT_TEAM_EXPERT_INVALID')
    await expectErrorCode(
      () => parse(expertMd({ tools: Array.from({ length: 33 }, (_, i) => `  - tool-${i}`).join('\n') })),
      'EXPERT_TEAM_EXPERT_INVALID',
    )
  })

  it('rejects malformed optional lists', async () => {
    await expectErrorCode(() => parse(expertMd({ skills: '  - 5' })), 'EXPERT_TEAM_EXPERT_INVALID')
    await expectErrorCode(() => parse(expertMd({ skills: '  - ""' })), 'EXPERT_TEAM_EXPERT_INVALID')
    await expectErrorCode(() => parse(expertMd({ handoffChecks: '  - ""' })), 'EXPERT_TEAM_EXPERT_INVALID')
  })
})
