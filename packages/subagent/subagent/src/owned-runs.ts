/** One-shot ownership from provider admission through awaited resource disposal. */
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { SubagentRun } from './types.ts'
import { SubagentError, SubagentStartupCleanupError } from './error.ts'

interface OwnedRun {
  readonly controller: AbortController
  readonly ready: Promise<void>
  run: SubagentRun | undefined
  cleanupFailure: AggregateError | undefined
}

/** Service-local one-shot run ownership; result settlement does not release resources. */
export class OwnedRuns {
  private readonly owners = new Map<Agent, Set<OwnedRun>>()
  private readonly closed = new WeakSet<Agent>()
  private disposing = false

  /**
   * Inspect unpublished starts and published runs awaiting disposal.
   * @param owner - exact delegating Agent.
   * @returns whether resources may still belong to this owner.
   */
  has(owner: Agent): boolean {
    return (this.owners.get(owner)?.size ?? 0) > 0
  }

  /**
   * Reopen a drained owner after its host authorizes a new admission interval.
   * @param owner - exact Agent with no retained one-shot resources.
   */
  reopen(owner: Agent): void {
    this.prepareReopen(owner)()
  }

  /**
   * Validate reopening without changing owner admission.
   * @param owner - exact Agent to inspect before a synchronous multi-service reopen.
   * @returns a non-throwing commit; invoke synchronously after all preparation, without yielding.
   */
  prepareReopen(owner: Agent): () => void {
    if (this.disposing || this.has(owner)) throw new SubagentError('subagent owner still has retained resources', 'OWNER_DRAINING')
    return () => { this.closed.delete(owner) }
  }

  /**
   * Reserve ownership before invoking the provider and retain it until disposal.
   * @param owner - exact delegating Agent.
   * @param signal - caller cancellation forwarded to the provider.
   * @param start - provider establishment with combined cancellation.
   * @returns a run whose disposal releases the reservation only on success.
   */
  async start(owner: Agent, signal: AbortSignal, start: (signal: AbortSignal) => Promise<SubagentRun>): Promise<SubagentRun> {
    if (this.disposing || this.closed.has(owner)) throw new SubagentError('subagent owner is draining', 'OWNER_DRAINING')
    signal.throwIfAborted()
    const controller = new AbortController()
    const ready = Promise.withResolvers<void>()
    const record: OwnedRun = { controller, ready: ready.promise, run: undefined, cleanupFailure: undefined }
    const records = this.owners.get(owner) ?? new Set<OwnedRun>()
    records.add(record)
    this.owners.set(owner, records)
    const remove = (): void => {
      records.delete(record)
      if (records.size === 0) this.owners.delete(owner)
    }
    try {
      const underlying = await start(AbortSignal.any([signal, controller.signal]))
      let closing: Promise<void> | undefined
      const run: SubagentRun = {
        id: underlying.id,
        localAgent: underlying.localAgent,
        result: underlying.result,
        dispose: () => {
          closing ??= Promise.resolve().then(() => underlying.dispose()).then(remove, (error: unknown) => {
            closing = undefined
            throw error
          })
          return closing
        },
      }
      record.run = run
      if (controller.signal.aborted || signal.aborted) {
        await run.dispose()
        throw controller.signal.aborted ? controller.signal.reason : signal.reason
      }
      return run
    } catch (error: unknown) {
      // Providers aggregate startup/rollback failures. Without a retry handle,
      // that failed cleanup remains unresolved rather than becoming quiet.
      if (record.run === undefined && error instanceof AggregateError) record.cleanupFailure = error
      throw error
    } finally {
      // Ordinary setup rejection owns no resources; failed rollback stays
      // visible until its provider proves cleanup.
      if (record.run === undefined && record.cleanupFailure === undefined) remove()
      ready.resolve()
    }
  }

  /**
   * Fence this owner, cancel unpublished starts, then await all owned disposal.
   * @param owner - exact delegating Agent; other owners remain admitted.
   * @returns after provider establishment and every successful resource release.
   */
  async drain(owner: Agent): Promise<void> {
    this.closed.add(owner)
    const records = [...(this.owners.get(owner) ?? [])]
    for (const record of records) record.controller.abort(new SubagentError('subagent owner is draining', 'OWNER_DRAINING'))
    await Promise.all(records.map(record => record.ready))
    const results = await Promise.allSettled(records.map(async (record) => {
      if (record.run !== undefined) {
        await record.run.dispose()
      } else if (record.cleanupFailure instanceof SubagentStartupCleanupError) {
        await record.cleanupFailure.cleanup()
        const owned = this.owners.get(owner)
        owned?.delete(record)
        if (owned?.size === 0) this.owners.delete(owner)
      } else if (record.cleanupFailure !== undefined) {
        throw record.cleanupFailure
      }
    }))
    const failures = results.filter((result): result is PromiseRejectedResult => result.status === 'rejected')
    if (failures.length > 0) throw new AggregateError(failures.map(result => result.reason as unknown), 'owned subagent disposal failed')
  }

  /**
   * Close service admission and release every retained owner.
   * @returns after all owners settle, rejecting if any release failed.
   */
  async dispose(): Promise<void> {
    this.disposing = true
    const results = await Promise.allSettled([...this.owners.keys()].map(owner => this.drain(owner)))
    const failures = results.filter((result): result is PromiseRejectedResult => result.status === 'rejected')
    if (failures.length > 0) throw new AggregateError(failures.map(result => result.reason as unknown), 'subagent service disposal failed')
  }
}
