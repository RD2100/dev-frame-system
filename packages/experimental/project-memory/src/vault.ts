/**
 * Vault layout and path containment: namespace derivation, safe workspace
 * segments, symlink/reparse rejection, and note path resolution inside the
 * user-selected Vault root. The service manages only the
 * `<vault>/devframe-memory/` subtree and never creates the Vault root.
 * @module @deepseek-ai/dsh-experimental-project-memory/vault
 */

import { lstat, mkdir, realpath } from 'node:fs/promises'
import { join } from 'node:path'
import { ProjectMemoryError } from './errors.ts'
import type { NoteId } from './ids.ts'
import type { MemoryNamespace, MemoryScope } from './types.ts'

/** The dedicated DevFrame-managed subtree inside the user's Vault. */
export const MEMORY_DIR = 'devframe-memory'

/** Windows reserved device names, rejected as workspace id segments. */
const WINDOWS_RESERVED = new Set([
  'CON', 'PRN', 'AUX', 'NUL',
  'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
  'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
])

/**
 * Validate that a value is safe to use as exactly one path segment on every
 * supported filesystem: no separators, traversal, control characters,
 * trailing dot/space, or Windows reserved device name.
 * @param value - Candidate segment.
 * @returns the same string, unchanged.
 * @throws {@link ProjectMemoryError} with code `MEMORY_INVALID_WORKSPACE_ID`
 * when the value is unsafe.
 */
export function validateWorkspaceSegment(value: string): string {
  if (
    value.length === 0 ||
    value.length > 128 ||
    value !== value.trim() ||
    value === '.' ||
    value === '..' ||
    /[/\\\0:]/.test(value) ||
    /[\u0000-\u001F\u007F]/.test(value) ||
    value.endsWith('.') ||
    WINDOWS_RESERVED.has(value.toUpperCase())
  ) {
    throw new ProjectMemoryError(
      'workspace id must be a safe single path segment',
      'MEMORY_INVALID_WORKSPACE_ID',
    )
  }
  return value
}

/**
 * Resolve the relative namespace directory for one scope. The project
 * namespace isolates workspaces from each other; the user namespace is the
 * explicitly allowed user memory directory.
 * @param scope - The requested scope.
 * @param workspaceId - Validated workspace segment.
 * @returns the relative namespace directory.
 */
export function namespaceOf(scope: MemoryScope, workspaceId: string): MemoryNamespace {
  return scope === 'user' ? 'user' : `projects/${validateWorkspaceSegment(workspaceId)}`
}

/**
 * The note's expected path relative to the Vault root, as recorded in its
 * receipt.
 * @param namespace - Relative namespace directory.
 * @param noteId - Derived note id.
 * @returns e.g. `devframe-memory/user/<id>.md`.
 */
export function noteRelativePath(namespace: MemoryNamespace, noteId: NoteId): string {
  return `${MEMORY_DIR}/${namespace}/${noteId}.md`
}

/**
 * Reject an unsafe Vault path state (unexpected symlink/reparse component or
 * escape from the allowed root).
 */
function rejectPath(detail: string): ProjectMemoryError {
  return new ProjectMemoryError(`vault path rejected: ${detail}`, 'MEMORY_PATH_REJECTED')
}

/** Read a Node filesystem error code without trusting an untyped boundary. */
function fsErrorCode(error: unknown): string | undefined {
  if (typeof error !== 'object' || error === null || !('code' in error)) return undefined
  const code = (error as { readonly code?: unknown }).code
  return typeof code === 'string' ? code : undefined
}

/** Preserve filesystem inspection failures instead of treating them as absence. */
function unavailable(detail: string, error: unknown): ProjectMemoryError {
  return new ProjectMemoryError(`vault path could not be inspected: ${detail}`, 'MEMORY_UNAVAILABLE', { cause: error })
}

/** `true` when `child` (both real, normalized) is strictly inside `root`. */
function isInsideRoot(child: string, root: string): boolean {
  const separator = root.endsWith('\\') || root.endsWith('/') ? '' : '\\'
  return child.startsWith(root + separator) || child.startsWith(root + '/')
}

/**
 * Walk a relative component list from the root and reject any existing
 * symlink/reparse component. A missing component stops the walk: nothing
 * below it exists yet.
 */
async function assertNoSymlinkComponents(rootReal: string, components: readonly string[]): Promise<void> {
  let current = rootReal
  for (const component of components) {
    current = join(current, component)
    let stats
    try {
      stats = await lstat(current)
    } catch (error: unknown) {
      if (fsErrorCode(error) === 'ENOENT') return
      throw unavailable(`component "${component}" is not readable`, error)
    }
    if (stats.isSymbolicLink()) {
      throw rejectPath(`unexpected symlink or reparse component "${component}"`)
    }
    if (!stats.isDirectory()) {
      throw rejectPath(`path component "${component}" is not a directory`)
    }
  }
}

/**
 * Resolve one namespace directory without following a symlink or reparse
 * point. Missing directories are normal because the memory subtree is lazy;
 * all other inspection failures stay explicit.
 * @param rootReal - Realpath of the Vault root.
 * @param namespace - Relative namespace directory.
 * @returns the absolute directory path and whether it exists.
 */
export async function resolveNamespaceDir(
  rootReal: string,
  namespace: MemoryNamespace,
): Promise<{ readonly path: string; readonly exists: boolean }> {
  const components = [MEMORY_DIR, ...namespace.split('/')]
  await assertNoSymlinkComponents(rootReal, components)
  const path = join(rootReal, ...components)
  let stats
  try {
    stats = await lstat(path)
  } catch (error: unknown) {
    if (fsErrorCode(error) === 'ENOENT') return { path, exists: false }
    throw unavailable('namespace directory is not readable', error)
  }
  if (stats.isSymbolicLink()) {
    throw rejectPath('namespace directory is a symlink or reparse point')
  }
  if (!stats.isDirectory()) {
    throw rejectPath('namespace path is not a directory')
  }
  let real: string
  try {
    real = await realpath(path)
  } catch (error: unknown) {
    throw unavailable('namespace directory realpath could not be read', error)
  }
  if (!isInsideRoot(real, rootReal)) {
    throw rejectPath('namespace directory resolves outside the vault root')
  }
  return { path, exists: true }
}

/**
 * Resolve one note's absolute file path inside the Vault, rejecting
 * traversal (by id shape, upstream), unexpected symlink components, and any
 * resolution that escapes the Vault root.
 * @param rootReal - Realpath of the Vault root.
 * @param namespace - Relative namespace directory.
 * @param noteId - Derived, host-issued note id.
 * @returns the absolute path and whether a (non-symlink) file exists there.
 */
export async function resolveNoteFilePath(
  rootReal: string,
  namespace: MemoryNamespace,
  noteId: NoteId,
): Promise<{ readonly path: string; readonly exists: boolean }> {
  const components = [MEMORY_DIR, ...namespace.split('/')]
  const namespaceDir = await resolveNamespaceDir(rootReal, namespace)
  const path = join(rootReal, ...components, `${noteId}.md`)
  if (!namespaceDir.exists) return { path, exists: false }
  let stats
  try {
    stats = await lstat(path)
  } catch (error: unknown) {
    if (fsErrorCode(error) === 'ENOENT') return { path, exists: false }
    throw unavailable(`note file "${noteId}.md" is not readable`, error)
  }
  if (stats.isSymbolicLink()) {
    throw rejectPath(`note file "${noteId}.md" is a symlink or reparse point`)
  }
  if (!stats.isFile()) throw rejectPath(`note path "${noteId}.md" is not a regular file`)
  let real: string
  try {
    real = await realpath(path)
  } catch (error: unknown) {
    throw unavailable(`note file "${noteId}.md" realpath could not be read`, error)
  }
  if (!isInsideRoot(real, rootReal)) {
    throw rejectPath('resolved note path escapes the vault root')
  }
  return { path, exists: true }
}

/**
 * Create the namespace directory (and the `devframe-memory` subtree) if
 * missing, then verify its real path stays inside the Vault root.
 * @param rootReal - Realpath of the Vault root.
 * @param namespace - Relative namespace directory.
 * @returns the absolute namespace directory path.
 * @throws {@link ProjectMemoryError} with code `MEMORY_WRITE_FAILED` when the
 * directory cannot be created, or `MEMORY_PATH_REJECTED` when the created
 * directory resolves outside the Vault root.
 */
export async function ensureNamespaceDir(rootReal: string, namespace: MemoryNamespace): Promise<string> {
  const components = [MEMORY_DIR, ...namespace.split('/')]
  const dir = join(rootReal, ...components)
  // Check both sides of mkdir: a pre-existing link must fail closed, and a
  // link planted while the recursive create is in flight must not become a
  // silent escape into a different subtree.
  await assertNoSymlinkComponents(rootReal, components)
  await mkdir(dir, { recursive: true })
  await assertNoSymlinkComponents(rootReal, components)
  const resolved = await resolveNamespaceDir(rootReal, namespace)
  if (!resolved.exists) throw new ProjectMemoryError('namespace directory was not created', 'MEMORY_WRITE_FAILED')
  return resolved.path
}
