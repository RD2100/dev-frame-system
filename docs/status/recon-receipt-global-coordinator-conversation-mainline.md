# Recon Receipt: Global Coordinator conversation mainline

> Governs write-capable work that turns the "总控" from a monitoring card inside
> the control plane into the primary conversation-shaped coordination surface,
> per `rules/recon.md` recon-001/003/005/008/009 and
> `rules/open-source-reuse.md` reuse-000/001/002/003/006.

## Target

- user_goal: Build a real Global Coordinator ("总控") that can talk, remember,
  decide, dispatch, and escalate across projects, instead of a read-only panel
  item.
- target_repo_or_kb: `<repo-root>`
- current_slice_goal: Lock the product boundary and build-vs-buy decision
  before more write-capable work lands in the cluster/control-plane/client area.
- requested_outcome: A durable decision doc that says what "总控" is, what it is
  not, which open-source systems must be reused, which DevFrame-owned seams must
  remain custom, and what order to implement next.
- date: 2026-06-30
- planner_agent_id: `codex-controller`

## Resource Map

- repository_roots:
  - `<repo-root>`
- top_level_tree:
  - `docs/status/`: product direction, recon receipts, reuse assessments, and
    roadmap artifacts.
  - `rules/`: recon/reuse governance.
  - `packages/control-plane/`: current control-plane runtime, dashboard, client
    contract, cluster runtime, team runtime, ACP integration, and read model.
  - `packages/ai-workflow-hub/`: workflow/orchestration experiments and
    LangGraph-bearing package.
- important_dirs:
  - `docs/status`
  - `rules`
  - `packages/control-plane/control_plane`
  - `packages/ai-workflow-hub/src/ai_workflow_hub`
- docs_read:
  - `docs/status/cluster-coordinator-design-and-roadmap.md`
  - `docs/status/local-agent-cluster-roadmap.md`
  - `docs/status/local-agent-control-plane-stage-8-open-source-reuse-visual-mvp.md`
  - `docs/status/recon-receipt-team-runtime.md`
  - `docs/status/recon-receipt-local-agent-client-mainline.md`
  - `rules/recon.md`
  - `rules/open-source-reuse.md`
- packages_apps_modules:
  - `control_plane.cluster_control`
  - `control_plane.cluster_run`
  - `control_plane.team_runtime`
  - `control_plane.visual_state`
  - `control_plane.client_manifest`
  - `control_plane.t3_bridge_bundle`
  - `ai_workflow_hub` (LangGraph-bearing orchestration package)
- runtime_entrypoints:
  - `devframe code`
  - `devframe workflow`
  - `devframe dashboard serve`
  - `devframe client`
  - `/api/t3/cluster-run`
  - `/api/t3/cluster-runs`
  - `/api/t3/cluster-run-events`
  - `/api/t3/cluster-run-agent`
- ui_entrypoints:
  - RD-Code / T3Code-derived client shell
  - current dashboard/control-plane view
  - current "总控" entry
- state_storage_locations:
  - runtime journals and cluster records under ignored runtime dirs
  - durable product/recon docs under `docs/status/`
- external_integrations:
  - T3Code / RD-Code: visual client reuse candidate
  - OpenCode: local coding-agent runtime
  - ACP: live agent execution backbone
  - LangGraph: preferred orchestration/state-machine reuse candidate
- notable_generated_or_vendor_paths:
  - `.devframe-runtime/external/t3code/` (external client checkout, outside the
    public repo)
  - no vendored orchestration/client source is allowed without reuse-004 review
- license_files_found:
  - public repo `LICENSE`
  - external candidates currently treated as MIT candidates based on prior
    project assessment; each import still requires exact source/license review

## Core Concepts

- concepts:
  - Global Coordinator (总体主控 / 总控)
  - Project Coordinator (项目级主控)
  - goal conversation
  - native chat vs team conversation
  - coordination policy
  - human escalation
  - agent roster
  - shared state / message bus / evidence store
- architecture_style:
  - reuse-first client shell + reuse-first orchestration core + DevFrame-owned
    governance and read model
- execution_model:
  - the Global Coordinator receives a goal, spawns or resumes a Project
    Coordinator, dispatches member agents, and keeps the conversation live until
    the goal is resolved or escalated
- session_model:
  - one goal = one team conversation; normal native chat remains a separate
    conversation kind
- review_model:
  - the conversation is the operating surface; the dashboard is monitoring and
    configuration only; approvals remain governed human gates
- evidence_model:
  - runtime facts, review gates, reports, and decision traces stay DevFrame
    owned even when client shell and orchestration mechanics are reused

## Problem Statement (from the current product state)

The current product is directionally correct but structurally wrong at the
"总控" surface:

1. the Global Coordinator is still represented like a monitoring item inside a
   page, not like a first-class conversation;
2. a new conversation is not project-aware enough at creation time;
3. the composition still feels like "a dashboard plus some cluster controls",
   not "a living coordinator replacing most of the user's decision fatigue";
4. the input/workbench shell is visually unstable enough that it reads as an
   unfinished control panel, not a mature daily cockpit;
5. the current cluster runtime can stream and drill down, but the product's
   top-level interaction model still does not expose the coordinator as the
   primary surface.

This is a product-boundary problem before it is a styling problem.

## Capability Matrix

- coordinator conversation shell
  - location: RD-Code / T3Code conversation UI + DevFrame client bridge
  - maturity: mature external shell candidate + partial internal bridge
  - reusable_as_is: no
  - reusable_with_adapter: yes
  - not_reusable: no
  - notes: reuse the shell and conversation ergonomics; DevFrame owns the
    meaning of the conversation
- multi-agent orchestration engine
  - location: current `team_runtime` + `cluster_run` + `workflow_engine` +
    `ai_workflow_hub`
  - maturity: partial in-repo implementation, but not yet a complete
    conversation-native coordinator runtime
  - reusable_as_is: no
  - reusable_with_adapter: yes, via LangGraph
  - not_reusable: no
  - notes: do not continue hand-rolling a full orchestration framework inside
    control-plane modules
- coding-agent execution backbone
  - location: OpenCode + ACP-backed execution path
  - maturity: strong
  - reusable_as_is: yes, with DevFrame governance wrapping
  - reusable_with_adapter: yes
  - not_reusable: no
  - notes: keep using OpenCode/ACP for execution; no need to replace this layer
    to fix the "总控" problem
- governance / evidence / review / gates
  - location: DevFrame control plane
  - maturity: DevFrame-owned core
  - reusable_as_is: no
  - reusable_with_adapter: no
  - not_reusable: yes
  - notes: this is the real product moat and must remain DevFrame-owned

## Reuse Candidate List

- candidate: T3Code / RD-Code shell
  - source: `https://github.com/pingdotgg/t3code`
  - exact_scope_to_reuse: conversation shell, workbench layout, project/thread
    navigation, editor-like coordination surface patterns
  - expected_adapter_work: make "总控" a first-class conversation entry, expose
    project binding and goal-conversation creation, keep dashboard as
    monitoring/config only
  - blocking_constraints: must not let reused shell become the source of truth
    for governance or state semantics
  - decision: must_reuse

- candidate: LangGraph
  - source: `https://github.com/langchain-ai/langgraph`
  - exact_scope_to_reuse: stateful multi-agent orchestration, durable workflow
    graph, supervisor/sub-agent handoff model, resumable execution
  - expected_adapter_work: map Global Coordinator / Project Coordinator /
    member-agent semantics onto a LangGraph-based orchestration core; project the
    runtime back into DevFrame's read model and evidence model
  - blocking_constraints: must not bypass DevFrame review/evidence/gate objects;
    LangGraph is the orchestration engine, not the governance owner
  - decision: must_reuse

- candidate: OpenCode + ACP
  - source: existing DevFrame/OpenCode integration
  - exact_scope_to_reuse: local coding-agent execution, session driving,
    permission-gated tool execution
  - expected_adapter_work: none beyond continuing current integration and
    feeding the orchestration layer
  - blocking_constraints: execution remains subordinate to coordinator policy and
    human gates
  - decision: must_reuse

- candidate: CrewAI
  - source: `https://github.com/crewAIInc/crewAI`
  - exact_scope_to_reuse: high-level crew/flow patterns only, if at all
  - expected_adapter_work: substantial; would overlap too much with DevFrame's
    own governance model and product shell
  - blocking_constraints: stronger product opinion, weaker fit for "DevFrame
    owns control plane semantics"
  - decision: reject_for_mainline

- candidate: Microsoft Agent Framework
  - source: Microsoft Agent Framework
  - exact_scope_to_reuse: future comparative benchmark for orchestration,
    checkpoints, A2A, and AG-UI
  - expected_adapter_work: high; ecosystem and integration cost are currently
    higher than LangGraph for this repo
  - blocking_constraints: would introduce a second orchestration worldview while
    the current repo already carries LangGraph-compatible direction
  - decision: keep_as_secondary_research

- candidate: OpenHands
  - source: `https://github.com/All-Hands-AI/OpenHands`
  - exact_scope_to_reuse: ideas and possibly future worker/runtime references
  - expected_adapter_work: high if used as a primary shell/runtime
  - blocking_constraints: too large a product overlap for the current mainline
  - decision: reject_for_mainline

## Integration Risk Table

- risk:
  - type: ux
  - severity: high
  - mitigation: define "总控 = conversation" as a product law; do not allow it
    to remain a panel card or dashboard module
  - owner: planner/product

- risk:
  - type: coupling
  - severity: high
  - mitigation: keep DevFrame governance, evidence, review, and gates outside
    the reused orchestration/client code; use thin adapters instead of deep
    entanglement
  - owner: planner/reviewer

- risk:
  - type: maintenance
  - severity: high
  - mitigation: stop expanding ad hoc internal orchestration logic across
    `cluster_*`, `workflow_engine`, and UI glue without a single reused engine
  - owner: planner

- risk:
  - type: architecture
  - severity: medium
  - mitigation: explicitly separate normal native chat from team conversation;
    one goal always maps to one coordinator-owned conversation
  - owner: planner/product

- risk:
  - type: unknown
  - severity: medium
  - mitigation: validate LangGraph fit through a thin adapter spike first, not a
    full migration in one shot
  - owner: planner

## Build-vs-Buy Decision

- must_reuse:
  - T3Code / RD-Code for the conversation/workbench shell
  - LangGraph for the coordinator/sub-agent orchestration engine
  - OpenCode/ACP for coding-agent execution

- should_adapt:
  - current DevFrame team runtime, cluster runs, and visual state as the
    governance/read-model projection layer over the reused orchestration engine
  - current dashboard as monitoring/configuration only

- can_spike:
  - a thin LangGraph-backed Global Coordinator adapter
  - a "总控会话 first" RD-Code entrypoint and project-bound goal creation flow

- must_build_new:
  - DevFrame-specific goal/project/conversation identity model
  - human escalation policy model
  - governance/read-model projection from orchestration facts to DevFrame
    evidence, gates, decisions, and conflict control

- rationale:
  - the hot-path multi-agent market has already validated that conversation
    shell, orchestration engine, and worker runtime are all mature capability
    domains; DevFrame's leverage is not re-implementing those from zero, but
    making them governed, attributable, inspectable, and low-attention for the
    user

## Product Laws (must not regress)

1. **The Global Coordinator is a conversation, not a dashboard card.**
2. **One goal equals one Project Coordinator conversation.**
3. **Dashboard is monitoring/configuration only, not the main interaction
   surface.**
4. **A new goal must bind to a project at creation time.**
5. **The coordinator exists to replace user attention, not to ask the user to
   drive the runtime manually.**

## Recommended Next Slice

- smallest_safe_increment:
  - make the RD-Code "总控" entry open a real coordinator conversation shell,
    not a message card/panel
  - let "new goal" explicitly choose target project + coordinator mode
  - keep the current dashboard as secondary monitoring

- worker_type_needed:
  - planner-owned design slice, then coder worker implementation against an
    approved adapter boundary

- files_or_modules_in_scope:
  - RD-Code/T3Code client shell entry flow
  - DevFrame client bridge / coordinator conversation contract
  - a thin LangGraph evaluation spike doc or adapter seam

- files_or_modules_out_of_scope:
  - full orchestration migration
  - replacing ACP/OpenCode
  - changing review/evidence/gate semantics

- evidence_required_for_completion:
  - visual acceptance: the first-class "总控" conversation can be opened and used
    like a normal chat
  - product acceptance: creating a new goal requires project binding
  - architecture acceptance: LangGraph reuse boundary recorded before more
    hand-written orchestration code lands

- review_gate_definition:
  - reject any slice that keeps "总控" as a dashboard widget or that adds more
    bespoke orchestration code without recording the LangGraph reuse boundary

- implementation_brief:
  - `docs/status/phase-1-global-coordinator-conversation-plan.md`

## Phase Plan

- **Phase 1 — Conversation-first shell correction**
  - "总控" becomes a first-class conversation entry in RD-Code
  - new goal flow binds project + coordinator target up front
  - fix input/workbench shell instability so the coordinator feels like a daily
    cockpit, not a diagnostics pane

- **Phase 2 — LangGraph-backed Project Coordinator seam**
  - introduce a thin LangGraph adapter for Project Coordinator execution
  - keep DevFrame read model/evidence/gates as the outer system of record
  - do not migrate everything at once

- **Phase 3 — Global Coordinator policy engine**
  - persistent singleton total-control conversation
  - human escalation policy
  - cross-project coordination and unbounded concurrent goals

- **Phase 4 — Full team-object maturity**
  - message bus, shared state/blackboard, review gates, conflict control, and
    agent drill-down all run as first-class runtime facts over the reused
    orchestration core

## Decision Summary

The mainline is:

- **UI shell:** RD-Code / T3Code
- **orchestration core:** LangGraph
- **executor backbone:** OpenCode / ACP
- **DevFrame-owned moat:** governance, evidence, review, gates, project
  context, state projection, and human escalation semantics

Any future slice that drifts back toward "dashboard-first total control" or
"continue hand-rolling the orchestrator" should be treated as off-mainline.
