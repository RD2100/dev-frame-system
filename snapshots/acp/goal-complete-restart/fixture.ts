/** Scripted host authorization and independent file review for the command restart recording. */
import type { Context } from '@deepseek-ai/cordis'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { SessionId } from '@deepseek-ai/dsh-session'
import { DevFrameSessionJournal, DevFrameReviewId } from '../../../packages/experimental/devframe/lib/index.js'
import { resultTupleOf } from '../../../packages/experimental/command-goal-binding/lib/index.js'
import type {} from '../../../packages/experimental/command-goal-binding/lib/index.js'

export const name = 'goal-complete-restart-fixture'
export const inject = ['agents', 'commands', 'goals', 'sessions', 'sessionProjections', 'commandGoalBinding']

/**
 * Run the host-approved commands and review once per process, before its first model request.
 * @param ctx - The real ACP host services; persisted state decides which side of the restart runs.
 */
export function apply(ctx: Context): void {
  const visited = new WeakSet<object>()
  ctx.on('agent/pre-step', async ({ agent }, next) => {
    if (visited.has(agent)) return await next()
    visited.add(agent)
    const command = async (line: string): Promise<void> => {
      const execution = await ctx.commands.execute(agent, line, [], new AbortController().signal)
      if (execution?.result.kind !== 'success') throw new Error(`Snapshot command rejected: ${line}: ${JSON.stringify(execution)}`)
    }
    if (ctx.goals.get(agent) === undefined) {
      await command('/devframe-start Verify the committed feature and retain its approval across restart')
      const state = ctx.sessionProjections.stateOf(agent.session, 'devframe')
      const binding = state?.bindings[0]
      const policy = state?.rolePolicy
      if (binding === undefined || policy == null) throw new Error('Start did not land its binding and role policy')
      const reviewer = SessionId('snapshot-command-reviewer')
      const journal = new DevFrameSessionJournal(session => ctx.sessions.flush(session), {
        requireReviewer(sessionId) {
          if (sessionId !== reviewer) throw new Error('Review requires the fixture-authorized independent reviewer')
        },
      })
      await journal.append(agent.session, 'devframe/role-policy', {
        ...policy,
        assignments: [...policy.assignments, { role: 'reviewer', sessionId: reviewer }],
      })
      // The scripted reviewer checks the committed artifact independently of the subprocess check.
      if (await readFile(join(process.cwd(), '.dsh', 'integration', 'target', 'feature.txt'), 'utf8') !== 'base\n') {
        throw new Error('Independent review rejected the committed base artifact')
      }
      await journal.append(agent.session, 'devframe/review', {
        version: 1, reviewId: DevFrameReviewId('review-command-restart'),
        binding: resultTupleOf(binding), snapshotId: binding.snapshotId,
        reviewerSessionId: reviewer, policyVersion: policy.policyVersion,
        decision: 'pass', findings: [],
      })
    } else {
      let sawDeferredResume = false
      const dispose = ctx.on('session/event', (session, event) => {
        if (session !== agent.session || event.type !== 'goal/change' || event.data.operation !== 'resume') return
        if (ctx.goals.get(agent)?.activation !== 'disarmed') throw new Error('Resume armed before its binding was durable')
        sawDeferredResume = true
      })
      try { await command('/devframe-resume') } finally { dispose() }
      if (!sawDeferredResume || ctx.goals.get(agent)?.activation !== 'armed') throw new Error('Durable resume did not activate continuation')
      await command('/goal-complete')
      if (ctx.goals.get(agent)?.phase !== 'complete') throw new Error('Restart completion did not complete the native Goal')
    }
    return await next()
  })
}
