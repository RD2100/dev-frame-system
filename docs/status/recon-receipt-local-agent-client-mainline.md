# Recon Receipt: Local Agent Client Mainline

Date: 2026-06-24
Planner: `codex-controller`
Status: `approved-for-next-slice`

## Target

- user_goal: Build DevFrame as a local native/desktop Agent Control Plane where the user can see multiple agent tasks, handoffs, review, evidence, and next actions.
- target_repo_or_kb: `D:\dev-frame-system`, with external candidates T3Code, OpenCode, CodexPro, and DevSpace.
- current_slice_goal: Preserve the client mainline direction and make future write-capable work depend on a directory-level recon and reuse decision.
- requested_outcome: Stop blind hand-rolling, use T3Code/OpenCode/CodexPro/DevSpace as evaluated resources, and continue development through OpenCode workers under @go review.
- planner_agent_id: `codex-controller`

## Resource Map

- repository_roots:
  - `D:\dev-frame-system`
- top_level_tree:
  - `AGENTS.md`: public project instructions and agent entry rules.
  - `rules/`: governance rules.
  - `docs/agent-runtime/`: runtime contracts, visual control-plane docs, and dispatch protocol.
  - `docs/status/`: public-safe milestone reports and reuse assessments.
  - `packages/control-plane/`: local Agent Control Plane read model, dashboard, client launch plan, T3 bridge, Web AI probes, and OpenCode dispatch surfaces.
  - `packages/ai-workflow-hub/`: OpenCode-oriented workflow and readiness references.
  - `schemas/`: public JSON contracts.
  - `scripts/`: verification runners.
  - `tools/`: @go evidence tooling and local wrapper.
- important_dirs:
  - `packages/control-plane/control_plane`
  - `packages/control-plane/tests`
  - `schemas`
  - `rules`
  - `docs/status`
- docs_read:
  - `AGENTS.md`
  - `rules/open-source-reuse.md`
  - `rules/recon.md`
  - `docs/status/t3code-client-mainline-reuse-assessment.md`
  - `docs/status/devframe-code-opencode-handoff.md`
  - `docs/agent-runtime/visual-control-plane.md`
  - `docs/agent-runtime/web-ai-adapter-contract.md`
  - `docs/agent-runtime/sub-agent-dispatch-protocol.md`
  - `C:\Users\RD\Downloads\deep-research-report.md`
- packages_apps_modules:
  - `control_plane.client_launcher`: zero-config local client launch plan.
  - `control_plane.client_manifest`: read-only native-client manifest.
  - `control_plane.t3_adapter`: DevFrame state projection into T3 shell shape.
  - `control_plane.t3_bridge_bundle`: installable bridge bundle for non-vendored T3Code checkouts.
  - `control_plane.provider_binding_probe`: summary-only CodexPro/DevSpace probe shapes.
  - `control_plane.playwright_bridge`: explicit Web GPT review submission fallback.
- runtime_entrypoints:
  - `devframe client`
  - `devframe client plan`
  - `devframe client t3desktop`
  - `devframe code`
  - `devframe web-ai probe`
  - `devframe web-ai live-check`
  - `devframe web-ai submit-review`
  - `tools/devframe-go.ps1`
- ui_entrypoints:
  - `/client-plan.json`
  - `/client-manifest.json`
  - `/t3-bridge.json`
  - `/t3-shell.json`
  - `/state.json`
  - `/actions.json`
  - `/go/dispatch`
  - lightweight dashboard at `/`
- service_entrypoints:
  - `control_plane.dashboard.build_dashboard_server`
  - `control_plane.dashboard.serve_dashboard`
- state_storage_locations:
  - ignored runtime state under `.devframe-runtime/`
  - public-safe schemas and docs under `schemas/` and `docs/`
- external_integrations:
  - T3Code: primary native client and project/thread/session UI reference.
  - OpenCode: local coding-agent runtime and worker backend.
  - CodexPro: Web AI to local repository MCP bridge reference.
  - DevSpace: allowed-roots/OAuth/worktree MCP bridge reference.
  - Web GPT: external reviewer through explicit context package fallback.
- notable_generated_or_vendor_paths:
  - No external source should be vendored into this public repo without `rules/open-source-reuse.md` review.
  - Runtime evidence belongs under ignored `.devframe-runtime/`.
- license_files_found:
  - T3Code and OpenCode are treated as MIT reuse candidates based on prior assessment.
  - Any source import still requires source URL, revision, license, and attribution review.

## Core Concepts

- concepts:
  - Local Agent Control Plane
  - external-brain workflow
  - Recon Gate
  - Reuse Gate
  - native client mainline
  - OpenCode worker runtime
  - Web GPT external reviewer
  - evidence and review gates
- domain_terms:
  - project, workspace, thread, session, turn, activity, checkpoint, agent, task, message, event, evidence, gate, decision, action.
- architecture_style:
  - Provider-neutral control plane with reused client/runtime surfaces and DevFrame-owned governance.
- execution_model:
  - Planner defines goal and slice, OpenCode coder workers implement, independent reviewer reviews, finalizer validates evidence.
- session_model:
  - `DevFrameSession` is provider-neutral; T3-compatible shell is a projection, not canonical state.
- review_model:
  - Local reviewer gate plus optional Web GPT external review via explicit submission package.
- evidence_model:
  - diffs, test logs, safety reports, chain evidence, review reports, Recon Receipts, and final reports.

## Core Data Models

- project/workspace:
  - DevFrame project contract and T3 project projection.
- thread/session:
  - DevFrame sessions projected into T3 thread/session views.
- message/event:
  - Needed next for real multi-agent team communication; currently partially represented by sessions/actions/runs.
- tool_call:
  - Worker/runtime events should come from OpenCode or compatible executor adapters.
- terminal_run:
  - Mature capability domain; must be reused/adapted, not hand-rolled without exception memo.
- diff/checkpoint:
  - T3Code checkpoint concepts and OpenCode output are reuse references; DevFrame owns evidence meaning.
- review/evidence:
  - @go evidence package and Web GPT review artifacts.
- policy/rules:
  - `rules/recon.md`, `rules/open-source-reuse.md`, SADP, and public-surface rules.

## Capability Matrix

- native_client_shell:
  - location: T3Code `apps/desktop` and DevFrame `client_launcher` bridge.
  - maturity: external candidate.
  - reusable_as_is: no.
  - reusable_with_adapter: yes.
  - not_reusable: no.
  - notes: T3Code should be primary client shell reference; DevFrame owns governance.
- project_thread_session_ui:
  - location: T3Code `apps/web`, `packages/contracts`, `client-runtime`.
  - maturity: external candidate.
  - reusable_as_is: no.
  - reusable_with_adapter: yes.
  - not_reusable: no.
  - notes: use as projection target and UI model.
- coding_worker_runtime:
  - location: OpenCode CLI/server/SDK/runtime.
  - maturity: external candidate.
  - reusable_as_is: partially.
  - reusable_with_adapter: yes.
  - not_reusable: no.
  - notes: OpenCode should be default worker backend, not product identity.
- web_ai_mcp_bridge:
  - location: CodexPro/DevSpace patterns; DevFrame `provider_binding_probe` and `mcp_live_probe`.
  - maturity: mainline for MCP live-check; ZIP/report submit-review remains fallback/review evidence only.
  - reusable_as_is: no.
  - reusable_with_adapter: yes.
  - not_reusable: no.
  - notes: `devframe web-ai probe` remains summary-only; `devframe web-ai live-check` is the mainline MCP live-check boundary. ZIP/report is fallback only. Remaining gap is real ChatGPT Developer Mode invocation through HTTPS tunnel.
- recon_gate:
  - location: DevFrame `rules/recon.md`.
  - maturity: DevFrame-owned governance.
  - reusable_as_is: n/a.
  - reusable_with_adapter: n/a.
  - not_reusable: yes.
  - notes: must be enforced by plans, manifests, review packages, and future guards.
- multi_agent_team_model:
  - location: DevFrame-owned future model.
  - maturity: missing mainline capability.
  - reusable_as_is: no.
  - reusable_with_adapter: partially via T3/OpenCode events.
  - not_reusable: no.
  - notes: implement Agent Registry, Task Board, Message Bus, Event Log, Evidence Store, Review Gate, and Conflict Control as DevFrame objects.

## Reuse Candidate List

- candidate: T3Code
  - source: `https://github.com/pingdotgg/t3code`
  - exact_scope_to_reuse: native desktop shell, project/thread/session/timeline/checkpoint interaction patterns, T3-compatible shell projection target.
  - expected_adapter_work: DevFrame read model to T3 shell/bridge, read-only launch plan, future write gates.
  - blocking_constraints: no vendoring without license/source/revision review; provider runtime must not become governance truth.
  - decision: should_adapt
- candidate: OpenCode
  - source: `https://github.com/anomalyco/opencode`
  - exact_scope_to_reuse: local coding-agent worker runtime, server/API/session/log/event outputs.
  - expected_adapter_work: worker reports, evidence extraction, task ownership, conflict control.
  - blocking_constraints: DevFrame must own task graph, evidence, review, and merge policy.
  - decision: should_adapt
- candidate: CodexPro
  - source: external Web AI MCP bridge reference.
  - exact_scope_to_reuse: ChatGPT Developer Mode / MCP bridge patterns, context handoff fallback.
  - expected_adapter_work: real MCP bridge profile and safety boundaries.
  - blocking_constraints: current DevFrame probe is summary-only; live bridge still needs validation.
  - decision: research_then_adapt
- candidate: DevSpace
  - source: external local workspace MCP bridge reference.
  - exact_scope_to_reuse: allowed roots, OAuth/owner approval, workspace/worktree bridge discipline.
  - expected_adapter_work: compatible Web AI adapter and project-root guard.
  - blocking_constraints: current DevFrame probe is summary-only; live bridge still needs validation.
  - decision: research_then_adapt

## Integration Risk Table

- risk: T3Code source import accidentally vendors external code into public repo.
  - type: license
  - severity: high
  - mitigation: keep reference checkout outside repo; import only after reuse-004 review.
  - owner: planner/reviewer
- risk: lightweight dashboard becomes main client by drift.
  - type: ux
  - severity: high
  - mitigation: manifest and launch plan must mark dashboard as auxiliary and T3Code as primary.
  - owner: planner
- risk: ZIP/report replaces MCP adapter.
  - type: architecture
  - severity: high
  - mitigation: keep ZIP/report under Evidence/Review Layer only.
  - owner: planner/reviewer
- risk: multi-agent support degenerates into parallel commands.
  - type: architecture
  - severity: high
  - mitigation: implement Agent Registry, Task Board, Message Bus, Event Log, Evidence Store, Review Gate, and Conflict Control.
  - owner: planner
- risk: OpenCode workers edit overlapping files.
  - type: maintenance
  - severity: medium
  - mitigation: use module leases/worktrees and serialized write sets.
  - owner: planner/executor

## Build-vs-Buy Decision

- must_reuse:
  - T3Code-inspired native client shell and project/thread/session interaction patterns.
  - OpenCode worker runtime for coding execution.
- should_adapt:
  - T3 shell projection, OpenCode evidence extraction, CodexPro/DevSpace Web AI bridge patterns.
- can_spike:
  - temporary ZIP/report review packages, dashboard-only diagnostics, non-vendored T3 bridge probes.
- must_build_new:
  - DevFrame Recon Gate, Agent Registry, Task Board, Message Bus, Evidence Graph, Review Gate, Conflict Control, provider-neutral state, and policy engine.
- rationale:
  - Existing projects cover client and worker mechanics, but not DevFrame's governance semantics or team communication contract.

## Unknowns / Questions

- unanswered_items:
  - Exact live T3Code desktop integration surface after current upstream changes.
  - Best OpenCode API surface for streaming worker events into DevFrame.
  - Real ChatGPT Developer Mode invocation through HTTPS tunnel (remaining gap after mainlining CodexPro/DevSpace MCP live path).
- required_verification:
  - Zero-config T3 desktop/native launch against DevFrame shell.
  - OpenCode worker session/event capture into DevFrame evidence.
  - Web AI adapter live MCP bridge spike separate from ZIP fallback.
- experiments_needed:
  - T3 desktop launch smoke.
  - OpenCode event-to-evidence mapping.
  - CodexPro/DevSpace live bridge validation.

## Recommended Next Slice

- smallest_safe_increment:
  - Expose this Recon Receipt and reuse decision in the client launch plan and visual client manifest so the native client can show the governance basis for the current mainline.
- worker_type_needed:
  - OpenCode coder worker.
- files_or_modules_in_scope:
  - `packages/control-plane/control_plane/client_launcher.py`
  - `packages/control-plane/control_plane/client_manifest.py`
  - `packages/control-plane/tests/test_client_launcher.py`
  - `packages/control-plane/tests/test_client_manifest.py`
  - `schemas/visual_client_manifest.schema.json` only if needed.
- files_or_modules_out_of_scope:
  - T3Code source imports.
  - provider runtime rewrites.
  - Web dashboard redesign.
  - real MCP bridge implementation.
- evidence_required_for_completion:
  - `diff.patch`
  - targeted pytest output
  - public snapshot verification
  - independent reviewer verdict
- review_gate_definition:
  - Reviewer must block if the slice hides the Recon Receipt, makes dashboard the mainline, treats ZIP/report as primary runtime, or claims live CodexPro/DevSpace integration without evidence.
