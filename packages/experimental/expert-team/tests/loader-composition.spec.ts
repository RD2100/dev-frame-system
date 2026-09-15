/**
 * The expert-team plugin through a REAL Loader composition: a cordis.yml with
 * the full stack (session, llm, persistence, projection, system prompt, tools,
 * agent registry, agent loop, default model) plus the expert-team mount over
 * BOTH the fixture pack and the shipped paper pack is booted by the actual
 * Loader, so the mount face under test is the one the shipped profiles use.
 * The assertions are the ones the unit suites cannot see: the shipped paper
 * pack mounts through the product face, a run executes phases in order with
 * schema-validated artifacts on disk, a human gate truly blocks progression
 * until the approval arrives, and a consult answers outside any run.
 * @module tests/loader-composition
 */

import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Include from '@deepseek-ai/cordis-plugin-include'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import AgentDefaultModelConfig from '@deepseek-ai/dsh-agent-default-model'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import LlmRuntime from '@deepseek-ai/dsh-llm'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { ToolExecutionResult } from '@deepseek-ai/dsh-tools'
import { MockAdapter, textResponse } from '../../../core/agent-loop/tests/mock-adapter.ts'
import * as expertTeam from '../src/index.ts'
import { RESULT_FENCE_OPEN } from '../src/index.ts'

/** Absolute path of one fixture pack under tests/fixtures. */
function fixturePath(name: string): string {
  return fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url))
}

/** Absolute path of the shipped paper data pack (sibling package). */
const PAPER_PACK = fileURLToPath(new URL('../../expert-pack-paper', import.meta.url))

let root: string | undefined
const contexts: Context[] = []

afterEach(async () => {
  await Promise.all(contexts.splice(0).map(ctx => ctx.fiber.dispose()))
  if (root !== undefined) await rm(root, { recursive: true, force: true })
  root = undefined
})

/** One no-op tool under a fixed name, standing in for a mounted deployment tool. */
function namedTool(name: string) {
  return defineTool({
    name,
    description: `test stub ${name}`,
    parameters: {},
    output: {
      schema: { type: 'object', additionalProperties: false, properties: {} },
      render: () => [{ type: 'text', text: name }],
    },
    async execute() { return {} },
  })
}

/** Write the cordis.yml under test: the full stack plus the expert-team mount. */
async function writeCompositionConfig(): Promise<string> {
  const configPath = join(root as string, 'cordis.yml')
  await writeFile(configPath, [
    "- name: '@deepseek-ai/dsh-session'",
    "- name: '@deepseek-ai/dsh-llm'",
    "- name: '@deepseek-ai/dsh-session-persistence-jsonl'",
    '  config:',
    `    root: ${JSON.stringify(join(root as string, 'sessions'))}`,
    '    compression: none',
    "- name: '@deepseek-ai/dsh-session-projection'",
    "- name: '@deepseek-ai/dsh-system-prompt'",
    "- name: '@deepseek-ai/dsh-tools'",
    "- name: '@deepseek-ai/dsh-agent'",
    "- name: '@deepseek-ai/dsh-agent-loop'",
    '  config:',
    '    agents: []',
    "- name: '@deepseek-ai/dsh-agent-default-model'",
    '  config:',
    '    provider: mock',
    '    model: mock',
    "- name: '@deepseek-ai/dsh-experimental-expert-team'",
    '  config:',
    '    packs:',
    `      - ${JSON.stringify(fixturePath('fixture-pack'))}`,
    `      - ${JSON.stringify(PAPER_PACK)}`,
    `    artifactsDir: ${JSON.stringify(join(root as string, 'artifacts'))}`,
    '',
  ].join('\n'))
  return configPath
}

async function loadComposition(configPath: string): Promise<Context> {
  const ctx = new Context()
  contexts.push(ctx)
  ctx.baseUrl = pathToFileURL(root as string).href + '/'
  await ctx.plugin(Loader)
  ctx.loader.builtins.include = Include
  const modules = new Map<string, unknown>([
    ['@deepseek-ai/dsh-session', SessionStore],
    ['@deepseek-ai/dsh-llm', LlmRuntime],
    ['@deepseek-ai/dsh-session-persistence-jsonl', JsonlSessionPersistence],
    ['@deepseek-ai/dsh-session-projection', SessionProjectionRegistry],
    ['@deepseek-ai/dsh-system-prompt', SystemPrompt],
    ['@deepseek-ai/dsh-tools', ToolRuntime],
    ['@deepseek-ai/dsh-agent', AgentRegistry],
    ['@deepseek-ai/dsh-agent-loop', AgentLoop],
    ['@deepseek-ai/dsh-agent-default-model', AgentDefaultModelConfig],
    ['@deepseek-ai/dsh-experimental-expert-team', expertTeam],
  ])
  ctx.loader.internal = {
    version: 'v2',
    async import(specifier: string) {
      if (!modules.has(specifier)) throw new Error(`unexpected Loader import: ${specifier}`)
      return modules.get(specifier)
    },
  } as unknown as NonNullable<typeof ctx.loader.internal>
  await ctx.loader.create({
    name: 'cordis:include',
    config: { path: pathToFileURL(configPath).href },
  })
  await ctx.loader.await()
  const unloaded = [...ctx.loader.entries()]
    .filter(entry => entry.fiber === undefined && !entry.disabled)
    .map(entry => entry.options.name)
  expect(unloaded).toEqual([])
  return ctx
}

interface Composition {
  ctx: Context
  artifactsDir: string
  adapter: MockAdapter
  /** Execute one model tool call as a live driver agent. */
  execute: (name: string, args: Record<string, unknown>) => Promise<ToolExecutionResult>
}

/** Boot the composition, register the mock model route and the stub deployment tools. */
async function boot(script: readonly unknown[]): Promise<Composition> {
  root = await mkdtemp(join(tmpdir(), 'dsh-expert-team-loader-'))
  await mkdir(join(root, 'artifacts'), { recursive: true })
  const configPath = await writeCompositionConfig()
  const ctx = await loadComposition(configPath)
  const adapter = new MockAdapter([...script] as never)
  ctx.llm.registerAdapter(['mock'], adapter)
  for (const tool of ['web_search', 'read_file', 'read', 'grep', 'glob', 'memory_search']) {
    ctx.tools.register(namedTool(tool))
  }
  const driver = (await ctx.agents.create({
    sessionId: SessionId('loader-driver'),
    agentOptions: { provider: 'mock', model: 'mock' },
  })).agent
  let callCount = 0
  return {
    ctx,
    artifactsDir: join(root, 'artifacts'),
    adapter,
    async execute(name, args) {
      callCount += 1
      return await ctx.tools.execute({
        callId: ToolCallId(`loader-${callCount}-${name}`),
        name,
        arguments: args,
        signal: new AbortController().signal,
        agent: driver,
      })
    },
  }
}

/** The model-facing text of one tool result. */
function textOf(result: ToolExecutionResult): string {
  return result.content.flatMap(block => block.type === 'text' && typeof block.text === 'string' ? [block.text] : []).join('')
}

/** Parse one run-snapshot tool result into the DTO the output schema declares. */
function runOf(result: ToolExecutionResult): {
  runId: string
  status: string
  phases: Array<{ phaseId: string; status: string; attempts: number }>
} {
  expect(result.isError, textOf(result)).toBe(false)
  return JSON.parse(textOf(result)) as ReturnType<typeof runOf>
}

/** One scripted phase reply: artifact body plus the fenced result object. */
function phaseReply(body: string, result: object): ReturnType<typeof textResponse> {
  return textResponse(`${body}\n\n${RESULT_FENCE_OPEN}\n${JSON.stringify(result, null, 2)}\n\`\`\``)
}

const PERSPECTIVES_RESULT = {
  artifactPath: 'perspectives.md',
  summary: '三个互相区分的研究视角',
  perspectives: [
    { title: '方法路线', why: '方法分歧决定提问方向' },
    { title: '应用场景', why: '真实痛点约束问题边界' },
    { title: '争议点', why: '概念争议本身值得研究' },
  ],
}

describe('expert team through a real Loader composition', () => {
  it('mounts the fixture pack and the shipped paper pack with their full phase chains', async () => {
    const b = await boot([])
    const listed = JSON.parse(textOf(await b.execute('expert_team_list', {}))) as unknown as {
      teams: Array<{
        team: string
        entry: string
        phases: Array<{ id: string; expert: string; dependsOn: string[]; artifact: string; gate?: string }>
        experts: Array<{ id: string }>
      }>
    }
    const fixture = listed.teams.find(team => team.team === 'paper-research')
    const paper = listed.teams.find(team => team.team === 'paper')
    expect(fixture?.entry).toBe('perspective-discovery')
    expect(fixture?.phases[1]).toMatchObject({ id: 'literature-review', gate: 'human-review' })

    // The shipped data pack, validated by the same mount: the M2 pipeline
    // with ten phases, three parallel review stages, and two human gates.
    expect(paper?.entry).toBe('perspective-discovery')
    expect(paper?.phases.map(phase => [phase.id, phase.expert, phase.dependsOn, phase.artifact, phase.gate])).toEqual([
      ['perspective-discovery', 'topic-scout', [], 'perspectives.md', undefined],
      ['literature-review', 'literature-reviewer', ['perspective-discovery'], 'survey.md', 'human-review'],
      ['idea-selection', 'idea-selector', ['literature-review'], 'research-questions.md', 'human-review'],
      ['method-design', 'method-designer', ['idea-selection'], 'method.md', undefined],
      ['experiments', 'experimenter', ['method-design'], 'experiments.md', undefined],
      ['writing', 'writer', ['experiments'], 'draft.md', undefined],
      ['review-methodology', 'reviewer-1', ['writing'], 'review-methodology.md', undefined],
      ['review-statistics', 'reviewer-2', ['writing'], 'review-statistics.md', undefined],
      ['review-writing', 'reviewer-3', ['writing'], 'review-writing.md', undefined],
      ['revision', 'writer', ['review-methodology', 'review-statistics', 'review-writing'], 'revision-plan.md', 'human-review'],
    ])
    // The pack owns its roster and may grow experts without this suite; the
    // four M1 reference experts must all mount.
    expect(paper?.experts.map(expert => expert.id).sort()).toEqual(
      expect.arrayContaining(['idea-selector', 'literature-reviewer', 'method-designer', 'topic-scout']),
    )
  })

  it('executes the pipeline in order, parks the gate until the approval, and lands artifacts', async () => {
    const b = await boot([
      // Phase 1, attempt 1: the reply lacks the fenced result object.
      textResponse('我先给出视角，但忘记结果对象。'),
      // Phase 1, attempt 2: the schema-valid perspectives result.
      phaseReply('# 研究视角\n\n- 方法路线\n- 应用场景\n- 争议点', PERSPECTIVES_RESULT),
      // Phase 2: the survey lands and the gate parks the run.
      phaseReply('# 综述\n\n这是综述正文。', { artifactPath: 'survey.md', summary: '综述完成。' }),
      // Phase 2 revision after the rejection.
      phaseReply('# 综述（修订）\n\n补全了引用。', { artifactPath: 'survey.md', summary: '修订后的综述。' }),
    ])
    const started = runOf(await b.execute('expert_team_run', { team: 'paper-research', input: '大模型推理加速' }))
    expect(started.status).toBe('waiting-approval')
    expect(started.phases.map(phase => [phase.phaseId, phase.status])).toEqual([
      ['perspective-discovery', 'done'],
      ['literature-review', 'gate-pending'],
    ])
    // The artifacts are durable files, and the run state mirrors the snapshot.
    const runDir = join(b.artifactsDir, started.runId)
    expect(await readFile(join(runDir, 'perspectives.md'), 'utf8')).toContain('方法路线')
    expect(await readFile(join(runDir, 'run-state.json'), 'utf8')).toContain('"waiting-approval"')

    // The gate truly blocks: a rejection re-drives the phase expert in its
    // own session and parks the run again before the approval resumes it.
    const rejected = runOf(await b.execute('expert_team_approve', {
      run_id: started.runId, decision: 'rejected', comment: '引用缺失',
    }))
    expect(rejected.status).toBe('waiting-approval')
    expect(rejected.phases[1]?.attempts).toBe(2)
    expect(JSON.stringify(b.adapter.requests[3])).toContain('引用缺失')
    const approved = runOf(await b.execute('expert_team_approve', { run_id: started.runId, decision: 'approved' }))
    expect(approved.status).toBe('completed')
    expect(approved.phases.map(phase => phase.status)).toEqual(['done', 'done'])
    expect(await readFile(join(runDir, 'survey.md'), 'utf8')).toContain('补全了引用')
  })

  it('answers a consultation through expert_team_run without touching the pipeline', async () => {
    const b = await boot([textResponse('STORM 先发散再收敛。')])
    const result = await b.execute('expert_team_run', {
      expert: 'topic-scout',
      team: 'paper',
      question: '什么是 STORM？',
    })
    expect(result.isError, textOf(result)).toBe(false)
    const parsed = JSON.parse(textOf(result))
    expect(parsed.answer).toBe('STORM 先发散再收敛。')
    expect(parsed.truncated).toBe(false)
    expect(JSON.stringify(b.adapter.requests[0])).toContain('什么是 STORM？')
    // The consult ran outside any run: the artifacts root is still empty.
    await expect(readdir(b.artifactsDir)).resolves.toEqual([])
  })
})
