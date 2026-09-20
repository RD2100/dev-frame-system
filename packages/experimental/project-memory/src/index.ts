/**
 * Public entry of `@deepseek-ai/dsh-experimental-project-memory`: the bounded
 * append-only project memory service over a user-selected Obsidian Vault
 * subtree. The host wires the service to its workspace identity, consent
 * flags, and the receipt store over the DSH session log.
 * @module @deepseek-ai/dsh-experimental-project-memory
 */

export { ProjectMemoryError, type ProjectMemoryErrorCode } from './errors.ts'
export { canonicalizeEntities, entitiesInclude, MAX_ENTITY_CHARS, MAX_NOTE_ENTITIES } from './entities.ts'
export { deriveNoteId, MAX_SOURCE_REF_BYTES, NoteId, validateSourceRef } from './ids.ts'
export {
  DEFAULT_MEMORY_LIMITS,
  DEFAULT_MEMORY_RETRY,
  resolveMemorySpec,
  type MemorySpecRequest,
} from './config.ts'
export { createMemoryReceiptStore } from './receipt.ts'
export {
  appendMemoryReceipt,
  createSessionLogReceiptStore,
  foldMemoryReceipts,
  rehydrateMemoryReceipts,
  type MemoryReceiptEventData,
} from './receipt-log.ts'
export { screenNoteBody, type ScreeningRuleId } from './screen.ts'
export { ProjectMemoryService, type ProjectMemoryReceipts } from './memory.ts'
// The Cordis loader resolves the package name to this entry and reads the
// plugin-protocol exports `name`, `inject`, `Config`, and `apply` by their
// exact names; `createMemoryTools` is the testable tool factory behind them.
export { apply, Config, createMemoryTools, inject, MEMORY_USAGE_SECTION, MEMORY_USAGE_SECTION_NAME, name } from './plugin.ts'
export {
  NOTE_SCHEMA_VERSION,
  type AssertionStatus,
  type MemoryAppendRequest,
  type MemoryAppendResult,
  type MemoryFreshness,
  type MemoryLimits,
  type MemoryNamespace,
  type MemoryNote,
  type MemoryNoteMeta,
  type MemoryReadRequest,
  type MemoryReadResult,
  type MemoryReceipt,
  type MemoryReceiptStore,
  type MemoryRetryPolicy,
  type MemoryScope,
  type MemorySearchHit,
  type MemorySearchRequest,
  type MemorySearchResult,
  type MemorySpec,
} from './types.ts'
export {
  getLibraryStatus,
  listLibraryFiles,
  readLibraryFile,
  searchLibrary,
  type LibraryFile,
  type LibrarySearchMatch,
  type LibrarySearchResult,
  type LibraryStatus,
  type ListLibraryOptions,
  type SearchLibraryOptions,
} from './library.ts'
export { MemoryLibraryGateway } from './gateway.ts'
export type {
  MemoryLibraryListRequest,
  MemoryLibraryReadRequest,
  MemoryLibraryReadResult,
  MemoryLibrarySearchRequest,
  MemoryLibrarySnapshot,
} from './client.ts'

