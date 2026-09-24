/**
 * The D1 Desktop overlay fixes the three launch-cwd path expressions of the
 * DevFrame profile bundle. Compose the bundle patch with the substituted
 * overlay exactly as `applyEntryPatches` does at load, and assert the three
 * fields are overridden while the rest of each row's config survives.
 * @module tests/desktop-plugin-delivery-overlay
 */

import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import { applyEntryPatches, entryListSchema, type PatchOptions } from '@deepseek-ai/cordis-plugin-include'
import * as yaml from 'js-yaml'

const PROFILE_PATCH = resolve(import.meta.dirname, '../../packages/experimental/devframe-profile/cordis.patch.yml')
const OVERLAY_PATCH = resolve(import.meta.dirname, 'desktop.devframe.cordis.patch.yml')

const WORKSPACE = 'C:/dsh-desktop-profile/devframe-workspace'
const PAPER = 'C:/dsh-desktop-profile/node_modules/@deepseek-ai/dsh-experimental-expert-pack-paper'
const DEV = 'C:/dsh-desktop-profile/node_modules/@deepseek-ai/dsh-experimental-expert-pack-dev'

async function parsePatch(file: string): Promise<PatchOptions[]> {
  const text = await readFile(file, 'utf8')
  return yaml.load(text, { schema: entryListSchema }) as PatchOptions[]
}

/** Read the overlay and substitute the D5 packaging-time tokens. */
async function overlay(substitute: boolean): Promise<PatchOptions[]> {
  let text = await readFile(OVERLAY_PATCH, 'utf8')
  if (substitute) {
    text = text
      .replaceAll('<DSH_WORKSPACE_ROOT>', WORKSPACE)
      .replaceAll('<PACK_PAPER_DIR>', PAPER)
      .replaceAll('<PACK_DEV_DIR>', DEV)
  }
  return yaml.load(text, { schema: entryListSchema }) as PatchOptions[]
}

/**
 * Compose the profile over the Web/base rows it patches, then the deployment
 * overlay. The profile disables and reconfigures four rows supplied by the
 * base bundle before inserting its own rows.
 */
async function compose(overlayRows: PatchOptions[], warn: (...args: unknown[]) => void): Promise<PatchOptions[]> {
  const bundle = await parsePatch(PROFILE_PATCH)
  const baseRows: Parameters<typeof applyEntryPatches>[0] = [
    { id: 'tool-subagent-control', name: '@deepseek-ai/dsh-tool-subagent-control' },
    { id: 'tool-subagent-list-agents', name: '@deepseek-ai/dsh-tool-subagent-control/list-agents' },
    { id: 'tool-subagent', name: '@deepseek-ai/dsh-tool-subagent' },
    { id: 'tool-subagent-fork', name: '@deepseek-ai/dsh-tool-subagent' },
  ]
  const base = applyEntryPatches(baseRows, bundle, warn)
  return applyEntryPatches(base, overlayRows, warn)
}

function findRow(rows: PatchOptions[], id: string): PatchOptions | undefined {
  return rows.find(row => row.id === id)
}

/** Typed projection of the two rows under test; `config` is schema-`any`. */
interface GoalConfig {
  readonly workspaceRoot?: string
}
interface ExpertConfig {
  readonly packs?: readonly string[]
}

describe('the D1 Desktop overlay', () => {
  it('replaces the three launch-cwd expressions and keeps every other row field', async () => {
    const warn = vi.fn()
    const composed = await compose(await overlay(true), warn)
    expect(warn).not.toHaveBeenCalled()

    const goal = findRow(composed, 'command-goal-binding')
    expect(goal?.config).toMatchObject({
      workspaceId: 'default',
      workspaceRoot: WORKSPACE,
      requiredChecksPath: { __jsExpr: "dshHomePath('required-checks.json')" },
      maxAttempts: 3,
      maxGoalRounds: 8,
      taskIds: ['devframe-goal'],
      checks: {
        version: 1,
        checks: [{
          checkId: 'git-diff-check',
          executable: 'git',
          arguments: ['diff', '--check'],
          cwd: WORKSPACE,
        }],
      },
    })

    const expert = findRow(composed, 'expert-team')
    expect(expert?.config).toEqual({
      packs: [PAPER, DEV],
      artifactsDir: { __jsExpr: "dshHomePath('expert-team-runs')" },
    })
  })

  it('leaves the substituted tokens as literal strings when staging forgot them, so load fails loud', async () => {
    const composed = await compose(await overlay(false), vi.fn())

    const goal = findRow(composed, 'command-goal-binding')
    expect((goal?.config as GoalConfig | undefined)?.workspaceRoot).toBe('<DSH_WORKSPACE_ROOT>')
    const expert = findRow(composed, 'expert-team')
    expect((expert?.config as ExpertConfig | undefined)?.packs).toEqual(['<PACK_PAPER_DIR>', '<PACK_DEV_DIR>'])
  })

  it('keeps the bundle row list intact and patches by id without inserts', async () => {
    const warn = vi.fn()
    const bundle = await parsePatch(PROFILE_PATCH)
    const composed = await compose(await overlay(true), warn)

    const inserted = bundle.flatMap(row => row.insert ?? [])
    // The four patched Web/base rows survive beside the profile's inserts.
    expect(composed.length).toBe(4 + inserted.length)
    for (const row of inserted) {
      if (row.id !== undefined && row.id !== 'command-goal-binding' && row.id !== 'expert-team') {
        expect(composed.some(candidate => candidate.id === row.id), `row ${row.id} must survive`).toBe(true)
      }
    }
    expect(warn).not.toHaveBeenCalled()
  })
})
