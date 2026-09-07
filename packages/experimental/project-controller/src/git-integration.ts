/** Git observations and exact-source integration (fast-forward or real merge) for the controller's exclusive main-tree writer. */

import { execFile } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { unlinkSync, writeFileSync } from 'node:fs'
import { realpath } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { isAbsolute, join, resolve } from 'node:path'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)

/** Explicit process limits supplied by the integration host. */
export interface IntegrationGitOptions {
  /** Git executable selected by the deployment. */
  readonly executable: string
  /** Maximum elapsed milliseconds for each subprocess. */
  readonly timeoutMs: number
  /** Maximum captured output bytes for each subprocess. */
  readonly maxOutputBytes: number
}

/** Exact reviewed source and target state; branch names are never accepted as commit identities. */
export interface IntegrationGitRequest {
  /** Independent source checkout whose clean HEAD was reviewed. */
  readonly sourcePath: string
  /** Controller-owned main checkout, under exclusive writer ownership. */
  readonly targetPath: string
  /** Full hexadecimal reviewed commit object ID. */
  readonly sourceCommit: string
  /** Full hexadecimal target HEAD observed before admission. */
  readonly targetHead: string
  /**
   * How the reviewed commit may reach the target: `fast-forward` (default)
   * requires the target to be an ancestor, `merge` requires the two heads
   * to have diverged and creates a real merge commit.
   */
  readonly mode?: 'fast-forward' | 'merge' | undefined
}

/** Post-execution observation; only `applied` permits recording integration. */
export type IntegrationGitObservation =
  | { readonly kind: 'applied'; readonly head: string }
  | { readonly kind: 'unchanged'; readonly head: string }
  | { readonly kind: 'conflicted'; readonly head: string }
  | { readonly kind: 'ambiguous'; readonly head: string; readonly clean: boolean }

/** Execute Git with argument boundaries and without ambient credentials or Git directory overrides. */
async function git(options: IntegrationGitOptions, cwd: string, args: readonly string[], signal?: AbortSignal,
  env?: Record<string, string | undefined>): Promise<string> {
  const baseEnv = env ?? Object.fromEntries(Object.entries(process.env).filter(([key]) =>
    !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key)))
  const result = await execFileAsync(options.executable, ['-C', cwd, ...args], {
    env: baseEnv,
    windowsHide: true,
    timeout: options.timeoutMs,
    maxBuffer: options.maxOutputBytes,
    encoding: 'utf8',
    ...(signal === undefined ? {} : { signal }),
  })
  return result.stdout.trim()
}

/**
 * Environment for the mutating merge: global and system Git config are
 * redirected to one real empty file so user- or machine-level entries
 * (external filters such as LFS, custom merge drivers, aliases) can never be
 * consulted by the merge — an in-tree `.gitattributes` naming such a
 * mechanism then fails loudly instead of executing ambient code. Only the
 * host-owned target checkout's local config remains. Git requires the
 * redirected files to exist and be readable, so the caller disposes them.
 * Preparation is synchronous on purpose: no await may sit between the final
 * admission guard and the spawn, or a gate closing in that gap could still
 * admit the merge.
 */
function isolatedMergeEnv(): { readonly env: Record<string, string | undefined>; dispose: () => void } {
  const emptyConfig = join(tmpdir(), `dsh-integration-isolated-config-${randomUUID()}`)
  writeFileSync(emptyConfig, '')
  return {
    env: {
      ...Object.fromEntries(Object.entries(process.env).filter(([key]) =>
        !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key))),
      GIT_CONFIG_GLOBAL: emptyConfig,
      GIT_CONFIG_SYSTEM: emptyConfig,
    },
    dispose: () => {
      try {
        unlinkSync(emptyConfig)
      } catch {
        // A disposable temp file whose unlink raced a lost process is harmless residue.
      }
    },
  }
}

/** Reject ambiguous references and invalid host limits before launching a process. */
function validate(request: IntegrationGitRequest, options: IntegrationGitOptions): void {
  if (!isAbsolute(request.sourcePath) || !isAbsolute(request.targetPath)
    || !/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(request.sourceCommit)
    || !/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(request.targetHead)) {
    throw new Error('Integration requires absolute checkout paths and full commit object IDs')
  }
  if (request.mode !== undefined && request.mode !== 'fast-forward' && request.mode !== 'merge') {
    throw new Error('Integration mode must be "fast-forward" or "merge"')
  }
  if (options.executable.length === 0 || !Number.isSafeInteger(options.timeoutMs) || options.timeoutMs < 1
    || !Number.isSafeInteger(options.maxOutputBytes) || options.maxOutputBytes < 1) {
    throw new Error('Integration requires a Git executable and positive process limits')
  }
}

/**
 * Classify the relation between the reviewed source and the observed target
 * without changing either checkout, so the host selects the integration
 * mode explicitly.
 * @param request - Reviewed source and observed target identities.
 * @param options - Explicit Git process settings.
 * @returns Identical heads, a fast-forwardable source, an already-integrated
 *   source, or a diverged pair whose integration needs the merge mode.
 * @throws when the two heads share no merge base (unrelated histories).
 */
export async function observeIntegrationRelation(
  request: IntegrationGitRequest,
  options: IntegrationGitOptions,
): Promise<'identical' | 'fast-forward' | 'already-integrated' | 'diverged'> {
  validate(request, options)
  if (request.sourceCommit === request.targetHead) return 'identical'
  await assertRelatedHistories(options, request.targetPath, request.targetHead, request.sourceCommit)
  if (await isAncestor(options, request.targetPath, request.targetHead, request.sourceCommit)) return 'fast-forward'
  if (await isAncestor(options, request.targetPath, request.sourceCommit, request.targetHead)) return 'already-integrated'
  return 'diverged'
}

/**
 * Whether one commit contains the other, reported by Git's ancestry check.
 * Exit 1 is Git's "not an ancestor" answer; every other failure is real and
 * propagates instead of masquerading as a diverged pair.
 */
async function isAncestor(options: IntegrationGitOptions, path: string, maybeAncestor: string, maybeDescendant: string): Promise<boolean> {
  try {
    await git(options, path, ['merge-base', '--is-ancestor', maybeAncestor, maybeDescendant])
    return true
  } catch (error) {
    if ((error as { code?: unknown }).code === 1) return false
    throw error
  }
}

/**
 * Require the two heads to share a merge base. Git's exit 1 answer means
 * unrelated histories and refuses the integration before any ancestry
 * question; every other failure is real and propagates.
 */
async function assertRelatedHistories(options: IntegrationGitOptions, path: string, targetHead: string, sourceCommit: string): Promise<void> {
  try {
    await git(options, path, ['merge-base', targetHead, sourceCommit])
  } catch (error) {
    if ((error as { code?: unknown }).code === 1) {
      throw new Error('Integration requires related source and target histories')
    }
    throw error
  }
}

/** Read the worktree state without refreshing its index or changing files. */
async function observe(options: IntegrationGitOptions, path: string): Promise<{ head: string; clean: boolean }> {
  const head = await git(options, path, ['rev-parse', '--verify', 'HEAD'])
  const status = await git(options, path, ['--no-optional-locks', 'status', '--porcelain=v1', '--untracked-files=all'])
  return { head, clean: status.length === 0 }
}

/**
 * Refuse a target checkout whose reachable Git config defines
 * process-running merge drivers or external checkout filters. The query
 * runs in the merge subprocess's own isolated environment — global and
 * system config stripped, repository config with `include.*` expanded, and
 * worktree config included exactly as the merge would resolve them — so a
 * driver or filter effective through any reachable channel cannot hide
 * from `--local`'s narrow scope. Config-defined `merge.<name>.driver` and
 * `filter.<name>.clean|smudge|process` entries execute arbitrary commands
 * selected by an in-tree `.gitattributes`. Exit 1 means no entries and is
 * the approved shape; any other failure is real and propagates.
 */
async function refuseReachableProcessConfig(options: IntegrationGitOptions, path: string): Promise<void> {
  const pattern = '^merge\\..+\\.driver$|^filter\\..+\\.(clean|smudge|process)$'
  const isolation = isolatedMergeEnv()
  try {
    const listing = await git(options, path, ['config', '--get-regexp', pattern], undefined, isolation.env)
    if (listing.length > 0) {
      throw new Error('Integration merge mode requires a target repository whose reachable Git config defines no custom merge drivers or external filters')
    }
  } catch (error) {
    if ((error as { code?: unknown }).code === 1) return
    throw error
  } finally {
    isolation.dispose()
  }
}

/**
 * Validate independent clean checkouts, repository identity, exact commits,
 * and the ancestry the requested mode needs: a fast-forward requires the
 * target to be an ancestor of the source, a merge requires the heads to
 * have diverged. The host must retain exclusive target writer ownership
 * until integration is recorded.
 * @param request - Reviewed source and observed target identities.
 * @param options - Explicit Git process settings.
 */
export async function inspectIntegrationGit(request: IntegrationGitRequest, options: IntegrationGitOptions): Promise<void> {
  validate(request, options)
  if (request.sourceCommit === request.targetHead) throw new Error('Integration requires an unapplied source commit')
  const source = await realpath(request.sourcePath)
  const target = await realpath(request.targetPath)
  if (source === target) throw new Error('Integration requires independent source and target worktrees')
  for (const path of [source, target]) {
    const top = await realpath(await git(options, path, ['rev-parse', '--show-toplevel']))
    if (path !== top) throw new Error('Integration paths must name checkout roots')
  }
  const sourceCommon = await realpath(resolve(source, await git(options, source, ['rev-parse', '--git-common-dir'])))
  const targetCommon = await realpath(resolve(target, await git(options, target, ['rev-parse', '--git-common-dir'])))
  if (sourceCommon !== targetCommon) throw new Error('Integration worktrees must belong to the same repository')
  const sourceState = await observe(options, source)
  const targetState = await observe(options, target)
  if (!sourceState.clean || !targetState.clean) throw new Error('Integration requires clean source and target worktrees')
  if (sourceState.head !== request.sourceCommit || targetState.head !== request.targetHead) {
    throw new Error('Integration source or target HEAD changed after admission was prepared')
  }
  await git(options, target, ['symbolic-ref', '--quiet', 'HEAD'])
  if (request.mode === 'merge') {
    await refuseReachableProcessConfig(options, request.targetPath)
    await assertRelatedHistories(options, request.targetPath, request.targetHead, request.sourceCommit)
    if (await isAncestor(options, request.targetPath, request.sourceCommit, request.targetHead)) {
      throw new Error('Integration merge mode requires an unmerged source; the target already contains it')
    }
    if (await isAncestor(options, request.targetPath, request.targetHead, request.sourceCommit)) {
      throw new Error('Integration merge mode requires a diverged source; use the fast-forward path')
    }
    return
  }
  await git(options, target, ['merge-base', '--is-ancestor', request.targetHead, request.sourceCommit])
}

/**
 * The two parents of the target HEAD when it is exactly a two-parent merge
 * commit; otherwise nothing. An octopus merge commit has more parents and
 * can never satisfy the reviewed two-parent shape.
 */
async function mergeParentsOf(options: IntegrationGitOptions, path: string): Promise<readonly [string, string] | undefined> {
  const line = (await git(options, path, ['rev-list', '--parents', '-n', '1', 'HEAD'])).split('\n').at(0) ?? ''
  const tokens = line.split(' ')
  if (tokens.length !== 3 || tokens[1] === undefined || tokens[2] === undefined) return undefined
  return [tokens[1], tokens[2]]
}

/**
 * Whether a merge is actually in progress with unmerged index entries. Both
 * pieces of evidence must hold: HEAD unmoved with a dirty tree alone cannot
 * distinguish a conflicted merge from a cancelled command or an external
 * write, and that shape stays ambiguous instead.
 */
async function isMergeConflicted(options: IntegrationGitOptions, path: string): Promise<boolean> {
  try {
    await git(options, path, ['rev-parse', '--verify', '--quiet', 'MERGE_HEAD'])
  } catch (error) {
    // Exit 1 is Git's "no such ref" answer; every other failure is real and stays an error.
    if ((error as { code?: unknown }).code === 1) return false
    throw error
  }
  const unmerged = await git(options, path, ['--no-optional-locks', 'ls-files', '--unmerged'])
  return unmerged.length > 0
}

/**
 * Observe an uncertain merge without repeating it or changing the checkout.
 * A merge-mode observation names the explicit conflict state: Git stopped
 * with HEAD unmoved and the worktree holding conflict markers for the
 * operator — it never reports that as a silent success.
 * @param request - Identities retained by the original integration operation.
 * @param options - Explicit Git process settings; observations use their own bounded calls.
 * @returns Applied, unchanged, conflicted, or ambiguous target state.
 */
export async function reconcileIntegrationGit(
  request: IntegrationGitRequest,
  options: IntegrationGitOptions,
): Promise<IntegrationGitObservation> {
  validate(request, options)
  const state = await observe(options, request.targetPath)
  if (request.mode === 'merge') {
    if (state.clean && state.head === request.targetHead) return { kind: 'unchanged', head: state.head }
    if (!state.clean && state.head === request.targetHead) {
      if (await isMergeConflicted(options, request.targetPath)) return { kind: 'conflicted', head: state.head }
      return { kind: 'ambiguous', ...state }
    }
    if (state.clean) {
      const parents = await mergeParentsOf(options, request.targetPath)
      if (parents !== undefined && parents[0] === request.targetHead && parents[1] === request.sourceCommit) {
        return { kind: 'applied', head: state.head }
      }
    }
    return { kind: 'ambiguous', ...state }
  }
  if (state.clean && state.head === request.sourceCommit) return { kind: 'applied', head: state.head }
  if (state.clean && state.head === request.targetHead) return { kind: 'unchanged', head: state.head }
  return { kind: 'ambiguous', ...state }
}

/**
 * Integrate the exclusively owned target once in the requested mode, then
 * reconcile its actual state even if Git throws. A fast-forward requires
 * the target to be an ancestor; a merge integrates a diverged reviewed
 * source as a real merge commit whose parents are the observed target head
 * and the exact reviewed source. The merge runs with an explicit config
 * bundle (`merge.ff=false`, `commit.gpgsign=false`, `core.hooksPath=/dev/null`)
 * and `--no-verify` so hooks, signing, and fast-forward overrides cannot
 * change what the command does, with global and system Git config stripped
 * from the merge environment and reachable custom merge drivers or external
 * checkout filters refused at inspection — no config-selected process can
 * influence the merge. The author identity comes from the host-owned target
 * checkout's local config. No reset, abort, retry, commit
 * creation, or automatic conflict resolution is performed: a conflicted merge
 * stops with HEAD unmoved and the conflict state left for the operator,
 * reported as the explicit `conflicted` observation once MERGE_HEAD and
 * unmerged index entries confirm it.
 * @param request - Exact reviewed source and target identities, with the mode.
 * @param options - Explicit Git process settings.
 * @param signal - Optional cancellation of the mutating command; final observation still runs.
 * @param beforeMerge - Synchronous host admission check immediately before spawning the mutating command.
 * @returns The observed target state plus any command failure, reported independently.
 */
export async function executeIntegrationGit(
  request: IntegrationGitRequest,
  options: IntegrationGitOptions,
  signal?: AbortSignal,
  beforeMerge?: () => void,
): Promise<{ readonly observation: IntegrationGitObservation; readonly commandError?: unknown }> {
  await inspectIntegrationGit(request, options)
  signal?.throwIfAborted()
  beforeMerge?.()
  // Everything between the guard above and the spawned merge is synchronous:
  // preparing the isolated environment creates its temp file with sync file
  // calls, so a gate closing in a microtask cannot slip into the window and
  // admit a merge that the host never admitted.
  const isolation = request.mode === 'merge' ? isolatedMergeEnv() : undefined
  const mergeArgs = request.mode === 'merge'
    ? ['-c', 'merge.ff=false', '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null',
      'merge', '--no-verify', '--no-edit', '--no-overwrite-ignore', request.sourceCommit]
    : ['merge', '--ff-only', '--no-edit', '--no-overwrite-ignore', request.sourceCommit]
  let commandError: unknown
  try {
    await git(options, request.targetPath, mergeArgs, signal, isolation?.env)
  } catch (error) {
    // The command may have advanced HEAD before transport failure or cancellation; observe before any decision.
    commandError = error
  } finally {
    isolation?.dispose()
  }
  const observation = await reconcileIntegrationGit(request, options)
  return commandError === undefined ? { observation } : { observation, commandError }
}
