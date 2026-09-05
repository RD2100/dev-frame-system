/**
 * Zod-validated host configuration of the agent-hierarchy policy. Every
 * deployment-varying choice — the role tool surfaces, the model-facing names
 * of the creation entry points, and the approved plugin scopes per lead — is
 * a validated `Config` field, so a misconfigured host fails loud at load and
 * nothing in the policy hardcodes a deployment's tool vocabulary.
 *
 * @module @deepseek-ai/dsh-experimental-agent-hierarchy/config
 */

import { z } from 'zod'
import { PluginId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { AgentHierarchyError } from './errors.ts'

/** One non-empty, unpadded name (tool names, plugin scopes, session ids). */
const name = z.string().refine(
  value => value.length > 0 && value.trim().length === value.length,
  'must be a non-empty trimmed name',
)

/** A list of names that must not repeat. */
const nameList = z.array(name).superRefine((list, ctx) => {
  const seen = new Set<string>()
  for (const entry of list) {
    if (seen.has(entry)) {
      ctx.addIssue({ code: 'custom', message: `duplicate name "${entry}"` })
    }
    seen.add(entry)
  }
})

/** Per-role tool surface: the inherited allow list plus optional host extras on the deny face. */
const roleToolPolicySchema = z.object({
  /** Global tools the role keeps; an empty list denies every global tool for the role. */
  inheritedTools: nameList,
  /** Host-selected additional scope-local tool names denied for the role. */
  denyScopedTools: nameList.optional(),
})

/** Raw, unbranded shape of {@link AgentHierarchyConfig} as the host supplies it. */
export const agentHierarchyConfigSchema = z
  .object({
    /** The three-role policy lookup table; `reviewer` is deliberately absent — its semantics live in the lead and worker deny faces. */
    roleToolPolicies: z.object({
      controller: roleToolPolicySchema,
      lead: roleToolPolicySchema,
      worker: roleToolPolicySchema,
    }),
    /** Model-facing names of tools that create delegated children through the subagent seam (spawn/fork). */
    delegationToolNames: nameList.default(['subagent', 'fork']),
    /** Team-local spawn/task-control tools denied for every role below the controller. */
    teamToolNames: nameList.default(['spawn_teammate', 'team_task_create', 'team_task_update', 'followup_task', 'interrupt_agent']),
    /** Any further agent-creating surface the host deploys (SDK bridges, future tools). */
    otherCreationToolNames: nameList.default([]),
    /** Approved plugin scopes per lead agent id. An unlisted lead is approved for nothing (fail closed). */
    leadPluginScopes: z
      .record(name, z.array(name))
      .transform(record => Object.fromEntries(Object.entries(record).map(([agentId, scopes]) => [agentId, scopes.map(PluginId)])))
      .default({}),
  })
  .superRefine((value, ctx) => {
    const overlap = value.delegationToolNames.filter(entry => value.teamToolNames.includes(entry))
    if (overlap.length > 0) {
      ctx.addIssue({
        code: 'custom',
        message: `delegationToolNames and teamToolNames overlap: ${overlap.map(entry => `"${entry}"`).join(', ')}`,
        path: ['delegationToolNames'],
      })
    }
  })

/** The resolved host configuration consumed by the policy, guard, and creation evaluator. */
export interface AgentHierarchyConfig {
  /** Per-role inherited allow lists and host-selected deny extras. */
  readonly roleToolPolicies: Readonly<Record<'controller' | 'lead' | 'worker', {
    /** Global tools the role keeps. */
    readonly inheritedTools: readonly string[]
    /** Host-selected additional scope-local denials. */
    readonly denyScopedTools?: readonly string[] | undefined
  }>>
  /** Tools that create delegated children through the subagent seam. */
  readonly delegationToolNames: readonly string[]
  /** Team-local spawn/task-control tools denied below the controller. */
  readonly teamToolNames: readonly string[]
  /** Any further agent-creating surface the host deploys. */
  readonly otherCreationToolNames: readonly string[]
  /** Approved plugin scopes per lead agent id; unlisted leads are approved for nothing. */
  readonly leadPluginScopes: Readonly<Record<string, readonly ReturnType<typeof PluginId>[]>>
}

/** The raw host configuration shape before validation, with defaulted fields optional. */
export type AgentHierarchyConfigInput = z.input<typeof agentHierarchyConfigSchema>

/**
 * Validate and resolve the host configuration, applying the documented
 * defaults. Called once at service construction so misconfiguration fails
 * loud at load, never at first enforcement.
 * @param input - The raw host configuration; omitted fields take defaults.
 * @returns The resolved configuration with branded plugin scopes.
 * @throws {@link AgentHierarchyError} with code `HIERARCHY_INVALID_CONFIG` when validation fails.
 */
export function parseAgentHierarchyConfig(input: AgentHierarchyConfigInput | undefined): AgentHierarchyConfig {
  const result = agentHierarchyConfigSchema.safeParse(input ?? {})
  if (!result.success) {
    const detail = result.error.issues.map(issue => `${issue.path.join('.')}: ${issue.message}`).join('; ')
    throw new AgentHierarchyError(`invalid agent-hierarchy config: ${detail}`, 'HIERARCHY_INVALID_CONFIG')
  }
  return result.data as AgentHierarchyConfig
}
