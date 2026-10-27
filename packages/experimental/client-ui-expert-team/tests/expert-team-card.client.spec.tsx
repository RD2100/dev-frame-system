// @vitest-environment jsdom
/** The expert center renders the mounted catalog, starts real runs, consults
 * experts, and lets a human review gated runs — unavailable capability
 * domains stay honest instead of presenting dead controls. */

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { RemoteResult } from '@deepseek-ai/dsh-api-remotes/client'
import type {
  ExpertTeamConsultResult,
  ExpertTeamRunDetail,
  ExpertTeamSnapshot,
} from '@deepseek-ai/dsh-experimental-expert-team/client'
import { RemoteError } from '@deepseek-ai/dsh-client-test-runtime'
import type { ExpertTeamCardFace, ExpertTeamCardProps } from '../src/client/ExpertTeamCard.tsx'
import { ExpertTeamCard } from '../src/client/ExpertTeamCard.tsx'
import { zh, type ExpertTeamKey } from '../src/client/locales.ts'

const t = ((key: ExpertTeamKey, params?: Record<string, unknown>) => {
  const text = zh[key]
  return params === undefined
    ? text
    : Object.entries(params).reduce((result, [name, value]) => result.replaceAll(`{${name}}`, String(value)), text)
}) as ExpertTeamCardProps['t']

const unusedHook = (() => { throw new Error('unused by the expert center') }) as never

const SNAPSHOT: ExpertTeamSnapshot = {
  teams: [
    {
      team: 'paper',
      title: '论文研究专家团',
      mode: 'pipeline',
      entry: 'topic-scout',
      experts: [
        { id: 'topic-scout', name: '课题侦察员', role: '发现研究视角', tools: ['read', 'memory_search'] },
      ],
      phases: [
        { id: 'topic-scout', expert: 'topic-scout', dependsOn: [], artifact: 'perspectives.md' },
      ],
    },
    {
      team: 'dev',
      title: '软件开发专家团',
      mode: 'hierarchical',
      entry: 'prd',
      experts: [
        { id: 'product-manager', name: '产品经理', role: '把需求翻译成 PRD', tools: ['read', 'grep'], hierarchyRole: 'controller' },
        { id: 'architect', name: '架构师', role: '把需求转成系统设计', tools: ['read', 'glob'], hierarchyRole: 'lead' },
      ],
      phases: [
        { id: 'prd', expert: 'product-manager', dependsOn: [], artifact: 'prd.md', gate: 'human-review', hierarchyRole: 'controller' },
        { id: 'architecture', expert: 'architect', dependsOn: ['prd'], artifact: 'design.md', hierarchyRole: 'lead' },
      ],
    },
  ],
  runs: [],
}

const ok = <T,>(value: T): RemoteResult<T> => ({ ok: true, value })

function face(overrides: Partial<ExpertTeamCardFace> = {}): ExpertTeamCardFace {
  return {
    load: vi.fn(async (): Promise<RemoteResult<ExpertTeamSnapshot>> => ok(SNAPSHOT)),
    summon: vi.fn(),
    startRun: vi.fn(async (): Promise<RemoteResult<ExpertTeamRunDetail>> => ok(RUN_DETAIL)),
    consult: vi.fn(async (): Promise<RemoteResult<ExpertTeamConsultResult>> => ok({ answer: '把需求拆成三步。', truncated: false })),
    approve: vi.fn(async (): Promise<RemoteResult<ExpertTeamRunDetail>> => ok(RUN_DETAIL)),
    getRun: vi.fn(async (): Promise<RemoteResult<ExpertTeamRunDetail>> => ok(RUN_DETAIL)),
    ...overrides,
  }
}

function props(actions: ExpertTeamCardFace): ExpertTeamCardProps {
  return {
    wide: true,
    renderSlot: (_name, _owner, options) => options?.fallback,
    t,
    useSessions: unusedHook,
    useSessionPendingInteraction: unusedHook,
    useWorkspaces: unusedHook,
    ...actions,
  }
}

const RUN_DETAIL: ExpertTeamRunDetail = {
  runId: 'run-1' as ExpertTeamRunDetail['runId'],
  teamId: 'dev',
  mode: 'hierarchical',
  status: 'waiting-approval',
  createdAt: '2026-09-17T00:00:00.000Z',
  phases: [
    {
      phaseId: 'prd',
      status: 'gate-pending',
      attempts: 1,
      artifact: { phaseId: 'prd', artifact: 'prd.md', relativePath: 'prd.md' },
      userQuestions: ['这个需求的目标用户是谁？'],
    },
    { phaseId: 'architecture', status: 'pending', attempts: 0 },
  ],
}

async function settle(): Promise<void> {
  await act(async () => { await Promise.resolve() })
}

afterEach(cleanup)

describe('the expert center catalog', () => {
  it('opens the catalog with mounted experts, team filters, and recent-run section', async () => {
    const actions = face()
    render(<ExpertTeamCard {...props(actions)} />)
    await settle()

    fireEvent.click(screen.getByRole('button', { name: '打开能力中心' }))
    expect(screen.getByRole('dialog', { name: '能力中心' })).not.toBeNull()
    expect(screen.getAllByRole('tab')).toHaveLength(4)
    expect(screen.queryByRole('button', { name: '打开记忆库' })).toBeNull()
    expect(screen.getByRole('main', { name: '专家目录' })).not.toBeNull()
    expect(screen.getByText('课题侦察员')).not.toBeNull()
    expect(screen.getByText('架构师')).not.toBeNull()
    expect(screen.getByText('2 个专家团 · 3 位专家')).not.toBeNull()
    expect(screen.getByText('最近运行')).not.toBeNull()
    expect(screen.getByText('暂无运行记录。')).not.toBeNull()
    expect(actions.load).toHaveBeenCalledTimes(2)
  })

  it('links each tab to its panel and supports roving arrow-key focus', async () => {
    render(<ExpertTeamCard {...props(face())} />)
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '打开能力中心' }))

    const tabs = screen.getAllByRole('tab')
    expect(tabs.filter(tab => (tab as HTMLButtonElement).tabIndex === 0)).toHaveLength(1)
    for (const tab of tabs) {
      const panelId = tab.getAttribute('aria-controls')
      const panel = panelId === null ? null : document.getElementById(panelId)
      expect(panel?.getAttribute('aria-labelledby')).toBe(tab.id)
    }

    const experts = screen.getByRole('tab', { name: '专家' })
    const skills = screen.getByRole('tab', { name: '技能' })
    fireEvent.keyDown(experts, { key: 'ArrowRight' })
    expect(skills.getAttribute('aria-selected')).toBe('true')
    expect(document.activeElement).toBe(skills)

    fireEvent.keyDown(skills, { key: 'End' })
    expect(screen.getByRole('tab', { name: '记忆库' }).getAttribute('aria-selected')).toBe('true')
  })

  it('filters cards by search text and shows the selected expert details', async () => {
    const actions = face()
    render(<ExpertTeamCard {...props(actions)} />)
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '打开能力中心' }))

    fireEvent.change(screen.getByRole('textbox', { name: '搜索专家' }), { target: { value: '架构' } })
    expect(screen.getByText('架构师')).not.toBeNull()
    expect(screen.queryByText('课题侦察员')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /架构师/ }))
    const detail = screen.getByRole('complementary', { name: '专家详情' })
    expect(detail.textContent).toContain('软件开发专家团')
    expect(detail.textContent).toContain('architecture')
    expect(detail.textContent).toContain('glob')
  })

  it('offers card summon actions and detail run/consult actions with editable prompts', async () => {
    const actions = face()
    render(<ExpertTeamCard {...props(actions)} />)
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '打开能力中心' }))

    const cardSummons = screen.getAllByRole('button', { name: '召唤' })
    expect(cardSummons).toHaveLength(3)
    fireEvent.click(cardSummons[0]!)
    expect(actions.summon).toHaveBeenCalledWith(
      expect.objectContaining({ expertId: 'topic-scout', expertName: '课题侦察员' }),
      expect.stringContaining('课题侦察员'),
    )
    expect(screen.queryByRole('dialog', { name: '能力中心' })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '打开能力中心' }))
    fireEvent.click(screen.getByRole('button', { name: /架构师/ }))
    expect(screen.getByRole('button', { name: '启动流水线' })).not.toBeNull()
    expect(screen.getByRole('button', { name: '召唤专家' })).not.toBeNull()
    expect(screen.getByText('专家帮你做')).not.toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '帮我把这个任务拆成可执行步骤。' }))
    const input = screen.getByRole('textbox', { name: '任务或问题' }) as HTMLInputElement
    expect(input.value).toBe('帮我把这个任务拆成可执行步骤。')
  })

  it('starts a pipeline run from the expert detail with the entered task', async () => {
    const actions = face()
    render(<ExpertTeamCard {...props(actions)} />)
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '打开能力中心' }))
    fireEvent.click(screen.getByRole('button', { name: /架构师/ }))

    const input = screen.getByRole('textbox', { name: '任务或问题' })
    fireEvent.change(input, { target: { value: '设计一个支付模块' } })
    fireEvent.click(screen.getByRole('button', { name: '启动流水线' }))
    await settle()

    expect(actions.startRun).toHaveBeenCalledWith({ teamId: 'dev', input: '设计一个支付模块' })
    expect(input).toHaveProperty('value', '')
  })

  it('consults an expert and shows the bounded answer in the detail', async () => {
    const consult = vi.fn(async (): Promise<RemoteResult<ExpertTeamConsultResult>> =>
      ok({ answer: '建议先做服务拆分。', truncated: false }))
    const actions = face({ consult })
    render(<ExpertTeamCard {...props(actions)} />)
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '打开能力中心' }))
    fireEvent.click(screen.getByRole('button', { name: /架构师/ }))

    const input = screen.getByRole('textbox', { name: '任务或问题' })
    fireEvent.change(input, { target: { value: '如何拆分服务？' } })
    fireEvent.click(screen.getByRole('button', { name: '召唤专家' }))
    await settle()

    expect(consult).toHaveBeenCalledWith({ teamId: 'dev', expertId: 'architect', question: '如何拆分服务？' })
    expect(screen.getByRole('region', { name: '专家回答' }).textContent).toContain('建议先做服务拆分。')
  })

  it('reports a consult failure without leaving the detail in a thinking state', async () => {
    const consult = vi.fn(async (): Promise<RemoteResult<ExpertTeamConsultResult>> => ({
      ok: false,
      // ExpertTeamError crosses the wire as gateway/internal (rpcFailure).
      error: new RemoteError('gateway/internal', 'model offline', {}),
    }))
    const actions = face({ consult })
    render(<ExpertTeamCard {...props(actions)} />)
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '打开能力中心' }))
    fireEvent.click(screen.getByRole('button', { name: /架构师/ }))

    const input = screen.getByRole('textbox', { name: '任务或问题' })
    fireEvent.change(input, { target: { value: '如何拆分服务？' } })
    fireEvent.click(screen.getByRole('button', { name: '召唤专家' }))
    await settle()

    expect(screen.getByRole('alert').textContent).toContain('model offline')
    expect(screen.queryByText('专家正在思考…')).toBeNull()
  })

  it('reviews a waiting-approval run: reads gate questions and records the decision', async () => {
    const getRun = vi.fn(async (): Promise<RemoteResult<ExpertTeamRunDetail>> => ok(RUN_DETAIL))
    const approve = vi.fn(async (): Promise<RemoteResult<ExpertTeamRunDetail>> => ok(RUN_DETAIL))
    const load = vi.fn(async (): Promise<RemoteResult<ExpertTeamSnapshot>> => ok({
      ...SNAPSHOT,
      runs: [{
        runId: 'run-1',
        teamId: 'dev',
        mode: 'hierarchical' as const,
        status: 'waiting-approval' as const,
        createdAt: '2026-09-17T00:00:00.000Z',
      }],
    }))
    const actions = face({ getRun, approve, load })
    render(<ExpertTeamCard {...props(actions)} />)
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '打开能力中心' }))

    fireEvent.click(screen.getByRole('button', { name: '审批' }))
    await settle()
    expect(getRun).toHaveBeenCalledWith({ runId: 'run-1' })
    expect(screen.getByText('需要你回答的问题')).not.toBeNull()
    expect(screen.getByText('这个需求的目标用户是谁？')).not.toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '通过' }))
    expect(approve).toHaveBeenCalledWith({ runId: 'run-1', decision: 'approved' })
  })

  it('records a rejection with the entered comment', async () => {
    const approve = vi.fn(async (): Promise<RemoteResult<ExpertTeamRunDetail>> => ok(RUN_DETAIL))
    const load = vi.fn(async (): Promise<RemoteResult<ExpertTeamSnapshot>> => ok({
      ...SNAPSHOT,
      runs: [{
        runId: 'run-1',
        teamId: 'dev',
        mode: 'hierarchical' as const,
        status: 'waiting-approval' as const,
        createdAt: '2026-09-17T00:00:00.000Z',
      }],
    }))
    const actions = face({ approve, load })
    render(<ExpertTeamCard {...props(actions)} />)
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '打开能力中心' }))
    fireEvent.click(screen.getByRole('button', { name: '审批' }))
    await settle()

    fireEvent.change(screen.getByRole('textbox', { name: '评审意见（可选）' }), { target: { value: '补充验收标准' } })
    fireEvent.click(screen.getByRole('button', { name: '拒绝' }))
    expect(approve).toHaveBeenCalledWith({ runId: 'run-1', decision: 'rejected', comment: '补充验收标准' })
  })

  it('reports unavailable capability tabs when no provider is mounted', async () => {
    const actions = face()
    render(<ExpertTeamCard {...props(actions)} />)
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '打开能力中心' }))

    fireEvent.click(screen.getByRole('tab', { name: '技能' }))
    expect(screen.getByRole('heading', { name: '技能' })).not.toBeNull()
    expect(screen.getByText('当前部署未启用技能。')).not.toBeNull()
    expect(screen.queryByRole('textbox', { name: '搜索专家' })).toBeNull()

    fireEvent.click(screen.getByRole('tab', { name: '连接器' }))
    expect(screen.getByRole('heading', { name: '连接器' })).not.toBeNull()
    expect(screen.getByText('当前部署未启用连接器。')).not.toBeNull()

    fireEvent.click(screen.getByRole('tab', { name: '记忆库' }))
    expect(screen.getByText('当前部署未启用记忆库。')).not.toBeNull()
  })

  it('dispatches each capability tab to its registered content and returns to the expert catalog', async () => {
    const renderSlot = vi.fn<ExpertTeamCardProps['renderSlot']>((_slot, _owner, options) => (
      <p>{options?.entryKey}</p>
    ))
    render(<ExpertTeamCard {...props(face())} renderSlot={renderSlot} />)
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '打开能力中心' }))

    for (const [label, key] of [['技能', 'skills'], ['连接器', 'connectors'], ['记忆库', 'library']] as const) {
      fireEvent.click(screen.getByRole('tab', { name: label }))
      expect(screen.getByRole('tabpanel', { name: label }).textContent).toBe(key)
      expect(renderSlot).toHaveBeenLastCalledWith('capabilities.center.tab', {}, expect.objectContaining({ entryKey: key }))
      expect(screen.queryByRole('textbox', { name: '搜索专家' })).toBeNull()
    }

    fireEvent.click(screen.getByRole('tab', { name: '专家' }))
    expect(screen.getByRole('main', { name: '专家目录' })).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '关闭能力中心' }))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('sorts by name and filters by the selected team', async () => {
    const actions = face()
    render(<ExpertTeamCard {...props(actions)} />)
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '打开能力中心' }))

    fireEvent.click(screen.getByRole('button', { name: '软件开发专家团', pressed: false }))
    expect(screen.queryByText('课题侦察员')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '名称', pressed: false }))
    expect(screen.getByText('架构师')).not.toBeNull()
  })

  it('reports a Remote failure and supports closing the surface', async () => {
    const load = vi.fn(async (): Promise<RemoteResult<ExpertTeamSnapshot>> => ({
      ok: false,
      error: new RemoteError('gateway/internal', 'offline', {}),
    }))
    const actions = face({ load })
    render(<ExpertTeamCard {...props(actions)} />)
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '打开能力中心' }))
    expect(screen.getByRole('alert').textContent).toContain('offline')
    fireEvent.click(screen.getByRole('button', { name: '关闭能力中心' }))
    expect(screen.queryByRole('dialog', { name: '能力中心' })).toBeNull()
  })
})
