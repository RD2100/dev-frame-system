/**
 * The Shadow conversation host: one persistent agent session that IS the
 * deployment's designated Shadow. At startup — and again on demand, because a
 * failed or raced startup must not poison later calls — the host creates or
 * restores that session through the core agent registry, composes its scoped
 * world in the factory setup (the four conversational tools, the persona
 * section, the design tool allowlist over the session's model face, a scoped
 * honest cwd variable for cwd-less persona templates, and, on a fresh
 * session, the host default model selection), and then serves the two
 * conversation verbs: post one human message into the session (the loop
 * claims and runs it) and read the persisted conversation surface back,
 * bounded and cursor-addressed.
 *
 * Ownership: only a session this host created or resumed is disposed here; a
 * session another composition row already owns is used as found and left to
 * its owner.
 * @module @deepseek-ai/dsh-experimental-shadow-controller/shadow-agent
 */

import type { Context } from '@deepseek-ai/cordis'
import { installModelSelection } from '@deepseek-ai/dsh-agent'
import type { Agent, AgentHandle, ModelSelection } from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-agent-default-model'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import type {} from '@deepseek-ai/cordis-plugin-loader'
import type { ToolExecution } from '@deepseek-ai/dsh-tools'
import { SessionId, SessionSeq } from '@deepseek-ai/dsh-session'
import type { Session, SessionEvent } from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-session-persistence'
import { Service } from '@deepseek-ai/cordis'
import type { ShadowRouter } from '@deepseek-ai/dsh-experimental-shadow-routing'
import { installShadowConversationTools, SHADOW_CONVERSATION_TOOL_NAMES } from './shadow-tools.ts'
import { SHADOW_PROMPT, SHADOW_PROMPT_SECTION } from './shadow-prompt.ts'
import type { ShadowConversationMessage, ShadowConversationPage } from './types.ts'

/** Default bound on one conversation read. */
const DEFAULT_PAGE_LIMIT = 50
/** Hard upper bound on one conversation read. */
const MAX_PAGE_LIMIT = 200

/**
 * The user-memory tool names the design admits into the Shadow face when the
 * deployment explicitly enables memory (the project-memory plugin mounted
 * them). Fixed strings: the allowlist is a design security invariant
 * (docs/detailDesign-part2.md, Project tools), not a deployment tunable.
 */
const MEMORY_TOOL_NAMES = ['memory_search', 'memory_read', 'memory_append'] as const

/**
 * The exact execution surface of the composed designated scope: the four
 * conversational tools plus explicitly enabled memory access. Every other
 * execution on this agent is denied.
 */
const SHADOW_EXECUTION_ALLOWLIST: ReadonlySet<string> = new Set([
  ...SHADOW_CONVERSATION_TOOL_NAMES,
  ...MEMORY_TOOL_NAMES,
])

/**
 * The designated session records no cwd (the host creates it outside any
 * workspace), so the loop's `cwd` variable resolves undefined and any persona
 * template referencing it — the presets' deployment persona does — fails
 * strict interpolation before the first model call. The scoped value shadows
 * the global provider with what the Shadow honestly is.
 */
const SHADOW_CWD_VARIABLE =
  'not fixed — you are the Shadow: you route work across authorized projects and never do project work yourself'

declare module '@deepseek-ai/cordis' {
  interface Context {
    /** Persistent Shadow conversation host over the designated session. */
    shadowAgent: ShadowAgent
  }
}

/**
 * Monotonic executor gate for the designated scope. `restrict()` filters only
 * what a scope inherits — the registry exempts a scope's OWN registrations so
 * a delegated child keeps the tools it answers through — and the shadow router
 * registers its `project_*` whitelist into this same layer, so visibility
 * cannot finish the convergence. A guard can: a returned reason denies, and
 * no listener can re-allow.
 * @param exec - the pending execution.
 * @returns a denial reason when the name is outside the allowlist, else `undefined`.
 */
function shadowAllowlistGuard(exec: Readonly<ToolExecution>): string | undefined {
  return SHADOW_EXECUTION_ALLOWLIST.has(exec.name)
    ? undefined
    : `tool "${exec.name}" is outside this session's allowlist`
}

/**
 * The memory tools the deployment actually mounted, as the restrict allow
 * list. `restrict()` fails loud naming an unknown global tool, so presence is
 * probed against the global layer at setup time; an empty result is legal and
 * hides the whole inherited face.
 * @param agentCtx - The Shadow agent's scoped creation context.
 * @returns the globally registered memory tool names.
 */
function enabledMemoryTools(agentCtx: Context): string[] {
  return MEMORY_TOOL_NAMES.filter(name => agentCtx.tools.get(name) !== undefined)
}

/**
 * Compose one Shadow agent's scoped world inside the factory setup: the four
 * conversational tools, the persona section, the design tool allowlist over
 * the session's model face, the scoped honest cwd variable, and, on a fresh
 * session, the host default model selection.
 */
function shadowSetup(router: ShadowRouter, selection: ModelSelection, fresh: boolean) {
  return (agentCtx: Context): void => {
    installShadowConversationTools(agentCtx, router)
    agentCtx.systemPrompt.section({ name: SHADOW_PROMPT_SECTION, order: 10, text: SHADOW_PROMPT })
    // The design allowlist is the composed session's whole tool face. Every
    // registration here is effect-scoped to this agent scope and unwinds
    // with it: native presentation pinned (a PTC deployment must not collapse
    // the face or hand the Shadow arbitrary program execution), inherited
    // tools hidden except explicitly enabled memory access, and execution
    // denied for anything else the scope ends up carrying.
    agentCtx.tools.presentAs('native')
    agentCtx.tools.restrict({ allow: enabledMemoryTools(agentCtx) })
    agentCtx.tools.guard(shadowAllowlistGuard)
    agentCtx.systemPrompt.variable('cwd', () => SHADOW_CWD_VARIABLE)
    if (fresh) installModelSelection(agentCtx, { current: selection, assembled: undefined })
  }
}

/** One conversation row per user or non-empty assistant message event. */
function messageRow(event: SessionEvent): Omit<ShadowConversationMessage, 'seq'> | undefined {
  if (event.type !== 'user/message' && event.type !== 'assistant/message') return undefined
  const content = event.type === 'user/message' ? event.data.content : event.data.message.content
  const text = content
    .filter(block => block.type === 'text')
    .map(block => block.text)
    .join('')
  if (text === '') return undefined
  return {
    role: event.type === 'user/message' ? 'user' : 'shadow',
    text,
    at: new Date(event.time).toISOString(),
  }
}

/**
 * Host service behind the controller's conversation verbs. Registered as
 * `ctx.shadowAgent`; every verb resolves the designated session on demand.
 */
export class ShadowAgent extends Service {
  static inject = ['agents']

  private ensurePromise: Promise<Agent> | undefined
  /** The handle this host created or resumed; a found-live agent is never owned here. */
  private owned: AgentHandle | undefined

  /**
   * Register the service; kick off the startup create-or-restore best
   * effort and own the created lifecycle for teardown.
   * @param ctx - Host context carrying the agents registry and the optional
   *   router, loader, default model, and persistence services.
   */
  constructor(ctx: Context) {
    super(ctx, 'shadowAgent')
    ctx.effect(() => () => this.owned?.dispose(), 'shadowAgent.lifecycle()')
    ctx.effect(() => {
      void this.ensure().catch((error: unknown) => {
        // Startup stays best effort: an unconfigured or half-mounted tree is
        // the fail-closed state, and every verb retries ensure() on demand.
        this.ctx.logger.warn(`the Shadow conversation did not start: ${error instanceof Error ? error.message : String(error)}`)
      })
      return () => undefined
    }, 'shadowAgent.startup()')
  }

  /**
   * Resolve the live Shadow agent, creating or restoring the designated
   * session on first use. Memoized; a failure is not memoized, so the next
   * verb retries.
   * @returns the live Shadow agent.
   */
  async ensure(): Promise<Agent> {
    this.ensurePromise ??= this.ensureOnce().catch((error: unknown) => {
      this.ensurePromise = undefined
      throw error
    })
    return await this.ensurePromise
  }

  /**
   * Post one human message into the Shadow session. The agent loop claims it
   * and runs the turn; the reply lands on the persisted conversation surface,
   * observable through {@link readConversation}.
   * @param text - Non-empty message text from the human.
   * @returns the accepted message's stable id.
   */
  async postMessage(text: string): Promise<{ readonly messageId: string }> {
    if (typeof text !== 'string' || text.trim().length === 0) {
      throw new Error('message text must be a non-empty string')
    }
    const agent = await this.ensure()
    const message = createUserMessage({
      content: [{ type: 'text', text }],
      source: { kind: 'user' },
    })
    agent.followup(message)
    return { messageId: message.id }
  }

  /**
   * Read the Shadow conversation surface, bounded and cursor-addressed.
   * Without `after`, the last up-to-`limit` rows; with `after`, the rows
   * beyond that sequence number. `cursor` is the log length at read time, or
   * the last returned row when the page truncated — poll by passing it back.
   * @param request - Optional cursor and page bound.
   * @returns the page of rows plus the continuation cursor.
   */
  async readConversation(request: { readonly after?: number; readonly limit?: number }): Promise<ShadowConversationPage> {
    const limit = request.limit ?? DEFAULT_PAGE_LIMIT
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_PAGE_LIMIT) {
      throw new Error(`limit must be an integer from 1 through ${String(MAX_PAGE_LIMIT)}`)
    }
    const agent = await this.ensure()
    const session = agent.session
    const length = session.seq
    if (request.after === undefined) {
      return { messages: this.tail(session, length, limit), cursor: length }
    }
    const after = request.after
    if (!Number.isSafeInteger(after) || after < 0 || after > length) {
      throw new Error(`after must be an integer from 0 through the session length ${String(length)}`)
    }
    const rows: ShadowConversationMessage[] = []
    // `after` is exclusive: the client passes the previous page's cursor back.
    for (let seq = after + 1; seq < length && rows.length < limit; seq++) {
      const event = session.eventAt(SessionSeq(seq))
      if (event === undefined) continue
      const row = messageRow(event)
      if (row === undefined) continue
      rows.push({ seq, ...row })
    }
    // A full page stops at its last row; the client resumes from there.
    const last = rows[rows.length - 1]
    return { messages: rows, cursor: rows.length < limit ? length : last === undefined ? length : last.seq }
  }

  /** The last up-to-`limit` conversation rows, oldest first. */
  private tail(session: Session, length: number, limit: number): ShadowConversationMessage[] {
    const rows: ShadowConversationMessage[] = []
    for (let seq = length - 1; seq >= 0 && rows.length < limit; seq--) {
      const event = session.eventAt(SessionSeq(seq))
      if (event === undefined) continue
      const row = messageRow(event)
      if (row === undefined) continue
      rows.push({ seq, ...row })
    }
    return rows.reverse()
  }

  /** The designation and router, or a loud honest failure. */
  private requireRouter(): { router: ShadowRouter; designation: string } {
    const router = this.ctx.get('shadowRouter')
    const designation = router?.readStatus().shadowSessionId
    if (router === undefined || designation === undefined) {
      throw new Error('this deployment declares no Shadow session; the conversation host stays unavailable')
    }
    return { router, designation }
  }

  /** Create or restore the designated session, or fail with the reason. */
  private async ensureOnce(): Promise<Agent> {
    // The startup call races sibling plugin mounts: settle the complete
    // application first so the router check sees the final composition — a
    // mounted router proceeds, and a deployment that declares no Shadow
    // session still fails with the same honest error.
    await this.ctx.get('loader')?.await()
    const { router, designation } = this.requireRouter()
    const id = SessionId(designation)
    // A composition row may already own the designated session; use it as
    // found and leave its lifecycle with its owner.
    const live = this.ctx.agents.get(id)
    if (live !== undefined) return live
    const defaultModel = this.ctx.get('agentDefaultModel')
    if (defaultModel === undefined) {
      throw new Error('the host composition provides no default model; the Shadow conversation stays unavailable')
    }
    const selection = defaultModel.currentSelection()
    const agentOptions = {
      provider: selection.provider,
      model: selection.model,
      ...(selection.reasoningEffort === undefined ? {} : { reasoningEffort: selection.reasoningEffort }),
    }
    const persistence = this.ctx.get('sessionPersistence')
    if (persistence !== undefined) {
      try {
        const handle = await this.ctx.agents.resume({
          resumeSessionId: id,
          agentOptions,
          setup: shadowSetup(router, selection, false),
        })
        this.owned = handle
        return handle.agent
      } catch (error: unknown) {
        // Only a genuinely absent artifact falls back to first creation;
        // corruption and backend failures stay loud.
        const exists = (await persistence.list()).some(header => header.id === id)
        if (exists) throw error
      }
    }
    const handle = await this.ctx.agents.create({
      sessionId: id,
      agentOptions,
      setup: shadowSetup(router, selection, true),
    })
    this.owned = handle
    return handle.agent
  }
}

export default ShadowAgent
