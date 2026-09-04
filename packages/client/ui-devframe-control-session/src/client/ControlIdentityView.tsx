import type { ChatNode } from '@deepseek-ai/dsh-client-ui-conversation/client'
import type { TranslateNS } from '@deepseek-ai/dsh-client-ui-slots'

/** Props consumed by the identity renderer; framework shares may add members. */
export interface ControlIdentityViewProps {
  readonly node: ChatNode<'devframe-controller-identity'>
  readonly t: TranslateNS<'client-ui-devframe-control-session'>
}

/**
 * Keep the durable identity event internal. The Global Controller is a
 * normal conversation surface; implementation metadata belongs in its
 * Session actions menu, not in the message stream.
 */
export function ControlIdentityView(props: ControlIdentityViewProps): null {
  void props.node.data
  void props.t
  return null
}
