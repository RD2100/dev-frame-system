/** Host-wide terminal admission and cleanup across isolated service instances. */
import { Context, Service } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { TerminalError } from '@deepseek-ai/dsh-terminal'
import type { TerminalSessionService } from '@deepseek-ai/dsh-terminal'

declare module '@deepseek-ai/cordis' {
  interface Context {
    terminalOwnership: TerminalOwnershipRegistry
  }
}

/** Retain every terminal provider until its owned resources have quiesced. */
export class TerminalOwnershipRegistry extends Service {
  static inject = ['agents']
  private readonly instances = new Set<TerminalSessionService>()
  private readonly fenced = new WeakSet<Agent>()
  private readonly drains = new WeakMap<Agent, number>()
  private generation = 0

  constructor(ctx: Context) { super(ctx, 'terminalOwnership') }

  /**
   * Register one instance from its own effect scope.
   * @param instance - terminal service contributing its complete resource inventory.
   * @returns disposer to call only after instance cleanup succeeds.
   */
  register(instance: TerminalSessionService): () => void {
    if (this.instances.has(instance)) throw new Error('terminal instance is already registered')
    this.instances.add(instance)
    this.generation++
    return () => { if (this.instances.delete(instance)) this.generation++ }
  }

  /**
   * Reject admission before a service reserves or starts backend work.
   * @param owner - exact Agent receiving terminal resources.
   */
  assertAdmission(owner: Agent): void {
    if (this.fenced.has(owner)) throw new TerminalError('PTY owner admission is closed', 'OWNER_NOT_LIVE')
  }

  /**
   * Fence an owner even with zero instances, then await all current instances.
   * @param owner - exact Agent whose resources must close.
   * @returns after all owned resources quiesce; cleanup failures retain the fence.
   */
  async drainOwned(owner: Agent): Promise<void> {
    this.fenced.add(owner)
    this.drains.set(owner, (this.drains.get(owner) ?? 0) + 1)
    const results = await Promise.allSettled([...this.instances].map(instance => instance.drainOwned(owner)))
    const failures = results.filter(result => result.status === 'rejected').map(result => result.reason as unknown)
    if (failures.length > 0) throw new AggregateError(failures, 'terminal owner cleanup failed')
  }

  /**
   * Observe published sessions and pending rollback in every registered instance.
   * @param owner - exact Agent whose activity is queried.
   * @returns whether any provider still owns resources for the Agent.
   */
  hasOwnerActivity(owner: Agent): boolean {
    return [...this.instances].some(instance => instance.hasOwnerActivity(owner))
  }

  /**
   * Preflight a project owner's entire terminal lineage without partial reopening.
   * @param owners - exact Agents sharing one host resume transaction.
   * @returns commit that validates every captured drain and provider before opening any owner.
   */
  prepareReopenOwners(owners: readonly Agent[]): () => void {
    const selected = [...owners]
    const prepare = (): (() => void)[] => {
      return selected.flatMap((owner) => {
        if (this.ctx.agents.get(owner.id) !== owner) throw new TerminalError('PTY owner is no longer live', 'OWNER_NOT_LIVE')
        return [...this.instances].map(instance => instance.prepareReopenOwned(owner))
      })
    }
    prepare()
    const generation = this.generation
    const drains = selected.map(owner => this.drains.get(owner))
    return () => {
      if (generation !== this.generation) throw new TerminalError('terminal instance directory changed before reopening', 'OWNER_NOT_LIVE')
      if (selected.some((owner, index) => drains[index] !== this.drains.get(owner))) {
        throw new TerminalError('terminal owner drain changed before reopening', 'OWNER_NOT_LIVE')
      }
      const commits = prepare()
      for (const commit of commits) commit()
      for (const owner of selected) this.fenced.delete(owner)
    }
  }
}

export default TerminalOwnershipRegistry
