/** Browser entry exposing the generated expert-team Remote to client plugins. */

// Package-name /remote import: the client build face resolves this through the
// GENERATED_REMOTE inline rule, so the emitted lib/types/client copy never
// re-resolves a depth-dependent relative path.
import expertTeamRemote from '@deepseek-ai/dsh-experimental-expert-team/remote'

export { expertTeamRemote }

/**
 * Module-table presence: expert-team's client surface is a value (the
 * generated Remote), not a plugin with behavior. A no-op `apply` lets the
 * loader create this row so `ui-expert-team` can require its `/client`
 * module-table specifier.
 */
export function apply(): void {}
