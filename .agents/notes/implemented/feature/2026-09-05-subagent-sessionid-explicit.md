# Agent Note: Explicit SessionID in the delegation tool surface

Status: implemented

English | [中文](2026-09-05-subagent-sessionid-explicit.zh.md)

## Problem

A continuable subagent's durable identity is its Session: the continuation manager brands every `childId` as `SessionId`, the session header carries `parentSession`/`origin`/`delegationDepth`, and the model-facing tools return that same value. But the surface labeled it an agent id: the `subagent` result field was `subagentId`, `list_agents` rows said `id`, and `send_message`/`interrupt_agent` said "agent id". Nothing at the model or user surface names the value a SessionID, so orchestration consumers that must not invent session identifiers recorded child identity as unavailable even though the real value was in hand.

## Decision

The model-facing delegation surface names the durable session identity `sessionId` and labels it SessionID in rendered text:

- the continuable `subagent` result field is `sessionId` (rendered `started continuable subagent; SessionID …`);
- `list_agents` entries carry `sessionId` (rendered `SessionID=…`), keeping the service-level `SubagentListEntry.id` unchanged;
- `send_message` and `interrupt_agent` describe their `agent_id` parameter as the SessionID.

One-shot foreground results keep `runId`: a one-shot child is not continuable, so its run identity, not a session address, is the settlement handle. One-shot background children keep the job id for the same reason.

## Alternatives considered

- Keep `subagentId` and document it as the session id. Rejected: the label ambiguity is the defect; a registry that copies "agent id" values into a SessionID column without a type-honest field repeats the unavailable-identity hole.
- Introduce a separate agent-identity namespace for the tools. Rejected: the tool values already are session ids; a second identity system multiplies routing keys and contradicts the one-durable-identity design of the subagent service.

## Consequences

Model and user surfaces now name the durable child identity SessionID, so orchestration consumers record and route child sessions without a second identity namespace. The service-level `ContinuableStart.childId` and `SubagentListEntry.id` keep their names, and `send_message`/`interrupt_agent` keep the `agent_id` parameter name while describing it as the SessionID. Recorded-session snapshot fixtures still expect the pre-rename field and description text, so `test:snapshot`/`test:web` stay red on that delta until their recorded outputs are refreshed.

## Verification

`pnpm exec vitest run packages/subagent` (769 tests) covers the renamed field, render text, and the send_message/interrupt_agent descriptions; `pnpm run verify-tool-catalog` regenerates the tool catalog from source; `pnpm run verify-translation-pairing` keeps the bilingual catalog and this note's pair in sync. Recorded-session snapshot suites remain a CI signal with the tool-description change in scope.
