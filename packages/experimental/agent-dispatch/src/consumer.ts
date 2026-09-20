/**
 * The model-facing dispatch entry: the `agent_dispatch` tool over
 * `ctx.agentDispatch` — the daily delegation face — plus the formal host
 * bootstrap service (`ctx.projectRun`) the host drives before the chain
 * runs. The task lifecycle's delivery/review/integration moves are owned
 * downstream (project_task, the delivery tools, and the integration path);
 * this module registers only the dispatch tool and mounts both services.
 * Results ride the ordinary tool call/result session events, so no new
 * session event is owed.
 * @module @deepseek-ai/dsh-experimental-agent-dispatch/consumer
 */

import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { ToolCallView } from '@deepseek-ai/dsh-tools'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { Agent, AgentOptions } from '@deepseek-ai/dsh-agent'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { apply as requestBudgetApply } from '@deepseek-ai/dsh-experimental-project-controller/request-budget-consumer'
import type {} from '@deepseek-ai/dsh-deepseek-llm-api-extensions'
import { createHostGoalBinding, resolveCommandGoalBindingConfig, START_GOAL_RUNNING_TEXT } from '@deepseek-ai/dsh-experimental-command-goal-binding'
import type { CommandGoalBindingConfig, GoalBindingComposition } from '@deepseek-ai/dsh-experimental-command-goal-binding'
import type { RequiredChecksConfigStore } from '@deepseek-ai/dsh-experimental-devframe'
import { AgentDispatch } from './service.ts'
import { AgentProjectRun } from './run.ts'
import { requireNonEmpty, resolveCaller } from './authorization.ts'

/** Cordis plugin name. */
export const name = 'agent-dispatch'

/** Plugin config. The formal bootstrap is explicit opt-in, so dispatch-only deployments load unchanged. */
export const Config: z<{
  bootstrap?: boolean
  checksLedgerPath?: string
  candidateScenarioPath?: string
  candidateRootSessionId?: string
}> = z.object({
  bootstrap: z.boolean(),
  checksLedgerPath: z.string(),
  candidateScenarioPath: z.string(),
  candidateRootSessionId: z.string(),
})

/** Services required by the plugin; the hierarchy stack missing fails the load. */
export const inject = [
  'tools',
  'systemPrompt',
  'workspaceRegistry',
  'worktreeRegistry',
  'agentHierarchy',
  'agentBindings',
  'agents',
  'sessions',
] as const

const DISPATCH_DESCRIPTION = 'Dispatch a child agent for one task onto one registered git worktree: the controller dispatches a lead, and a lead dispatches workers inside its approved plugin scopes. Name the task id, the plugin scope, and the worktree id (get worktree ids from worktree_create or the host), and pass a briefing prompt for a fresh dispatch — the briefing is queued only after the child is published. Every result carries ack: what the child\'s own durable log proves about the task (briefed while pending, claimed while executing, terminal with the turn\'s recorded ending — completed means the task finished cleanly, dropped when the briefing was cancelled unrun). If this task already has a dispatched child, the tool refuses and names it: pass retry: true to reuse that child instead, which never re-delivers the briefing and reports the task\'s current ack, or pass followup: true with a new prompt to continue that child with explicit instructions. The engine owns the child\'s lifecycle and the hierarchy owns every denial; refusals name the cause and the fix.'

const GUIDANCE = 'The agent dispatch tool is the daily delegation entry over the agent hierarchy. The controller dispatches a lead per task onto its own registered worktree; the lead dispatches workers inside the plugin scopes approved for it in the deployment\'s leadPluginScopes. Every dispatch binds the worktree\'s single-writer lock to the new child for its whole life. A retried task reuses the existing child (retry: true) — never re-brief a running child.'

/** The tool names this plugin registers, in registration order. */
export const TOOL_NAMES = ['agent_dispatch'] as const

/**
 * Resolve the approved parent route a dispatched child inherits: the latest
 * request header owns provider, model, and reasoning effort after
 * request-time selection; creation options are the fallback before the
 * first request and retain the configured output-token limit. Only the
 * route fields pass — the child never receives the parent's whole option
 * bag — and the standard persona's required {{model}} variable resolves
 * from them.
 * @param parent - the delegating parent agent.
 * @returns the detached route options for the child's creation.
 */
function parentRouteForDelegation(parent: Agent): AgentOptions {
  const requestConfig = parent.session.requestHeader()?.config
  if (requestConfig === undefined) {
    return {
      ...(parent.options.provider !== undefined ? { provider: parent.options.provider } : {}),
      ...(parent.options.model !== undefined ? { model: parent.options.model } : {}),
      ...(parent.options.reasoningEffort !== undefined ? { reasoningEffort: parent.options.reasoningEffort } : {}),
      ...(parent.options.maxTokens !== undefined ? { maxTokens: parent.options.maxTokens } : {}),
    }
  }
  return {
    provider: requestConfig.provider,
    model: requestConfig.model,
    ...(requestConfig.reasoningEffort === undefined ? {} : { reasoningEffort: requestConfig.reasoningEffort }),
    ...(parent.options.maxTokens !== undefined ? { maxTokens: parent.options.maxTokens } : {}),
  }
}

/** The plain pending-state card, titled from the call's arguments. */
function callCard(title: string, rawInput?: string): ToolCallView {
  return { card: 'generic', title, ...rawInput !== undefined ? { rawInput } : {} }
}

/** The services the candidate Goal-binding composition fiber requires, in mount order. */
const GOAL_BINDING_INJECT = [
  'commands',
  'goals',
  'sessions',
  'sessionProjections',
  'agents',
  'subagents',
  'terminalOwnership',
  'projectController',
  'agentBindings',
  'workspaceRegistry',
  'worktreeRegistry',
] as const

/**
 * The bounded wait for the composition fiber to activate. A configured
 * deployment activates within its load turn; only a missing dependency
 * keeps the fiber PENDING to the bound.
 */
const GOAL_BINDING_MOUNT_TIMEOUT_MS = 10_000

/**
 * Mount the one Goal-binding composition for the candidate host on a
 * dedicated child fiber carrying exactly the configured workspace facts, and
 * resolve with the live composition once the fiber activates. The default
 * launch-directory row stays disabled in the candidate overlay, so this is
 * the composition instance the whole process shares.
 *
 * The declared injections order the fiber's activation after
 * `terminalOwnership`, so the mounted stop tree is complete. A missing
 * service would otherwise leave the fiber PENDING forever with no rejection
 * path, so the mount is bounded: past the timeout the stuck fiber is
 * disposed (a late provider must not double-mount behind this failure) and
 * the service store is probed with `ctx.get` to name the missing services
 * in the thrown error.
 * @param ctx - The plugin fiber's context the composition fiber mounts on.
 * @param config - The runtime-resolved workspace configuration.
 * @param requiredChecks - The candidate host's shared approved-checks store.
 * @returns The mounted composition.
 */
function mountGoalComposition(
  ctx: Context,
  config: CommandGoalBindingConfig,
  requiredChecks: RequiredChecksConfigStore,
): Promise<GoalBindingComposition> {
  return new Promise((resolve, reject) => {
    const fiber = ctx.plugin({
      id: 'candidate-goal-binding',
      inject: [...GOAL_BINDING_INJECT],
      apply: (goalCtx: Context) => {
        try {
          clearTimeout(timer)
          resolve(createHostGoalBinding(goalCtx, resolveCommandGoalBindingConfig(config), requiredChecks))
        } catch (error) {
          clearTimeout(timer)
          reject(error instanceof Error ? error : new Error(String(error)))
        }
      },
    })
    const timer = setTimeout(() => {
      void fiber.dispose()
      const missing = GOAL_BINDING_INJECT.filter(name => ctx.get(name) === undefined)
      reject(new Error(
        `candidate-goal-binding did not activate within ${GOAL_BINDING_MOUNT_TIMEOUT_MS}ms; `
        + `missing or inactive required services: ${missing.join(', ') || 'none reported (the fiber never activated)'}`))
    }, GOAL_BINDING_MOUNT_TIMEOUT_MS)
  })
}

/** The ack shape the tool result carries: the derived state plus the flush verdict. */
interface DispatchAckValue {
  readonly state: string
  readonly durable: boolean
  readonly degraded?: boolean
  readonly completed?: boolean
  readonly reasonKind?: string
  readonly turn?: number
}

/**
 * Render one dispatch, reuse, or followup outcome, with the
 * durable-acknowledgment state the child's log proves. Reuse never
 * re-briefs; its text tells the model exactly where the task stands so
 * the next decision (wait, recover, or a new task) is grounded.
 */
function renderDispatchText(value: {
  childId: string
  role: string
  taskId: string
  worktreeId: string
  reused: boolean
  followup: boolean
  ack: DispatchAckValue
}): string {
  const head = !value.reused
    ? `Dispatched ${value.role} child ${value.childId} for task '${value.taskId}' on worktree ${value.worktreeId}, bound as the worktree's single writer`
    : value.followup
      ? `Followup delivered to ${value.role} child ${value.childId} for task '${value.taskId}' on worktree ${value.worktreeId}`
      : `Reusing ${value.role} child ${value.childId} for task '${value.taskId}' on worktree ${value.worktreeId}`
  const durability = value.ack.durable ? '' : value.ack.degraded === true
    ? ' The durability backend failed this check (degraded).'
    : ' No durability backend participated in the check.'
  const tail = value.followup
    ? '; the new instructions are queued on the child\'s inbox.'
    : !value.reused
      ? '.'
      : value.ack.state === 'terminal' && value.ack.completed === true
        ? '; the task\'s terminal state is durable (completed).'
        : value.ack.state === 'terminal'
          ? `; the claiming turn ended without completing (reason: ${value.ack.reasonKind ?? 'unknown'}, turn ${String(value.ack.turn ?? '?')}); recover the child or dispatch a new task.`
          : value.ack.state === 'claimed'
            ? '; the child is executing the briefing, its terminal state is not recorded yet.'
            : value.ack.state === 'dropped'
              ? '; the briefing was cancelled unrun, dispatch a new task.'
              : value.ack.state === 'unbriefed'
                ? '; no briefing for this task is recorded in the recovered session.'
                : value.ack.state === 'unavailable'
                  ? '; the child is not live in this process, recover it through the recovery lane.'
                  : '; the earlier briefing stands, none re-queued.'
  return head + tail + durability
}

/**
 * Mount the model-facing dispatch seam: the formal host bootstrap service on
 * the plugin's fiber, then the dispatch tool and its usage guidance.
 * Loading without the hierarchy stack fails at activation; the formal host
 * bootstrap additionally requires the project controller when opted in.
 * @param ctx - The plugin's context.
 * @param config - The schema-validated plugin config.
 * @returns Resolves once the opted-in host and cold candidate commands are mounted.
 */
export async function apply(ctx: Context, config?: {
  bootstrap?: boolean
  checksLedgerPath?: string
  candidateScenarioPath?: string
  candidateRootSessionId?: string
}): Promise<void> {
  // The candidate host process is the single project scope: when the root
  // session id is pinned, the request budget mounts on this same scope, so
  // every model stream in the process charges this hierarchy's budget and
  // no other scope exists to mis-reject.
  if (config?.candidateRootSessionId !== undefined) {
    const budgetConfig = { controllerSessionId: config.candidateRootSessionId }
    // Await the child fiber so the Loader cannot report this host active before
    // the admission listener has joined the model-stream waterfall.
    await ctx.plugin({
      id: 'candidate-request-budget',
      inject: ['llm', 'agents', 'agentBindings', 'projectController'] as const,
      apply: (budgetCtx) => { requestBudgetApply(budgetCtx, budgetConfig) },
    })
  }
  // Constructing AgentDispatch mounts ctx.agentDispatch on this plugin
  // fiber, so the seam lives and dies with the plugin (HMR-safe by
  // construction). The formal host bootstrap is opt-in: deployments that
  // set `bootstrap` must mount the project controller, and the mount fails
  // loud when its authorities are missing.
  new AgentDispatch(ctx)
  if (config?.bootstrap === true) {
    const runConfig: { checksLedgerPath?: string; candidateScenarioPath?: string } = {}
    if (config.checksLedgerPath !== undefined) runConfig.checksLedgerPath = config.checksLedgerPath
    if (config.candidateScenarioPath !== undefined) runConfig.candidateScenarioPath = config.candidateScenarioPath
    // The controller stack is a dependency of the opt-in bootstrap face only:
    // the sub-fiber `ctx.inject` establishes the injection context (a bare
    // `new Service` only provides, it does not resolve static inject), and
    // the service and tool die with it when the controller is unmounted.
    // The default dispatch-only face carries zero controller dependency.
    await ctx.inject(config.candidateRootSessionId === undefined ? ['projectController'] : ['projectController', 'goals'], async (bootstrapCtx) => {
      const run = new AgentProjectRun(bootstrapCtx, runConfig)
      if (runConfig.candidateScenarioPath !== undefined) {
        bootstrapCtx.tools.register(defineTool({
          name: 'project_host_start',
          description: 'Host bootstrap for the formal candidate chain: adopt the host-prepared worktrees, bind the calling session as the project controller, take the writer locks, open board admission, and verify the approved check digests against the shared ledger. Every capability input comes from the host-owned scenario file; this tool takes no arguments and must run before any task tool. Re-runnable after a restart to re-acquire the locks and confirm the persisted identity.',
          parameters: {},
          output: {
            schema: { type: 'object', additionalProperties: false, properties: {
              workspaceId: { type: 'string', required: true },
              controllerSessionId: { type: 'string', required: true },
              lifecycle: { type: 'string', required: true },
              tasks: { type: 'array', required: true, items: { type: 'object', additionalProperties: false, properties: {
                taskId: { type: 'string', required: true }, worktreeId: { type: 'string', required: true }, digest: { type: 'string', required: true }, coldLockHolder: { type: 'string' },
              } } },
              leadWorktreeId: { type: 'string' },
            } },
            render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
          },
          isConcurrencySafe: () => false,
          async execute(_args, exec) {
            if (exec.agent === undefined) {
              throw new Error('project_host_start requires a calling agent (exec.agent was undefined)')
            }
            return await run.hostStart(exec.agent.id)
          },
          presentCall: () => ({ card: 'generic', title: 'Host bootstrap start' }),
          presentResult: () => ({ card: 'generic' }),
        }))
      }
      // The fixed root's first pre-step completes the whole bootstrap face —
      // hostStart, the formal Goal binding through the public startBoundGoal
      // entry, and admission — before next() releases the first model stream,
      // so the budget's first charged request already sees the bound root and
      // the open admission. The chain never depends on a model tool call to
      // reach this state.
      if (config.candidateRootSessionId !== undefined) {
        const rootId = config.candidateRootSessionId
        let bootstrapped = false
        // The mounted composition survives a failed start/resume: the fiber
        // carries the one process-shared composition, and mounting it again
        // would register its commands and listeners a second time.
        let composition: GoalBindingComposition | undefined
        const mount = async (workspaceId: string, targetPath: string) => {
          return await mountGoalComposition(ctx, {
            workspaceId,
            workspaceRoot: targetPath,
            // The one ledger: the same absolute file the bootstrap's
            // approvals write, required explicitly by the formal config.
            requiredChecksPath: run.requiredChecksLedgerPath,
            // The start gate checks the clean target tree; the workers' own
            // artifact probes and the final acceptance list stay separate.
            checks: { version: 1, checks: [{
              checkId: 'git-diff-check', executable: 'git', arguments: ['diff', '--quiet', 'HEAD'], cwd: targetPath,
            }] },
            taskIds: run.candidateTaskIds ?? [],
            maxAttempts: 4,
            stopChain: true,
          }, run.sharedChecksStore())
        }
        if (bootstrapCtx.workspaceRegistry.list().length > 0) {
          const scenario = await run.loadCandidateScenario()
          const existingWorkspace = bootstrapCtx.workspaceRegistry.list().find(row => row.path === scenario.anchorPath)
          if (existingWorkspace !== undefined) {
            if (scenario.targetWorktreePath === undefined) throw new Error('candidate bootstrap requires a target worktree in the scenario')
            composition = await mount(existingWorkspace.id, scenario.targetWorktreePath)
          }
        }
        let bootstrap: Promise<void> | undefined
        bootstrapCtx.on('agent/pre-step', async (_data, next) => {
          if (bootstrapped) return next()
          const agent = bootstrapCtx.agents.currentInitiator()
          if (agent === undefined || String(agent.session.id) !== rootId) return next()
          if (composition !== undefined) {
            const currentGoal = bootstrapCtx.goals.get(agent)
            const restored = (await composition.bindingStore.load(ControllerSessionId(agent.id)))
              .find(binding => binding.goalId === currentGoal?.id)
            if (restored?.lifecycle === 'admission_open' && restored.goalRevision === currentGoal?.revision) {
              bootstrapped = true
              return next()
            }
          }
          if (bootstrap === undefined) {
            bootstrap = (async () => {
              const receipt = await run.hostStart(agent.id)
              const targetPath = run.candidateTargetWorktreePath
              if (targetPath === undefined) {
                throw new Error('candidate bootstrap requires a target worktree in the scenario')
              }
              composition ??= await mount(receipt.workspaceId, targetPath)
              const result = await composition.startBoundGoal({ agent, rawInput: 'Run the candidate fullchain: both workers deliver their own artifacts through the lead.' })
              if (result.kind !== 'success') {
                // A restart re-enters this pre-step while the goal is still
                // current, so the fold refuses a second start. The public
                // resume lane is the honest recovery: it aligns the binding
                // store with the log projection, refuses a pending stop,
                // resumes the same goal, and lands the revision-advanced
                // binding. Any other start refusal — and any resume refusal —
                // fails the bootstrap loudly; nothing is swallowed.
                if (result.text !== START_GOAL_RUNNING_TEXT) {
                  throw new Error(`devframe-start refused: ${result.text}`)
                }
                const resumed = await composition.resumeBoundGoal({ agent, rawInput: '' })
                if (resumed.kind !== 'success') {
                  throw new Error(`devframe-resume refused: ${resumed.text}`)
                }
              }
              // The marker flips only after the whole face succeeded, so a
              // failed bootstrap is retried by the next pre-step instead of
              // being bypassed.
              bootstrapped = true
            })()
          }
          try {
            await bootstrap
          } finally {
            bootstrap = undefined
          }
          return next()
        })
      }
    })
  }

  ctx.systemPrompt.section({
    name: 'tool:agent-dispatch',
    // Older official runtimes predate the TOOL_AGENT_DISPATCH placement; keep
    // the repository's 2850 slot when the host cannot name it.
    order: Number.isFinite(ctx.systemPrompt.getSectionOrder('TOOL_AGENT_DISPATCH'))
      ? ctx.systemPrompt.getSectionOrder('TOOL_AGENT_DISPATCH')
      : 2850,
    text: GUIDANCE,
  })

  ctx.tools.register(defineTool({
    name: 'agent_dispatch',
    description: DISPATCH_DESCRIPTION,
    parameters: {
      role: {
        type: 'string',
        required: true,
        description: "The child's hierarchy role: 'lead' from the controller, or 'worker' from a lead.",
      },
      taskId: {
        type: 'string',
        required: true,
        description: 'The task this child owns; one task has at most one dispatched child.',
      },
      pluginId: {
        type: 'string',
        required: true,
        description: "The plugin scope the child works under; a lead's worker scope must be in that lead's approved set.",
      },
      worktreeId: {
        type: 'string',
        required: true,
        description: 'The registered worktree id the child will own as its single writer, from worktree_create or the host.',
      },
      prompt: {
        type: 'string',
        description: 'The task briefing queued to a freshly dispatched child after publication. Never re-sent on a retry; with followup: true it is the continuation instructions for the existing child instead.',
      },
      retry: {
        type: 'boolean',
        description: 'Pass true to reuse the child this task already has instead of dispatching a new one; no briefing is queued on reuse.',
      },
      followup: {
        type: 'boolean',
        description: 'Pass true with a prompt to deliver explicit continuation instructions to the child this task already has: the instructions queue as the child\'s next ordinary turn and wake it. Requires an existing dispatched child; a fresh dispatch never queues a followup.',
      },
      childId: {
        type: 'string',
        description: 'The preallocated session id for the child, when the deployment configures one (the leadPluginScopes approved sets are keyed by these ids). Omitted, the engine allocates the identity.',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          childId: { type: 'string', required: true },
          role: { type: 'string', required: true },
          taskId: { type: 'string', required: true },
          worktreeId: { type: 'string', required: true },
          reused: { type: 'boolean', required: true },
          followup: { type: 'boolean', required: true },
          ack: {
            type: 'object',
            required: true,
            additionalProperties: false,
            properties: {
              state: { type: 'string', required: true },
              durable: { type: 'boolean', required: true },
              degraded: { type: 'boolean' },
              completed: { type: 'boolean' },
              reasonKind: { type: 'string' },
              turn: { type: 'number' },
            },
          },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: renderDispatchText(value),
      }],
    },
    isConcurrencySafe: () => false,
    async execute(args, exec) {
      if (args.role !== 'lead' && args.role !== 'worker') {
        throw new Error(`the agent dispatch tool: 'role' must be 'lead' or 'worker', got '${args.role}'`)
      }
      // Capture the narrowed role before any await: later dispatch-building
      // code sits behind calls that would widen the property back to string.
      const dispatchRole: 'lead' | 'worker' = args.role
      const caller = await resolveCaller(exec.agent, ctx.workspaceRegistry.list(), ctx.worktreeRegistry)
      const worktreeId = brandString<WorktreeId>(requireNonEmpty(args.worktreeId, 'worktreeId'))
      const row = ctx.worktreeRegistry.list(caller.workspace.id).find(entry => entry.id === worktreeId)
      if (row === undefined) {
        throw new Error(
          `the agent dispatch tool: worktree '${worktreeId}' is not registered under the calling session's workspace; `
          + 'dispatch onto a worktree this workspace holds a row for',
        )
      }
      const taskId = TaskId(requireNonEmpty(args.taskId, 'taskId'))
      const existing = args.retry === true || args.followup === true
        ? ctx.agentDispatch.findDispatchedChild(caller.agent, taskId)
        : undefined
      if (args.retry === true && existing === undefined) {
        throw new Error(
          `the agent dispatch tool: task '${taskId}' has no dispatched child to reuse; `
          + 'dispatch fresh without retry',
        )
      }
      if (args.followup === true && existing === undefined) {
        throw new Error(
          `the agent dispatch tool: task '${taskId}' has no dispatched child to follow up; `
          + 'dispatch fresh without followup',
        )
      }
      // Fail loud on a followup without instructions: silently dispatching
      // or reusing without delivering anything would hide the caller's
      // mistake behind an honest-looking receipt.
      if (args.followup === true && (args.prompt === undefined || requireNonEmpty(args.prompt, 'prompt') === '')) {
        throw new Error(
          `the agent dispatch tool: task '${taskId}' passed followup: true without a prompt; `
          + 'pass the continuation instructions with the followup, or dispatch without followup',
        )
      }
      // A restart leaves the reserved child's durable binding without a live
      // instance. The recovery lane restores the exact identity and worktree
      // (no re-briefing, no replacement child); the followup, if any, rides
      // the second hot-reuse call below, because the recovery lane never
      // re-tasks a child.
      const dispatchRequest = {
        cwd: row.path,
        role: dispatchRole,
        taskId,
        pluginId: PluginId(requireNonEmpty(args.pluginId, 'pluginId')),
        worktree: {
          worktreeId: row.id,
          worktreePath: row.path,
          branch: row.branch,
        },
      }
      const cold = existing !== undefined && !existing.live
      const child = cold
        ? await ctx.agentDispatch.recoverChildAgent(caller.agent, dispatchRequest, {
          workspaceId: caller.workspace.id,
          sessionId: existing.record.agentId,
          agentOptions: parentRouteForDelegation(caller.agent),
        })
        : await ctx.agentDispatch.createChildAgent(caller.agent, dispatchRequest, {
          workspaceId: caller.workspace.id,
          ...(args.childId !== undefined ? { sessionId: brandString<SessionId>(requireNonEmpty(args.childId, 'childId')) } : {}),
          ...(existing !== undefined ? { sessionId: existing.record.agentId } : {}),
          ...(existing === undefined && args.prompt !== undefined && requireNonEmpty(args.prompt, 'prompt') !== ''
            ? { prompt: args.prompt }
            : {}),
          ...(existing !== undefined && args.followup === true && args.prompt !== undefined && requireNonEmpty(args.prompt, 'prompt') !== ''
            ? { followupPrompt: args.prompt }
            : {}),
          // The child must assemble the standard persona, whose {{model}}
          // variable resolves from its own agent options: inherit only the
          // approved parent route (the request header owns provider/model and
          // effort after request-time selection) and the configured output
          // limit - never the parent's whole option bag.
          agentOptions: parentRouteForDelegation(caller.agent),
        })
      if (cold && args.followup === true && args.prompt !== undefined && requireNonEmpty(args.prompt, 'prompt') !== '') {
        // The recovered child is live again; the hot-reuse lane delivers the
        // continuation under the deterministic followup identity. The engine
        // dedupe answers with the same child, so no second child exists.
        await ctx.agentDispatch.createChildAgent(caller.agent, dispatchRequest, {
          workspaceId: caller.workspace.id,
          sessionId: existing.record.agentId,
          followupPrompt: args.prompt,
          agentOptions: parentRouteForDelegation(caller.agent),
        })
      }
      const ack = await ctx.agentDispatch.taskAck(caller.agent, taskId)
      if (ack === undefined) {
        throw new Error(`the agent dispatch tool: task '${taskId}' has no dispatched child to acknowledge`)
      }
      return {
        childId: String(child.record.agentId),
        role: args.role,
        taskId,
        worktreeId: String(row.id),
        reused: existing !== undefined,
        followup: existing !== undefined && args.followup === true,
        ack: {
          state: ack.state,
          durable: ack.durable,
          ...(ack.degraded === undefined ? {} : { degraded: true }),
          ...(ack.completed === undefined ? {} : { completed: ack.completed }),
          ...(ack.turnEnd === undefined ? {} : { reasonKind: ack.turnEnd.reason.kind, turn: ack.turnEnd.turn }),
        },
      }
    },
    presentCall: args => callCard(`agent dispatch: ${args.role} for '${args.taskId}'`),
    presentResult: () => ({ card: 'generic' }),
  }))
}
