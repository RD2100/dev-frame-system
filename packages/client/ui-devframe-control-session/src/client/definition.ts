import type {
  ChatConversationViewNode,
  ConversationMatch,
  ConversationNodeContext,
  ConversationNodeDefinition,
} from '@deepseek-ai/dsh-client-runtime/client'
import type { ControllerIdentityV1 } from '@deepseek-ai/dsh-devframe-control-session/types'
import type { SessionEvent, SessionEventType } from '@deepseek-ai/dsh-session/types'
import type { ControlSessionKey } from './locales.ts'

declare module '@deepseek-ai/dsh-client-ui-conversation/client' {
  interface ChatNodeDataMap {
    'devframe-controller-identity': ControllerIdentityView
  }
}

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    'client-ui-devframe-control-session': ControlSessionKey
  }
}

/** Privacy-bounded projection of one controller identity event. */
export interface ControllerIdentityView {
  readonly role: ControllerIdentityV1['role'] | 'unknown'
  readonly sessionId: string
  readonly scopeId: string
  readonly schemaVersion: 1
  readonly readiness: 'identity-recorded' | 'blocked'
}

const IDENTITY_EVENT_TYPE = 'controller/identity' as SessionEventType
const ID_PART_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false
  const prototype = Reflect.getPrototypeOf(value)
  return prototype === Object.prototype || prototype === null
}

function exactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value).sort()
  const wanted = [...expected].sort()
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index])
}

function validIdPart(value: unknown): value is string {
  return typeof value === 'string' && ID_PART_PATTERN.test(value)
}

function blockedIdentity(): ControllerIdentityView {
  return {
    role: 'unknown',
    sessionId: '',
    scopeId: '',
    schemaVersion: 1,
    readiness: 'blocked',
  }
}

function projectIdentity(value: unknown): ControllerIdentityView {
  if (!isPlainRecord(value)
    || value.schemaVersion !== 1
    || !validIdPart(value.profileId)) return blockedIdentity()

  if (value.role === 'global'
    && exactKeys(value, ['cwd', 'profileId', 'role', 'schemaVersion', 'sessionId'])
    && typeof value.cwd === 'string'
    && value.cwd.length > 0
    && value.sessionId === `devframe-global:${value.profileId}`) {
    return {
      role: 'global',
      sessionId: value.sessionId,
      scopeId: value.profileId,
      schemaVersion: 1,
      readiness: 'identity-recorded',
    }
  }

  if (value.role === 'project'
    && exactKeys(value, ['cwd', 'profileId', 'role', 'schemaVersion', 'sessionId', 'workspaceId'])
    && typeof value.cwd === 'string'
    && value.cwd.length > 0
    && validIdPart(value.workspaceId)
    && value.sessionId === `devframe-controller:${value.workspaceId}`) {
    return {
      role: 'project',
      sessionId: value.sessionId,
      scopeId: value.workspaceId,
      schemaVersion: 1,
      readiness: 'identity-recorded',
    }
  }

  return blockedIdentity()
}

/** Project one required identity event while excluding every unlisted field. */
export const controllerIdentityDefinition: ConversationNodeDefinition<ControllerIdentityView> = {
  kind: 'devframe-controller-identity',
  target: 'chat',
  match: (event: SessionEvent) => event.type === IDENTITY_EVENT_TYPE && event.seq === 0
    ? { id: `controller-identity:${event.seq}`, role: 'start' }
    : null,
  start: (_context: ConversationNodeContext<ControllerIdentityView>, match: ConversationMatch) =>
    projectIdentity(match.event.data),
  update: context => context.state,
  publication: () => 'none',
  buildViewNode: (context: ConversationNodeContext<ControllerIdentityView>) => {
    const start = context.start
    if (start === undefined) return null
    const node: ChatConversationViewNode = {
      key: context.key,
      kind: context.kind,
      id: context.id,
      target: 'chat',
      data: context.state,
      anchorSeq: start.event.seq,
      location: start.location,
      visibility: 'visible',
    }
    return node
  },
}
