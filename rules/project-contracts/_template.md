# Project Contract -- template

Use this template when a project needs rdgoal total-control orchestration.

```yaml
project_id: example-project
title: Example Project
goal: >
  Build a complete working prototype. Prefer visible end-to-end progress over
  perfect internal polish.
non_goals:
  - Do not publish a production release.
  - Do not introduce paid services.
autonomy_level: total_control
decision_policy:
  direction_choice: choose_recommended_path
  unclear_requirement: infer_minimal_prototype
  destructive_local_change: snapshot_then_execute
  architecture_choice: prefer_existing_project_style
  external_side_effect: draft_only
prototype_bias:
  prefer_working_mvp: true
  prefer_existing_stack: true
  leave_adjustment_notes: true
stop_lines:
  - spend money
  - publish production release
  - delete remote production data
  - expose secrets
priority: 3
owner: you
created_at: "2026-06-21T00:00:00+00:00"
```

The controller should continue through direction choices and local reversible
risk. It should prepare drafts, not execute live external effects.
