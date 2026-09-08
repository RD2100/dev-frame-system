/**
 * Typed failures shared by subagent service and provider operations.
 *
 * @module @deepseek-ai/dsh-subagent
 */

import { HarnessError } from '@deepseek-ai/dsh-llm'

/** Typed failure for the subagent seam. */
export class SubagentError extends HarnessError {
  constructor(message: string, code: string, options?: ErrorOptions) {
    super(message, code, options)
    this.name = 'SubagentError'
  }
}

/** Startup failed while provider-owned resources still require awaited cleanup. */
export class SubagentStartupCleanupError extends AggregateError {
  private closing: Promise<void> | undefined
  constructor(errors: readonly unknown[], message: string, private readonly retryCleanup: () => Promise<void>) {
    super(errors, message)
  }

  /**
   * Retry the provider's real resource disposal after unpublished startup failed.
   * @returns after all retained resources release; rejection preserves ownership.
   */
  cleanup(): Promise<void> {
    this.closing ??= Promise.resolve().then(this.retryCleanup).catch((error: unknown) => {
      this.closing = undefined
      throw error
    })
    return this.closing
  }
}
