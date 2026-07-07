# Recon Receipt: real multi-agent team runtime (M1)

> Governs write-capable work that turns the *projected* team objects into real,
> recorded runtime objects, per `rules/recon.md` recon-001/003/008/009 and
> `docs/agent-runtime/reuse-depth-review-method.md`. Pairs with
> `docs/status/local-agent-cluster-roadmap.md` (M1, critical path).

## Target
- user_goal: A mature, T3Code-like governed agent cluster where multiple agents
  collaborate; the team must be modeled as first-class runtime objects, not
  inferred from parallel runs (recon-008).
- target_repo_or_kb: `<repo-root>` (control-plane package).
- current_slice_goal: Slice 1 — make the **Event Log** and **Message Bus** real,
  durable, recorded-at-runtime objects for `/go` execution, instead of values
  synthesized at read time. Other team objects stay projected (declared below).
- requested_outcome: When agents actually execute, the controller records real
  team events (task created/claimed, handoff, result) to a durable journal
  outside the repo; the read model surfaces those real records (real-first,
  projection as fallback). Default/no-execute paths stay byte-identical. Hermetic
  verification; full gates green.
- date: 2026-06-26
- planner_agent_id: kiro
- approval: Human owner authorized priority-ordered M1->M2->M3 progression with
  full automation and mandatory independent review.

## Resource Map
- repository_roots: `<repo-root>`
- packages_apps_modules: `packages/control-plane/control_plane`
- runtime_entrypoints: `cli/` (devframe code/go), `go_dispatch.py`
  (`run_go_dispatch`, `_execute_parallel` -> `_run_group` ->
  `_run_agent_in_place`).
- state_storage_locations (reuse target): `control_plane/runtime_store.py`
  (`RuntimeStore` append-only JSONL journal `rdgoal-events.jsonl`, with an
  outside-repo guard) + `JournalEvent` dataclass.
  `control_plane/orchestrator.py` already appends lifecycle events
  (project_registered, status_changed, decision_made,
  execution_report_ingested).
- read model: `control_plane/visual_state.py` `_build_team_model` and its
  `_team_message_bus` / `_team_event_log` / `_team_task_board` (today these
  SYNTHESIZE team objects from dispatches/runs/gates at read time).
- schema: `schemas/visual_control_plane_state.schema.json` already defines
  `team_message`, `team_event`, `team_task`, `team_agent`, etc.
- external_integrations: OpenCode executor (driven via CLI subprocess).
- license_files_found: repo `LICENSE` (public distribution).

## Core Concepts
- execution_model: controller prepares rdgoal packets, then `_execute_parallel`
  runs grouped agents (write-set serialized; optional `--isolate` worktrees).
- review_model: ExecutionReport ingested -> acceptance gate (projected).
- evidence_model: packets/reports under runtime-dir outside repo; journal JSONL.

## Core Data Models (slice scope)
- message/event: reuse `JournalEvent {event_type, project_id, payload,
  timestamp, event_id}` persisted append-only as JSONL.
- task: a go-run agent (agent_id, shard, targets) becomes a Task with a
  lifecycle (created -> claimed -> done/failed) recorded as events.
- agent: agent_id already stable (`coding-agent-N`); registry stays projected.

## Capability Matrix
- durable event journal
  - location: `control_plane/runtime_store.py`
  - maturity: production (used by orchestrator; outside-repo guard; tested).
  - reusable_as_is: YES for append/read JSONL semantics and safety guard.
  - notes: hardcodes filename `rdgoal-events.jsonl`; slice uses a dedicated
    `team-events.jsonl` to avoid polluting the existing digest.
- team object projection
  - location: `visual_state.py` `_build_team_model`
  - maturity: production read model, but values are synthesized, not recorded.
  - reusable_with_adapter: YES — keep as fallback; prefer recorded events when
    present.

## Reuse Candidate List
- candidate: `RuntimeStore` + `JournalEvent`
  - source: in-repo `control_plane/runtime_store.py`
  - exact_scope_to_reuse: append-only JSONL persistence + outside-repo guard +
    event dataclass shape.
  - expected_adapter_work: a thin `TeamRuntime` that writes a dedicated
    `team-events.jsonl` and a reader that folds events into schema-shaped
    message_bus/event_log/task_board entries.
  - decision: REUSE (no new dependency, no hand-rolled persistence).
- candidate: existing `_team_*` projection functions
  - decision: KEEP as fallback; do not delete (backward compatible).

## Integration Risk Table
- risk: recording team events changes the existing read model / breaks tests.
  - type: correctness | severity: high
  - mitigation: record ONLY in the execution path (when agents actually run).
    Prepare-only `/go` (the wheel smoke and most tests) writes no team events,
    so projection is unchanged. Read model is real-first only when a run has
    recorded events. Full pytest + wheel smoke are the gate.
- risk: journal path leaks into the public repo.
  - type: privacy/public-surface | severity: medium
  - mitigation: reuse `RuntimeStore`'s outside-repo guard; journal lives under
    runtime-dir. Read model surfaces summaries, not absolute journal paths.
- risk: doing too much (all 7 team objects at once).
  - type: coupling | severity: medium
  - mitigation: slice limited to Event Log + Message Bus + minimal Task
    lifecycle. Agent Registry, Evidence Store, Review Gate, Conflict Control
    stay projected and are explicitly declared deferred (recon-008 subset rule).

## Build-vs-Buy Decision
- must_reuse: the `RuntimeStore`/`JournalEvent` persistence *pattern* (append-only
  JSONL + outside-repo guard shape) and the existing schema team_* shapes;
  existing projection as fallback.
- must_build_new: a thin `control_plane/team_runtime.py` (`TeamRuntime` recorder
  + `build_team_runtime_view` reader) and the go_dispatch wiring to emit real
  events during execution. Note: `TeamRuntime` reimplements the small JSONL
  append/read+guard rather than importing `RuntimeStore`, because `RuntimeStore`
  hardcodes its filename (`rdgoal-events.jsonl`) and a different event shape;
  this is acknowledged pattern-reuse (~30 lines), not code-reuse. A future
  cleanup could parameterize `RuntimeStore`'s filename to share the code.
- rationale: persistence and safety patterns already exist and are tested; the
  genuinely new thing is recording real team facts at runtime and reading them
  back.

## Unknowns / Questions
- How richly to model handoff vs message vs event in slice 1 — kept minimal:
  one `task_created`, one `task_claimed`, one `result`/`handoff` per agent.
- Future slices: Agent Registry as real runtime presence; Conflict Control from
  real worktree ownership; Review Gate verdicts recorded (not projected).

## Recommended Next Slice (this receipt unlocks)
- smallest_safe_increment: `team_runtime.py` (recorder + reader) + go_dispatch
  emits real team events during `_execute_parallel`; `visual_state` prefers
  recorded events when present, else falls back to projection.
- worker_type_needed: planner-implemented spike adopted after independent review
  (recon-004).
- files_in_scope: `control_plane/team_runtime.py` (new), `control_plane/go_dispatch.py`,
  `control_plane/visual_state.py`.
- files_out_of_scope: schema (reuse existing team_* shapes), T3 adapter, CLI,
  the other four team objects.
- evidence_required_for_completion: hermetic tests for record+read and
  projection-fallback; full `python -m pytest -q` green; `verify-public-snapshot.ps1`
  and `verify-control-plane-wheel.ps1` green; independent reviewer verdict.
- review_gate_definition: PASS requires real recorded events surfaced, no
  default-path regression, journal stays outside repo, projection preserved as
  fallback.

## Deferred (require updated receipt)
- Agent Registry / Evidence Store as real recorded runtime objects (currently
  projected). Task Board status is projected from go-run metadata.
- Real inter-agent message passing (agent-to-agent), task claim contention, and
  blackboard/shared memory.

## Delivered slices
- **Slice 1** (Event Log + Message Bus): `team_runtime.py` records
  `task_created`/`task_claimed`/`task_result` to `team-events.jsonl` during
  execution; read model surfaces them real-first. Reviewed PASS-WITH-NITS; nits
  resolved (full-schema e2e validation, `.gitignore` journal names, wording).
- **Slice 2** (Conflict Control + Review Gate): `build_team_runtime_view` now
  also derives `conflict_control` (file ownership from each task's recorded
  targets) and `review_gates` (acceptance facts from each recorded task result)
  from the SAME durable events — no extra recording, no extra write risk. Merged
  into the read model real-first. So 4 of 7 team objects (Event Log, Message Bus,
  Conflict Control, Review Gate) are now real recorded objects; Agent Registry,
  Task Board, and Evidence Store remain projected (deferred above).
