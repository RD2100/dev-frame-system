/**
 * The four conversational tools the Shadow agent's scope carries, backed by
 * the shadow router's host write bridges and status read. The schemas speak
 * only task concepts — path, workspace, controller, message, readiness — and
 * request ids are minted here because each model action is one fresh intent.
 * The installer registers into one agent scope and returns the disposer.
 * @module @deepseek-ai/dsh-experimental-shadow-controller/shadow-tools
 */

import { randomUUID } from 'node:crypto'
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { InferValue, ValueSchemaSpec } from '@deepseek-ai/dsh-tools'
import type { ShadowRouter } from '@deepseek-ai/dsh-experimental-shadow-router'

/** The conversational tool names, in registration order. */
export const SHADOW_CONVERSATION_TOOL_NAMES = [
  'shadow_open_project',
  'shadow_message_controller',
  'shadow_release_project',
  'shadow_status',
] as const

const OPEN_VALUE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    workspace_id: { type: 'string', required: true },
    controller_session_id: { type: 'string', required: true },
    state: {
      type: 'string',
      required: true,
      enum: ['reserving', 'provisioning', 'ready', 'stopping', 'stopped', 'needs_attention', 'failed'],
    },
    canonical_path: { type: 'string', required: true },
  },
} as const

const MESSAGE_VALUE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    message_id: { type: 'string', required: true },
    workspace_id: { type: 'string', required: true },
    status: { type: 'string', required: true, enum: ['received'] },
  },
} as const

const RELEASE_VALUE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    workspace_id: { type: 'string', required: true },
    status: { type: 'string', required: true, enum: ['stopping', 'stopped'] },
    cancelled_deliveries: { type: 'integer', required: true },
  },
} as const

const STATUS_VALUE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    shadow_live: { type: 'boolean', required: true },
    authorized_roots: { type: 'array', required: true, items: { type: 'string' } },
    projects: {
      type: 'array',
      required: true,
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          workspace_id: { type: 'string', required: true },
          canonical_path: { type: 'string', required: true },
          binding_revision: { type: 'integer', required: true },
          state: {
            type: 'string',
            required: true,
            enum: ['reserving', 'provisioning', 'ready', 'stopping', 'stopped', 'needs_attention', 'failed'],
          },
        },
      },
    },
  },
} as const

/**
 * Declare one canonical output schema with compact model-facing JSON; the
 * declared schema makes the compiler check `execute` against the value the
 * model is promised.
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

/** Reject any argument key outside the declared parameter surface. */
function assertNoExtraArgs(toolName: string, args: object, allowed: readonly string[]): void {
  const extra = Object.keys(args).filter(key => !allowed.includes(key))
  if (extra.length > 0) throw new Error(`tool "${toolName}" received unknown argument(s): ${extra.join(', ')}`)
}

/**
 * Register exactly the four conversational tools into one agent scope.
 * @param agentCtx - The Shadow agent's scoped creation context.
 * @param router - The shadow router backing every tool call.
 * @returns the disposer removing all four registrations.
 */
export function installShadowConversationTools(agentCtx: Context, router: ShadowRouter): () => void {
  const disposers: Array<() => unknown> = []
  const register = (disposer: () => unknown): void => { disposers.push(disposer) }
  try {
    register(agentCtx.tools.register(defineTool({
      name: 'shadow_open_project',
      description: 'Open one existing project directory as an independent controller root. The directory must already exist under one of the authorized roots; nothing is created. Returns the workspace id, its controller session, and readiness.',
      parameters: {
        path: { type: 'string', required: true, description: 'Existing, authorized, absolute project root directory.' },
      },
      output: jsonOutput(OPEN_VALUE_SCHEMA),
      async execute(args) {
        assertNoExtraArgs('shadow_open_project', args, ['path'])
        const opened = await router.openProjectForHost({ path: args.path, requestId: randomUUID() })
        const value: InferValue<typeof OPEN_VALUE_SCHEMA> = {
          workspace_id: opened.workspaceId,
          controller_session_id: opened.controllerSessionId,
          state: opened.state,
          canonical_path: opened.canonicalPath,
        }
        return value
      },
    })))

    register(agentCtx.tools.register(defineTool({
      name: 'shadow_message_controller',
      description: 'Deliver one message to an opened project\'s controller. Returns a received receipt: the controller durably accepted the input, which never claims the work ran or succeeded. The target session is resolved by the host from the project\'s authorized state and cannot be chosen.',
      parameters: {
        workspace_id: { type: 'string', required: true, description: 'Workspace id returned by shadow_open_project.' },
        text: { type: 'string', required: true, description: 'Bounded, self-contained message text for the controller.' },
      },
      output: jsonOutput(MESSAGE_VALUE_SCHEMA),
      async execute(args) {
        assertNoExtraArgs('shadow_message_controller', args, ['workspace_id', 'text'])
        const sent = await router.sendToProjectForHost({ workspaceId: args.workspace_id, text: args.text, requestId: randomUUID() })
        const value: InferValue<typeof MESSAGE_VALUE_SCHEMA> = {
          message_id: sent.messageId,
          workspace_id: sent.workspaceId,
          status: sent.status,
        }
        return value
      },
    })))

    register(agentCtx.tools.register(defineTool({
      name: 'shadow_release_project',
      description: 'Stop and close exactly one opened project. Its pending work stays visible as cancelled; the row stays listed as stopped. Other projects are unaffected.',
      parameters: {
        workspace_id: { type: 'string', required: true, description: 'Workspace id of the project to release.' },
      },
      output: jsonOutput(RELEASE_VALUE_SCHEMA),
      async execute(args) {
        assertNoExtraArgs('shadow_release_project', args, ['workspace_id'])
        const released = await router.releaseProjectForHost({ workspaceId: args.workspace_id, requestId: randomUUID() })
        const value: InferValue<typeof RELEASE_VALUE_SCHEMA> = {
          workspace_id: released.workspaceId,
          status: released.status,
          cancelled_deliveries: released.cancelledDeliveries,
        }
        return value
      },
    })))

    register(agentCtx.tools.register(defineTool({
      name: 'shadow_status',
      description: 'Read the current facts: whether the Shadow designation is live, the authorized roots, and every project with its workspace id, path, revision, and state. Read-only.',
      parameters: {},
      output: jsonOutput(STATUS_VALUE_SCHEMA),
      execute() {
        const status = router.readStatus()
        const value: InferValue<typeof STATUS_VALUE_SCHEMA> = {
          shadow_live: status.shadowLive,
          authorized_roots: [...status.authorizedRoots],
          projects: status.bindings.map(row => ({
            workspace_id: row.workspaceId,
            canonical_path: row.canonicalPath,
            binding_revision: row.bindingRevision,
            state: row.state,
          })),
        }
        return Promise.resolve(value)
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
