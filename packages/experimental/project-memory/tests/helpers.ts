/**
 * Shared test harness: one temp Vault root (plus one outside directory for
 * escape probes), a real receipt store that records committed receipts the
 * way the session log would, and the real service over them.
 * @module tests/helpers
 */

import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  createMemoryReceiptStore,
  ProjectMemoryService,
  resolveMemorySpec,
  type MemoryAppendRequest,
  type MemoryReceipt,
  type MemoryReceiptStore,
  type MemorySpec,
  type MemorySpecRequest,
} from '../src/index.ts'

/** The per-spec harness: one temp Vault, one outside probe dir, one service. */
export interface Harness {
  /** The user-selected Vault root (a real temp directory). */
  readonly vaultRoot: string
  /** A directory outside the Vault for escape-probe targets. */
  readonly outsideRoot: string
  /** The service under test, with appends and user scope enabled. */
  readonly service: ProjectMemoryService
  /** The resolved spec the service runs on. */
  readonly spec: MemorySpec
  /** Every receipt the service committed, in order (session-log stand-in). */
  readonly committedReceipts: MemoryReceipt[]
  /** Remove both temp directories. */
  dispose(): Promise<void>
}

/** Harness options; every field may be omitted to keep the default. */
export type HarnessOptions = {
  readonly [K in keyof Omit<MemorySpecRequest, 'vaultRoot' | 'workspaceId'>]?: MemorySpecRequest[K]
}

/**
 * Build one harness over a fresh temp Vault.
 * @param options - Spec overrides; `workspaceId` defaults to `ws-alpha`.
 * @returns the harness; the caller owns disposal.
 */
export async function makeHarness(options: HarnessOptions = {}): Promise<Harness> {
  const vaultRoot = await mkdtemp(join(tmpdir(), 'dsh-project-memory-'))
  const outsideRoot = await mkdtemp(join(tmpdir(), 'dsh-project-memory-out-'))
  const committed: MemoryReceipt[] = []
  const backing = createMemoryReceiptStore()
  const receipts: MemoryReceiptStore = {
    read: noteId => backing.read(noteId),
    write: async receipt => {
      committed.push(receipt)
      await backing.write(receipt)
    },
  }
  const spec = resolveMemorySpec({
    vaultRoot,
    writeEnabled: true,
    userScopeEnabled: true,
    workspaceId: 'ws-alpha',
    ...options,
  })
  const service = new ProjectMemoryService(spec, receipts)
  return {
    vaultRoot,
    outsideRoot,
    service,
    spec,
    committedReceipts: committed,
    async dispose() {
      await rm(vaultRoot, { recursive: true, force: true })
      await rm(outsideRoot, { recursive: true, force: true })
    },
  }
}

/** Overrides for the default append request fixture. */
export type AppendOverrides = Partial<MemoryAppendRequest>

/** One valid default append request (a project observation). */
export function appendRequest(overrides: AppendOverrides = {}): MemoryAppendRequest {
  return {
    scope: 'project',
    sourceRef: 'session-alpha#event-1',
    kind: 'fact',
    body: 'The deploy script lives in scripts/deploy.ps1',
    assertionStatus: 'observed',
    ...overrides,
  }
}
