/** Stable failure classifications for the optional memory layer. */
export type AgentMemoryErrorCode =
  | 'MEMORY_UNAVAILABLE'
  | 'MEMORY_INVALID_REQUEST'
  | 'MEMORY_CONTENT_REJECTED'
  | 'MEMORY_SCOPE_FORBIDDEN'
  | 'MEMORY_PERSISTENCE'
  | 'MEMORY_CONFLICT'

export class AgentMemoryError extends Error {
  override readonly name = 'AgentMemoryError'
  constructor(message: string, readonly code: AgentMemoryErrorCode, options?: { cause?: unknown }) {
    super(message, options)
  }
}
