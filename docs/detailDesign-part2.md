---
description: Proposed Shadow routing between independent project sessions and durable message delivery.
---

# Detailed Design Part 2: Shadow and Multiple Projects

English | [中文](detailDesign-part2.zh.md)

## Summary

This reference is a candidate extension after [single-project operation](detailDesign-part1.md#user-flow), its early stop/recovery checks, and the usefulness trial. Shadow routes user intent between independent project roots; it does not own a nested Team, a second task board, or unrestricted execution. Cross-root delivery is new implementation work, not the existing intra-Team mailbox. The pilot does not depend on implementing this part.

## Table of Contents

- [Requirements and ownership](#requirements)
- [Project tools](#tools)
- [Opening and routing](#routing)
- [Delivery and retry behavior](#delivery)
- [Status, stopping, and presentation](#status)

<a id="requirements"></a>

## Requirements and ownership

Use the [native workspace registry](../packages/workspace/workspace/src/index.ts) for canonical project identity and the [root-session controller](../packages/api/session-controller/src/agent.ts) as the reference for create/resume behavior. Native sessions, Team tasks, and event logs remain their own state owners.

| ID | Required behavior | Acceptance owner |
| --- | --- | --- |
| `R2.1` | Resolve one authorized workspace to one current controller and prevent cross-project routing. | [AT2-01, AT2-02](testAndAcceptance.md#part2) |
| `R2.2` | Deduplicate repeated opens and reject unsafe path aliases or conflicting roots. | [AT2-03, AT2-04](testAndAcceptance.md#part2) |
| `R2.3` | Persist cross-root delivery and distinguish received work from completed work. | [AT2-05, AT2-06](testAndAcceptance.md#part2) |
| `R2.4` | Stop and inspect one project without affecting another project's execution. | [AT2-07, AT2-08](testAndAcceptance.md#part2) |

The only new project index is a binding stored through DSH's native domain persistence: `workspaceId`, reserved `controllerSessionId`, `profileKey`, `bindingRevision`, opening `requestId`, and provisioning state. The role profile is host-selected. Do not duplicate project paths, native task rows, transcripts, or a separate completion state in this binding.

A binding revision fences obsolete requests when a controller is deliberately replaced. A process-local mutex can serialize operations in the first single-process deployment, but the durable binding and operation IDs must survive restart. Multiple processes writing the same runtime store are not supported by this design.

<a id="tools"></a>

## Project tools

Expose four proposed tools to Shadow. A project worker or reviewer receives none of them. Validate tool JSON, the actual caller, and workspace authorization before resolving a session.

Shadow's model-facing allowlist contains only these routing tools and explicitly enabled user-memory access. It has no arbitrary filesystem/shell execution, raw session-control tools, plugin self-modification, or unrestricted MCP access. Host-owned project creation uses separately validated user grants; it does not inherit unrestricted authority from Shadow's prompt.

| Tool | Input | Result and error behavior |
| --- | --- | --- |
| `project_open` | Existing authorized `path`, stable `requestId`. | Return `workspaceId`, controller identity, revision, and readiness. Reject missing directories, unauthorized roots, or profile/cwd conflicts; never create a directory silently. |
| `project_send` | `workspaceId`, `bindingRevision`, `goalId`, `acceptanceHash`, stable `requestId`, `mode` (`work` or `note`), bounded text. | Return delivery ID and receipt state; reject stale binding/work identity, stopped admission, or full queues. Receipt is not execution success. |
| `project_status` | One authorized `workspaceId`, or an authorized bounded page of projects. | Derive state from native sessions/tasks, delivery state, and active jobs; include observation time and blocking reason. |
| `project_stop` | `workspaceId`, expected revision, stable `requestId`. | Stop only the selected project's admission and execution; return `stopping` until its owned work is drained. Repeating the same stop is safe. |

The caller cannot supply an arbitrary target session ID. The host resolves it from the authorized binding. Reusing a `requestId` with the same normalized input returns the earlier result; reusing it with different input returns `request_conflict`. The UI/host retains request IDs across retries instead of asking a model to invent a fresh ID each time.

<a id="routing"></a>

## Opening and routing

Canonicalize existing roots using the native workspace rules and the actual filesystem, including Windows case and junction aliases. Reject simultaneously writable roots that overlap physically; a string prefix check alone is insufficient. Separate worktrees may be separate projects only when their working directories are disjoint and shared Git mutations remain unavailable to workers.

1. Validate the requested path and project authorization; resolve or create its native workspace identity.
2. Under the per-workspace creation mutex, read the existing binding; return it if it is valid.
3. If no binding exists, reserve one controller session ID and persist a provisioning binding before creating the session.
4. Create an independent root with the project's approved cwd and preset; do not set Shadow as its subagent parent.
5. Persist readiness only after session creation and required role setup are durable; publish the result to Shadow.

A crash after reservation is reconciled against that same session ID. If identity, cwd, or policy does not match, leave the project in `needs_attention`; do not create another writer as a fallback. Session restart behavior must respect native goals' [explicit recovery policy](detailDesign-part4.md#recovery).

<a id="delivery"></a>

## Delivery and retry behavior

Cross-root delivery uses a small sender intent and target receipt in native session persistence. Follow the durability ordering of the [native Team mailbox](../packages/experimental/agent-team/src/mailbox.ts), but do not call its membership-checked methods as if unrelated roots were teammates. Reuse a proven helper only if it actually supports the required identities.

The proposed message fields are `messageId`, `requestId`, source session, workspace ID, binding revision, target session, `goalId`, `acceptanceHash`, mode, bounded content/reference, and creation time. IDs and work ownership are fixed before the first durable write and do not change on retries. A message for a previous Goal cannot be rerouted to the controller's current Goal.

```text
Sender: persist intent + flush
  -> Target: validate identity/revision + deduplicate messageId
  -> Target: persist accepted input + flush
  -> Sender: persist received receipt + flush

received != started != completed
```

A `work` message schedules a follow-up only when its Goal and acceptance binding match an authorized open run; a `note` is quiet input with the same ownership check. Sending a message does not create or replace a Goal. Starting or resuming uses the same validated human-authorization path as [Part 1](detailDesign-part1.md#user-flow); Shadow cannot invent a grant. Retrying pre-crash delivery does not authorize old work to restart.

Target deduplication covers durable inbox input, not arbitrary external side effects. If a command may have started before a crash but its result is unknown, mark execution `ambiguous` and inspect native job/process evidence. Do not repeat irreversible work merely because the sender lacks a receipt.

Delivery retries are bounded and reuse the same ID; exhaustion leaves a visible queued/failed operation for a human decision. Queue and message-size limits apply before accepting new input. The exact proposed defaults are owned by [Part 4](detailDesign-part4.md#limits).

<a id="status"></a>

## Status, stopping, and presentation

Present `idle`, `running`, `waiting`, `stopping`, `stopped`, `completed`, and `needs_attention` as derived UI states, not as a competing persistent task state machine. `completed` requires the Part 1 completion result; an empty queue or idle model is not enough. A stale observation shows its timestamp and cannot authorize writes.

Stopping closes only the selected project's queue, disarms its goal driver, cancels its controller and children, and waits for owned processes to drain. Preserve already accepted messages as cancelled or pending human handling; never silently drop them or automatically migrate them to a replacement controller. [Part 4](detailDesign-part4.md#stopping) defines the timeout behavior.

Extend the existing [single-project journey](detailDesign-part1.md#user-flow) with project selection and the four Shadow tools; do not invent a separate approval or resume flow. Existing session navigation and tool cards show project/controller, current Goal/task, delivery state, last activity, and blocking reason. Read-only status refresh never wakes agents and excludes other projects' content and secrets.

## Dev Note

Do not introduce a separate HTTP gateway or distributed broker for this slice. Reconsider an external transport only when multiple processes or machines are a demonstrated requirement; carry these delivery IDs, authorization checks, and ambiguity semantics into that later design.
