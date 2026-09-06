/**
 * Acceptance harness minimal LLM adapter (v14-accept worker, design §0/§1).
 *
 * Satisfies the route registration the in-process compositions need
 * (`ctx.llm.registerAdapter(['mock'], adapter)`), and otherwise enforces the
 * keyless invariant: the adapter is harness-owned code that never imports any
 * `packages/**` tests path, and its `stream` — the only method the
 * `LlmAdapter` base class requires (`packages/llm/llm/src/index.ts`) — throws
 * `ACCEPTANCE_LLM_TOUCHED` on the first pull without ever producing a chunk.
 * Any scenario that reaches the model fails loud on the spot.
 * @module harness/lib/mock-adapter
 */

import { LlmAdapter } from '@deepseek-ai/dsh-llm'

/**
 * The fail-loud acceptance adapter. All other `LlmAdapter` members keep the
 * base-class defaults (providerInfo, providerRetryPolicy, imageRequestPricing,
 * listModels, resolveModel, prepareCall) — routing registration and model
 * resolution never touch the network.
 */
export class AcceptanceMockAdapter extends LlmAdapter {
  /**
   * Stream one model call — which must never happen in an acceptance run.
   * @param {import('@deepseek-ai/dsh-llm').GenerateOptions} options - the
   *   fully assembled request that reached the adapter.
   * @returns {AsyncIterable<import('@deepseek-ai/dsh-llm').StreamChunk>} an
   *   iterable whose first pull throws; no chunk is ever produced.
   */
  async *stream(options) {
    const route = options?.provider === undefined || options?.model === undefined
      ? ''
      : ` (provider "${options.provider}", model "${options.model}")`
    throw new Error(`ACCEPTANCE_LLM_TOUCHED${route}: an acceptance scenario reached the LLM stream; any LLM touch fails the scenario (design §0 keyless invariant)`)
  }
}

/**
 * Register the fail-loud adapter on the composition's LLM runtime.
 * @param {import('@deepseek-ai/cordis').Context} ctx - the booted composition.
 * @returns {unknown} the registration disposer returned by `registerAdapter`.
 */
export function registerMockAdapter(ctx) {
  return ctx.llm.registerAdapter(['mock'], new AcceptanceMockAdapter())
}
