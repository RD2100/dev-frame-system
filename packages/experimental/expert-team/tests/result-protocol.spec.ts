/**
 * Result-protocol unit behavior: the fenced-JSON tail split, the phase result
 * contract (declared artifact name, bounded summary, openQuestions, pack
 * schema), the consult answer bound, and the three composed model-facing
 * briefing texts.
 */

import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  composeConsultMessage,
  composePhaseBriefing,
  composeRevisionMessage,
} from '../src/index.ts'
import type { RevisionReason } from '../src/index.ts'
import {
  MAX_ARTIFACT_BYTES,
  RESULT_FENCE_OPEN,
  parseConsultAnswer,
  parsePhaseResult,
  splitPhaseReply,
} from '../src/index.ts'
import type { ExpertDef, PhaseDef, TeamDef } from '../src/index.ts'
import { expectErrorCode, fixturePath } from './helpers.ts'

/** The fixture pack's first phase: artifact with a declared schema. */
const PHASE: PhaseDef = {
  id: 'perspective-discovery',
  expert: 'topic-scout',
  dependsOn: [],
  output: { artifact: 'perspectives.md', schema: 'schemas/perspectives.schema.json' },
}

/** A valid result object that also satisfies the fixture pack schema. */
const VALID_RESULT = {
  artifactPath: 'perspectives.md',
  summary: '三个互相区分的研究视角',
  perspectives: [
    { title: '方法路线', why: '方法分歧决定提问方向' },
    { title: '应用场景', why: '真实痛点约束问题边界' },
    { title: '争议点', why: '概念争议本身值得研究' },
  ],
}

/** Wrap one reply body into the fenced result protocol. */
function reply(body: string, result: unknown): string {
  return `${body}\n\n${RESULT_FENCE_OPEN}\n${JSON.stringify(result, null, 2)}\n\`\`\`\n`
}

describe('splitPhaseReply', () => {
  it('splits the body from the trailing result block and tolerates a quoted fence in the body', () => {
    const body = '# 视角清单\n\n正文里可以引用一个示例：\n\n```json\n{"not": "the result"}\n```'
    const split = splitPhaseReply(reply(body, VALID_RESULT))
    expect(split.body).toBe(body)
    expect(split.result).toEqual(VALID_RESULT)
  })

  it('trims the body to non-blank text without the fence block', () => {
    const split = splitPhaseReply(`正文\n\n${RESULT_FENCE_OPEN}\n{"artifactPath":"perspectives.md","summary":"s"}\n\`\`\``)
    expect(split.body).toBe('正文')
  })

  it('fails loud on a missing, unclosed, or succeeded result block', async () => {
    await expectErrorCode(() => splitPhaseReply('没有结果块的回复'), 'EXPERT_TEAM_RESULT_INVALID')
    await expectErrorCode(
      () => splitPhaseReply(`${RESULT_FENCE_OPEN}\n{"a":1}`),
      'EXPERT_TEAM_RESULT_INVALID',
    )
    await expectErrorCode(
      () => splitPhaseReply(`${RESULT_FENCE_OPEN}\n{}\n\`\`\`\n后续内容`),
      'EXPERT_TEAM_RESULT_INVALID',
    )
  })

  it('rejects a blank body, an oversized body, and non-JSON fenced content', async () => {
    await expectErrorCode(
      () => splitPhaseReply(`\n\n${RESULT_FENCE_OPEN}\n{}\n\`\`\``),
      'EXPERT_TEAM_RESULT_INVALID',
    )
    await expectErrorCode(
      () => splitPhaseReply(`${'x'.repeat(MAX_ARTIFACT_BYTES + 1)}\n${RESULT_FENCE_OPEN}\n{}\n\`\`\``),
      'EXPERT_TEAM_RESULT_INVALID',
    )
    await expectErrorCode(
      () => splitPhaseReply(`正文\n${RESULT_FENCE_OPEN}\n{not json}\n\`\`\``),
      'EXPERT_TEAM_RESULT_INVALID',
    )
  })
})

describe('parsePhaseResult', () => {
  it('accepts a result that names the declared artifact and satisfies the pack schema', async () => {
    const schemaText = await readFile(
      join(fixturePath('fixture-pack'), PHASE.output.schema ?? ''),
      'utf8',
    )
    const result = parsePhaseResult(VALID_RESULT, PHASE, schemaText)
    expect(result).toEqual({ artifactPath: 'perspectives.md', summary: '三个互相区分的研究视角' })
  })

  it('rejects a foreign artifactPath, a blank summary, and a non-object result', async () => {
    await expectErrorCode(
      () => parsePhaseResult({ ...VALID_RESULT, artifactPath: 'other.md' }, PHASE, undefined),
      'EXPERT_TEAM_RESULT_INVALID',
    )
    await expectErrorCode(
      () => parsePhaseResult({ ...VALID_RESULT, summary: '  ' }, PHASE, undefined),
      'EXPERT_TEAM_RESULT_INVALID',
    )
    await expectErrorCode(() => parsePhaseResult('text', PHASE, undefined), 'EXPERT_TEAM_RESULT_INVALID')
  })

  it('validates openQuestions shape and enumerates every schema violation in one failure', async () => {
    await expectErrorCode(
      () => parsePhaseResult({ ...VALID_RESULT, openQuestions: [''] }, PHASE, undefined),
      'EXPERT_TEAM_RESULT_INVALID',
    )
    const schemaText = await readFile(join(fixturePath('fixture-pack'), PHASE.output.schema ?? ''), 'utf8')
    try {
      parsePhaseResult(
        { ...VALID_RESULT, perspectives: VALID_RESULT.perspectives.slice(0, 2) },
        PHASE,
        schemaText,
      )
      expect.unreachable()
    } catch (error: unknown) {
      const detail = error instanceof Error ? error.message : String(error)
      expect(detail).toContain('fails the declared schema')
      expect(detail).toContain('/perspectives')
    }
  })
})

describe('parseConsultAnswer', () => {
  it('passes a bounded answer through and truncates an oversized one at a code point', () => {
    expect(parseConsultAnswer('简短回答')).toEqual({ answer: '简短回答', truncated: false })
    const oversized = '好'.repeat(70 * 1024)
    const bounded = parseConsultAnswer(oversized)
    expect(bounded.truncated).toBe(true)
    expect(Buffer.byteLength(bounded.answer, 'utf8')).toBeLessThanOrEqual(64 * 1024)
    expect(bounded.answer.endsWith('好')).toBe(true)
  })
})

/** The fixture team definition fragment the briefings compose against. */
const TEAM: TeamDef = {
  team: 'paper-research',
  title: '论文研究专家团',
  mode: 'pipeline',
  entry: 'perspective-discovery',
  phases: [PHASE],
}

/** The fixture topic-scout expert definition fragment. */
const EXPERT: ExpertDef = {
  id: 'topic-scout',
  team: 'paper-research',
  name: '选题侦察员',
  role: '从研究主题中发掘多样的研究视角',
  goal: '产出覆盖不同方法立场、可指导后续提问的研究视角清单',
  tools: ['web_search', 'read_file'],
  persona: '你是选题侦察员。',
}

describe('briefing composition', () => {
  it('composes the phase briefing with the run input, upstream paths, handoff checks, and output contract', () => {
    const briefing = composePhaseBriefing({
      team: TEAM,
      phase: PHASE,
      expert: { ...EXPERT, handoffChecks: ['每个视角都说明为什么值得研究'] },
      upstream: [{ phaseId: 'earlier', artifact: 'earlier.md', relativePath: 'earlier.md' }],
      upstreamPaths: new Map([['earlier', '/run/dir/earlier.md']]),
      input: '大模型推理加速',
      supersededOpenQuestions: [],
      schemaText: '{"type":"object"}',
    })
    expect(briefing).toContain('# 阶段任务：perspective-discovery（团队「论文研究专家团」）')
    expect(briefing).toContain('大模型推理加速')
    expect(briefing).toContain('/run/dir/earlier.md')
    expect(briefing).toContain('每个视角都说明为什么值得研究')
    expect(briefing).toContain('perspectives.md')
    expect(briefing).toContain(RESULT_FENCE_OPEN)
    expect(briefing).toContain('{"type":"object"}')
  })

  it('omits the sections the phase does not declare', () => {
    const briefing = composePhaseBriefing({
      team: TEAM,
      phase: { ...PHASE, output: { artifact: 'perspectives.md' } },
      expert: EXPERT,
      upstream: [],
      upstreamPaths: new Map(),
      input: '主题',
      supersededOpenQuestions: [],
    })
    expect(briefing).not.toContain('## 阶段输入')
    expect(briefing).not.toContain('## 上游产物')
    expect(briefing).not.toContain('## handoff 核查清单')
    expect(briefing).not.toContain('```json\n{')
  })

  it('composes the revision follow-ups for a gate rejection with and without a comment', () => {
    const withComment = composeRevisionMessage({ kind: 'gate-rejection', comment: '第二段引用不足' } satisfies RevisionReason)
    expect(withComment).toContain('第二段引用不足')
    const withoutComment = composeRevisionMessage({ kind: 'gate-rejection' } satisfies RevisionReason)
    expect(withoutComment).toContain('没有附批注')
    const validation = composeRevisionMessage({ kind: 'validation-failure', detail: 'summary 缺失' } satisfies RevisionReason)
    expect(validation).toContain('summary 缺失')
  })

  it('frames the consult message as a run-free question', () => {
    const message = composeConsultMessage('什么是 STORM？')
    expect(message).toContain('单专家咨询')
    expect(message).toContain('什么是 STORM？')
  })
})
