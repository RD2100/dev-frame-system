/**
 * Orchestration unit behavior over the real plugin mount: a run drives its
 * phases in declaration order through persona-scoped subagents, retries the
 * result contract within its bound, parks at the declared human gate, records
 * the reviewer's decision (a rejection revises the same phase session), and
 * consults an expert without touching run state. Every misconfiguration or
 * unknown-reference failure is loud with its stable code.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { mkdir, mkdtemp, readFile, readdir, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import type { Fiber } from '@deepseek-ai/cordis'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import AgentDefaultModelConfig from '@deepseek-ai/dsh-agent-default-model'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import type { ToolExecutionResult } from '@deepseek-ai/dsh-tools'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { remoteMethods } from '@deepseek-ai/dsh-typert-protocol'
import { SessionId } from '@deepseek-ai/dsh-session'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import { MockAdapter, textResponse } from '../../../core/agent-loop/tests/mock-adapter.ts'
import { RESULT_FENCE_OPEN } from '../src/index.ts'
import * as expertTeam from '../src/index.ts'
import type { TeamRun } from '../src/index.ts'
import type { ExpertTeamErrorCode } from '../src/index.ts'
import { copyFixturePack, fixturePath } from './helpers.ts'

const CONTEXTS: Context[] = []
const ROOTS: string[] = []

afterEach(async () => {
  for (const ctx of CONTEXTS.splice(0).reverse()) await ctx.fiber.dispose()
  for (const root of ROOTS.splice(0)) await rm(root, { recursive: true, force: true })
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

interface Bench {
  ctx: Context
  root: string
  artifactsDir: string
  adapter: MockAdapter
  /** The expert-team plugin's own fiber; disposing it alone unmounts the plugin. */
  pluginFiber: Fiber
  /** Execute one model tool call as a live driver agent. */
  execute: (name: string, args: Record<string, unknown>) => Promise<ToolExecutionResult>
  dispose: () => Promise<void>
}

interface BenchOptions {
  /** Scripted model replies, consumed one per generate call. */
  script: Parameters<typeof MockAdapter.prototype.stream>[0] extends never ? never : readonly unknown[]
  /** Register the deployment tools the fixture experts allowlist. */
  stubTools?: boolean
  /** Extra tool names to register beyond the default stub set. */
  extraTools?: readonly string[]
  /** Mount the default-model service (default true). */
  defaultModel?: boolean
  /** Extra packs to mount beside the pipeline fixture. */
  extraPacks?: readonly string[]
  /** Override the mounted packs entirely (default: the pipeline fixture plus extras). */
  packs?: readonly string[]
}

/** Boot the real plugin over the loop's test dependencies and a scripted mock adapter. */
async function bench(options: BenchOptions): Promise<Bench> {
  const root = await mkdtemp(join(tmpdir(), 'dsh-expert-team-orchestrate-'))
  ROOTS.push(root)
  const artifactsDir = join(root, 'artifacts')
  await mkdir(artifactsDir, { recursive: true })
  const ctx = new Context()
  CONTEXTS.push(ctx)
  await mountAgentLoopTestDependencies(ctx)
  if (options.stubTools !== false) {
    ctx.tools.register(namedTool('web_search'))
    ctx.tools.register(namedTool('read_file'))
  }
  for (const tool of options.extraTools ?? []) {
    ctx.tools.register(namedTool(tool))
  }
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(AgentLoop, { agents: [] })
  const adapter = new MockAdapter([...options.script] as never)
  ctx.llm.registerAdapter(['mock'], adapter)
  if (options.defaultModel !== false) {
    await ctx.plugin(AgentDefaultModelConfig, { provider: 'mock', model: 'mock' })
  }
  const pluginFiber = ctx.plugin(expertTeam, {
    packs: options.packs === undefined ? [fixturePath('fixture-pack'), ...(options.extraPacks ?? [])] : [...options.packs],
    artifactsDir,
  })
  await pluginFiber.await()
  const driver = (await ctx.agents.create({
    sessionId: SessionId('expert-driver'),
    agentOptions: { provider: 'mock', model: 'mock' },
  })).agent
  let callCount = 0
  return {
    ctx,
    root,
    artifactsDir,
    adapter,
    pluginFiber,
    async execute(name, args) {
      callCount += 1
      return await ctx.tools.execute({
        callId: ToolCallId(`orchestrate-${callCount}-${name}`),
        name,
        arguments: args,
        signal: new AbortController().signal,
        agent: driver,
      })
    },
    async dispose() {
      await ctx.fiber.dispose()
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
  phases: Array<{
    phaseId: string
    status: string
    attempts: number
    error?: string
    reviews?: Array<{ decision: string; at: string; comment?: string }>
    artifact?: { artifact: string }
  }>
  reviews?: unknown
} {
  expect(result.isError, textOf(result)).toBe(false)
  return JSON.parse(textOf(result)) as ReturnType<typeof runOf>
}

/**
 * Assert that one tool execution settles as the named stable failure. The
 * tool registry converts a thrown {@link ExpertTeamError}-shaped failure into
 * an `isError` result whose `error.info` carries `{ name, code }`, so the
 * code is asserted on the result, never by re-parsing the message.
 */
async function expectToolErrorCode(run: () => Promise<ToolExecutionResult>, code: ExpertTeamErrorCode): Promise<void> {
  const result = await run()
  expect(result.isError, textOf(result)).toBe(true)
  if (!result.isError) return
  expect(result.error.info?.name).toBe('ExpertTeamError')
  expect(result.error.info?.code).toBe(code)
}

/** One scripted phase reply: artifact body plus the fenced result object. */
function phaseReply(body: string, result: object): ReturnType<typeof textResponse> {
  return textResponse(`${body}\n\n${RESULT_FENCE_OPEN}\n${JSON.stringify(result, null, 2)}\n\`\`\``)
}

/** The valid perspective-discovery result for the fixture pack's schema. */
const PERSPECTIVES_RESULT = {
  artifactPath: 'perspectives.md',
  summary: '三个互相区分的研究视角',
  perspectives: [
    { title: '方法路线', why: '方法分歧决定提问方向' },
    { title: '应用场景', why: '真实痛点约束问题边界' },
    { title: '争议点', why: '概念争议本身值得研究' },
  ],
}

describe('pipeline orchestration', () => {
  it('drives phases in order, retries the result contract, parks at the gate, and completes after approval', async () => {
    const b = await bench({
      script: [
        // Phase 1, attempt 1: the reply lacks the fenced result object.
        textResponse('我发现了三个研究视角，但忘记按契约给出结果对象。'),
        // Phase 1, attempt 2: the schema-valid perspectives result.
        phaseReply('# 研究视角\n\n- 方法路线\n- 应用场景\n- 争议点', PERSPECTIVES_RESULT),
        // Phase 2: the survey lands and the gate parks the run.
        phaseReply('# 综述\n\n这是综述正文，每条论断都带引用。', {
          artifactPath: 'survey.md',
          summary: '综述完成，gaps 分析见文末。',
        }),
        // Phase 2 revision after the rejection.
        phaseReply('# 综述（修订）\n\n补全了第三节的引用。', {
          artifactPath: 'survey.md',
          summary: '修订后的综述，引用完整。',
        }),
      ],
    })
    try {
      const started = runOf(await b.execute('expert_team_run', { team: 'paper-research', input: '大模型推理加速' }))
      expect(started.status).toBe('waiting-approval')
      expect(started.phases).toEqual([
        {
          phaseId: 'perspective-discovery',
          status: 'done',
          attempts: 2,
          artifact: { phaseId: 'perspective-discovery', artifact: 'perspectives.md', relativePath: 'perspectives.md', schema: 'schemas/perspectives.schema.json' },
        },
        {
          phaseId: 'literature-review',
          status: 'gate-pending',
          attempts: 1,
          artifact: { phaseId: 'literature-review', artifact: 'survey.md', relativePath: 'survey.md' },
          userQuestions: ['请审阅 survey.md 并给出 approve 或 reject 决定。'],
        },
      ])

      // Durable artifacts: the reply bodies landed, each with one trailing newline.
      const runDir = join(b.artifactsDir, started.runId)
      expect(await readFile(join(runDir, 'perspectives.md'), 'utf8')).toMatch(/- 争议点\n$/u)
      expect(await readFile(join(runDir, 'survey.md'), 'utf8')).toContain('这是综述正文')
      // The mirrored run state agrees with the tool snapshot.
      const persisted = JSON.parse(await readFile(join(runDir, 'run-state.json'), 'utf8')) as TeamRun
      expect(persisted.status).toBe('waiting-approval')
      expect(persisted.phases.map(phase => phase.status)).toEqual(['done', 'gate-pending'])

      // Model-visible: the persona, the output contract, and the pack schema
      // text reached the phase-1 briefing, and the phase-2 briefing referenced
      // the upstream artifact by path.
      expect(JSON.stringify(b.adapter.requests[0])).toContain('选题侦察员')
      expect(JSON.stringify(b.adapter.requests[0])).toContain('输出契约')
      expect(JSON.stringify(b.adapter.requests[0])).toContain('Perspective discovery phase result')
      expect(JSON.stringify(b.adapter.requests[2])).toContain('perspectives.md')

      // status reads the parked run.
      const status = runOf(await b.execute('expert_team_status', { run_id: started.runId }))
      expect(status.status).toBe('waiting-approval')

      // The rejection returns the artifact to the same phase session.
      const rejected = runOf(await b.execute('expert_team_approve', {
        run_id: started.runId,
        decision: 'rejected',
        comment: '第三节的引用缺失',
      }))
      expect(rejected.status).toBe('waiting-approval')
      expect(rejected.phases[1]?.attempts).toBe(2)
      const revisionRequest = JSON.stringify(b.adapter.requests[3])
      expect(revisionRequest).toContain('第三节的引用缺失')
      expect(revisionRequest).toContain('阶段任务：literature-review')

      // The approval resumes the pipeline to completion.
      const approved = runOf(await b.execute('expert_team_approve', { run_id: started.runId, decision: 'approved' }))
      expect(approved.status).toBe('completed')
      expect(approved.phases.map(phase => phase.status)).toEqual(['done', 'done'])
      // Completed runs retire their phase sessions.
      expect(b.ctx.agents.get(SessionId(`expert-team-${started.runId}-literature-review`))).toBeUndefined()

      // The decision history is recorded, and approving again fails loud.
      const finalState = JSON.parse(await readFile(join(runDir, 'run-state.json'), 'utf8')) as TeamRun
      const reviews = finalState.phases[1]?.reviews
      expect(reviews).toHaveLength(2)
      expect(reviews?.[0]?.decision).toBe('rejected')
      expect(reviews?.[0]?.comment).toBe('第三节的引用缺失')
      expect(typeof reviews?.[0]?.at).toBe('string')
      expect(reviews?.[1]?.decision).toBe('approved')
      expect(typeof reviews?.[1]?.at).toBe('string')
      await expectToolErrorCode(
        () => b.execute('expert_team_approve', { run_id: started.runId, decision: 'approved' }),
        'EXPERT_TEAM_GATE_PENDING',
      )
    } finally {
      await b.dispose()
    }
  })
})

describe('post-approval follow-up', () => {
  it('delivers the acceptance follow-up on approval and sends none on rejection', async () => {
    const b = await bench({
      script: [
        // Phase 1 lands its artifact.
        phaseReply('# 研究视角\n\n- 方法路线\n- 应用场景\n- 争议点', PERSPECTIVES_RESULT),
        // Phase 2 lands its artifact and the gate parks the run.
        phaseReply('# 综述\n\n这是综述正文。', { artifactPath: 'survey.md', summary: '综述完成。' }),
        // Phase 2 revision after the rejection.
        phaseReply('# 综述（修订）\n\n补全了引用。', { artifactPath: 'survey.md', summary: '修订后的综述。' }),
        // The post-approval follow-up turn.
        textResponse('收到，我会把已接受的结论记入记忆。'),
      ],
    })
    try {
      const run = runOf(await b.execute('expert_team_run', { team: 'paper-research', input: '主题' }))
      expect(run.status).toBe('waiting-approval')

      // The rejection re-drives the phase but sends no acceptance follow-up.
      const rejected = runOf(await b.execute('expert_team_approve', {
        run_id: run.runId, decision: 'rejected', comment: '引用不足',
      }))
      expect(rejected.status).toBe('waiting-approval')
      expect(JSON.stringify(b.adapter.requests)).not.toContain('人类关口已通过')

      // The approval completes the run and delivers the follow-up turn with
      // the reviewer comment.
      const approved = runOf(await b.execute('expert_team_approve', {
        run_id: run.runId, decision: 'approved', comment: '通过，引用完整',
      }))
      expect(approved.status).toBe('completed')
      await vi.waitFor(() => {
        const followup = JSON.stringify(b.adapter.requests[3])
        expect(followup).toContain('人类关口已通过')
        expect(followup).toContain('通过，引用完整')
      })
    } finally {
      await b.dispose()
    }
  })

  it('completes the run even when the post-approval follow-up fails', async () => {
    const b = await bench({
      script: [
        phaseReply('# 研究视角\n\n- 方法路线\n- 应用场景\n- 争议点', PERSPECTIVES_RESULT),
        phaseReply('# 综述\n\n这是综述正文。', { artifactPath: 'survey.md', summary: '综述完成。' }),
        // No scripted reply for the follow-up turn: its model call fails.
      ],
    })
    try {
      const run = runOf(await b.execute('expert_team_run', { team: 'paper-research', input: '主题' }))
      expect(run.status).toBe('waiting-approval')
      const approved = runOf(await b.execute('expert_team_approve', { run_id: run.runId, decision: 'approved' }))
      expect(approved.status).toBe('completed')
      expect(approved.phases.map(phase => phase.status)).toEqual(['done', 'done'])
      const persisted = JSON.parse(await readFile(join(b.artifactsDir, run.runId, 'run-state.json'), 'utf8')) as TeamRun
      expect(persisted.status).toBe('completed')
      const reviews = persisted.phases[1]?.reviews
      expect(reviews).toHaveLength(1)
      expect(reviews?.[0]?.decision).toBe('approved')
      expect(typeof reviews?.[0]?.at).toBe('string')
    } finally {
      await b.dispose()
    }
  })
})

describe('orchestration failures', () => {
  it('parks a run failed when a phase exhausts its result-contract retries', async () => {
    const b = await bench({
      script: [textResponse('没有结果对象'), textResponse('仍然没有结果对象'), textResponse('还是没有结果对象')],
    })
    try {
      const run = runOf(await b.execute('expert_team_run', { team: 'paper-research', input: '主题' }))
      expect(run.status).toBe('failed')
      expect(run.phases[0]?.status).toBe('failed')
      expect(run.phases[0]?.attempts).toBe(3)
      expect(run.phases[0]?.error).toContain('phase result contract violated')
      // A failed run has no gate awaiting a decision.
      await expectToolErrorCode(
        () => b.execute('expert_team_approve', { run_id: run.runId, decision: 'approved' }),
        'EXPERT_TEAM_GATE_PENDING',
      )
    } finally {
      await b.dispose()
    }
  })

  it('parks a failed gated phase waiting-approval, refuses its approval without recording a review, and re-opens it by rejection', async () => {
    const b = await bench({
      script: [
        // Phase 1 succeeds; phase 2 exhausts its result-contract retries.
        phaseReply('# 研究视角\n\n- 方法路线\n- 应用场景\n- 争议点', PERSPECTIVES_RESULT),
        textResponse('没有结果对象'), textResponse('仍然没有结果对象'), textResponse('还是没有结果对象'),
        // The guided revision after the rejection.
        phaseReply('# 综述（修订）\n\n补全了引用。', { artifactPath: 'survey.md', summary: '修订后的综述。' }),
      ],
    })
    try {
      const run = runOf(await b.execute('expert_team_run', { team: 'paper-research', input: '主题' }))
      expect(run.status).toBe('waiting-approval')
      expect(run.phases[0]?.status).toBe('done')
      expect(run.phases[1]?.status).toBe('failed')
      expect(run.phases[1]?.error).toContain('phase result contract violated')

      // The human cannot approve a failed phase, and the refusal records no review.
      await expectToolErrorCode(
        () => b.execute('expert_team_approve', { run_id: run.runId, decision: 'approved' }),
        'EXPERT_TEAM_GATE_PENDING',
      )
      const afterRefusal = runOf(await b.execute('expert_team_status', { run_id: run.runId }))
      expect(afterRefusal.phases[1]?.reviews).toBeUndefined()

      // A rejection with a comment re-opens the phase as a guided revision.
      const rejected = runOf(await b.execute('expert_team_approve', {
        run_id: run.runId, decision: 'rejected', comment: '先按契约补结果对象',
      }))
      expect(rejected.status).toBe('waiting-approval')
      expect(rejected.phases[1]?.status).toBe('gate-pending')
      expect(rejected.phases[1]?.attempts).toBe(4)
      const reviews = rejected.phases[1]?.reviews
      expect(reviews).toHaveLength(1)
      expect(reviews?.[0]?.decision).toBe('rejected')
      expect(reviews?.[0]?.comment).toBe('先按契约补结果对象')
      expect(typeof reviews?.[0]?.at).toBe('string')
      const revisionRequest = JSON.stringify(b.adapter.requests[4])
      expect(revisionRequest).toContain('先按契约补结果对象')
      expect(revisionRequest).toContain('阶段任务：literature-review')
    } finally {
      await b.dispose()
    }
  })

  it('accepts a hierarchical team at run start', async () => {
    const b = await bench({ script: [], extraPacks: [fixturePath('fixture-pack-hierarchical')] })
    try {
      await expectToolErrorCode(
        () => b.execute('expert_team_run', { team: 'code-builders', input: '需求' }),
        'EXPERT_TEAM_TOOL_MISSING',
      )
    } finally {
      await b.dispose()
    }
  })

  it('runs a hierarchical team through controller and worker phases', async () => {
    const b = await bench({
      script: [
        phaseReply('# 实施计划\n\n- 步骤1：搭建框架\n- 步骤2：实现核心逻辑', {
          artifactPath: 'plan.md',
          summary: '计划完成，包含两个实施步骤',
        }),
        phaseReply('# 实现补丁\n\n- 新增模块入口\n- 绑定核心接口', {
          artifactPath: 'patch.diff',
          summary: '补丁完成，覆盖计划中的核心改动',
        }),
      ],
      extraPacks: [fixturePath('fixture-pack-hierarchical')],
      extraTools: ['edit_file'],
    })
    try {
      const run = runOf(await b.execute('expert_team_run', { team: 'code-builders', input: '需求' }))
      expect(run.status).toBe('completed')
      expect(run.phases).toHaveLength(2)
      expect(run.phases[0]?.status).toBe('done')
      expect(run.phases[0]?.artifact?.artifact).toBe('plan.md')
      expect(run.phases[1]?.status).toBe('done')
      expect(run.phases[1]?.artifact?.artifact).toBe('patch.diff')

      // Durable artifacts: reply bodies landed, each with one trailing newline.
      const runDir = join(b.artifactsDir, run.runId)
      const planContent = await readFile(join(runDir, 'plan.md'), 'utf8')
      expect(planContent).toContain('实施计划')
      expect(planContent).toMatch(/核心逻辑\n$/u)
      const patchContent = await readFile(join(runDir, 'patch.diff'), 'utf8')
      expect(patchContent).toContain('实现补丁')
      expect(patchContent).toMatch(/核心接口\n$/u)

      // Mirrored run state.
      const persisted = JSON.parse(await readFile(join(runDir, 'run-state.json'), 'utf8')) as TeamRun
      expect(persisted.status).toBe('completed')
      expect(persisted.phases.map(p => p.status)).toEqual(['done', 'done'])
    } finally {
      await b.dispose()
    }
  })

  it('records hierarchy bindings when agentBindings is mounted', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-expert-team-hierarchy-'))
    ROOTS.push(root)
    const ctx = new Context()
    CONTEXTS.push(ctx)
    await mountAgentLoopTestDependencies(ctx)
    ctx.tools.register(namedTool('read_file'))
    ctx.tools.register(namedTool('edit_file'))
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(AgentLoop, { agents: [] })
    // Mount storage-backed binding registry so the runtime's best-effort
    // bind path has a real target.
    const storageRoot = join(root, 'storage')
    await mkdir(storageRoot, { recursive: true })
    await ctx.plugin(Storage)
    await ctx.plugin(StorageJson, { root: storageRoot })
    await ctx.plugin(StorageDomain, { backend: 'json' })
    await ctx.plugin(AgentBindingRegistry)

    const artifactsDir = join(root, 'artifacts')
    await mkdir(artifactsDir, { recursive: true })
    const adapter = new MockAdapter([
      phaseReply('# 实施计划\n\n- 步骤1：搭建框架', {
        artifactPath: 'plan.md',
        summary: '计划完成',
      }),
      phaseReply('# 实现补丁\n\n- 新增模块入口', {
        artifactPath: 'patch.diff',
        summary: '补丁完成',
      }),
    ] as never)
    ctx.llm.registerAdapter(['mock'], adapter)
    await ctx.plugin(AgentDefaultModelConfig, { provider: 'mock', model: 'mock' })
    const pluginFiber = ctx.plugin(expertTeam, {
      packs: [fixturePath('fixture-pack-hierarchical')],
      artifactsDir,
    })
    await pluginFiber.await()
    const driver = (await ctx.agents.create({
      sessionId: SessionId('hierarchy-driver'),
      agentOptions: { provider: 'mock', model: 'mock' },
    })).agent
    try {
      const run = runOf(await ctx.tools.execute({
        callId: ToolCallId('hierarchy-test-run'),
        name: 'expert_team_run',
        arguments: { team: 'code-builders', input: '需求' },
        agent: driver,
        signal: new AbortController().signal,
      }))
      expect(run.status).toBe('completed')

      // The binding registry should carry two records: the controller phase
      // (plan) with no parent, and the worker phase (implement) whose parent
      // is the controller's session.
      const bindings = ctx.agentBindings.list()
      expect(bindings).toHaveLength(2)
      const planBinding = bindings.find(b => b.taskId === 'plan')
      const implementBinding = bindings.find(b => b.taskId === 'implement')
      expect(planBinding?.role).toBe('controller')
      expect(planBinding?.parentSessionId).toBeUndefined()
      expect(implementBinding?.role).toBe('worker')
      expect(implementBinding?.parentSessionId).toBe(planBinding?.agentId)
      expect(implementBinding?.pluginId).toBe('expert-team')
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('fails loud when an expert names an unmounted tool and leaves no run behind', async () => {
    const b = await bench({ script: [], stubTools: false })
    try {
      await expectToolErrorCode(
        () => b.execute('expert_team_run', { team: 'paper-research', input: '主题' }),
        'EXPERT_TEAM_TOOL_MISSING',
      )
      // consult_expert was folded into expert_team_run: the removed tool
      // name is no longer registered, so the framework rejects it directly.
      const consultResult = await b.execute('consult_expert', { team: 'paper-research', expert: 'topic-scout', question: '？' })
      expect(consultResult.isError, textOf(consultResult)).toBe(true)
      expect(consultResult.error?.info?.name).toBe('ToolNotFoundError')
      // Consultation mode through expert_team_run also fails with the plugin error.
      await expectToolErrorCode(
        () => b.execute('expert_team_run', { team: 'paper-research', expert: 'topic-scout', question: '？' }),
        'EXPERT_TEAM_TOOL_MISSING',
      )
      // Nothing was created: no run directories exist.
      await expect(readdir(b.artifactsDir)).resolves.toEqual([])
    } finally {
      await b.dispose()
    }
  })

  it('fails the run loud when the deployment provides no default model', async () => {
    const b = await bench({ script: [], defaultModel: false })
    try {
      await expectToolErrorCode(
        () => b.execute('expert_team_run', { team: 'paper-research', input: '主题' }),
        'EXPERT_TEAM_MODEL_MISSING',
      )
      // The started run settled to failed instead of staying 'running'.
      const entries = await readdir(b.artifactsDir)
      const runDirs = entries.filter(name => name !== 'run-index.json')
      expect(runDirs).toHaveLength(1)
      const persisted = JSON.parse(
        await readFile(join(b.artifactsDir, runDirs[0] ?? '', 'run-state.json'), 'utf8'),
      ) as TeamRun
      expect(persisted.status).toBe('failed')
      expect(persisted.phases[0]?.error).toContain('default model')
    } finally {
      await b.dispose()
    }
  })

  it('fails the run loud when a declared skill loses its SKILL.md before derive time', async () => {
    const pack = await copyFixturePack('fixture-pack')
    ROOTS.push(pack)
    const b = await bench({ script: [], packs: [pack] })
    try {
      // The pack mounted with the skill present; deleting it before the run
      // must fail the derive loud under the same catalog code.
      await rm(join(pack, 'skills', 'topic-scout', 'SKILL.md'))
      await expectToolErrorCode(
        () => b.execute('expert_team_run', { team: 'paper-research', input: '主题' }),
        'EXPERT_TEAM_SKILL_MISSING',
      )
      // The started run settled failed instead of staying 'running'.
      const entries = await readdir(b.artifactsDir)
      const runDirs = entries.filter(name => name !== 'run-index.json')
      expect(runDirs).toHaveLength(1)
      const persisted = JSON.parse(
        await readFile(join(b.artifactsDir, runDirs[0] ?? '', 'run-state.json'), 'utf8'),
      ) as TeamRun
      expect(persisted.status).toBe('failed')
    } finally {
      await b.dispose()
    }
  })

  it('rolls back its contributions and rethrows when a tool registration fails at mount', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    try {
      const disposed: string[] = []
      // Hand-built context: this unit pins the failure path of `apply` only;
      // the successful mount face is covered by the real composition suites.
      const ctx = {
        reflect: { provide: () => {} },
        provide: (name: string) => () => { throw new Error(`disposal of ${name} exploded`) },
        systemPrompt: { section: () => () => disposed.push('usage section') },
        effect: () => () => disposed.push('derived session disposal'),
        tools: {
          register: (definition: { readonly name: string }) => {
            if (definition.name === 'expert_team_run') {
              throw new Error('tool "expert_team_run" is already registered')
            }
            return () => disposed.push(`tool:${definition.name}`)
          },
        },
      } as unknown as Context
      let mountError: unknown
      let mounted = false
      try {
        await expertTeam.apply(ctx, { packs: [fixturePath('fixture-pack')], artifactsDir: 'unused' })
        mounted = true
      } catch (error: unknown) {
        mountError = error
      }
      expect(mounted).toBe(false)
      // The original load error is rethrown, not masked by the rollback.
      expect(mountError instanceof Error ? mountError.message : String(mountError)).toContain('already registered')
      // The disposer that failed is awaited, named, and warned about.
      expect(warn).toHaveBeenCalledWith(expect.stringContaining('[expert-team] mount rollback'))
      expect(warn).toHaveBeenCalledWith(expect.stringContaining('expertTeam service'))
      expect(warn).toHaveBeenCalledWith(expect.stringContaining('exploded'))
      // Everything that mounted before the failure unwound, in reverse order.
      expect(disposed).toEqual(['tool:expert_team_list', 'derived session disposal', 'usage section'])
    } finally {
      warn.mockRestore()
    }
  })

  it('fails lookups loud for unknown teams, runs, and malformed run ids', async () => {
    const b = await bench({ script: [] })
    try {
      await expectToolErrorCode(
        () => b.execute('expert_team_run', { team: 'ghost-team', input: '主题' }),
        'EXPERT_TEAM_TEAM_MISSING',
      )
      await expectToolErrorCode(() => b.execute('expert_team_status', { run_id: 'run-nope' }), 'EXPERT_TEAM_RUN_UNKNOWN')
      await expectToolErrorCode(() => b.execute('expert_team_status', { run_id: 'a/b' }), 'EXPERT_TEAM_RUN_UNKNOWN')
    } finally {
      await b.dispose()
    }
  })

  it('answers a consultation through expert_team_run without touching run state', async () => {
    const b = await bench({ script: [textResponse('STORM 是一种先发散再收敛的预写作方法。')] })
    try {
      const result = await b.execute('expert_team_run', {
        team: 'paper-research',
        expert: 'topic-scout',
        question: '什么是 STORM？',
      })
      expect(result.isError, textOf(result)).toBe(false)
      const answer = JSON.parse(textOf(result)) as { answer: string; truncated: boolean }
      expect(answer).toEqual({ answer: 'STORM 是一种先发散再收敛的预写作方法。', truncated: false })
      expect(JSON.stringify(b.adapter.requests[0])).toContain('什么是 STORM？')
      expect(JSON.stringify(b.adapter.requests[0])).toContain('选题侦察员')
      // A consult leaves no run directory behind.
      await expect(readdir(b.artifactsDir)).resolves.toEqual([])
    } finally {
      await b.dispose()
    }
  })

  it('publishes the status and execution Remote beside the four model tools', async () => {
    const b = await bench({ script: [] })
    try {
      const gateway = b.ctx.get('expertTeamGateway')
      expect(gateway).toBeDefined()
      if (gateway === undefined) throw new Error('expertTeamGateway was not published')
      expect(remoteMethods(gateway)).toEqual([
        { method: 'view', invocation: { kind: 'direct' } },
        { method: 'startRun', invocation: { kind: 'direct' } },
        { method: 'consult', invocation: { kind: 'direct' } },
        { method: 'approve', invocation: { kind: 'direct' } },
        { method: 'getRun', invocation: { kind: 'direct' } },
      ])
      expect(gateway.view().teams.map(team => team.team)).toEqual(['paper-research'])
      expect(gateway.view().runs).toEqual([])
    } finally {
      await b.dispose()
    }
  })

  it('unmounts cleanly and removes the service, Remote, and four tools', async () => {
    const b = await bench({ script: [] })
    try {
      expect(b.ctx.tools.get('expert_team_list')).toBeDefined()
      expect(b.ctx.tools.get('expert_team_run')).toBeDefined()
      expect(b.ctx.tools.get('expert_team_status')).toBeDefined()
      expect(b.ctx.tools.get('expert_team_approve')).toBeDefined()
      expect(b.ctx.get('expertTeam')).toBeDefined()
      expect(b.ctx.get('expertTeamGateway')).toBeDefined()
    } finally {
      // Dispose the plugin fiber alone: the unmount must remove exactly the
      // plugin's contributions, not the shared test dependencies.
      await b.pluginFiber.dispose()
    }
    expect(b.ctx.tools.get('expert_team_list')).toBeUndefined()
    expect(b.ctx.get('expertTeam')).toBeUndefined()
    expect(b.ctx.get('expertTeamGateway')).toBeUndefined()
  })
})
