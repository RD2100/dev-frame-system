/**
 * The stable error type for the expert-team packages.
 * @module @deepseek-ai/dsh-experimental-expert-team/errors
 */

import { HarnessError } from '@deepseek-ai/dsh-llm'

/**
 * Structured failure thrown by the expert-team catalog half and later by the
 * orchestration half, so host admission and diagnostics can route on the code
 * alone. Extending {@link HarnessError} keeps the `{ name, code }`
 * classification on the tool result and its `tool/result` session event.
 * Construction is the inherited `(message, code, options)` form; `code`
 * draws from {@link ExpertTeamErrorCode} by caller discipline.
 */
export class ExpertTeamError extends HarnessError {}
