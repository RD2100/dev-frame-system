# Recon Receipt: workflow orchestration engine (M3)

> Governs write-capable work that adds a real multi-phase workflow engine over
> the team objects, per `rules/recon.md` recon-001/003/004/008/009 and
> `docs/agent-runtime/reuse-depth-review-method.md`. Pairs with
> `docs/status/local-agent-cluster-roadmap.md` (M3, critical path) and builds on
> `docs/status/recon-receipt-team-runtime.md` (M1).

## Target
- user_goal: "Trigger multiple agents into a collaborative workflow" with a
  controller deciding next moves — the literal definition of the agent cluster.
- target_repo_or_kb: `<repo-root>` (control-plane package).
- current_slice_goal: Slice 1 — a real phase-based workflow engine that drives a
  coding goal through recorded phases (plan -> execute -> review), records each
  phase transition and the controller's verdict as real team events (reusing the
  M1 `TeamRuntime` journal), and returns a structured result. It orchestrates the
  EXISTING executor (`go_dispatch`) and the EXISTING decision shape; it does not
  invent a new executor or a new model driver (that is M2/ACP).
- requested_outcome: `WorkflowEngine.run_coding_workflow(...)` produces a
  recorded, inspectable multi-phase collaboration with a real reviewer verdict
  derived from recorded task results; default/other code paths unchanged;
  hermetic verification (no tokens); full gates green.
- date: 2026-06-26
- planner_agent_id: kiro
- approval: Human owner authorized priority-ordered M1->M2->M3 progression with
  full automation and a final comprehensive independent review.

## Resource Map
- packages_apps_modules: `packages/control-plane/control_plane`
- reuse targets:
  - `control_plane/go_dispatch.py` — `run_go_dispatch` (prepare), `execute_go_run`
    (execute), already records team task events via `TeamRuntime`.
  - `control_plane/team_runtime.py` — `TeamRuntime` recorder +
    `build_team_runtime_view` reader (M1).
  - `control_plane/decision_engine.py` — existing `DecisionMode`
    (continue/revise/stop/escalate) shape used across the read model.
- read model: `visual_state.py` `_build_team_model` (event_log, message_bus).
- schema: `schemas/visual_control_plane_state.schema.json` `team_event` /
  `team_message` shapes (reused; no schema change).

## Core Concepts
- roles: coordinator (plan), executor(s) (run shards), reviewer (verdict).
- execution_model: phases run sequentially; the execute phase reuses the
  write-set-serialized, optionally isolated parallel executor.
- decision_model: the reviewer phase computes a verdict (continue/revise/stop)
  from recorded task_result statuses — a real controller decision, recorded.

## Capability Matrix
- multi-phase orchestration
  - location: none today; role phases are implicit in `/go` (prepare+execute) and
    projected gates.
  - maturity: absent as an explicit engine.
  - reusable_with_adapter: the executor and team journal are reused; the engine
    is the new thin conductor.
- decision shape
  - location: `decision_engine.py` DecisionMode enum.
  - reusable_as_is: YES (verdict vocabulary).

## Reuse Candidate List
- candidate: `go_dispatch` prepare/execute + `TeamRuntime`
  - decision: REUSE as the executor and the recording substrate.
- candidate: ai-workflow-hub LangGraph orchestrator (other package)
  - decision: DEFER consolidation. recon-008 note: the roadmap calls for merging
    the two orchestrators into one source of truth; this slice does NOT merge
    them (out of scope), it adds the control-plane-native engine first and
    records the consolidation as future work to avoid a large risky rewrite.

## Integration Risk Table
- risk: a new engine duplicates/forks orchestration logic.
  - type: coupling | severity: medium
  - mitigation: the engine is a thin conductor that REUSES go_dispatch and the
    team journal; it adds phase/verdict recording, not a second executor.
    Consolidation with ai-workflow-hub is explicitly deferred and recorded.
- risk: recording workflow events changes the existing read model / tests.
  - type: correctness | severity: medium
  - mitigation: workflow events use new event types folded additively into
    event_log/message_bus; runs without workflow events are unchanged. Full
    pytest + wheel smoke gate it.
- risk: the engine spends tokens during tests.
  - type: cost | severity: high
  - mitigation: the engine accepts a `worker_command` override; tests use a
    trivial cross-platform no-op command worker. No OpenCode in tests.

## Build-vs-Buy Decision
- must_reuse: `go_dispatch` executor, `TeamRuntime` journal, `DecisionMode`
  verdict vocabulary, existing schema team_* shapes.
- must_build_new: `control_plane/workflow_engine.py` (the phase conductor +
  verdict) and `TeamRuntime.record_workflow_event`; a read-side fold of
  workflow_* events.
- rationale: the executor and recording substrate exist and are tested; the new
  thing is an explicit, recorded, role-phased controller loop.

## Unknowns / Questions
- Consolidating control-plane rdgoal vs ai-workflow-hub LangGraph into one
  source of truth (deferred; large).
- Live multi-agent driving (M2/ACP) — the executor here is still CLI-subprocess.

## Recommended Next Slice (this receipt unlocks)
- smallest_safe_increment: `WorkflowEngine.run_coding_workflow` driving
  plan -> execute -> review with recorded phase events and a recorded verdict;
  read-side fold of workflow events; hermetic tests; optional thin CLI surface.
- worker_type_needed: planner-implemented spike adopted after the final
  comprehensive independent review (recon-004).
- files_in_scope: `control_plane/workflow_engine.py` (new),
  `control_plane/team_runtime.py` (record + fold workflow events),
  `control_plane/cli/` (optional `devframe workflow` surface).
- files_out_of_scope: ai-workflow-hub consolidation, ACP/live driving, schema.
- evidence_required_for_completion: hermetic tests (phases recorded, verdict
  correct, no-op worker); full `python -m pytest -q` green;
  `verify-public-snapshot.ps1` and `verify-control-plane-wheel.ps1` green;
  covered by the final comprehensive independent review.

## Deferred (require updated receipt)
- Merge control-plane and ai-workflow-hub orchestrators into one engine.
- Drive the execute phase over ACP live sessions (M2) instead of CLI subprocess.
- Reviewer phase using a real reviewer agent (not just status aggregation).
