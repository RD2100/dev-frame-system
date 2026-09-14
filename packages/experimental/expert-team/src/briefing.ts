/**
 * Model-facing phase briefings and follow-ups, composed from pack data. All
 * static wording here is part of the pinned model-visible phase contract: the
 * persona carries the craft, the briefing carries the run facts, the upstream
 * artifact references, the handoff checks, and the output contract — including
 * the fenced-JSON result protocol the orchestrator's parser enforces.
 * @module @deepseek-ai/dsh-experimental-expert-team/briefing
 */

import { RESULT_FENCE_OPEN } from './result-protocol.ts'
import type { ArtifactRef, ExpertDef, PhaseDef, TeamDef } from './types.ts'

/** Inputs of one phase briefing. */
export interface PhaseBriefingInput {
  /** The team the phase belongs to (title used in the header). */
  readonly team: TeamDef
  /** The phase to execute. */
  readonly phase: PhaseDef
  /** The expert that owns the phase. */
  readonly expert: ExpertDef
  /** Artifacts of the phase's declared upstream phases, in depends_on order. */
  readonly upstream: readonly ArtifactRef[]
  /** Absolute paths of the upstream artifacts, keyed by phase id. */
  readonly upstreamPaths: ReadonlyMap<string, string>
  /** The run request's free-form input (for example, the research topic). */
  readonly input: string
  /** The pack schema's JSON text when the phase declares one; absent otherwise. */
  readonly schemaText?: string
}

/**
 * Compose the initial briefing for one phase execution.
 * @param request - The run facts and the output contract inputs.
 * @returns the briefing text delivered as the phase subagent's first user
 *   message.
 */
export function composePhaseBriefing(request: PhaseBriefingInput): string {
  const { team, phase, expert } = request
  const sections: string[] = []
  sections.push([
    `# 阶段任务：${phase.id}（团队「${team.title}」）`,
    '',
    '运行请求：',
    '',
    request.input,
  ].join('\n'))
  if (phase.input !== undefined) {
    sections.push(['## 阶段输入', '', phase.input].join('\n'))
  }
  if (request.upstream.length > 0) {
    const lines = request.upstream.map(ref => {
      const path = request.upstreamPaths.get(ref.phaseId)
      return `- ${ref.phaseId} 的产物 ${ref.artifact}：${path ?? '(路径缺失)' }`
    })
    sections.push(['## 上游产物', '', '用读取类工具阅读以下上游产物后再开始工作：', '', ...lines].join('\n'))
  }
  if (expert.handoffChecks !== undefined && expert.handoffChecks.length > 0) {
    const checks = expert.handoffChecks.map((check, index) => `${index + 1}. ${check}`)
    sections.push(['## handoff 核查清单', '', '开始产出前逐项核查，未通过就停在阶段开始并说明原因：', '', ...checks].join('\n'))
  }
  sections.push(composeOutputContract(phase, request.schemaText))
  return sections.join('\n\n')
}

/**
 * Compose the output-contract section: where the artifact lands, the fenced
 * JSON result protocol, and the schema text when the phase declares one. The
 * wording is pinned — the orchestrator parses exactly this protocol.
 */
function composeOutputContract(phase: PhaseDef, schemaText: string | undefined): string {
  const schemaSection = schemaText === undefined
    ? []
    : ['', '本阶段的结果对象必须同时通过以下 JSON Schema 校验（schema 全文）：', '', '```json', schemaText, '```']
  return [
    '## 输出契约',
    '',
    `把本阶段产物写成 Markdown 回复正文；运行器会把正文写入运行目录下的 ${phase.output.artifact}（你没有写文件的工具，不要尝试写盘）。`,
    '',
    `在回复的最末尾，用一个 ${RESULT_FENCE_OPEN} 围栏代码块给出阶段结果对象，围栏块之后不要再输出任何内容。结果对象字段：`,
    '',
    `- artifactPath：必须是 "${phase.output.artifact}"。`,
    '- summary：本阶段结果的中文摘要（必填，非空）。',
    '- openQuestions：可选，字符串数组，列出未解决或需要人类判断的问题。',
    ...schemaSection,
  ].join('\n')
}

/**
 * Compose the follow-up message for one revision round: a human gate
 * rejection with its comment, or a schema-validation failure with its
 * violations. Delivered to the SAME phase subagent session, so the expert
 * revises in context.
 * @param reason - Why the phase is being re-driven.
 * @returns the follow-up user message text.
 */
export function composeRevisionMessage(reason: GateRejection | ValidationFailure): string {
  if (reason.kind === 'gate-rejection') {
    const comment = reason.comment === undefined || reason.comment.trim().length === 0
      ? '人类关口驳回了当前产物，没有附批注。请对照 handoff 核查清单重新检查并修订。'
      : `人类关口驳回了当前产物，批注如下：\n\n${reason.comment}`
    return [
      comment,
      '',
      '请按批注修订：重新给出完整的产物正文，并在回复最末尾按输出契约给出新的 ```json 阶段结果对象。',
    ].join('\n')
  }
  return [
    `上一轮回复的阶段结果未通过校验，原因：${reason.detail}`,
    '',
    '请重新给出完整的产物正文，并在回复最末尾按输出契约给出新的 ```json 阶段结果对象，修复上述全部问题。',
  ].join('\n')
}

/** A human gate sent the artifact back with an optional comment. */
export type GateRejection = { readonly kind: 'gate-rejection'; readonly comment?: string }

/** The previous reply failed the result contract; `detail` names every violation. */
export type ValidationFailure = { readonly kind: 'validation-failure'; readonly detail: string }

/** Why one phase is being re-driven. */
export type RevisionReason = GateRejection | ValidationFailure

/**
 * Compose the post-approval follow-up for one gated phase: the artifact was
 * accepted by the human gate. Delivered to the SAME phase session once the
 * approval took effect, so the persona's post-acceptance steps (for example
 * a memory note) can fire in a real turn. No new phase result is owed.
 * @param comment - The reviewer comment, when the decision carried one.
 * @returns the follow-up user message text.
 */
export function composeGateAcceptanceMessage(comment?: string): string {
  const accepted = '人类关口已通过当前产物，本阶段结束，无需再给出阶段结果对象。'
  if (comment === undefined || comment.trim().length === 0) {
    return accepted
  }
  return [accepted, '', '评审批注如下：', '', comment].join('\n')
}

/**
 * Compose the consult question for one single-expert consultation. The expert
 * persona is already composed into the consult session's prompt; the message
 * carries only the question.
 * @param question - The caller's question text, verbatim.
 * @returns the consult user message text.
 */
export function composeConsultMessage(question: string): string {
  return [
    '以下是一次单专家咨询（不属于任何流水线运行，不需要产出阶段产物或结果对象）。直接回答问题本身：',
    '',
    question,
  ].join('\n')
}
