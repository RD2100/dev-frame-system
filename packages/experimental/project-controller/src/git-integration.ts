/** Git observations and fast-forward execution for the controller's exclusive main-tree writer. */

import { execFile } from 'node:child_process'
import { realpath } from 'node:fs/promises'
import { isAbsolute, resolve } from 'node:path'
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
}

/** Post-execution observation; only `applied` permits recording integration. */
export type IntegrationGitObservation =
  | { readonly kind: 'applied'; readonly head: string }
  | { readonly kind: 'unchanged'; readonly head: string }
  | { readonly kind: 'ambiguous'; readonly head: string; readonly clean: boolean }

/** Execute Git with argument boundaries and without ambient credentials or Git directory overrides. */
async function git(options: IntegrationGitOptions, cwd: string, args: readonly string[], signal?: AbortSignal): Promise<string> {
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
    !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key)))
  const result = await execFileAsync(options.executable, ['-C', cwd, ...args], {
    env,
    windowsHide: true,
    timeout: options.timeoutMs,
    maxBuffer: options.maxOutputBytes,
    encoding: 'utf8',
    ...(signal === undefined ? {} : { signal }),
  })
  return result.stdout.trim()
}

/** Reject ambiguous references and invalid host limits before launching a process. */
function validate(request: IntegrationGitRequest, options: IntegrationGitOptions): void {
  if (!isAbsolute(request.sourcePath) || !isAbsolute(request.targetPath)
    || !/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(request.sourceCommit)
    || !/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(request.targetHead)) {
    throw new Error('Integration requires absolute checkout paths and full commit object IDs')
  }
  if (options.executable.length === 0 || !Number.isSafeInteger(options.timeoutMs) || options.timeoutMs < 1
    || !Number.isSafeInteger(options.maxOutputBytes) || options.maxOutputBytes < 1) {
    throw new Error('Integration requires a Git executable and positive process limits')
  }
}

/** Read the worktree state without refreshing its index or changing files. */
async function observe(options: IntegrationGitOptions, path: string): Promise<{ head: string; clean: boolean }> {
  const head = await git(options, path, ['rev-parse', '--verify', 'HEAD'])
  const status = await git(options, path, ['--no-optional-locks', 'status', '--porcelain=v1', '--untracked-files=all'])
  return { head, clean: status.length === 0 }
}

/**
 * Validate independent clean checkouts, repository identity, exact commits, and fast-forward ancestry.
 * The host must retain exclusive target writer ownership until integration is recorded.
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
  await git(options, target, ['merge-base', '--is-ancestor', request.targetHead, request.sourceCommit])
}

/**
 * Observe an uncertain merge without repeating it or changing the checkout.
 * @param request - Identities retained by the original integration operation.
 * @param options - Explicit Git process settings; observations use their own bounded calls.
 * @returns Applied, unchanged, or ambiguous target state.
 */
export async function reconcileIntegrationGit(
  request: IntegrationGitRequest,
  options: IntegrationGitOptions,
): Promise<IntegrationGitObservation> {
  validate(request, options)
  const state = await observe(options, request.targetPath)
  if (state.clean && state.head === request.sourceCommit) return { kind: 'applied', head: state.head }
  if (state.clean && state.head === request.targetHead) return { kind: 'unchanged', head: state.head }
  return { kind: 'ambiguous', ...state }
}

/**
 * Fast-forward the exclusively owned target once, then reconcile its actual state even if Git throws.
 * No reset, abort, retry, commit creation, or automatic conflict resolution is performed.
 * @param request - Exact reviewed source and target identities.
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
  let commandError: unknown
  try {
    await git(options, request.targetPath, ['merge', '--ff-only', '--no-edit', '--no-overwrite-ignore', request.sourceCommit], signal)
  } catch (error) {
    // The command may have advanced HEAD before transport failure or cancellation; observe before any decision.
    commandError = error
  }
  const observation = await reconcileIntegrationGit(request, options)
  return commandError === undefined ? { observation } : { observation, commandError }
}
