/**
 * The four model-facing Shadow tools and the whitelist installer. The Shadow
 * model face is exactly these routing tools plus any explicitly enabled user
 * memory access — never the host shell, raw session control, or unrestricted
 * MCP surface. Project developers and reviewers never receive them: the
 * installer registers into a scope only when the host designates that agent
 * as Shadow, and every tool re-checks the caller against the designation
 * before touching any state.
 * @module @deepseek-ai/dsh-experimental-shadow-router/tools
 */

import type { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { InferValue, ValueSchemaSpec } from '@deepseek-ai/dsh-tools'
import { ShadowRouterError } from './errors.ts'
import type { ShadowRouter } from './service.ts'

/** The tool names the Shadow whitelist contributes, in registration order. */
export const SHADOW_TOOL_NAMES = ['project_open', 'project_send', 'project_status', 'project_stop'] as const

const OPEN_VALUE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    workspaceId: { type: 'string', required: true },
    controllerSessionId: { type: 'string', required: true },
    bindingRevision: { type: 'integer', required: true },
    state: {
      type: 'string',
      required: true,
      enum: ['reserving', 'provisioning', 'ready', 'stopping', 'stopped', 'needs_attention', 'failed'],
    },
    canonicalPath: { type: 'string', required: true },
  },
} as const

const SEND_VALUE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    messageId: { type: 'string', required: true },
    workspaceId: { type: 'string', required: true },
    status: { type: 'string', required: true, enum: ['received'] },
  },
} as const

const STOP_VALUE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    workspaceId: { type: 'string', required: true },
    status: { type: 'string', required: true, enum: ['stopping', 'stopped'] },
    cancelledDeliveries: { type: 'integer', required: true },
    bindingRevision: { type: 'integer', required: true },
  },
} as const

const DELIVERY_SUMMARY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    messageId: { type: 'string', required: true },
    mode: { type: 'string', required: true, enum: ['work', 'note'] },
    goalId: { type: 'string', required: true },
    state: { type: 'string', required: true, enum: ['queued', 'received', 'completed', 'cancelled'] },
    createdAt: { type: 'string', required: true },
    receivedAt: { type: 'string' },
    completedAt: { type: 'string' },
    cancelReason: { type: 'string' },
  },
} as const

const PROJECT_ENTRY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    workspaceId: { type: 'string', required: true },
    canonicalPath: { type: 'string', required: true },
    controllerSessionId: { type: 'string', required: true },
    controllerLive: { type: 'boolean', required: true },
    profileKey: { type: 'string', required: true },
    bindingRevision: { type: 'integer', required: true },
    state: {
      type: 'string',
      required: true,
      enum: ['reserving', 'provisioning', 'ready', 'stopping', 'stopped', 'needs_attention', 'failed'],
    },
    failureReason: { type: 'string' },
    activeGoalId: { type: 'string' },
    blockedReason: { type: 'string' },
    deliveries: { type: 'array', required: true, items: DELIVERY_SUMMARY_SCHEMA },
    deliveriesTruncated: { type: 'boolean', required: true },
  },
} as const

const STATUS_VALUE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    projects: { type: 'array', required: true, items: PROJECT_ENTRY_SCHEMA },
    nextCursor: { type: 'integer' },
    observedAt: { type: 'string', required: true },
  },
} as const

/**
 * Declare one canonical output schema with compact model-facing JSON. Every
 * Shadow result is a fixed record, so the declared schema is what makes the
 * compiler check `execute` against the value the model is promised.
 * @param schema - canonical value schema for one tool.
 * @returns the `output` declaration accepted by {@link defineTool}.
 */
function jsonOutput<const S extends ValueSchemaSpec>(schema: S): {
  schema: S
  render: (args: unknown, value: InferValue<S>) => [{ type: 'text'; text: string }]
} {
  return {
    schema,
    render: (_args: unknown, value: InferValue<S>) => [{ type: 'text', text: JSON.stringify(value) }],
  }
}

/** Recover the exact caller guaranteed by Agent-scoped tool discovery. */
function callingAgent(agent: Agent | undefined, toolName: string): Agent {
  /* v8 ignore next 2 -- Shadow tools are registered only in the exact Shadow scope, so discovery supplies this carrier. */
  if (agent === undefined) throw new Error(`${toolName} requires a calling Agent`)
  return agent
}

/**
 * Reject any argument key outside the declared parameter surface. The tool
 * runtime compiles parameters to an implicitly open object root, so this seam
 * owns the whitelist guarantee that the caller cannot smuggle fields — a
 * forged target session id must fail loud, never be silently ignored.
 */
function assertNoExtraArgs(toolName: string, args: object, allowed: readonly string[]): void {
  const extra = Object.keys(args).filter(key => !allowed.includes(key))
  if (extra.length > 0) {
    throw new ShadowRouterError(
      `project tool "${toolName}" received unknown argument(s): ${extra.join(', ')}`,
      'SHADOW_INVALID_REQUEST',
    )
  }
}

/**
 * Register exactly the four project tools into one Agent scope — the whole
 * Shadow whitelist contribution. Returns the scope-local disposer.
 * @param agent - The agent the host designated as Shadow.
 * @param _ctx - Mounting context; reserved for future cross-scope wiring.
 * @param router - The shadow router backing every tool call.
 * @returns the disposer removing all four registrations.
 */
export function installShadowTools(agent: Agent, _ctx: Context, router: ShadowRouter): () => void {
  const scoped = agent.ctx
  const disposers: Array<() => unknown> = []
  const register = (disposer: () => unknown): void => { disposers.push(disposer) }
  try {
    register(scoped.tools.register(defineTool({
      name: 'project_open',
      description: 'Open one authorized existing project directory as an independent controller root and return its workspace identity, controller session, binding revision, and readiness. Repeated opens of the same root deduplicate; reuse the same request_id unchanged across retries.',
      parameters: {
        path: { type: 'string', required: true, description: 'Existing, authorized, absolute project root directory. Missing directories are never created.' },
        request_id: { type: 'string', required: true, description: 'Stable request id for deduplication; the same id with different input is rejected.' },
      },
      output: jsonOutput(OPEN_VALUE_SCHEMA),
      async execute(args, exec) {
        assertNoExtraArgs('project_open', args, ['path', 'request_id'])
        return await router.openProject(callingAgent(exec.agent, 'project_open'), {
          path: args.path,
          requestId: args.request_id,
        })
      },
    })))

    register(scoped.tools.register(defineTool({
      name: 'project_send',
      description: 'Deliver one bounded work or note message to an open project\'s controller. Returns a delivery id and a received receipt; the receipt never claims the work ran or succeeded. The target session is resolved by the host from the authorized binding and cannot be chosen.',
      parameters: {
        workspace_id: { type: 'string', required: true, description: 'Workspace id returned by project_open.' },
        binding_revision: { type: 'integer', required: true, description: 'Binding revision the sender observed; stale revisions are rejected.' },
        goal_id: { type: 'string', required: true, description: 'Goal the message belongs to; a previous Goal\'s message is never delivered to the current Goal.' },
        acceptance_hash: { type: 'string', required: true, description: 'Acceptance association paired with the goal.' },
        request_id: { type: 'string', required: true, description: 'Stable request id; retries of the same delivery reuse it unchanged.' },
        mode: { type: 'string', required: true, enum: ['work', 'note'], description: 'work schedules follow-up; note is quiet input.' },
        text: { type: 'string', required: true, description: 'Bounded, self-contained message text.' },
      },
      output: jsonOutput(SEND_VALUE_SCHEMA),
      async execute(args, exec) {
        assertNoExtraArgs('project_send', args, ['workspace_id', 'binding_revision', 'goal_id', 'acceptance_hash', 'request_id', 'mode', 'text'])
        return await router.sendToProject(callingAgent(exec.agent, 'project_send'), {
          workspaceId: args.workspace_id,
          bindingRevision: args.binding_revision,
          goalId: args.goal_id,
          acceptanceHash: args.acceptance_hash,
          requestId: args.request_id,
          mode: args.mode,
          text: args.text,
        })
      },
    })))

    register(scoped.tools.register(defineTool({
      name: 'project_status',
      description: 'Read one project or one bounded page of projects: controller state, binding revision, delivery states with their observation time, and blocking reasons. Read-only; it never wakes a model and never reports a received receipt as completion.',
      parameters: {
        workspace_id: { type: 'string', description: 'One workspace to observe; omit for a bounded page of every authorized project.' },
        cursor: { type: 'integer', description: 'Zero-based page offset. Defaults to 0.' },
        limit: { type: 'integer', description: 'Page size, 1 through the configured maximum. Defaults to the configured maximum.' },
      },
      output: jsonOutput(STATUS_VALUE_SCHEMA),
      async execute(args, exec) {
        assertNoExtraArgs('project_status', args, ['workspace_id', 'cursor', 'limit'])
        return await router.projectStatus(callingAgent(exec.agent, 'project_status'), {
          ...args.workspace_id === undefined ? {} : { workspaceId: args.workspace_id },
          ...args.cursor === undefined ? {} : { cursor: args.cursor },
          ...args.limit === undefined ? {} : { limit: args.limit },
        })
      },
    })))

    register(scoped.tools.register(defineTool({
      name: 'project_stop',
      description: 'Stop exactly one project: close its receiving, cancel its pending deliveries (kept visible, never dropped), and report stopping until the host confirms the project quiescent. Other projects are unaffected; repeating the same stop is safe.',
      parameters: {
        workspace_id: { type: 'string', required: true, description: 'Workspace id of the project to stop.' },
        expected_revision: { type: 'integer', required: true, description: 'Binding revision the caller asserts; stale revisions are rejected.' },
        request_id: { type: 'string', required: true, description: 'Stable request id; repeating the same stop reuses it unchanged.' },
      },
      output: jsonOutput(STOP_VALUE_SCHEMA),
      async execute(args, exec) {
        assertNoExtraArgs('project_stop', args, ['workspace_id', 'expected_revision', 'request_id'])
        return await router.stopProject(callingAgent(exec.agent, 'project_stop'), {
          workspaceId: args.workspace_id,
          expectedRevision: args.expected_revision,
          requestId: args.request_id,
        })
      },
    })))
  } catch (error: unknown) {
    for (const dispose of disposers.reverse()) void dispose()
    throw error
  }
  return () => {
    for (const dispose of disposers.reverse()) void dispose()
  }
}
