/**
 * File-backed {@link GoalBindingStore} reference implementation: the durable
 * controller-session Goal bindings and the workspace current bindings persist
 * as one JSON ledger whose path the host Config supplies, so an admitted Goal
 * outlives the process that started it.
 *
 * The ledger is the untrusted durable boundary and is validated wholesale on
 * every read: unparseable bytes, a wrong envelope (including a future
 * `version`), a binding or current record failing its schema or invariants,
 * and a repeated binding identity or workspace current all fail loud with
 * `GOAL_BINDING_PERSISTENCE` — a corrupt ledger is never repaired or
 * overwritten. A missing ledger is an empty store, never an error. Publishes
 * go through a same-directory temp file + rename, so a reader sees the old or
 * the new complete ledger and never a torn one; there are no locks, so the
 * store assumes a single writer and concurrent writers are last-writer-wins.
 * This is an injectable alternative to {@link MemoryGoalBindingStore}, not a
 * production composition: wiring it into a profile or host Config belongs to
 * the owning wave.
 * @module @deepseek-ai/dsh-experimental-devframe/goal-binding-file-store
 */

import { randomBytes } from 'node:crypto'
import { readFile, rename, writeFile } from 'node:fs/promises'
import { z } from 'zod'
import { GoalId as nativeGoalId } from '@deepseek-ai/dsh-goal'
import {
  ControllerSessionId,
  type GoalBinding,
  GoalBindingError,
  type GoalBindingStore,
  TaskId,
} from './controller/goal-binding.ts'
import {
  AcceptanceHash,
  ConfigurationConfirmationId,
  DevFrameSnapshotId,
  SourceFingerprint,
  WorkspaceId,
} from './shared/types.ts'
import type { ProjectBindingRecord } from './shared/types.ts'

/** Ledger format generation; a ledger written by another generation fails loud. */
const LEDGER_VERSION = 1

/** One identifier string at the durable boundary: non-empty, trimmed, and re-branded on decode. */
const identifierSchema = z.string().refine(
  value => value.length > 0 && value === value.trim(),
  { message: 'must be a non-empty trimmed string' },
)

/** One native Goal revision, aligned with the controller's revision validation. */
const goalRevisionSchema = z.number().refine(
  value => Number.isSafeInteger(value) && value >= 1,
  { message: 'must be a positive safe integer' },
)

/** One budget, matching the controller invariant that consumption stays within its limit. */
const budgetSchema = z.object({
  maxAttempts: z.number().refine(
    value => Number.isSafeInteger(value) && value >= 1,
    { message: 'maxAttempts must be a safe integer >= 1' },
  ),
  consumedAttempts: z.number().refine(
    value => Number.isSafeInteger(value) && value >= 0,
    { message: 'consumedAttempts must be a safe integer >= 0' },
  ),
}).strict().refine(
  budget => budget.consumedAttempts <= budget.maxAttempts,
  { message: 'consumedAttempts must not exceed maxAttempts' },
)

/** One human-approval reference as persisted. */
const confirmationSchema = z.object({
  id: identifierSchema,
  acceptanceHash: identifierSchema,
}).strict()

/** One full binding as persisted, every field required and unknown keys rejected. */
const bindingSchema = z.object({
  version: z.literal(LEDGER_VERSION),
  workspaceId: identifierSchema,
  controllerSessionId: identifierSchema,
  goalId: identifierSchema,
  goalRevision: goalRevisionSchema,
  taskIds: z.array(identifierSchema).min(1).refine(
    values => new Set(values).size === values.length,
    { message: 'task ids must be unique' },
  ),
  acceptanceHash: identifierSchema,
  sourceFingerprint: identifierSchema,
  snapshotId: identifierSchema,
  confirmation: confirmationSchema,
  lifecycle: z.enum([
    'admission_open',
    'stop_requested',
    'quiescence_confirmed',
    'stopped',
    'ambiguous',
    'needs_attention',
  ]),
  budget: budgetSchema,
}).strict()

/** One workspace current record as persisted, without the binding-only fields. */
const currentSchema = z.object({
  workspaceId: identifierSchema,
  controllerSessionId: identifierSchema,
  goalId: identifierSchema,
  goalRevision: goalRevisionSchema,
  acceptanceHash: identifierSchema,
  sourceFingerprint: identifierSchema,
  confirmation: confirmationSchema,
  lifecycle: z.enum([
    'admission_open',
    'stop_requested',
    'quiescence_confirmed',
    'stopped',
    'ambiguous',
    'needs_attention',
  ]),
}).strict()

const ledgerSchema = z.object({
  version: z.literal(LEDGER_VERSION),
  bindings: z.array(bindingSchema),
  currents: z.array(currentSchema),
}).strict()

/** The serializable whole-ledger document every publish writes. */
interface LedgerDocument {
  readonly version: typeof LEDGER_VERSION
  readonly bindings: readonly GoalBinding[]
  readonly currents: readonly ProjectBindingRecord[]
}

/** The parsed-and-validated ledger document every read and write builds on. */
interface ValidatedLedger {
  readonly bindings: readonly GoalBinding[]
  readonly currents: readonly ProjectBindingRecord[]
}

/**
 * Build the stable corruption error every ledger validation failure routes
 * through, so a broken durable boundary never surfaces as another code.
 * @param path - ledger path named in the fail-loud message.
 * @param summary - one-line description of what disagreed with the contract.
 * @param cause - underlying parse or schema error, when one exists.
 * @returns the persistence-classified corruption error.
 */
function corruptError(path: string, summary: string, cause?: unknown): GoalBindingError {
  return new GoalBindingError(
    `goal binding ledger "${path}" is corrupt: ${summary}`,
    'GOAL_BINDING_PERSISTENCE',
    cause === undefined ? {} : { cause },
  )
}

/**
 * Parse raw ledger bytes into the wholesale-validated, re-branded form: the
 * envelope and every binding and current record are schema-decoded and
 * identity-checked before any lookup runs, so corruption anywhere fails
 * every load, read, save, and write regardless of which identity is
 * requested.
 * @param raw - ledger bytes read as UTF-8 text.
 * @param path - ledger path named in the fail-loud messages.
 * @returns the validated bindings and currents in file order.
 * @throws {@link GoalBindingError} with `GOAL_BINDING_PERSISTENCE` when the
 *   bytes are not JSON, fail the ledger envelope or a record schema, or
 *   repeat a binding identity or workspace current.
 */
async function parseLedger(raw: string, path: string): Promise<ValidatedLedger> {
  let document: unknown
  try {
    document = JSON.parse(raw)
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error)
    throw corruptError(path, `not valid JSON (${reason})`, error)
  }
  const envelope = ledgerSchema.safeParse(document)
  if (!envelope.success) {
    const summary = envelope.error.issues
      .map(issue => [issue.path.map(String).join('.') || '(root)', issue.message].join(': '))
      .join('; ')
    throw corruptError(path, summary, envelope.error)
  }
  const bindingIdentities = new Set<string>()
  for (const [index, entry] of envelope.data.bindings.entries()) {
    const identity = `${entry.controllerSessionId}\u0000${entry.goalId}`
    if (bindingIdentities.has(identity)) {
      throw corruptError(
        path,
        `binding ${index} repeats the identity ("${entry.controllerSessionId}", "${entry.goalId}")`,
      )
    }
    bindingIdentities.add(identity)
  }
  const currentWorkspaces = new Set<string>()
  for (const [index, entry] of envelope.data.currents.entries()) {
    if (currentWorkspaces.has(entry.workspaceId)) {
      throw corruptError(path, `current ${index} repeats the workspace "${entry.workspaceId}"`)
    }
    currentWorkspaces.add(entry.workspaceId)
  }
  return {
    bindings: envelope.data.bindings.map(entry => ({
      version: 1,
      workspaceId: WorkspaceId(entry.workspaceId),
      controllerSessionId: ControllerSessionId(entry.controllerSessionId),
      goalId: nativeGoalId(entry.goalId),
      goalRevision: entry.goalRevision,
      taskIds: entry.taskIds.map(value => TaskId(value)),
      acceptanceHash: AcceptanceHash(entry.acceptanceHash),
      sourceFingerprint: SourceFingerprint(entry.sourceFingerprint),
      snapshotId: DevFrameSnapshotId(entry.snapshotId),
      confirmation: {
        id: ConfigurationConfirmationId(entry.confirmation.id),
        acceptanceHash: AcceptanceHash(entry.confirmation.acceptanceHash),
      },
      lifecycle: entry.lifecycle,
      budget: {
        maxAttempts: entry.budget.maxAttempts,
        consumedAttempts: entry.budget.consumedAttempts,
      },
    })),
    currents: envelope.data.currents.map(entry => ({
      workspaceId: WorkspaceId(entry.workspaceId),
      controllerSessionId: ControllerSessionId(entry.controllerSessionId),
      goalId: nativeGoalId(entry.goalId),
      goalRevision: entry.goalRevision,
      acceptanceHash: AcceptanceHash(entry.acceptanceHash),
      sourceFingerprint: SourceFingerprint(entry.sourceFingerprint),
      confirmation: {
        id: ConfigurationConfirmationId(entry.confirmation.id),
        acceptanceHash: AcceptanceHash(entry.confirmation.acceptanceHash),
      },
      lifecycle: entry.lifecycle,
    })),
  }
}

/**
 * Read and wholesale-validate the ledger, treating an absent file as an
 * empty store so a first save does not need the ledger to pre-exist.
 * @param path - ledger path from the store Config.
 * @returns the validated ledger, or `undefined` when the file does not exist.
 * @throws raw fs errors other than ENOENT, unwrapped.
 * @throws {@link GoalBindingError} per {@link parseLedger}.
 */
async function readLedger(path: string): Promise<ValidatedLedger | undefined> {
  const raw = await readFile(path, 'utf8').catch((error: NodeJS.ErrnoException) => {
    // ENOENT is absence (an empty ledger, not an error); every other fs
    // failure is a real IO error rethrown raw so its true cause reaches
    // the caller.
    if (error.code !== 'ENOENT') throw error
    return undefined
  })
  return raw === undefined ? undefined : await parseLedger(raw, path)
}

/**
 * Compare the immutable work tuple while allowing revision and lifecycle
 * movement. Field-for-field it mirrors the frozen controller-private
 * `sameBinding` helper (src/controller/goal-binding.ts); the shape is a
 * field-pair array so the two comparisons stay independent implementations.
 * @param left - one binding already in the ledger.
 * @param right - the incoming binding under the same identity.
 * @returns true only when every immutable field pair matches.
 */
function sameImmutableBinding(left: GoalBinding, right: GoalBinding): boolean {
  const pairs: Array<readonly [unknown, unknown]> = [
    [left.controllerSessionId, right.controllerSessionId],
    [left.goalId, right.goalId],
    [left.workspaceId, right.workspaceId],
    [left.acceptanceHash, right.acceptanceHash],
    [left.sourceFingerprint, right.sourceFingerprint],
    [left.snapshotId, right.snapshotId],
    [left.confirmation.id, right.confirmation.id],
    [left.confirmation.acceptanceHash, right.confirmation.acceptanceHash],
    [left.budget.maxAttempts, right.budget.maxAttempts],
    [left.budget.consumedAttempts, right.budget.consumedAttempts],
    [left.taskIds.length, right.taskIds.length],
  ]
  for (const [index, id] of left.taskIds.entries()) {
    pairs.push([id, right.taskIds[index]])
  }
  return pairs.every(([leftValue, rightValue]) => leftValue === rightValue)
}

/** Host-supplied settings for the file-backed Goal binding store. */
export interface FileGoalBindingStoreOptions {
  /**
   * Path of the JSON binding ledger, used exactly as given. Created by the
   * first `save`; the parent directory must already exist (a missing
   * directory fails save loud with the raw fs error).
   */
  readonly path: string
}

/**
 * File-backed durable {@link GoalBindingStore} reference implementation:
 * bindings and workspace currents persist as one JSON ledger at the
 * Config-supplied path and every read validates the whole document (the
 * failure routing is documented on the module). Publishes replace the ledger
 * via a same-directory temp file + rename, so a concurrent reader sees the
 * old or the new complete ledger; there are no locks, so the store assumes a
 * single writer and concurrent writers are last-writer-wins. An injectable
 * alternative to {@link MemoryGoalBindingStore}; production composition
 * wiring belongs to the owning wave.
 */
export class FileGoalBindingStore implements GoalBindingStore {
  private readonly ledgerPath: string

  /**
   * @param options - host-resolved store settings; `options.path` is the
   *   ledger location used exactly as given.
   */
  constructor(options: FileGoalBindingStoreOptions) {
    this.ledgerPath = options.path
  }

  /**
   * Load detached binding copies for one controller Session, reading and
   * validating the whole ledger first.
   * @param controllerSessionId - controller identity selecting the records.
   * @returns the Session's bindings in file order; `[]` when the ledger
   *   does not exist.
   * @throws {@link GoalBindingError} with `GOAL_BINDING_PERSISTENCE` when the
   *   ledger is corrupt. Non-ENOENT fs errors propagate unwrapped.
   */
  async load(controllerSessionId: ControllerSessionId): Promise<readonly GoalBinding[]> {
    const ledger = await readLedger(this.ledgerPath)
    return (ledger?.bindings ?? [])
      .filter(binding => binding.controllerSessionId === controllerSessionId)
  }

  /**
   * Read the current shared project binding for one workspace, reading and
   * validating the whole ledger first.
   * @param workspaceId - workspace selecting the record.
   * @returns the workspace's current record, or `undefined` when the ledger
   *   does not exist or the workspace has none.
   * @throws {@link GoalBindingError} with `GOAL_BINDING_PERSISTENCE` when the
   *   ledger is corrupt. Non-ENOENT fs errors propagate unwrapped.
   */
  async read(workspaceId: WorkspaceId): Promise<ProjectBindingRecord | undefined> {
    const ledger = await readLedger(this.ledgerPath)
    return ledger?.currents.find(record => record.workspaceId === workspaceId)
  }

  /**
   * Save one binding, accepting an identical or equal-or-advanced retry and
   * rejecting identity reuse with changed task, acceptance, or budget data.
   * @param binding - immutable Goal binding to retain.
   * @throws {@link GoalBindingError} with `GOAL_BINDING_PERSISTENCE` when the
   *   existing ledger is corrupt — save never repairs or overwrites
   *   corruption — and with `GOAL_BINDING_CONFLICT` when the identity already
   *   carries a different immutable tuple or an earlier revision. Raw fs
   *   errors (e.g. a missing parent directory) propagate unwrapped.
   */
  async save(binding: GoalBinding): Promise<void> {
    const ledger = await readLedger(this.ledgerPath)
    const bindings = [...ledger?.bindings ?? []]
    const index = bindings.findIndex(record =>
      record.controllerSessionId === binding.controllerSessionId
      && record.goalId === binding.goalId)
    if (index !== -1) {
      const current = bindings[index]
      if (current !== undefined && sameImmutableBinding(current, binding)
        && binding.goalRevision >= current.goalRevision) {
        bindings[index] = binding
      } else {
        throw new GoalBindingError(
          `Goal "${binding.goalId}" already has a different binding`,
          'GOAL_BINDING_CONFLICT',
        )
      }
    } else {
      bindings.push(binding)
    }
    await this.publishDocument({ version: LEDGER_VERSION, bindings, currents: ledger?.currents ?? [] })
  }

  /**
   * Write the current shared project binding for one workspace as an upsert,
   * reading and validating the whole ledger first.
   * @param record - already validated record to persist.
   * @throws {@link GoalBindingError} with `GOAL_BINDING_PERSISTENCE` when the
   *   existing ledger is corrupt — write never repairs or overwrites
   *   corruption. Raw fs errors propagate unwrapped.
   */
  async write(record: ProjectBindingRecord): Promise<void> {
    const ledger = await readLedger(this.ledgerPath)
    const currents = [...ledger?.currents ?? []]
    const index = currents.findIndex(existing => existing.workspaceId === record.workspaceId)
    if (index === -1) currents.push(record)
    else currents[index] = record
    await this.publishDocument({ version: LEDGER_VERSION, bindings: ledger?.bindings ?? [], currents })
  }

  /**
   * Atomically publish the whole ledger: write a same-directory temp file,
   * then rename it over the ledger path.
   * @param document - the complete next ledger state.
   */
  private async publishDocument(document: LedgerDocument): Promise<void> {
    const tempPath = `${this.ledgerPath}.${randomBytes(6).toString('hex')}.tmp`
    await writeFile(tempPath, `${JSON.stringify(document, null, 2)}\n`, 'utf8')
    await rename(tempPath, this.ledgerPath)
  }
}
