/**
 * File-backed Goal binding store: the JSON ledger's durable boundary.
 * Binding and workspace-current round trips across store instances, a
 * controller-level restart resuming the bound Goal from the same ledger,
 * idempotent and conflicting save outcomes on the reused
 * `GOAL_BINDING_CONFLICT` code, corrupt ledger documents on the stable
 * `GOAL_BINDING_PERSISTENCE` code with the file's bytes never repaired,
 * missing-ledger and raw-fs behavior, the pinned pretty-JSON format, and
 * detached loads with per-workspace current upserts.
 * @module dsh-experimental-devframe/tests/goal-binding-file-store
 */

import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { GoalId } from '@deepseek-ai/dsh-goal'
import {
  ControllerSessionId,
  GoalBindingController,
  GoalBindingError,
  TaskId,
  createHumanAuthorization,
} from '../src/controller/goal-binding.ts'
import type { GoalBinding, NativeGoalPort, NativeGoalState } from '../src/controller/goal-binding.ts'
import { FileGoalBindingStore } from '../src/goal-binding-file-store.ts'
import {
  AcceptanceHash,
  ConfigurationConfirmationId,
  DevFrameSnapshotId,
  SourceFingerprint,
  WorkspaceId,
} from '../src/shared/types.ts'
import type { ProjectBindingRecord } from '../src/shared/types.ts'

const CONFLICT = { name: 'GoalBindingError', code: 'GOAL_BINDING_CONFLICT' }
const CORRUPT = { name: 'GoalBindingError', code: 'GOAL_BINDING_PERSISTENCE' }

/** Temp roots acquired by this file, drained to quiescence by afterEach. */
const tempRoots: string[] = []

afterEach(async () => {
  const roots = [...tempRoots]
  tempRoots.length = 0
  await Promise.all(roots.map(root => rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })))
})

/** Create one unique temp directory and a store whose ledger lives inside it. */
async function ledgerFixture(): Promise<{ path: string; store: FileGoalBindingStore }> {
  const root = await mkdtemp(join(tmpdir(), 'dsh-devframe-goalstore-'))
  tempRoots.push(root)
  const path = join(root, 'goal-binding-ledger.json')
  return { path, store: new FileGoalBindingStore({ path }) }
}

/** Write raw ledger bytes directly, bypassing the store, to pin the durable boundary. */
function writeLedger(path: string, content: string): Promise<void> {
  return writeFile(path, content, 'utf8')
}

/** One complete binding; `overrides` injects field deviations. */
function bindingFixture(overrides: Partial<GoalBinding> = {}): GoalBinding {
  return {
    version: 1,
    workspaceId: WorkspaceId('workspace-ledger'),
    controllerSessionId: ControllerSessionId('controller-ledger'),
    goalId: GoalId('goal-ledger-1'),
    goalRevision: 2,
    taskIds: [TaskId('task-1')],
    acceptanceHash: AcceptanceHash('acceptance-ledger'),
    sourceFingerprint: SourceFingerprint('source-ledger'),
    snapshotId: DevFrameSnapshotId('snapshot-ledger'),
    confirmation: {
      id: ConfigurationConfirmationId('confirm-ledger'),
      acceptanceHash: AcceptanceHash('acceptance-ledger'),
    },
    lifecycle: 'admission_open',
    budget: { maxAttempts: 3, consumedAttempts: 1 },
    ...overrides,
  }
}

/** One complete workspace current record; `overrides` injects field deviations. */
function recordFixture(overrides: Partial<ProjectBindingRecord> = {}): ProjectBindingRecord {
  return {
    workspaceId: WorkspaceId('workspace-ledger'),
    controllerSessionId: ControllerSessionId('controller-ledger'),
    goalId: GoalId('goal-ledger-1'),
    goalRevision: 2,
    acceptanceHash: AcceptanceHash('acceptance-ledger'),
    sourceFingerprint: SourceFingerprint('source-ledger'),
    confirmation: {
      id: ConfigurationConfirmationId('confirm-ledger'),
      acceptanceHash: AcceptanceHash('acceptance-ledger'),
    },
    lifecycle: 'admission_open',
    ...overrides,
  }
}

/** One start request for the controller-level restart case. */
function startRequest(overrides: Partial<Parameters<GoalBindingController['start']>[0]> = {}) {
  return {
    objective: 'implement goal binding persistence',
    taskIds: [TaskId('task-1')],
    acceptanceHash: AcceptanceHash('acceptance-a'),
    sourceFingerprint: SourceFingerprint('source-a'),
    snapshotId: DevFrameSnapshotId('snapshot-a'),
    budget: { maxAttempts: 3 },
    authorization: createHumanAuthorization('confirm-a'),
    ...overrides,
  }
}

interface TraceGoal extends NativeGoalState {
  activation: 'armed' | 'disarmed'
}

/** Build the minimal native Goal port shape used by the controller restart case. */
function fakeGoals(trace: string[]): NativeGoalPort & { current: TraceGoal | undefined } {
  let nextGoal = 1
  const port: NativeGoalPort & { current: TraceGoal | undefined } = {
    current: undefined,
    create(request) {
      trace.push(`goal:create:${request.objective}`)
      const goal: TraceGoal = {
        id: GoalId(`goal-${nextGoal}`),
        revision: 1,
        phase: 'active',
        activation: 'armed',
      }
      nextGoal += 1
      port.current = goal
      return goal
    },
    disarm() {
      trace.push('goal:disarm')
      if (port.current !== undefined) port.current = { ...port.current, activation: 'disarmed' }
      return port.current
    },
    get() {
      trace.push('goal:get')
      return port.current
    },
    resume(ref) {
      trace.push(`goal:resume:${ref.id}:${ref.revision}`)
      if (port.current === undefined || port.current.id !== ref.id) {
        throw new Error('resume target mismatch')
      }
      port.current = {
        ...port.current,
        revision: port.current.revision + 1,
        activation: 'armed',
      }
      return port.current
    },
    complete(ref) {
      trace.push(`goal:complete:${ref.id}:${ref.revision}`)
      if (port.current === undefined || port.current.id !== ref.id) {
        throw new Error('complete target mismatch')
      }
      port.current = {
        ...port.current,
        revision: port.current.revision + 1,
        phase: 'complete',
        activation: 'disarmed',
      }
      return port.current
    },
  }
  return port
}

/** One schema-valid binding entry as it sits in the ledger JSON. */
function validBindingEntry(
  overrides: Record<string, unknown> = {},
  extra: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    version: 1,
    workspaceId: 'workspace-ledger',
    controllerSessionId: 'controller-ledger',
    goalId: 'goal-ledger-1',
    goalRevision: 2,
    taskIds: ['task-1'],
    acceptanceHash: 'acceptance-ledger',
    sourceFingerprint: 'source-ledger',
    snapshotId: 'snapshot-ledger',
    confirmation: { id: 'confirm-ledger', acceptanceHash: 'acceptance-ledger' },
    lifecycle: 'admission_open',
    budget: { maxAttempts: 3, consumedAttempts: 1 },
    ...overrides,
    ...extra,
  }
}

/** One schema-valid current entry as it sits in the ledger JSON. */
function validCurrentEntry(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    workspaceId: 'workspace-ledger',
    controllerSessionId: 'controller-ledger',
    goalId: 'goal-ledger-1',
    goalRevision: 2,
    acceptanceHash: 'acceptance-ledger',
    sourceFingerprint: 'source-ledger',
    confirmation: { id: 'confirm-ledger', acceptanceHash: 'acceptance-ledger' },
    lifecycle: 'admission_open',
    ...overrides,
  }
}

/** Drop one field from an otherwise valid binding entry. */
function bindingEntryWithout(field: string): Record<string, unknown> {
  const entry = validBindingEntry()
  delete entry[field]
  return entry
}

/** Wrap entries into the envelope JSON; `extra` injects schema-violating tail keys. */
function ledgerJson(bindings: readonly unknown[] = [], currents: readonly unknown[] = [], extra = ''): string {
  return `{"version":1,"bindings":${JSON.stringify(bindings)},"currents":${JSON.stringify(currents)}${extra}}`
}

const corruptLedgers: Array<[string, string]> = [
  ['not valid JSON bytes', '{not json'],
  ['ledger version 0', '{"version":0,"bindings":[],"currents":[]}'],
  ['a future ledger version', '{"version":2,"bindings":[],"currents":[]}'],
  ['an unknown top-level key', ledgerJson([], [], ',"extra":true')],
  ['a missing bindings field', '{"version":1,"currents":[]}'],
  ['a missing currents field', '{"version":1,"bindings":[]}'],
  ['a non-array bindings value', '{"version":1,"bindings":"none","currents":[]}'],
  ['a non-array currents value', '{"version":1,"bindings":[],"currents":"none"}'],
  ['a non-object root', '[]'],
  ['a string root', '"ledger"'],
  ['a binding entry missing a required field', ledgerJson([bindingEntryWithout('acceptanceHash')])],
  ['a binding entry with an unknown key', ledgerJson([validBindingEntry({}, { extra: true })])],
  ['an empty branded identifier', ledgerJson([validBindingEntry({ workspaceId: '' })])],
  ['a whitespace-padded branded identifier', ledgerJson([validBindingEntry({ workspaceId: ' workspace-ledger ' })])],
  ['a blank branded identifier', ledgerJson([validBindingEntry({ workspaceId: '   ' })])],
  ['a non-positive goal revision', ledgerJson([validBindingEntry({ goalRevision: 0 })])],
  ['a non-safe-integer goal revision', ledgerJson([validBindingEntry({ goalRevision: 1.5 })])],
  ['an empty taskIds array', ledgerJson([validBindingEntry({ taskIds: [] })])],
  ['a duplicate task id', ledgerJson([validBindingEntry({ taskIds: ['task-1', 'task-1'] })])],
  ['a budget consuming above its maximum', ledgerJson([validBindingEntry({ budget: { maxAttempts: 3, consumedAttempts: 4 } })])],
  ['a lifecycle outside the enum', ledgerJson([validBindingEntry({ lifecycle: 'detached' })])],
  ['a duplicate binding identity', ledgerJson([validBindingEntry(), validBindingEntry()])],
  ['a duplicate workspace current', ledgerJson([], [validCurrentEntry(), validCurrentEntry({ goalId: 'goal-ledger-2' })])],
]

describe('file-backed binding round-trip and persistence', () => {
  it('persists one binding across store instances with brands intact', async () => {
    const { path, store } = await ledgerFixture()
    const binding = bindingFixture()
    await store.save(binding)
    const fresh = new FileGoalBindingStore({ path })
    await expect(fresh.load(binding.controllerSessionId)).resolves.toEqual([binding])
    await expect(fresh.load(ControllerSessionId('controller-other'))).resolves.toEqual([])
  })

  it('persists the workspace current record across store instances', async () => {
    const { path, store } = await ledgerFixture()
    const record = recordFixture()
    await store.write(record)
    const fresh = new FileGoalBindingStore({ path })
    await expect(fresh.read(record.workspaceId)).resolves.toEqual(record)
    await expect(fresh.read(WorkspaceId('workspace-other'))).resolves.toBeUndefined()
  })
})

describe('controller-level restart through the file store', () => {
  it('resumes the bound Goal on a fresh controller reading the same ledger', async () => {
    const { path } = await ledgerFixture()
    const controllerA = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-restart'),
      controllerSessionId: ControllerSessionId('controller-restart'),
      goals: fakeGoals([]),
      store: new FileGoalBindingStore({ path }),
    })
    const started = await controllerA.start(startRequest())

    const goalsB = fakeGoals([])
    goalsB.current = {
      id: started.goalId,
      revision: started.goalRevision,
      phase: 'active',
      activation: 'disarmed',
    }
    const controllerB = new GoalBindingController({
      workspaceId: WorkspaceId('workspace-restart'),
      controllerSessionId: ControllerSessionId('controller-restart'),
      goals: goalsB,
      store: new FileGoalBindingStore({ path }),
    })
    const resumed = await controllerB.resume(
      { controllerSessionId: ControllerSessionId('controller-restart'), goalId: started.goalId },
      createHumanAuthorization('confirm-restart'),
    )
    expect(resumed).toEqual({ ...started, goalRevision: started.goalRevision + 1 })
    expect(controllerB.admissionState).toBe('open')
  })
})

describe('file-backed save identity semantics', () => {
  it('keeps a repeated identical save idempotent in the ledger', async () => {
    const { path, store } = await ledgerFixture()
    await store.save(bindingFixture())
    await store.save(bindingFixture())
    const document = JSON.parse(await readFile(path, 'utf8')) as { bindings: readonly unknown[] }
    expect(document.bindings).toHaveLength(1)
  })

  it('replaces the stored binding in place when the same tuple advances its revision', async () => {
    const { path, store } = await ledgerFixture()
    await store.save(bindingFixture())
    await store.save(bindingFixture({ goalRevision: 3 }))
    const document = JSON.parse(await readFile(path, 'utf8')) as { bindings: Array<{ goalRevision: number }> }
    expect(document.bindings).toHaveLength(1)
    expect(document.bindings[0]?.goalRevision).toBe(3)
  })

  it('rejects identity reuse with a different acceptance hash on both instances', async () => {
    const { path, store } = await ledgerFixture()
    await store.save(bindingFixture())
    const reused = bindingFixture({
      acceptanceHash: AcceptanceHash('acceptance-other'),
      confirmation: {
        id: ConfigurationConfirmationId('confirm-ledger'),
        acceptanceHash: AcceptanceHash('acceptance-other'),
      },
    })
    await expect(store.save(reused)).rejects.toMatchObject(CONFLICT)
    const fresh = new FileGoalBindingStore({ path })
    await expect(fresh.save(reused)).rejects.toMatchObject(CONFLICT)
  })

  it('rejects a save whose revision precedes the stored one for the same tuple', async () => {
    const { path, store } = await ledgerFixture()
    await store.save(bindingFixture({ goalRevision: 3 }))
    await expect(store.save(bindingFixture())).rejects.toMatchObject(CONFLICT)
    const document = JSON.parse(await readFile(path, 'utf8')) as { bindings: Array<{ goalRevision: number }> }
    expect(document.bindings).toHaveLength(1)
    expect(document.bindings[0]?.goalRevision).toBe(3)
  })
})

describe('file-backed corrupt ledger boundary', () => {
  it('refuses to save onto a corrupt ledger instead of repairing it', async () => {
    const { path, store } = await ledgerFixture()
    await writeLedger(path, '{not json')
    const before = await readFile(path)
    const rejection = await store.save(bindingFixture()).then(() => null, (error: unknown) => error)
    expect(rejection).toBeInstanceOf(GoalBindingError)
    const error = rejection as GoalBindingError
    expect(error.code).toBe('GOAL_BINDING_PERSISTENCE')
    expect(error.message).toContain(path)
    expect((await readFile(path)).equals(before)).toBe(true)
  })

  it.each(corruptLedgers)('rejects %s on load and save with GOAL_BINDING_PERSISTENCE', async (_label, raw) => {
    const { path, store } = await ledgerFixture()
    await writeLedger(path, raw)
    await expect(store.load(ControllerSessionId('controller-ledger'))).rejects.toMatchObject(CORRUPT)
    await expect(store.save(bindingFixture())).rejects.toMatchObject(CORRUPT)
  })
})

describe('file-backed missing ledger and raw fs errors', () => {
  it('treats a missing ledger as an empty store', async () => {
    const { store } = await ledgerFixture()
    await expect(store.load(ControllerSessionId('controller-ledger'))).resolves.toEqual([])
    await expect(store.read(WorkspaceId('workspace-ledger'))).resolves.toBeUndefined()
  })

  it('propagates the raw fs error when saving into a missing directory', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-devframe-goalstore-'))
    tempRoots.push(root)
    const store = new FileGoalBindingStore({ path: join(root, 'absent', 'ledger.json') })
    const rejection = await store.save(bindingFixture()).then(() => null, (error: unknown) => error)
    expect(rejection).toBeInstanceOf(Error)
    expect(rejection).not.toBeInstanceOf(GoalBindingError)
  })

  it('propagates the raw fs error when the ledger path is a directory', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-devframe-goalstore-'))
    tempRoots.push(root)
    const store = new FileGoalBindingStore({ path: root })
    const rejection = await store.save(bindingFixture()).then(() => null, (error: unknown) => error)
    expect(rejection).toBeInstanceOf(Error)
    expect(rejection).not.toBeInstanceOf(GoalBindingError)
  })
})

describe('file-backed ledger format and detachment', () => {
  it('writes a pretty JSON ledger with the pinned format and exactly one trailing newline', async () => {
    const { path, store } = await ledgerFixture()
    await store.save(bindingFixture())
    const raw = await readFile(path, 'utf8')
    const document = JSON.parse(raw) as { version: number; bindings: readonly unknown[] }
    expect(document.version).toBe(1)
    expect(document.bindings).toHaveLength(1)
    expect(raw.startsWith('{\n  "version": 1,')).toBe(true)
    expect(raw.endsWith('\n')).toBe(true)
    expect(raw.endsWith('\n\n')).toBe(false)
  })

  it('returns detached bindings that do not affect later reads', async () => {
    const { store } = await ledgerFixture()
    await store.save(bindingFixture())
    const loaded = await store.load(ControllerSessionId('controller-ledger'))
    const first = loaded[0]
    if (first === undefined) throw new Error('expected the saved binding')
    const mutated = first as { goalRevision: number; budget: { consumedAttempts: number } }
    mutated.goalRevision = 99
    mutated.budget.consumedAttempts = 99
    await expect(store.load(ControllerSessionId('controller-ledger'))).resolves.toEqual([bindingFixture()])
  })

  it('keeps two workspaces currents independent under upsert', async () => {
    const { path, store } = await ledgerFixture()
    const a = recordFixture()
    const b = recordFixture({ workspaceId: WorkspaceId('workspace-b'), goalId: GoalId('goal-ledger-2') })
    await store.write(a)
    await store.write(b)
    const updated = recordFixture({ goalRevision: 5, lifecycle: 'stopped' })
    await store.write(updated)
    const document = JSON.parse(await readFile(path, 'utf8')) as {
      currents: Array<{ workspaceId: string; goalRevision: number }>
    }
    expect(document.currents).toHaveLength(2)
    expect(document.currents[0]?.workspaceId).toBe('workspace-ledger')
    expect(document.currents[0]?.goalRevision).toBe(5)
    const fresh = new FileGoalBindingStore({ path })
    await expect(fresh.read(a.workspaceId)).resolves.toEqual(updated)
    await expect(fresh.read(b.workspaceId)).resolves.toEqual(b)
  })
})
