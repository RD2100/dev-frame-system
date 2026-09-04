/** Stop one admitted project while retaining its writer until native work drains. */

import type { Agent, AgentRegistry } from '@deepseek-ai/dsh-agent'
import type { GoalService } from '@deepseek-ai/dsh-goal'
import type { JobRegistry } from '@deepseek-ai/dsh-jobs'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { SubprocessHandle } from '@deepseek-ai/dsh-subprocess'
import { deadline, MAX_TIMER_DELAY_MS } from '@deepseek-ai/dsh-timeout'
import type { ProjectLifecycleState } from '../shared/types.ts'

/** An owned process captured at dispatch; absent handles require reconciliation. */
export interface StopProcess {
  readonly ownerSession: SessionId
  readonly label: string
  /** Stable operation identity retained across inventory refreshes and restart. */
  readonly operationId?: string
  readonly handle?: SubprocessHandle
}

/** A resource whose cancellation, cleanup, or durable state is unconfirmed. */
export interface StopIssue {
  readonly resource: string
  readonly reason: 'timeout' | 'identity_unknown' | 'operation_failed' | 'unconfirmed'
}

/** Durable observations; confirmed quiescence does not itself release writer ownership. */
export interface StopObservation {
  readonly status: Extract<ProjectLifecycleState, 'stop_requested' | 'quiescence_confirmed' | 'needs_attention'>
  readonly remaining: readonly StopIssue[]
}

/** Result published only after the final flush and writer-release commit. */
export interface StopResult {
  readonly status: 'stopped' | 'needs_attention'
  readonly remaining: readonly StopIssue[]
}

/** Native capabilities and host-owned admission/persistence for one serialized stop. */
export interface StopProjectOptions {
  readonly agents: readonly Agent[]
  readonly registry: Pick<AgentRegistry, 'get'>
  readonly goals: Pick<GoalService, 'disarm' | 'pause'>
  readonly jobs: Pick<JobRegistry, 'list' | 'kill' | 'wait'>
  /** Return every captured process, including identities unresolved after restart. */
  readonly processes: () => readonly StopProcess[]
  readonly graceMs: number
  /** Synchronously fence dispatch, tool admission, callbacks, and new ownership. */
  readonly closeAdmission: () => void
  /** Append to the owning native Session; never interpret quiescence as released. */
  readonly record: (observation: StopObservation) => void
  /** Flush all participating Session state through native persistence. */
  readonly flush: () => Promise<void>
  /** Synchronous owner-checked release; a throw must retain the writer. */
  readonly releaseWriter: () => void
}

/** Wait within the shared stop deadline without interpreting timeout as settlement. */
async function bounded(work: Promise<unknown>, signal: AbortSignal): Promise<boolean> {
  let onAbort: () => void = () => {}
  const expired = new Promise<boolean>((resolve) => {
    onAbort = () => { resolve(false) }
    if (signal.aborted) onAbort()
    else signal.addEventListener('abort', onAbort, { once: true })
  })
  try {
    return await Promise.race([work.then(() => true), expired])
  } finally {
    signal.removeEventListener('abort', onAbort)
  }
}

/**
 * Close admission, cancel only known descendants, and flush before releasing ownership.
 * The host serializes calls for the same writer and retains unresolved identities across restart.
 * @param options - native live handles and the owning project's durable state adapter.
 * @returns stopped only after confirmed cleanup and flush; otherwise retained ownership.
 */
export async function stopProject(options: StopProjectOptions): Promise<StopResult> {
  if (!Number.isFinite(options.graceMs) || options.graceMs <= 0 || options.graceMs > MAX_TIMER_DELAY_MS) {
    throw new Error('stop graceMs must be a positive finite timer delay')
  }
  using bound = deadline(undefined, options.graceMs, 'DEVFRAME_STOP_TIMEOUT')
  const issues: StopIssue[] = []
  const pending = new Set<string>()
  const active = options.agents.filter(agent => options.registry.get(agent.id) === agent)
  const owners = new Set(active.map(agent => agent.id))
  const attempt = (resource: string, action: () => void): void => {
    try {
      action()
    } catch (_operationFailed) {
      issues.push({ resource, reason: 'operation_failed' })
    }
  }
  const observe = (status: StopObservation['status']): void => {
    attempt('session:record', () => { options.record({ status, remaining: [...issues] }) })
  }
  const drain = (resource: string, action: () => Promise<boolean | void>): Promise<void> => {
    pending.add(resource)
    return Promise.resolve().then(action).then((confirmed) => {
      pending.delete(resource)
      if (confirmed === false) issues.push({ resource, reason: 'unconfirmed' })
    }, () => {
      pending.delete(resource)
      issues.push({ resource, reason: 'operation_failed' })
    })
  }

  attempt('admission', options.closeAdmission)
  for (const agent of options.agents) {
    if (!owners.has(agent.id)) issues.push({ resource: `agent:${agent.id}`, reason: 'identity_unknown' })
  }
  for (const agent of active) {
    attempt(`goal:${agent.id}`, () => {
      const goal = options.goals.disarm(agent)
      if (goal?.phase === 'active') options.goals.pause(agent, { id: goal.id, revision: goal.revision })
    })
  }
  observe('stop_requested')

  const seenJobs = new Set<string>()
  const seenProcesses = new Set<SubprocessHandle | string>()
  const processResources = new WeakMap<SubprocessHandle, string>()
  let nextProcessResource = 0
  const processIdentity = (process: StopProcess): SubprocessHandle | string => {
    if (process.handle !== undefined) return process.handle
    return process.operationId ?? `${process.ownerSession}:${process.label}`
  }
  const processResource = (process: StopProcess): string => {
    if (process.handle === undefined) return `process:${process.operationId ?? process.label}`
    const existing = processResources.get(process.handle)
    if (existing !== undefined) return existing
    const resource = `process:${process.operationId ?? process.label}:${++nextProcessResource}`
    processResources.set(process.handle, resource)
    return resource
  }
  const cancelOwned = (): Promise<void>[] => {
    const waits: Promise<void>[] = []
    for (const agent of active) {
      attempt(`jobs:${agent.id}`, () => {
        for (const job of options.jobs.list(agent)) {
          if (job.ownerSession !== agent.id || seenJobs.has(job.id)) continue
          seenJobs.add(job.id)
          if (job.status === 'completed' || job.status === 'killed') continue
          const resource = `job:${job.id}`
          attempt(resource, () => { options.jobs.kill(job.id, agent, 'project stop') })
          waits.push(drain(resource, async () => {
            const settled = await options.jobs.wait(job.id, options.graceMs, agent, bound.signal)
            return settled.status === 'completed' || settled.status === 'killed'
          }))
        }
      })
    }
    attempt('processes:inventory', () => {
      for (const process of options.processes()) {
        const identity = processIdentity(process)
        if (seenProcesses.has(identity)) continue
        seenProcesses.add(identity)
        const resource = processResource(process)
        const handle = process.handle
        if (!owners.has(process.ownerSession) || handle === undefined) {
          issues.push({ resource, reason: 'identity_unknown' })
          continue
        }
        attempt(resource, () => { handle.terminate() })
        waits.push(drain(resource, async () => {
          await handle.done
          return handle.waitForExit(bound.signal)
        }))
      }
    })
    return waits
  }

  const waits = cancelOwned()
  for (const agent of active) {
    attempt(`agent:${agent.id}`, () => { agent.cancel({ kind: 'user' }, { keepInbox: true }) })
    waits.push(drain(`agent:${agent.id}`, () => agent.whenIdle()))
  }
  await bounded(Promise.all(waits), bound.signal)
  // A tool already executing when admission closed may have registered a job while draining.
  if (!bound.signal.aborted) await bounded(Promise.all(cancelOwned()), bound.signal)
  for (const resource of pending) issues.push({ resource, reason: 'timeout' })
  observe(issues.length === 0 ? 'quiescence_confirmed' : 'needs_attention')
  await bounded(drain('session:flush', options.flush), bound.signal)
  if (pending.has('session:flush')) issues.push({ resource: 'session:flush', reason: 'timeout' })
  if (issues.length === 0) attempt('writer:release', options.releaseWriter)
  return { status: issues.length === 0 ? 'stopped' : 'needs_attention', remaining: [...issues] }
}
