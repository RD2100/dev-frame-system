# Recon Receipt: Obsidian Stage 4 Sync

## Target
- user_goal: Move the paper module toward the Codex + Obsidian self-growing research knowledge-base loop.
- target_repo_or_kb: D:\dev-frame-system
- current_slice_goal: Add a safe bidirectional-sync planning slice for generated paper notes.
- requested_outcome: Read one allowlisted Obsidian note through Local REST API, compare it with local generated Markdown, and emit a sync plan that protects user-authored content.
- date: 2026-06-24
- planner_agent_id: Codex

## Resource Map
- repository_roots:
  - D:\dev-frame-system
- important_dirs:
  - packages/ai-workflow-hub/src/ai_workflow_hub/context_layer/adapters
  - packages/ai-workflow-hub/tests
  - schemas
  - docs/status
- docs_read:
  - AGENTS.md
  - rules/recon.md
  - rules/open-source-reuse.md
  - docs/status/recon-receipt-obsidian-stage3.md
- packages_apps_modules:
  - obsidian_rest_api.py: scoped Local REST API client and push/probe helpers.
  - public_research_kb_pilot.py: generated paper notes, dashboard, public source/RAG/citation evidence.
- runtime_entrypoints:
  - aihub paper obsidian-rest-probe
  - aihub paper public-research-kb-pilot
- service_entrypoints:
  - Obsidian Local REST API on loopback.
- state_storage_locations:
  - Caller-provided vault target folder for Markdown.
  - Caller-provided runtime_dir for generated reports and indexes.
- external_integrations:
  - Obsidian Local REST API plugin.
  - Obsidian URI protocol.
  - Obsidian plugin Vault API semantics as the future plugin boundary.
- notable_generated_or_vendor_paths:
  - No external source vendored.
  - .devframe-runtime/atgo-runs for ignored execution evidence.
- license_files_found:
  - No third-party code copied into the repo in this slice.

## Core Concepts
- concepts:
  - Local file: generated Markdown currently on disk.
  - Remote note: current Obsidian note content returned by Local REST API.
  - Managed block: bounded DevFrame-owned region that can be safely updated.
  - User block: note content outside DevFrame managed markers, preserved by default.
  - Sync plan: non-mutating report that says create, update managed block, no-op, conflict, or blocked.
- architecture_style:
  - CLI adapter around mature Obsidian APIs; no custom plugin in this slice.
- execution_model:
  - Read only one allowlisted vault-relative path.
  - Produce a plan first; mutation remains explicit.
- review_model:
  - Focused unit tests prove token redaction, path safety, user-content preservation, and no accidental writes.
- evidence_model:
  - Reports contain statuses, fingerprints, and short action names, not note bodies or secrets.

## Core Data Models
- project/workspace: caller-provided vault and target folder.
- thread/session: one CLI/probe invocation.
- message/event: not applicable.
- tool_call: Local REST API GET/PUT/POST calls.
- terminal_run: pytest and CLI probe.
- diff/checkpoint: managed block fingerprints.
- review/evidence: @go evidence directory with diff, tests, guard, reviewer report, final report.
- policy/rules: no secret persistence, no full vault scan, no write outside allowlisted relative path.

## Capability Matrix
- capability_name: Obsidian REST read/write
  - location: external Local REST API plugin plus obsidian_rest_api.py adapter
  - maturity: external mature API, local adapter pilot
  - reusable_as_is: external API yes
  - reusable_with_adapter: yes
  - not_reusable: false
  - notes: Reuse GET/PUT/open endpoints; own only minimal report/safety semantics.
- capability_name: Obsidian plugin-native sync
  - location: Obsidian official Vault API
  - maturity: mature plugin API
  - reusable_as_is: later
  - reusable_with_adapter: later
  - not_reusable: false
  - notes: Official guidance distinguishes cached display reads from direct reads before modification; future plugin can use Vault.read/modify.
- capability_name: Git-based vault sync
  - location: Obsidian Git plugin
  - maturity: mature for backup/device sync
  - reusable_as_is: no
  - reusable_with_adapter: not for paper note merge semantics
  - not_reusable: true
  - notes: Useful for vault backup, not for DevFrame managed-block merge planning.

## Reuse Candidate List
- candidate: Obsidian Local REST API
  - source: https://github.com/coddingtonbear/obsidian-local-rest-api
  - exact_scope_to_reuse: authenticated scoped note GET/PUT/open and MCP bridge.
  - expected_adapter_work: token-safe client methods, path validation, non-mutating sync plan.
  - blocking_constraints: user must provide API key; plugin has had path traversal advisories, so adapter must reject unsafe paths before requests.
  - decision: adapt now.
- candidate: Obsidian official Vault API
  - source: https://docs.obsidian.md/Plugins/Vault
  - exact_scope_to_reuse: future plugin-side read/modify semantics.
  - expected_adapter_work: future TypeScript plugin or MCP bridge, not this CLI slice.
  - blocking_constraints: custom plugin packaging is premature.
  - decision: learn from semantics, defer implementation.
- candidate: Obsidian Git plugin
  - source: https://github.com/Vinzent03/obsidian-git
  - exact_scope_to_reuse: vault backup and cross-device sync.
  - expected_adapter_work: none for this slice.
  - blocking_constraints: does not manage DevFrame note schema or managed-block conflicts.
  - decision: reject for this slice.

## Integration Risk Table
- risk: remote note body leaks into report
  - type: privacy
  - severity: high
  - mitigation: report only fingerprints, byte/char counts, and action codes.
  - owner: paper module
- risk: unsafe vault path reaches Local REST API
  - type: security
  - severity: high
  - mitigation: reject empty, dot, dot-dot, and normalized traversal before HTTP.
  - owner: obsidian_rest_api.py
- risk: user notes overwritten
  - type: ux
  - severity: high
  - mitigation: this slice plans only; future writes must update managed block while preserving outside content.
  - owner: paper module
- risk: pluginization delayed
  - type: maintenance
  - severity: medium
  - mitigation: keep REST adapter thin and compatible with future plugin/MCP boundary.
  - owner: paper module

## Build-vs-Buy Decision
- must_reuse:
  - Obsidian Local REST API for live read/write.
  - Obsidian URI for local open links.
- should_adapt:
  - Official Vault API semantics for future plugin-side merge behavior.
- can_spike:
  - MCP bridge use after CLI sync plan is stable.
- must_build_new:
  - Token-safe sync plan report, managed-block comparison, and DevFrame-specific conflict statuses.
- rationale: The mature API surfaces already exist; DevFrame should own only paper schema, evidence, safety, and merge policy.

## Unknowns / Questions
- unanswered_items:
  - Whether user's final vault flow prefers REST-only, MCP, or a custom plugin UI.
  - Whether dashboard refresh should be triggered by CLI, Obsidian command, or scheduler.
- required_verification:
  - Unit tests with fake REST client.
  - CLI probe remains token-safe.
  - No full vault scan or note body persistence.
- experiments_needed:
  - Real key write/read smoke after user sets OBSIDIAN_REST_API_KEY locally.

## Recommended Next Slice
- smallest_safe_increment:
  - Add Local REST API read_note and build a non-mutating sync-plan report for one local Markdown file and one vault-relative note path.
- worker_type_needed:
  - One coding worker plus independent reviewer.
- files_or_modules_in_scope:
  - packages/ai-workflow-hub/src/ai_workflow_hub/context_layer/adapters/obsidian_rest_api.py
  - packages/ai-workflow-hub/tests/test_obsidian_rest_api.py
  - packages/ai-workflow-hub/src/ai_workflow_hub/cli.py
- files_or_modules_out_of_scope:
  - Custom Obsidian plugin source.
  - Full vault scan.
  - Scheduler.
  - Multi-agent paper analysis.
- evidence_required_for_completion:
  - Focused pytest passes.
  - py_compile passes.
  - @go evidence includes diff, tests, guard, review, and final report.
- review_gate_definition:
  - Block if token values, raw remote note bodies, absolute vault paths, or unsafe paths appear in reports; block if any default path writes to Obsidian without an explicit write flag.
