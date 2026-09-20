# Agent Note: Expert center actions hand off through a new conversation

Status: implemented

English | [中文](2026-09-16-expert-center-summon.zh.md)

## Problem

The catalog made mounted experts discoverable, but a user had no direct path from an expert card to a conversation that used that expert. Directly mutating orchestration state from the browser would also cross the Host-owned run and approval boundary.

## Decision

Expert cards expose a hover- and focus-visible `Summon` action. The detail surface exposes `Summon expert` and three locale-owned prompt suggestions. Each action closes the catalog, stages a plain expert identity and editable prompt, and calls the existing `uiWorkspace.startSession()` flow. `ExpertSelectionController` waits for the resulting blank Session, writes the prompt through `ctx.conversation.input`, and publishes a session-scoped chip in `conversation.input.left`. The user submits the prompt through the normal composer; the browser never calls `expert_team_run` or `expert_team_approve` directly.

## Alternatives considered

**Call `expert_team_run` directly from the browser.** Rejected: the Host/model boundary owns orchestration, gates, and run history; the UI should not create a second mutation path.

**Submit the summon prompt immediately.** Rejected: the selected expert and prompt remain visible and editable, so the user can add context, change the wording, or remove the selection before sending.

**Show a selection only inside the catalog.** Rejected: the choice must remain visible at the point where the user edits and submits the new conversation.

## Consequences

The reference card and detail interactions now have a complete, reversible user path into the existing Conversation surface. A successful handoff produces a blank Session with a visible expert chip and draft; submitting it uses the existing model-facing expert-team tools. A missing Workspace leaves the selection staged until the normal Session flow can produce a blank Session. Skills and Connectors remain display-only because their data sources are still absent.

## Testing

The Expert center tests cover card summon, detail summon, and suggestion actions. The selection tests cover prompt staging, asynchronous blank-Session reconciliation, and chip removal. The live DevFrame browser flow confirmed a new blank Session with a staged prompt and selected-expert chip.

## Related

[The Expert center catalog note](2026-09-16-expert-center-ui.md) owns catalog discovery; [the client package contract](../../../../packages/experimental/client-ui-expert-team/README.md) documents the user-facing flow.
