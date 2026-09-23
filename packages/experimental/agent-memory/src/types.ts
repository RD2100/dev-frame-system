/** Public vocabulary for persistent agent memory. */

export type MemoryKind = 'episode' | 'semantic' | 'procedural'
/** Lifecycle states used by every durable memory kind. */
export type MemoryStatus = 'candidate' | 'active' | 'conflicted' | 'superseded' | 'expired' | 'archived' | 'deleted'
/** Evidence authority attached to a durable memory record. */
export type Authority = 'source_code' | 'user_explicit' | 'official_documentation' | 'test_result' | 'tool_result' | 'agent_inference' | 'unknown'

/** The explicit address at which a memory is valid. Undefined fields are wildcards. */
export interface MemoryScope {
  /** Optional user identity that owns the memory record. */
  readonly userId?: string
  /** Workspace identity that contains the memory record. */
  readonly workspaceId?: string
  /** Optional project identity within the workspace. */
  readonly projectId?: string
  /** Repository identity associated with the record. */
  readonly repository?: string
  /** Branch identity associated with the record. */
  readonly branch?: string
  /** Task identity associated with the record. */
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

/** Structured record of one completed or attempted task. */
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

/** Sourced statement about a subject and predicate. */
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

/** Reusable procedure candidate or active procedure. */
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

/** Audit record for one retrieval and context injection. */
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

/** One ranked item selected for a rendered memory context. */
export interface ContextItem {
  readonly id: string
  readonly kind: MemoryKind
  readonly text: string
  readonly score: number
  readonly reason: string
}

/** Rendered retrieval result and its trace metadata. */
export interface MemoryContext {
  readonly items: readonly ContextItem[]
  readonly text: string
  readonly traceId: string
  readonly truncated: boolean
}

/** Query and scope supplied to memory retrieval. */
export interface RetrieveRequest {
  readonly query: string
  readonly scope: MemoryScope
  readonly budgetBytes?: number
  readonly runId?: string
}

/** Input fields accepted when recording an episode. */
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

/** Input fields accepted when upserting a semantic fact. */
export interface SemanticInput {
  readonly scope: MemoryScope
  readonly subject: string
  readonly predicate: string
  readonly object: string
  readonly statement: string
  readonly source: MemorySource
  readonly confidence?: number
}

/** Input fields accepted when registering a procedure. */
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

/** Suggested procedure derived from repeated episode evidence. */
export interface ConsolidationCandidate {
  readonly kind: 'semantic' | 'procedural'
  readonly evidenceIds: readonly string[]
  readonly summary: string
}
