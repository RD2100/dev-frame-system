/** Branded cross-plugin identifiers owned by the project-contracts vocabulary. */

import { brandString, type Branded } from '@deepseek-ai/dsh-brand'
import { ProjectContractsError } from './errors.ts'

/**
 * Identifies one plugin scope of the pluginized hierarchy. A lead is granted
 * one or more plugin scopes and may create workers only inside them.
 */
export type PluginId = Branded<'PluginId'>

/**
 * Identifies one project task on the board. The brand string is
 * `ProjectTaskId`, deliberately distinct from the experimental DevFrame
 * team-task brand, so the two task vocabularies cannot mix at a type level.
 */
export type TaskId = Branded<'ProjectTaskId'>

/**
 * Brand a validated plugin identifier.
 * @param value - Non-empty, untrimmed-free plugin identifier.
 * @returns the same string, branded at compile time.
 * @throws {@link ProjectContractsError} with code `CONTRACTS_INVALID_ID`
 * when the value is empty, whitespace-only, or padded.
 */
export function PluginId(value: string): PluginId {
  return brandString<PluginId>(requireId(value, 'pluginId'))
}

/**
 * Brand a validated task identifier.
 * @param value - Non-empty, untrimmed-free task identifier.
 * @returns the same string, branded at compile time.
 * @throws {@link ProjectContractsError} with code `CONTRACTS_INVALID_ID`
 * when the value is empty, whitespace-only, or padded.
 */
export function TaskId(value: string): TaskId {
  return brandString<TaskId>(requireId(value, 'taskId'))
}

/** Validate one identifier before applying its compile-time brand. */
function requireId(value: string, field: string): string {
  if (typeof value !== 'string' || value.length === 0 || value.trim().length === 0 || value !== value.trim()) {
    throw new ProjectContractsError(
      `${field} must be a non-empty trimmed string`,
      'CONTRACTS_INVALID_ID',
    )
  }
  return value
}
