/**
 * The `@subagent` mention source: candidates come from the Host
 * `subagents/providers` directory RPC, which serves the live `ctx.subagents`
 * registry — never a client-side roster. A picked mention inserts literal
 * `@<provider> ` text, so the mention rides the ordinary user message and
 * needs no reference codec or session event of its own.
 * @module @deepseek-ai/dsh-client-ui-subagent/client/mentions
 */
import type {
  InputTriggerSource, PickOutcome,
} from '@deepseek-ai/dsh-client-ui-input-trigger/client'

/** Registry-truth provider directory read: resolves the live names, rejects on failure. */
export type ReadProviders = () => Promise<readonly string[]>

/** Menu group display order: below the `reference` (default) and `cordis` (1) @ groups. */
const MENTION_SOURCE_ORDER = 2

/**
 * Create the mentionable-provider `@` source.
 * @param readProviders - the `subagents/providers` directory read; rejection
 *   drops this source's menu group (the pipeline's candidate-failure policy).
 * @returns the source; `lexicon` stays `undefined` until the first read
 *   settles, so draft decoration only ever reflects a settled registry roll.
 */
export function createSubagentMentionSource(readProviders: ReadProviders): InputTriggerSource {
  let roll: readonly string[] | undefined
  const listeners = new Set<() => void>()
  const changed = (next: readonly string[]): boolean => {
    const previous = roll
    return previous === undefined
      || next.length !== previous.length
      || next.some((name, index) => name !== previous[index])
  }
  const refresh = async (): Promise<void> => {
    const names = await readProviders()
    if (!changed(names)) return
    roll = names
    for (const listener of [...listeners]) listener()
  }
  return {
    trigger: '@',
    name: 'subagent',
    order: MENTION_SOURCE_ORDER,
    async candidates(_session, { query, signal }) {
      await refresh()
      if (signal.aborted) return []
      return (roll ?? [])
        .filter(name => name.includes(query))
        .map(name => ({ name }))
    },
    warm() {
      // Prewarm is fire-and-forget: a failed directory read only delays the
      // roll, and the first candidate fetch reports the failure itself.
      refresh().catch((error: unknown) => {
        console.error('[ui-subagent] provider directory prewarm failed:', error)
      })
    },
    lexicon() {
      return roll
    },
    subscribeLexicon(_session, listener) {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
    onPick({ candidate }): PickOutcome {
      return { text: `@${candidate.name} ` }
    },
  }
}
