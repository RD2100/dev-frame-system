/**
 * Shared test helpers: real git invocation for repository setup. The code
 * under test spawns git through the subprocess seam; these helpers exist so
 * setup and assertions never depend on it.
 * @module tests/helpers
 */

import { execFile } from 'node:child_process'

/**
 * Run one git command, failing loud with its stderr.
 * @param cwd - Working directory for the invocation.
 * @param args - git arguments after the executable.
 * @returns the collected stdout.
 */
export function git(cwd: string, ...args: string[]): Promise<string> {
  return new Promise((resolvePromise, rejectPromise) => {
    execFile('git', args, { cwd, windowsHide: true }, (error, stdout, stderr) => {
      if (error !== null) {
        const code = typeof (error as NodeJS.ErrnoException).code === 'string' ? ` code=${(error as NodeJS.ErrnoException).code}` : ''
        rejectPromise(new Error(`git ${args.join(' ')} failed${code}: ${error.message} stderr=${String(stderr ?? '')}`))
      } else {
        resolvePromise(String(stdout))
      }
    })
  })
}

/** git prints worktree paths with forward slashes; normalize both sides for containment checks. */
export function gitStyle(path: string): string {
  return path.replace(/\\/g, '/').toLowerCase()
}
