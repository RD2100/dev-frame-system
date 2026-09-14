/**
 * The expert runtime: turns one phase definition into a derived subagent and
 * drives it to a validated artifact. The derivation seam is the core agent
 * registry's scoped-create face (`ctx.agents.create({ sessionId, meta, agentOptions, setup })`)
 * — the same seam the Shadow conversation host composes its designated
 * session through — followed by `agent.followup()` plus `await agent.whenIdle()`
 * to drive one turn. It is deliberately NOT the agent-hierarchy dispatch
 * engine: a pipeline phase needs a persona-scoped session with a bounded tool
 * face, no worktree, and no role binding; hierarchical mode (deferred) is the
 * seam that would map gates onto dispatch instead. Deriving through the
 * registry keeps this package a plain plugin over existing loop behavior —
 * no new execution loop.
 *
 * Per phase, the runtime owns the bounded retry loop over the result
 * contract. A phase expert has no write tool by design, so the runtime
 * persists the artifact body from the expert's reply and re-drives the same
 * session on a contract failure — revisions stay in context.
 * @module @deepseek-ai/dsh-experimental-expert-team/runtime
 */

import { randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import type { Agent, AgentHandle, ModelSelection } from '@deepseek-ai/dsh-agent'
import { writeFileAtomic } from '@deepseek-ai/dsh-atomic-write'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import type { UserMessage } from '@deepseek-ai/dsh-llm'
import { SessionId, SessionSeq } from '@deepseek-ai/dsh-session'
import type { Session } from '@deepseek-ai/dsh-session'
import type { ToolExecution } from '@deepseek-ai/dsh-tools'
import {
  composeConsultMessage,
  composeGateAcceptanceMessage,
  composePhaseBriefing,
  composeRevisionMessage,
} from './briefing.ts'
import type { RevisionReason } from './briefing.ts'
import type { ExpertCatalog, LoadedTeam } from './catalog.ts'
import { ExpertTeamError } from './errors.ts'
import type { RunId } from './ids.ts'
import { parseConsultAnswer, parsePhaseResult, splitPhaseReply } from './result-protocol.ts'
import type { PhaseResult } from './result-protocol.ts'
import type { ArtifactRef, ExpertDef, PhaseDef } from './types.ts'

/** Result-contract retries after the first attempt; a bound of the phase contract, not a tunable. */
const MAX_RESULT_RETRIES = 2

/** One phase execution request, owned by the orchestrator. */
export interface PhaseExecutionRequest {
  /** The mounted team the phase belongs to. */
  readonly team: LoadedTeam
  /** The phase to execute. */
  readonly phase: PhaseDef
  /** Artifacts of the phase's declared upstream phases, in depends_on order. */
  readonly upstream: readonly ArtifactRef[]
  /** Absolute artifact paths, keyed by upstream phase id. */
  readonly upstreamPaths: ReadonlyMap<string, string>
  /** The run request's free-form input. */
  readonly input: string
  /** The owning run; names the phase session. */
  readonly runId: RunId
  /** The existing run directory the artifact is written into. */
  readonly runDir: string
  /** When the phase is re-driven (gate rejection), the human's reason. */
  readonly revision?: RevisionReason
}

/** How one phase execution ended. */
export type PhaseExecutionOutcome =
  | { readonly ok: true; readonly attempts: number; readonly result: PhaseResult }
  | { readonly ok: false; readonly attempts: number; readonly detail: string }

/**
 * Derives persona-scoped subagents and drives single phases. One instance per
 * mounted plugin; the plugin's fiber owns disposal through
 * {@link ExpertRuntime.dispose}.
 */
export class ExpertRuntime {
  /** Handles this runtime created, keyed by session id string. */
  private readonly owned = new Map<string, AgentHandle>()
  /** Pack schema text cache, keyed by `packDir|schemaPath`; pack files are static per process. */
  private readonly schemaCache = new Map<string, string>()

  constructor(
    private readonly ctx: Context,
    private readonly catalog: ExpertCatalog,
  ) {}

  /**
   * Prove every tool name of one expert's allowlist is mounted globally.
   * Called before a run starts and before a consult derives, so a pack naming
   * an unmounted tool fails loud at the earliest resolvable point instead of
   * mid-phase.
   * @param expert - The expert whose allowlist is checked.
   * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_TOOL_MISSING`
   *   naming the first unmounted tool.
   */
  requireMountedTools(expert: ExpertDef): void {
    for (const tool of expert.tools) {
      if (this.ctx.tools.get(tool) === undefined) {
        throw new ExpertTeamError(
          `expert ${expert.id} declares tool "${tool}", which this deployment does not mount`,
          'EXPERT_TEAM_TOOL_MISSING',
        )
      }
    }
  }

  /**
   * Execute one phase to a validated artifact: derive or reuse the phase
   * session, deliver the briefing (or, on a live session, the revision
   * follow-up), and retry the result contract at most {@link MAX_RESULT_RETRIES}
   * times. The artifact file is written only after the reply passed its
   * contract, so a parked failure never leaves a half-accepted artifact.
   * @param request - The phase, its run facts, and the upstream references.
   * @returns the outcome; a failure carries the last contract detail for the
   *   run state and the human gate.
   */
  async executePhase(request: PhaseExecutionRequest): Promise<PhaseExecutionOutcome> {
    const expert = this.catalog.getExpert(request.team.def.team, request.phase.expert)
    this.requireMountedTools(expert)
    const schemaText = request.phase.output.schema === undefined
      ? undefined
      : await this.loadSchemaText(request.team.packDir, request.phase.output.schema)
    const agent = await this.derivePhaseAgent(request, expert)
    if (request.revision !== undefined) {
      agent.followup(this.pluginMessage(composeRevisionMessage(request.revision)))
    }
    const maxAttempts = 1 + MAX_RESULT_RETRIES
    let attempts = 0
    for (;;) {
      attempts += 1
      await agent.whenIdle()
      const reply = lastAssistantText(agent.session)
      let body: string
      let result: PhaseResult
      try {
        const split = splitPhaseReply(reply)
        result = parsePhaseResult(split.result, request.phase, schemaText)
        body = split.body
      } catch (error: unknown) {
        const detail = error instanceof Error ? error.message : String(error)
        if (attempts < maxAttempts && error instanceof ExpertTeamError && error.code === 'EXPERT_TEAM_RESULT_INVALID') {
          agent.followup(this.pluginMessage(composeRevisionMessage({ kind: 'validation-failure', detail })))
          continue
        }
        return { ok: false, attempts, detail }
      }
      // Exactly one trailing newline: the artifact is ordinary text output,
      // and only written after the contract passed.
      await writeFileAtomic(join(request.runDir, request.phase.output.artifact), `${body}\n`, { mode: 0o600 })
      return { ok: true, attempts, result }
    }
  }

  /**
   * Consult one expert outside any run: derive a fresh single-turn session
   * with the same persona and allowlist composition as a phase, deliver the
   * question, and return the final answer text. The session is disposed
   * before returning; a consult leaves no artifacts and no run state.
   * @param team - The mounted team the expert belongs to.
   * @param expert - The expert to consult.
   * @param question - The caller's question, delivered verbatim.
   * @returns the answer text and whether it was truncated to the return bound.
   */
  async consult(team: LoadedTeam, expert: ExpertDef, question: string): Promise<{ readonly answer: string; readonly truncated: boolean }> {
    this.requireMountedTools(expert)
    const sessionId = SessionId(`expert-team-consult-${randomUUID()}`)
    const handle = await this.createExpertAgent(sessionId, team.packDir, expert)
    this.owned.set(String(sessionId), handle)
    try {
      handle.agent.followup(this.pluginMessage(composeConsultMessage(question)))
      await handle.agent.whenIdle()
      return parseConsultAnswer(lastAssistantText(handle.agent.session))
    } finally {
      this.owned.delete(String(sessionId))
      await handle.dispose()
    }
  }

  /**
   * Deliver the post-approval follow-up to a gated phase's live session: the
   * artifact was accepted by the human gate (the reviewer comment included
   * when present), so the persona's post-acceptance steps can fire in a real
   * turn. Best-effort by contract: a retired or unknown session is a no-op,
   * and the caller floats this promise so a delivery failure never fails the
   * run.
   * @param runId - The owning run; names the phase session.
   * @param phase - The gated phase whose session receives the follow-up.
   * @param comment - The reviewer comment, when the decision carried one.
   */
  async notifyGateAccepted(runId: RunId, phase: PhaseDef, comment?: string | undefined): Promise<void> {
    const sessionId = SessionId(`expert-team-${String(runId)}-${phase.id}`)
    const live = this.ctx.agents.get(sessionId)
    if (live === undefined) return
    live.followup(this.pluginMessage(composeGateAcceptanceMessage(comment)))
    await live.whenIdle()
  }

  /**
   * Dispose the phase sessions of one completed run. A run parked at a gate
   * keeps its sessions so a rejection can revise its expert in context.
   * @param runId - The run whose phase sessions are retired.
   */
  async retireRun(runId: RunId): Promise<void> {
    const prefix = `expert-team-${String(runId)}-`
    for (const [sessionId, handle] of [...this.owned]) {
      if (!sessionId.startsWith(prefix)) continue
      this.owned.delete(sessionId)
      await handle.dispose()
    }
  }

  /** Dispose every handle this runtime still owns; the plugin disposer calls this. */
  async dispose(): Promise<void> {
    const handles = [...this.owned.values()]
    this.owned.clear()
    await Promise.all(handles.map(handle => handle.dispose()))
  }

  /**
   * Reuse the live phase session or derive it. Reuse is what makes a gate
   * rejection a revision: the same session re-drives with the human's comment
   * in context. A fresh derivation always receives the full briefing, even
   * when a revision was requested (a fresh session has no context to revise).
   */
  private async derivePhaseAgent(request: PhaseExecutionRequest, expert: ExpertDef): Promise<Agent> {
    const sessionId = SessionId(`expert-team-${String(request.runId)}-${request.phase.id}`)
    const live = this.ctx.agents.get(sessionId)
    if (live !== undefined) return live
    const handle = await this.createExpertAgent(sessionId, request.team.packDir, expert, request.runDir)
    this.owned.set(String(sessionId), handle)
    handle.agent.followup(this.pluginMessage(composePhaseBriefing({
      team: request.team.def,
      phase: request.phase,
      expert,
      upstream: request.upstream,
      upstreamPaths: request.upstreamPaths,
      input: request.input,
      ...(request.phase.output.schema === undefined
        ? {}
        : { schemaText: await this.loadSchemaText(request.team.packDir, request.phase.output.schema) }),
    })))
    return handle.agent
  }

  /**
   * Create one expert agent: the scoped-create seam's setup window composes
   * the persona section, one section per declared pack skill, the expert's
   * tool allowlist as both a visibility restriction and an executor guard
   * (the decision is enforced where execution happens), and native
   * presentation — a persona-driven expert must not have its face collapsed
   * into a PTC transport. The run directory is the session's durable cwd: it
   * is where every referenced artifact lives.
   */
  private async createExpertAgent(sessionId: SessionId, packDir: string, expert: ExpertDef, cwd?: string): Promise<AgentHandle> {
    const selection = this.requireDefaultModel()
    const allow = new Set<string>(expert.tools)
    const setup = async (agentCtx: Context): Promise<void> => {
      agentCtx.systemPrompt.section({ name: 'expert-team:persona', order: 10, text: composePersonaSection(expert) })
      let skillOrder = 11
      for (const skill of expert.skills ?? []) {
        const text = await this.loadSkillText(packDir, expert.id, skill)
        agentCtx.systemPrompt.section({ name: `expert-team:skill:${skill}`, order: skillOrder, text })
        skillOrder += 1
      }
      agentCtx.tools.presentAs('native')
      agentCtx.tools.restrict({ allow: [...allow] })
      agentCtx.tools.guard((exec: Readonly<ToolExecution>): string | undefined =>
        allow.has(exec.name)
          ? undefined
          : `tool "${exec.name}" is outside expert ${expert.id}'s tool allowlist`,
      )
    }
    return await this.ctx.agents.create({
      sessionId,
      ...cwd === undefined ? {} : { meta: { cwd } },
      agentOptions: {
        provider: selection.provider,
        model: selection.model,
        ...(selection.reasoningEffort === undefined ? {} : { reasoningEffort: selection.reasoningEffort }),
      },
      setup,
    })
  }

  /** The deployment's default model selection, or a loud composition failure. */
  private requireDefaultModel(): ModelSelection {
    const defaultModel = this.ctx.get('agentDefaultModel')
    if (defaultModel === undefined) {
      throw new ExpertTeamError(
        'this deployment provides no default model selection; expert-team cannot derive expert subagents',
        'EXPERT_TEAM_MODEL_MISSING',
      )
    }
    return defaultModel.currentSelection()
  }

  /** Wrap one briefing text as a plugin-sourced user message. */
  private pluginMessage(text: string): UserMessage {
    return createUserMessage({
      content: [{ type: 'text', text }],
      source: { kind: 'plugin', plugin: 'expert-team' },
    })
  }

  /** Load and cache one pack schema file's text; pack files are static per process. */
  private async loadSchemaText(packDir: string, schemaPath: string): Promise<string> {
    const key = `${packDir}|${schemaPath}`
    const cached = this.schemaCache.get(key)
    if (cached !== undefined) return cached
    const text = await readFile(resolve(packDir, schemaPath), 'utf8')
    this.schemaCache.set(key, text)
    return text
  }

  /**
   * Load one declared pack skill's SKILL.md text. Mount-time validation
   * proved the file existed; a file that vanished since stays loud under the
   * same catalog code — the persona references the skill, and silently
   * dropping it would compose a promise the face cannot keep.
   */
  private async loadSkillText(packDir: string, expertId: string, skill: string): Promise<string> {
    const path = resolve(packDir, 'skills', skill, 'SKILL.md')
    return await readFile(path, 'utf8').catch((error: unknown) => {
      throw new ExpertTeamError(
        `expert ${expertId} declares skill ${skill}, whose SKILL.md is no longer readable in the pack`,
        'EXPERT_TEAM_SKILL_MISSING',
        { cause: error },
      )
    })
  }
}

/**
 * The persona prompt section: front-matter identity facts plus the persona
 * body verbatim. The body is the pack author's craft text and stays
 * untouched; the header carries the structured facts the body may reference.
 */
function composePersonaSection(expert: ExpertDef): string {
  return [
    `# ${expert.name}（expert id: ${expert.id}）`,
    '',
    `角色：${expert.role}`,
    `目标：${expert.goal}`,
    '',
    expert.persona.trimEnd(),
  ].join('\n')
}

/** The final assistant text of one session, scanning newest-first. */
function lastAssistantText(session: Session): string {
  for (let seq = session.seq - 1; seq >= 0; seq -= 1) {
    const event = session.eventAt(SessionSeq(seq))
    if (event === undefined || event.type !== 'assistant/message') continue
    return event.data.message.content
      .filter(block => block.type === 'text')
      .map(block => block.text)
      .join('')
  }
  return ''
}
