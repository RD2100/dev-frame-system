/** Real dispatch registries with isolated Git worktrees and deterministic child-turn admission. */
import { execFile } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { promisify } from 'node:util'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-experimental-session-identity'
import type {} from '@deepseek-ai/dsh-workspace'
import { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'

export const name = 'dispatch-settlement-followup'
export const inject = ['workspaceRegistry', 'worktreeRegistry', 'agentBindings', 'storageDomain']

/**
 * Seed real registry state; child turns wait until their dispatching parent turn ends.
 * @param ctx - The SDK profile's registries and agent lifecycle.
 */
export async function apply(ctx: Context): Promise<void> {
  const root = join(process.cwd(), '.dsh', 'dispatch')
  const repo = join(root, 'repo')
  await mkdir(repo, { recursive: true })
  await mkdir(join(root, 'empty-template'))
  await writeFile(join(root, 'empty-config'), '')
  const env = Object.fromEntries(Object.entries(process.env)
    .filter(([key]) => !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key)))
  const git = async (...args: string[]) => await promisify(execFile)('git', ['-C', repo, ...args], {
    env: { ...env, GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: join(root, 'empty-config') },
    windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024,
  })
  await git('init', '--template=' + join(root, 'empty-template'), '-b', 'main')
  for (const [key, value] of [
    ['user.name', 'Dispatch Snapshot'], ['user.email', 'snapshot@example.invalid'],
    ['commit.gpgsign', 'false'], ['core.hooksPath', join(root, 'no-hooks')],
  ] as const) await git('config', key, value)
  await git('commit', '--allow-empty', '-m', 'snapshot base')
  const workspace = await ctx.workspaceRegistry.create(repo)
  const tree = await ctx.worktreeRegistry.create({
    workspaceId: workspace.id, path: join(root, 'lead'), branch: 'feature/review',
  })
  // Only the generated identity changes: Git observations and all registry operations stay real.
  const domain = ctx.storageDomain.get('worktree_registry')
  if (domain === undefined) throw new Error('Dispatch snapshot worktree domain is not open')
  const table = domain.table('worktrees')
  const record = table.get(tree.id)
  if (record === undefined) throw new Error('Dispatch snapshot worktree was not persisted')
  await table.put(WorktreeId('wt-review-0001'), record)
  await table.delete(tree.id)

  const initialized = new WeakSet<object>()
  const parentEnds = [Promise.withResolvers<undefined>(), Promise.withResolvers<undefined>()]
  ctx.on('session/event', (session, event) => {
    if (session.header.parentSession !== undefined || event.type !== 'turn/end') return
    if (event.data.turn === 1) parentEnds[0]!.resolve(undefined)
    if (event.data.turn === 3) parentEnds[1]!.resolve(undefined)
  })
  ctx.on('agent/pre-step', async ({ agent, turn, signal }, next) => {
    if (agent.session.header.parentSession === undefined) {
      if (!initialized.has(agent)) {
        await ctx.agentBindings.bind({ agentId: agent.id, role: 'controller' })
        initialized.add(agent)
      }
      return next()
    }
    const fence = parentEnds[turn - 1]
    if (fence === undefined) throw new Error(`Dispatch snapshot has no child turn ${turn}`)
    signal.throwIfAborted()
    const aborted = Promise.withResolvers<never>()
    const onAbort = () => { aborted.reject(signal.reason) }
    signal.addEventListener('abort', onAbort, { once: true })
    try {
      await Promise.race([fence.promise, aborted.promise])
      return await next()
    } finally {
      signal.removeEventListener('abort', onAbort)
    }
  })
}
