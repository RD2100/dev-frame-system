/** The gateway is a thin delegation layer: verify each Remote method passes
 * the UI request through to the orchestrator and returns its result. */

import { Context } from '@deepseek-ai/cordis'
import { describe, expect, it, vi } from 'vitest'
import { ExpertTeamGateway } from '../src/gateway.ts'
import type { TeamOrchestrator } from '../src/orchestrate.ts'
import type { TeamRun } from '../src/types.ts'

const RUN: TeamRun = {
  runId: 'run-1' as TeamRun['runId'],
  teamId: 'dev',
  mode: 'hierarchical',
  status: 'running',
  createdAt: '2026-09-17T00:00:00.000Z',
  phases: [{ phaseId: 'prd', status: 'running', attempts: 1 }],
}

/** Build one fake orchestrator and return its spies alongside for assertions. */
function fakeOrchestrator(): {
  readonly orchestrator: TeamOrchestrator
  readonly listTeams: ReturnType<typeof vi.fn>
  readonly listRuns: ReturnType<typeof vi.fn>
  readonly startRun: ReturnType<typeof vi.fn>
  readonly consult: ReturnType<typeof vi.fn>
  readonly approve: ReturnType<typeof vi.fn>
  readonly getRun: ReturnType<typeof vi.fn>
} {
  const listTeams = vi.fn(() => [])
  const listRuns = vi.fn(() => [{ ...RUN, status: 'running' as const }])
  const startRun = vi.fn(async () => RUN)
  const consult = vi.fn(async () => ({ answer: '先拆分服务。', truncated: false }))
  const approve = vi.fn(async () => RUN)
  const getRun = vi.fn(() => RUN)
  const orchestrator = {
    listTeams,
    listRuns,
    startRun,
    consult,
    approve,
    getRun,
  } as unknown as TeamOrchestrator
  return { orchestrator, listTeams, listRuns, startRun, consult, approve, getRun }
}

describe('ExpertTeamGateway Remote delegation', () => {
  it('view() reads the catalog and run index', () => {
    const { orchestrator, listTeams, listRuns } = fakeOrchestrator()
    const gateway = new ExpertTeamGateway(new Context(), orchestrator)
    const snapshot = gateway.view()
    expect(snapshot.teams).toEqual([])
    expect(snapshot.runs).toHaveLength(1)
    expect(listTeams).toHaveBeenCalledOnce()
    expect(listRuns).toHaveBeenCalledOnce()
  })

  it('startRun() passes the team and input through', async () => {
    const { orchestrator, startRun } = fakeOrchestrator()
    const gateway = new ExpertTeamGateway(new Context(), orchestrator)
    await expect(gateway.startRun({ teamId: 'dev', input: '设计支付模块' })).resolves.toBe(RUN)
    expect(startRun).toHaveBeenCalledWith('dev', '设计支付模块')
  })

  it('consult() passes the team, expert, and question through', async () => {
    const { orchestrator, consult } = fakeOrchestrator()
    const gateway = new ExpertTeamGateway(new Context(), orchestrator)
    await expect(gateway.consult({ teamId: 'dev', expertId: 'architect', question: '如何拆分服务？' })).resolves
      .toEqual({ answer: '先拆分服务。', truncated: false })
    expect(consult).toHaveBeenCalledWith('dev', 'architect', '如何拆分服务？')
  })

  it('approve() forwards the decision and an explicit comment', async () => {
    const { orchestrator, approve } = fakeOrchestrator()
    const gateway = new ExpertTeamGateway(new Context(), orchestrator)
    await expect(gateway.approve({ runId: 'run-1', decision: 'rejected', comment: '补充验收标准' })).resolves.toBe(RUN)
    expect(approve).toHaveBeenCalledWith('run-1', 'rejected', '补充验收标准')
  })

  it('approve() omits the comment when the UI sends none', async () => {
    const { orchestrator, approve } = fakeOrchestrator()
    const gateway = new ExpertTeamGateway(new Context(), orchestrator)
    await gateway.approve({ runId: 'run-1', decision: 'approved' })
    expect(approve).toHaveBeenCalledWith('run-1', 'approved', undefined)
  })

  it('getRun() reads one live run snapshot', () => {
    const { orchestrator, getRun } = fakeOrchestrator()
    const gateway = new ExpertTeamGateway(new Context(), orchestrator)
    expect(gateway.getRun({ runId: 'run-1' })).toBe(RUN)
    expect(getRun).toHaveBeenCalledWith('run-1')
  })
})
