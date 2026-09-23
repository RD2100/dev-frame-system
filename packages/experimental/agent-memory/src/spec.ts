/** Durable storage-domain schema for agent memory. */
import { z } from 'zod'
import { defineDomain, domainTable } from '@deepseek-ai/dsh-storage-domain'
import type { MemoryEpisode, MemoryTrace, ProceduralMemory, SemanticMemory } from './types.ts'

const scope = z.object({
  userId: z.string().optional(), workspaceId: z.string().optional(), projectId: z.string().optional(),
  repository: z.string().optional(), branch: z.string().optional(), taskId: z.string().optional(),
}).strict()
const source = z.object({
  type: z.enum(['source_code', 'user_explicit', 'official_documentation', 'test_result', 'tool_result', 'agent_inference', 'unknown']),
  ref: z.string().min(1), hash: z.string().optional(), timestamp: z.string().optional(), creator: z.string().optional(),
}).strict()
const status = z.enum(['candidate', 'active', 'conflicted', 'superseded', 'expired', 'archived', 'deleted'])

export const episodeSchema = z.object({
  id: z.string().min(1), scope, taskType: z.string().min(1), summary: z.string().min(1),
  actions: z.array(z.string()), decisions: z.array(z.string()), errors: z.array(z.string()),
  result: z.enum(['success', 'failure', 'partial', 'unknown']), resultSummary: z.string(),
  artifacts: z.array(z.string()), sourceRefs: z.array(z.string()),
  createdAt: z.string(), updatedAt: z.string(), status, authority: source.shape.type,
}).strict() as z.ZodType<MemoryEpisode>

export const semanticSchema = z.object({
  id: z.string().min(1), scope, subject: z.string().min(1), predicate: z.string().min(1),
  object: z.string().min(1), statement: z.string().min(1), source,
  confidence: z.number().min(0).max(1), authority: source.shape.type, status, validFrom: z.string(), validUntil: z.string().optional(),
  supersedes: z.array(z.string()).optional(), supersededBy: z.string().optional(), createdAt: z.string(), updatedAt: z.string(),
}).strict() as z.ZodType<SemanticMemory>

export const procedureSchema = z.object({
  id: z.string().min(1), name: z.string().min(1), trigger: z.array(z.string()),
  preconditions: z.array(z.string()), steps: z.array(z.string()),
  successCriteria: z.array(z.string()), failureConditions: z.array(z.string()), version: z.number().int().positive(), status, scope,
  sourceRefs: z.array(z.string()), createdAt: z.string(), updatedAt: z.string(),
}).strict() as z.ZodType<ProceduralMemory>

export const traceSchema = z.object({
  id: z.string().min(1), runId: z.string().min(1), query: z.string(), scope, retrieved: z.array(z.string()), injected: z.array(z.string()),
  created: z.array(z.string()), superseded: z.array(z.string()), scores: z.record(z.string(), z.number()), createdAt: z.string(),
}).strict() as z.ZodType<MemoryTrace>

export const agentMemoryDomainSpec = defineDomain({
  name: 'agent_memory',
  version: 1,
  layout: 'per-record',
  tables: {
    episodes: domainTable<string, MemoryEpisode>(episodeSchema),
    facts: domainTable<string, SemanticMemory>(semanticSchema),
    procedures: domainTable<string, ProceduralMemory>(procedureSchema),
    traces: domainTable<string, MemoryTrace>(traceSchema),
  },
})
