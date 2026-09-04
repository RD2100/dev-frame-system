# `@deepseek-ai/dsh-client-ui-devframe-control-session`

English | [中文](README.zh.md)

Browser-side projection of the version 1 `controller/identity` Session event into DSH's native conversation surface. The plugin registers one `ConversationNodeDefinition`, locale dictionaries, and one keyed `conversation.chat.node` renderer; disposal removes all three effect-owned registrations.

## Projection and privacy

The projection accepts only the exact role-specific field set and verifies that the payload's deterministic Session ID matches its bounded profile or workspace ID. A valid event renders role, Session ID, scope ID, schema version, and `identity-recorded`. Malformed, mismatched, null, array, or extra-field payloads render a bounded `blocked` state with empty IDs instead of echoing input.

Canonical cwd is required by the event contract but is never selected into the card. Absolute paths, credentials, prompts, nested payloads, and unknown fields are likewise not rendered. Values render as React text nodes. This package owns no persistent store, network access, controller lifecycle, or second workbench.

## Model Experience

### Browser identity projection

#### What the model sees

Nothing directly. The plugin only renders the logged `controller/identity` event as a browser conversation node and does not add prompt content, tools, messages, or model requests.

#### Token effect

Zero direct tokens because browser rendering does not enter model context.

#### KV Cache effect

The browser-only projection does not create or invalidate a model-request prefix.

## Known Limitations and Deferred Work

- **Identity evidence, not live readiness** — `identity-recorded` means the bounded event passed client validation; it does not prove that the Host controller remains live or can execute work.
- **Payload projection only** — the browser node cannot independently prove that the payload belongs to the containing Session header or that the full log has exactly one identity event. The Host controller remains the authority for those checks.
- **Read-only node** — the surface exposes no open, retry, repair, dispatch, or policy action.
- **Version 1 only** — any other schema version fails closed to the bounded `blocked` view until this package adds and tests an explicit migration.
