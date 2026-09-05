# Agent Note: Shadow project tools authorize targets through the binding store, not the mailbox

Status: implemented

English | [中文](2026-09-05-shadow-router-project-tools-binding-store.zh.md)

## Problem

The Shadow layer needs one host-designated session that can open independent project roots and route work into them. Two prior patterns competed for that seam: agent-team mailboxes validate targets by team membership, and ad-hoc tool surfaces let the model choose a target session id directly. Both are wrong here — team membership says nothing about which directory a writer owns, and a model-chosen session id lets one project's caller reach into another's controller. The router needed a target authority that survives crashes, is scoped to exactly one agent, and cannot be forged from tool arguments.

## Decision

`packages/experimental/shadow-router` splits the seam: the four project tools (`project_open`, `project_send`, `project_status`, `project_stop`) are installed only into the agent scope the host marks with `markShadow`, and every dispatch resolves its target through the durable binding store keyed by workspace id — never through a caller-supplied session id. The binding store and the tools move in lockstep: `project_open` persists the provisioning state machine (`reserving → provisioning → ready`, with `failed` rollback and `needs_attention` parking) before a controller root session exists; `project_send` accepts input only against the binding's current revision and its host-authorized Goal/acceptance association, persisting the `queued` intent and the `received` acceptance as separate durable rows; `project_stop` cancels only that binding's queued rows and parks it in `stopping` until the host confirms. Unknown tool-argument keys are rejected at the tool seam (the shared parameter schema is implicitly open, so the whitelist owns that check), which is what makes a forged `target_session_id` fail loud instead of being ignored.

## Alternatives considered

**Reuse agent-team mailbox delivery for cross-root work.** Rejected: mailboxes authorize by membership, which answers "is this sender allowed in the team" and not "is this workspace's controller the right target"; the binding store already holds the canonical-path and revision facts routing needs, so a second membership authority would only drift from it.

**Let the model pass the controller session id per call.** Rejected: the model never learns the controller id's role and one leakage turns any session into a cross-root writer; the target must derive from the authorized binding, and the open schema keeps it that way.

**Persist deliveries only after acceptance.** Rejected: a crash between model-visible scheduling and controller acceptance would then lose the intent exactly once per interruption; the two-write order (intent, then acceptance) is what lets restart converge to one visible received row without duplicating the task.

## Consequences

The Shadow's model face is exactly four tools whose targets are host-owned, and every authorization fact survives restart in one domain table the router itself rebuilds. The costs: host compositions must mark the Shadow and call the host-only seams (`setActiveGoal`, `completeDelivery`, `confirmProjectStopped`, `recoverDeliveries`) themselves, deliveries stay invisible to controllers until the host forwards them, and a second live router over one storage root fails loud because the JSON backend refuses a second handle — each accepted here because the alternative is a target authority the model could steer.
