/** Public vocabulary for persistent agent memory. */

export type MemoryKind = 'episode' | 'semantic' | 'procedural'
export type MemoryStatus = 'candidate' | 'active' | 'conflicted' | 'superseded' | 'expired' | 'archived' | 'deleted'
export type Authority = 'source_code' | 'user_explicit' | 'official_documentation' | 'test_result' | 'tool_result' | 'agent_inference' | 'unknown'

/** The explicit address at which a memory is valid. Undefined fields are wildcards. */
export interface MemoryScope {
  readonly userId?: string
  readonly workspaceId?: string
  readonly projectId?: string
  readonly repository?: string
  readonly branch?: string
  readonly taskId?: string
}

/** Source evidence attached to a long-lived memory. */
export interface MemorySource {
  readonly type: Authority
  readonly ref: string
  readonly hash?: string
  readonly timestamp?: string
  readonly creator?: string
}

export interface MemoryEpisode {
  readonly id: string
  readonly scope: MemoryScope
  readonly taskType: string
  readonly summary: string
  readonly actions: readonly string[]
  readonly decisions: readonly string[]
  readonly errors: readonly string[]
  readonly result: 'success' | 'failure' | 'partial' | 'unknown'
  readonly resultSummary: string
  readonly artifacts: readonly string[]
  readonly sourceRefs: readonly string[]
  readonly createdAt: string
  readonly updatedAt: string
  readonly status: MemoryStatus
  readonly authority: Authority
}

export interface SemanticMemory {
  readonly id: string
  readonly scope: MemoryScope
  readonly subject: string
  readonly predicate: string
  readonly object: string
  readonly statement: string
  readonly source: MemorySource
  readonly confidence: number
  readonly authority: Authority
  readonly status: MemoryStatus
  readonly validFrom: string
  readonly validUntil?: string
  readonly supersedes?: readonly string[]
  readonly supersededBy?: string
  readonly createdAt: string
  readonly updatedAt: string
}

export interface ProceduralMemory {
  readonly id: string
  readonly name: string
  readonly trigger: readonly string[]
  readonly preconditions: readonly string[]
  readonly steps: readonly string[]
  readonly successCriteria: readonly string[]
  readonly failureConditions: readonly string[]
  readonly version: number
  readonly status: MemoryStatus
  readonly scope: MemoryScope
  readonly sourceRefs: readonly string[]
  readonly createdAt: string
  readonly updatedAt: string
}

export interface MemoryTrace {
  readonly id: string
  readonly runId: string
  readonly query: string
  readonly scope: MemoryScope
  readonly retrieved: readonly string[]
  readonly injected: readonly string[]
  readonly created: readonly string[]
  readonly superseded: readonly string[]
  readonly scores: Readonly<Record<string, number>>
  readonly createdAt: string
}

export interface ContextItem {
  readonly id: string
  readonly kind: MemoryKind
  readonly text: string
  readonly score: number
  readonly reason: string
}

export interface MemoryContext {
  readonly items: readonly ContextItem[]
  readonly text: string
  readonly traceId: string
  readonly truncated: boolean
}

export interface RetrieveRequest {
  readonly query: string
  readonly scope: MemoryScope
  readonly budgetBytes?: number
  readonly runId?: string
}

export interface EpisodeInput {
  readonly scope: MemoryScope
  readonly taskType: string
  readonly summary: string
  readonly actions?: readonly string[]
  readonly decisions?: readonly string[]
  readonly errors?: readonly string[]
  readonly result?: MemoryEpisode['result']
  readonly resultSummary?: string
  readonly artifacts?: readonly string[]
  readonly sourceRefs?: readonly string[]
  readonly authority?: Authority
}

export interface SemanticInput {
  readonly scope: MemoryScope
  readonly subject: string
  readonly predicate: string
  readonly object: string
  readonly statement: string
  readonly source: MemorySource
  readonly confidence?: number
}

export interface ProcedureInput {
  readonly scope: MemoryScope
  readonly name: string
  readonly trigger: readonly string[]
  readonly preconditions?: readonly string[]
  readonly steps: readonly string[]
  readonly successCriteria?: readonly string[]
  readonly failureConditions?: readonly string[]
  readonly sourceRefs?: readonly string[]
}

export interface ConsolidationCandidate {
  readonly kind: 'semantic' | 'procedural'
  readonly evidenceIds: readonly string[]
  readonly summary: string
}
