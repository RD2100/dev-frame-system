import { describe, expect, it } from 'vitest'
import {
  DEVFRAME_DELEGATION_DEPTH_BUDGET,
  DEVFRAME_SPAWN_TOOL_NAME,
  devframeSpawnOverrides,
} from '../src/hierarchy/index.ts'

describe('devframeSpawnOverrides', () => {
  it('pins the whole DevFrame tree to the controller-lead-worker budget', () => {
    expect(DEVFRAME_DELEGATION_DEPTH_BUDGET).toBe(2)
  })

  it('keeps a lead spawn-capable under the depth budget alone', () => {
    expect(devframeSpawnOverrides('lead')).toEqual({ maxDepth: 2 })
    expect(devframeSpawnOverrides('lead').toolFilter).toBeUndefined()
  })

  it('denies only the spawn tool for a worker and keeps its reporting channel', () => {
    const overrides = devframeSpawnOverrides('worker')
    expect(overrides.maxDepth).toBe(2)
    expect(overrides.toolFilter).toEqual({ deny: ['subagent'] })
    expect(overrides.toolFilter!.deny).not.toContain('send_message')
    expect(overrides.toolFilter!.deny).not.toContain('interrupt_agent')
  })

  it('uses the deployed delegation tool name when the deployment renamed it', () => {
    expect(devframeSpawnOverrides('worker', { spawnToolName: 'delegate_tasks' }))
      .toEqual({ maxDepth: 2, toolFilter: { deny: ['delegate_tasks'] } })
    expect(DEVFRAME_SPAWN_TOOL_NAME).toBe('subagent')
  })

  it('returns detached overrides that later calls cannot mutate', () => {
    const first = devframeSpawnOverrides('worker')
    const second = devframeSpawnOverrides('worker')
    expect(first).not.toBe(second)
    expect(first.toolFilter).not.toBe(second.toolFilter)
    expect(devframeSpawnOverrides('lead')).toEqual({ maxDepth: 2 })
  })
})
