# T3 Coordinator Entry Consumer Guide

This guide is for a future RD-Code/T3Code shell checkout that wants to consume
DevFrame's read-only Global Coordinator entry point:

```http
GET /api/t3/coordinator-entry
```

This endpoint is a shell read model. It is not an orchestration runtime, not a
dashboard private-state API, and not a write surface.

## Shell Rules

The shell should:

- fetch `GET /api/t3/coordinator-entry`
- render from the returned read-only view model
- treat `schemas/t3_coordinator_entry.schema.json` as the contract reference
- validate behavior against `packages/control-plane/tests/fixtures/t3_coordinator_entry/`

The shell should not:

- send `POST`, `PUT`, `PATCH`, or `DELETE` to this endpoint
- assume LangGraph exists
- read dashboard-private state or internal stores
- start agents, approvals, queues, schedulers, or background runners from this endpoint

## View Model Fields

Use these fields as the first shell-facing view model:

- `selectedProject`
- `projectOptions`
- `globalCoordinatorThread`
- `projectCoordinatorThread`
- `goalConversations`
- `shellThreads`
- `conversationModel`
- `canStartCoordinatorGoal`
- `emptyStateReason`
- `disabledReason`

`projectCoordinatorThread` must match `selectedProject.projectId` exactly. If
the selected project has no matching goal conversation, render no project
coordinator thread instead of falling back to another project's goal.

## Minimal Consumer Sketch

```ts
export async function loadCoordinatorEntry() {
  const response = await fetch("/api/t3/coordinator-entry", {
    method: "GET",
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    return {
      selectedProject: null,
      projectOptions: [],
      globalCoordinatorThread: null,
      projectCoordinatorThread: null,
      goalConversations: [],
      shellThreads: [],
      conversationModel: null,
      canStartCoordinatorGoal: false,
      emptyStateReason: "malformed_entry_response",
      disabledReason: "missing_required_project",
    };
  }

  return response.json();
}
```

Keep this layer thin. The first real shell slice should prove navigation and
rendering, not agent execution.

## Required Render States

Use the fixture directory as the shell's first acceptance checklist:

- `no_projects.json`: render the global coordinator, disable project-bound goal start, and show `missing_required_project`.
- `global_coordinator_only.json`: render the global coordinator without inventing a project goal thread.
- `project_with_goal_conversations.json`: render the matching project coordinator thread and the remaining goal list.
- `project_without_goal_conversations.json`: render the selected project with no project coordinator thread.
- `project_alpha_without_matching_goal_conversation.json`: do not show a beta goal as alpha's coordinator thread.
- `can_start_coordinator_goal_false.json`: disable start actions and surface `disabledReason`.
- `malformed_or_partial_entry_response.json`: fail closed with explicit empty/disabled state.

## Future Shell Checklist

- [ ] Fetch `GET /api/t3/coordinator-entry` on initial load.
- [ ] Re-fetch on project selection changes if the shell maintains local selection.
- [ ] Render the ten view-model fields above without reaching into dashboard internals.
- [ ] Handle `emptyStateReason` and `disabledReason` with visible, non-crashing states.
- [ ] Keep coordinator-entry read-only; do not add execution, approval, queue, or scheduler behavior.
- [ ] Compare shell behavior against the fixture scenarios before adding richer UX.
- [ ] Defer LangGraph wiring until the first read-only shell path is proven.

## Boundary

This guide intentionally stops at read and render. The next real product slice
is external RD-Code/T3Code shell integration. LangGraph orchestration, agent
execution, approvals, and shared-state coordination remain later slices.
