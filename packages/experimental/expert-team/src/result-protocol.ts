/**
 * The phase-result contract between the orchestrator and a phase expert: the
 * expert writes its artifact as the body of its final reply and closes the
 * reply with one fenced JSON result object naming the artifact and
 * summarizing the phase. This module splits such a reply, checks the result
 * object against the phase's output contract (declared artifact name, minimal
 * shape, and — when the phase declares one — the pack's JSON Schema), and
 * reports every violation as an `EXPERT_TEAM_RESULT_INVALID` failure detail.
 * Pure functions; the filesystem belongs to the runtime.
 * @module @deepseek-ai/dsh-experimental-expert-team/result-protocol
 */

import Ajv from 'ajv'
import type { AnySchema, ValidateFunction } from 'ajv'
import { ExpertTeamError } from './errors.ts'
import type { PhaseDef } from './types.ts'

/**
 * The fenced-JSON marker a phase reply must end with. Fixed: the marker is
 * part of the model-visible phase contract pinned by the runtime, not a
 * per-deployment choice.
 */
export const RESULT_FENCE_OPEN = '```json'

/** The closing fence of the result block. */
const RESULT_FENCE_CLOSE = '```'

/** Maximum UTF-8 bytes of one artifact body. */
export const MAX_ARTIFACT_BYTES = 256 * 1024
/** Maximum UTF-8 bytes of one result `summary` string. */
const MAX_SUMMARY_BYTES = 8 * 1024
/** Maximum UTF-8 bytes of one returned consult answer. */
export const MAX_CONSULT_ANSWER_BYTES = 64 * 1024

/** The minimal result-object shape every phase reply must satisfy. */
export interface PhaseResult {
  /** The declared artifact file name; the runtime writes the reply body there. */
  readonly artifactPath: string
  /** Non-empty Chinese summary of the phase outcome. */
  readonly summary: string
  /** Optional open questions the phase wants to surface to the human. */
  readonly openQuestions?: readonly string[]
}

/** A successfully split reply: the artifact body and the parsed result object. */
export interface SplitPhaseReply {
  /** Artifact body: the reply text before the result fence, trailing blanks trimmed. */
  readonly body: string
  /** The parsed result object, before contract validation. */
  readonly result: unknown
}

/**
 * Split one final phase reply into artifact body and result object. The
 * result block is the LAST `json`-fenced code block of the reply; a body that
 * itself quotes fenced JSON is therefore safe. Lines after the closing fence
 * must be blank.
 * @param reply - The full final assistant text of the phase turn.
 * @returns the body and the raw parsed result.
 * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_RESULT_INVALID` when
 *   the marker fence is missing, the block is not closed, the fenced content
 *   is not valid JSON, or non-blank content follows the block.
 */
export function splitPhaseReply(reply: string): SplitPhaseReply {
  const lines = reply.split('\n')
  let open = -1
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    if (lines[index]?.trim() === RESULT_FENCE_OPEN) {
      open = index
      break
    }
  }
  if (open === -1) {
    throw resultInvalid('the reply does not end with a ```json result block')
  }
  let close = -1
  for (let index = open + 1; index < lines.length; index += 1) {
    if (lines[index]?.trim() === RESULT_FENCE_CLOSE) {
      close = index
      break
    }
  }
  if (close === -1) {
    throw resultInvalid('the ```json result block is not closed')
  }
  const trailing = lines.slice(close + 1).find(line => line.trim().length > 0)
  if (trailing !== undefined) {
    throw resultInvalid('the reply continues after the ```json result block')
  }
  const body = lines.slice(0, open).join('\n').replace(/\n+$/, '')
  if (body.trim().length === 0) {
    throw resultInvalid('the artifact body before the result block is blank')
  }
  if (Buffer.byteLength(body, 'utf8') > MAX_ARTIFACT_BYTES) {
    throw resultInvalid(`the artifact body exceeds ${MAX_ARTIFACT_BYTES} UTF-8 bytes`)
  }
  let result: unknown
  try {
    result = JSON.parse(lines.slice(open + 1, close).join('\n'))
  } catch (error: unknown) {
    throw resultInvalid('the fenced result block is not valid JSON', { cause: error })
  }
  return { body, result }
}

/**
 * Validate one parsed result object against the phase's output contract: the
 * minimal shape every phase owes (declared artifact name, non-empty bounded
 * summary, optional open questions) plus the pack's JSON Schema when the
 * phase declares one. Schema compilation is cached per schema text.
 * @param result - The raw parsed result object.
 * @param phase - The phase whose output contract applies.
 * @param schemaText - The pack schema's JSON text when `output.schema` is
 *   declared; absent otherwise.
 * @returns the validated result.
 * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_RESULT_INVALID`
 *   naming every violated expectation.
 */
export function parsePhaseResult(result: unknown, phase: PhaseDef, schemaText: string | undefined): PhaseResult {
  if (typeof result !== 'object' || result === null || Array.isArray(result)) {
    throw resultInvalid('the phase result must be a JSON object')
  }
  const record = result as Record<string, unknown>
  const artifactPath = record.artifactPath
  if (typeof artifactPath !== 'string' || artifactPath.length === 0) {
    throw resultInvalid('the phase result must declare a non-empty artifactPath string')
  }
  if (artifactPath !== phase.output.artifact) {
    throw resultInvalid(
      `the phase result names artifact "${artifactPath}", but the phase contract declares "${phase.output.artifact}"`,
    )
  }
  const summary = record.summary
  if (typeof summary !== 'string' || summary.trim().length === 0) {
    throw resultInvalid('the phase result must carry a non-empty summary string')
  }
  if (Buffer.byteLength(summary, 'utf8') > MAX_SUMMARY_BYTES) {
    throw resultInvalid(`the result summary exceeds ${MAX_SUMMARY_BYTES} UTF-8 bytes`)
  }
  const openQuestions = record.openQuestions
  if (openQuestions !== undefined && !isStringList(openQuestions)) {
    throw resultInvalid('the result openQuestions must be an array of non-empty strings when present')
  }
  if (schemaText !== undefined) {
    assertSchema(schemaText, result, phase)
  }
  return {
    artifactPath,
    summary,
    ...(Array.isArray(openQuestions) ? { openQuestions: [...openQuestions] as string[] } : {}),
  }
}

/**
 * Validate one model-produced consult answer against the return bound.
 * @param answer - The final assistant text of the consult session.
 * @returns the answer text — truncated at a code point to the
 *   {@link MAX_CONSULT_ANSWER_BYTES} bound when it exceeds it — and whether
 *   truncation happened.
 */
export function parseConsultAnswer(answer: string): { readonly answer: string; readonly truncated: boolean } {
  if (Buffer.byteLength(answer, 'utf8') > MAX_CONSULT_ANSWER_BYTES) {
    return { answer: truncateAtCodePoint(answer, MAX_CONSULT_ANSWER_BYTES), truncated: true }
  }
  return { answer, truncated: false }
}

/** Truncate one string to at most `maxBytes` UTF-8 bytes without splitting a code point. */
function truncateAtCodePoint(value: string, maxBytes: number): string {
  let end = value.length
  while (end > 0 && Buffer.byteLength(value.slice(0, end), 'utf8') > maxBytes) {
    // Walk back over one UTF-16 code unit; surrogate halves are re-checked
    // against the byte budget, so the loop always terminates below length.
    end -= 1
  }
  return value.slice(0, end)
}

/** Every entry a non-empty single-line string. */
function isStringList(value: unknown): value is unknown[] {
  return Array.isArray(value)
    && value.every(item => typeof item === 'string' && item.trim().length > 0)
}

/** Compile cache: pack schemas are static per process, keyed by their text. */
const compiledSchemas = new Map<string, ValidateFunction>()

/**
 * Validate one result against the pack's JSON Schema (draft-07 as shipped by
 * the packs). Failures enumerate every violation so one revision round can
 * fix them all.
 */
function assertSchema(schemaText: string, result: unknown, phase: PhaseDef): void {
  let validate = compiledSchemas.get(schemaText)
  if (validate === undefined) {
    let parsed: AnySchema
    try {
      parsed = JSON.parse(schemaText) as AnySchema
    } catch (error: unknown) {
      throw resultInvalid(`the phase ${phase.id} schema file is not valid JSON`, { cause: error })
    }
    validate = new Ajv({ allErrors: true }).compile(parsed)
    compiledSchemas.set(schemaText, validate)
  }
  if (!validate(result)) {
    const violations = (validate.errors ?? []).map(error => `${error.instancePath || '/'} ${error.message ?? 'is invalid'}`)
    throw resultInvalid(`the phase result fails the declared schema: ${violations.join('; ')}`)
  }
}

/** Build the stable result-contract failure. */
function resultInvalid(detail: string, options?: ErrorOptions): ExpertTeamError {
  return new ExpertTeamError(`phase result contract violated: ${detail}`, 'EXPERT_TEAM_RESULT_INVALID', options)
}
