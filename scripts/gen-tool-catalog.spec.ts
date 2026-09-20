/** Project task schemas are harvested without executing task or Worker operations. */
import { Context } from '@deepseek-ai/cordis'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import { expect, it } from 'vitest'
import { assertToolsHarvested, PROJECT_TASK_TOOL_PACKAGE, PROJECT_DELIVERY_TOOL_PACKAGE, PROJECT_GOAL_EVIDENCE_TOOL_PACKAGE } from './gen-tool-catalog.ts'

it('harvests whole-Goal tools without opening the checks ledger or executing processes', async () => {
  const ctx = new Context()
  try {
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(SystemPrompt)
    await ctx.plugin(ToolRuntime)
    await PROJECT_GOAL_EVIDENCE_TOOL_PACKAGE.mount(ctx)
    const schemas = ctx.tools.schemas()
    expect(schemas.map(schema => schema.name)).toEqual(['project_goal_verify', 'project_goal_review'])
    expect(schemas[1]?.parameters.required).toEqual(['verificationId', 'decision', 'findings'])
    expect(() =>{  assertToolsHarvested(PROJECT_GOAL_EVIDENCE_TOOL_PACKAGE, 0) }).toThrow('booted without registering a single tool')
  } finally { await ctx.fiber.dispose() }
})

it('harvests the independently mounted project task schema', async () => {
  const ctx = new Context()
  try {
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(SystemPrompt)
    await ctx.plugin(ToolRuntime)
    await PROJECT_TASK_TOOL_PACKAGE.mount(ctx)
    const schemas = ctx.tools.schemas()
    expect(schemas.map(schema => schema.name)).toEqual(['project_task'])
    expect(schemas[0]?.parameters).toMatchObject({
      type: 'object', required: ['action', 'taskId'],
      properties: { action: { type: 'string' }, taskId: { type: 'string' }, briefing: { type: 'string' } },
    })
    expect(Object.keys(schemas[0]?.parameters.properties ?? {})).toEqual(['action', 'taskId', 'title', 'pluginId', 'briefing'])
    expect(() => { assertToolsHarvested(PROJECT_TASK_TOOL_PACKAGE, schemas.length) }).not.toThrow()
  } finally {
    await ctx.fiber.dispose()
  }
})

it('rejects a task consumer that mounted without registering its tool', () => {
  expect(() => { assertToolsHarvested(PROJECT_TASK_TOOL_PACKAGE, 0) }).toThrow('booted without registering a single tool')
})


it('harvests delivery and review schemas without executing their service placeholders', async () => {
  const ctx = new Context()
  try {
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(SystemPrompt)
    await ctx.plugin(ToolRuntime)
    await PROJECT_DELIVERY_TOOL_PACKAGE.mount(ctx)
    const schemas = ctx.tools.schemas()
    expect(schemas.map(schema => schema.name)).toEqual(['project_deliver', 'project_evidence', 'project_review', 'project_commit'])
    expect(schemas[0]?.parameters.required).toEqual(['taskId'])
    expect(Object.keys(schemas[0]?.parameters.properties ?? {})).toEqual(['taskId', 'retryChecks'])
    expect(schemas[1]?.parameters.required).toEqual(['taskId'])
    expect(Object.keys(schemas[1]?.parameters.properties ?? {})).toEqual(['taskId'])
    expect(schemas[2]?.parameters.required).toEqual(['taskId', 'decision', 'findings'])
    expect(Object.keys(schemas[2]?.parameters.properties ?? {})).toEqual(['taskId', 'decision', 'findings'])
    expect(() => { assertToolsHarvested(PROJECT_DELIVERY_TOOL_PACKAGE, 0) }).toThrow('booted without registering a single tool')
  } finally {
    await ctx.fiber.dispose()
  }
})
