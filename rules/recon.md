# Reconnaissance Rules

These rules define the Repository / Knowledge Base Reconnaissance Protocol
(RKR). RKR turns "look at the directory first" into a governance gate, not a
suggestion.

## RULE recon-001: Recon Gate Before Write-Capable Work

- **Priority**: P0
- **Trigger**: Any task that creates, edits, vendors, wraps, or replaces a
  client, agent UI, session model, runtime, terminal, diff viewer, provider
  binding, MCP bridge, multi-agent surface, evidence store, review gate, or
  other mature capability area.
- **Rule**: The planner must produce an approved Recon Receipt before any
  coder worker receives write-capable instructions. Until the Recon Receipt is
  approved, workers are read-only.
- **Verification**: The plan, TaskSpec, review package, or evidence directory
  references a Recon Receipt ID or path.
- **Conflict Handling**: Missing Recon Receipt blocks the task. Do not replace
  the receipt with an informal chat summary.

## RULE recon-002: Directory-Level Resource Map Required

- **Priority**: P0
- **Trigger**: Recon Gate activation.
- **Rule**: The Recon Receipt must include a directory-level resource map:
  top-level tree, important apps/packages/docs/examples, runtime entrypoints,
  UI/client entrypoints, service entrypoints, state storage locations, external
  integrations, generated/vendor paths, and license files.
- **Verification**: Receipt includes concrete paths or inspected source names,
  not boolean self-attestation.
- **Conflict Handling**: If the directory cannot be fully inspected, record the
  blocker and downgrade the next slice to a spike or research task.

## RULE recon-003: Capability Matrix and Reuse Decision Required

- **Priority**: P0
- **Trigger**: Proposing or implementing a capability that may exist in this
  repo, a mature open-source project, or an approved runtime.
- **Rule**: The Recon Receipt must include a Capability Matrix, Reuse Candidate
  List, Integration Risk Table, and Build-vs-Buy Decision.
- **Verification**: The receipt names inspected candidates, the exact reuse or
  adapter boundary, rejected candidates, rejection reasons, and any custom code
  that DevFrame must own.
- **Conflict Handling**: If candidates are unknown or unverified, the task may
  only proceed as read-only research or a narrow spike.

## RULE recon-004: Planner and Coder Role Separation

- **Priority**: P1
- **Trigger**: Multi-agent or delegated work.
- **Rule**: The planner owns reconnaissance, architecture judgment, reuse
  decisions, task slicing, and review focus. Coder workers implement only
  approved slices. Planner-written product code is treated as spike code unless
  explicitly reviewed and adopted.
- **Verification**: TaskSpec or execution report identifies planner, coder, and
  reviewer roles separately.
- **Conflict Handling**: If a planner also implements product code, reviewer
  must treat the change as higher risk and verify that it does not bypass the
  approved Recon Receipt.

## RULE recon-005: Mature Capability Domains Need Exception Memos

- **Priority**: P0
- **Trigger**: Hand-writing a mature capability domain after Recon Gate.
- **Rule**: Custom implementation of client shell, desktop shell, timeline UI,
  terminal, diff viewer, provider binding, MCP bridge, multi-agent runtime,
  checkpoint/snapshot, evidence store, review gate, or conflict control requires
  an exception memo.
- **Verification**: Exception memo proves existing projects do not satisfy the
  requirement, integration cost exceeds implementation plus maintenance cost, a
  license/product boundary blocks reuse, security/privacy constraints block
  reuse, or the work is a temporary spike.
- **Conflict Handling**: Missing exception memo blocks the task.

## RULE recon-006: ZIP and Report Bundles Are Not Main Runtime Channels

- **Priority**: P1
- **Trigger**: Web AI, reviewer, or MCP adapter work.
- **Rule**: Context ZIPs, exported reports, and handoff bundles are fallback,
  audit, or review artifacts. They must not replace direct runtime integration,
  MCP/tool calling, or programmable worker APIs when those are available.
- **Verification**: Architecture notes place ZIP/report outputs under evidence
  or review layers, not the primary execution channel.
- **Conflict Handling**: If live integration is unavailable, record the bundle
  path as a fallback and keep a follow-up item for the direct adapter.

## RULE recon-007: Recon Receipt Template

- **Priority**: P2
- **Trigger**: Writing or reviewing a Recon Receipt.
- **Rule**: Use the standard receipt sections below unless a narrower project
  template exists.
- **Verification**: Receipt contains all required headings or explains why a
  heading is not applicable.
- **Conflict Handling**: Incomplete receipts may be accepted only for read-only
  research, not write-capable worker dispatch.

```markdown
# Recon Receipt

## Target
- user_goal:
- target_repo_or_kb:
- current_slice_goal:
- requested_outcome:
- date:
- planner_agent_id:

## Resource Map
- repository_roots:
- top_level_tree:
- important_dirs:
- docs_read:
- examples_read:
- packages_apps_modules:
- runtime_entrypoints:
- ui_entrypoints:
- service_entrypoints:
- state_storage_locations:
- external_integrations:
- notable_generated_or_vendor_paths:
- license_files_found:

## Core Concepts
- concepts:
- domain_terms:
- architecture_style:
- execution_model:
- session_model:
- review_model:
- evidence_model:

## Core Data Models
- project/workspace:
- thread/session:
- message/event:
- tool_call:
- terminal_run:
- diff/checkpoint:
- review/evidence:
- policy/rules:

## Capability Matrix
- capability_name:
  - location:
  - maturity:
  - reusable_as_is:
  - reusable_with_adapter:
  - not_reusable:
  - notes:

## Reuse Candidate List
- candidate:
  - source:
  - exact_scope_to_reuse:
  - expected_adapter_work:
  - blocking_constraints:
  - decision:

## Integration Risk Table
- risk:
  - type: license | security | privacy | maintenance | coupling | performance | ux | unknown
  - severity:
  - mitigation:
  - owner:

## Build-vs-Buy Decision
- must_reuse:
- should_adapt:
- can_spike:
- must_build_new:
- rationale:

## Unknowns / Questions
- unanswered_items:
- required_verification:
- experiments_needed:

## Recommended Next Slice
- smallest_safe_increment:
- worker_type_needed:
- files_or_modules_in_scope:
- files_or_modules_out_of_scope:
- evidence_required_for_completion:
- review_gate_definition:
```

## RULE recon-008: Multi-Agent Work Requires Team Objects

- **Priority**: P1
- **Trigger**: Planning, implementing, or reviewing multi-agent orchestration,
  client timelines, task boards, worker dispatch, review gates, evidence
  routing, or inter-agent communication.
- **Rule**: Do not treat parallel commands, multiple sessions, or multiple
  model invocations as a team by themselves. The plan or TaskSpec must identify
  the relevant first-class team objects: Agent Registry, Task Board, Message
  Bus, Event Log, Evidence Store, Blackboard or Shared Memory, Review Gate, and
  Conflict Control. A slice may implement only a subset, but it must say which
  subset is in scope and how the remaining objects are represented, deferred, or
  intentionally out of scope.
- **Verification**: Execution reports and reviewer packages reference concrete
  agent IDs, task IDs, handoff or message records, evidence paths, review
  verdicts, and conflict or worktree ownership when applicable.
- **Conflict Handling**: If these objects are absent, downgrade the work to a
  single-worker spike or block the multi-agent/client milestone until the team
  object model is recorded.

## RULE recon-009: Recon Receipts Are Evidence Artifacts

- **Priority**: P1
- **Trigger**: Completing Recon Gate, dispatching coder workers, or reviewing
  any mature capability slice.
- **Rule**: A Recon Receipt must be stored as a durable artifact and referenced
  from the TaskSpec, execution report, or Evidence Store. Chat-only summaries,
  transient terminal output, or informal status notes do not unlock
  write-capable implementation.
- **Verification**: The evidence set includes a receipt path or artifact ID and
  downstream diff, test, and review reports reference it.
- **Conflict Handling**: If no durable receipt exists, keep the next action
  read-only or create the receipt before dispatching coder workers.
