# Skill Asset Utilization Plan

State: active planning record

Last updated: 2026-07-05

Related docs: [Methodology Skills Registry](../agent-runtime/methodology-skills.md), [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md), [Design Coverage Gap Remediation Plan](design-coverage-gap-remediation-plan.md), [Review-First Governance Kernel Implementation Spec](review-first-governance-kernel-implementation-spec.md), [Asset Utilization Inventory](asset-utilization-inventory-20260705.md)

## Purpose

This plan turns existing project, local, and plugin skills from passive inventory
into governed workflow assets. It does not make every available skill part of the
public product, and it does not change the current implementation priority:
Phase 1A remains the review-first governance kernel.

The practical goal is simple: when a future agent enters this repository, it
should know which skill chain belongs to which work type, what artifact that
chain must produce, and what evidence proves the skill was useful instead of
decorative.

## Current Repo Reality

The repository already has a real skill substrate:

- Built-in methodology skills live under `tools/skills/<skill-id>/SKILL.md`.
- `skill_registry.py` discovers repository skills from their `SKILL.md` files.
- `methodology_dispatch.py` resolves explicit methodology triggers and folds the
  chosen skill content into dispatch constraints.
- `custom_skills.py` stores scoped runtime custom skills.
- `visual_state.py` projects a read-only `skills` snapshot for clients.
- The dashboard exposes `/api/t3/skills` for client inspection.

The substrate is useful, but it is still underused in four ways:

- Skills are discoverable, but not consistently attached to work-type routes.
- Skill use is not yet recorded as first-class evidence.
- Skill versions do not yet have immutable fingerprints, revision history, or
  promotion records.
- The large local/plugin skill pool is not governed as a supply-chain input, so
  it can confuse planning if treated as product capability.

## Asset Tiers

### Tier 1: Canonical project skills

These are repo-governed workflow assets that may be referenced by repo docs,
dispatch contracts, and future acceptance evidence. They are not automatically
public product capabilities:

| Skill | Current role | Utilization target |
|---|---|---|
| `intent-framing-gate` | Clarifies task intent before execution | Required before high-ambiguity planning or user-intent repair |
| `context-pack-builder` | Builds bounded context bundles | Required for external review, handoff, and cross-agent dispatch |
| `evidence-driven-acceptance` | Blocks unsupported completion claims | Required final gate for implementation and delegated work |
| `review-governance-kernel` | Defines the next governance implementation slice | Required for Phase 1A coding and tests |
| `external-brain` | Packages and submits web-AI review context | Required for GPT Web review loops |
| `bind-chrome` | Binds browser review to a persistent CDP Chrome profile | Required when browser state matters |
| `tdd` | Drives red-green-refactor implementation loops | Required for narrow kernel fixtures and regression tests |

### Tier 2: Local operating skills

These are useful local execution aids, but they are not automatically product
features. They can be named in handoffs and reviewer notes when used:

| Skill family | Examples | Use boundary |
|---|---|---|
| Development discipline | `coding-discipline`, `devprocess` | Agent work hygiene, not runtime product behavior |
| Recon and review | `codebase-recon`, `review`, `security-review`, `verify-before-complete` | Local verification and review depth |
| Frontend and testing | `frontend-design`, `webapp-testing`, `accessibility` | Later UI/prototype work after Phase 1A |
| Documentation and handoff | `write-docs`, `handoff`, `doc-coauthoring` | Repo docs and next-agent continuity |
| Test and lint | `test`, `lint`, `performance-lint` | Evidence generation, not substitute acceptance |

### Tier 3: Plugin and imported skills

Plugin/cache skills are supply-chain inputs. They may inform work after a reuse
or intake check, but they must not be presented as repository capability merely
because they exist on the current machine.

## Work-Type Skill Router

Use this table before dispatching future work. If a work type is missing, add a
row here before creating new runtime behavior.

| Work type | Required skill chain | Required artifact | Acceptance evidence |
|---|---|---|---|
| Phase 1A governance kernel implementation | `review-governance-kernel` -> `tdd` -> `evidence-driven-acceptance` | Schema or fixture change plus negative/positive tests | Targeted tests, public snapshot verification, evidence manifest |
| External GPT Web review | `context-pack-builder` -> `external-brain` -> `bind-chrome` | Review bundle with manifest, context ledger, redaction report, prompt, validator output | CDP submission trace, GPT verdict, required edits applied or explicitly deferred |
| Next-agent handoff | `context-pack-builder` -> local `handoff` practice -> `evidence-driven-acceptance` | Repo-local handoff doc plus copyable next-agent contract | Exact paths, changed files, tests run, known gaps |
| Code review or cleanup batch | local `review` -> `security-review` when relevant -> `evidence-driven-acceptance` | Findings-first review or cleanup inventory update | Real diff review, `git diff --check`, targeted tests or stated no-code boundary |
| Repo onboarding / capability map | `codebase-recon` practice -> `context-pack-builder` when dispatching | Updated map or planning doc | Source file citations, inventory synchronization, reviewer index update |
| Docs-only governance or planning update | `intent-framing-gate` when scope is ambiguous -> local `write-docs` practice -> `evidence-driven-acceptance` | Updated planning doc plus synchronized public entrypoints | `git diff --check`, public snapshot verification when public surface changes, changed-path summary |
| Public snapshot or release verification | `context-pack-builder` when dispatching findings -> `evidence-driven-acceptance` | Verification report or reviewer-index update | `scripts/verify-public-snapshot.ps1`, release/readiness references, no generated/private artifacts in public tree |
| Evidence-only or test-only repair slice | `tdd` when changing tests -> `evidence-driven-acceptance` | Test fixture, evidence record, or verifier repair | Failing-path reproduction when possible, targeted test pass, no runtime behavior claim without production-path evidence |
| Dependency or reuse-first adoption | reuse assessment -> local `security-review` when dependency risk exists -> `evidence-driven-acceptance` | Recon receipt or reuse assessment with scope and rollback | License/provenance check, existing-open-source comparison, no dependency promotion without explicit acceptance |
| UI or visual control-plane prototype | `intent-framing-gate` -> `frontend-design` -> `webapp-testing` | Prototype spec or implementation slice | Screenshot/playwright evidence after Phase 1A preconditions |
| External/imported skill adoption | reuse/intake assessment -> `context-pack-builder` if reviewed externally | Intake note with license, provenance, scope, and rollback | Explicit allowlist decision and no automatic promotion |

Non-goals for this router:

- no skill marketplace;
- no automatic import of local or plugin skills;
- no inferred default routing when the work type is unclear;
- no dashboard authority over the governance object model;
- no skill-based self-promotion from "used" to "accepted".

## Implementation Plan

### Step 0: Skill-router prerequisite

Status: this plan.

Add a public router that explains which skill chain belongs to which work type,
and treat that route selection as a prerequisite for the next coding slice.
Before Phase 1A work begins, the agent should be able to name the work type, the
required skill chain, the expected artifact, and the acceptance evidence.

This is deliberately router-first and automation-later: the route must be known
before implementation starts, but deeper telemetry should wait until the
governance object model can carry and validate the evidence.

### Step 1: Phase 1A stays the first coding slice

Implement the review-first governance kernel from
`review-first-governance-kernel-implementation-spec.md`.

Skill utilization requirement:

- Treat `review-governance-kernel`, `tdd`, and `evidence-driven-acceptance` as
  the mandatory chain for the slice.
- Represent skill use in existing governance objects, fixtures, or evidence
  payloads instead of adding a new top-level runtime subsystem.
- Include at least one negative test where unsupported or stale evidence blocks
  acceptance.

### Step 0A: Agent discipline catalog sidecar

This is a prerequisite planning layer for reliable skill use, and a deferred
runtime layer for enforcement. The project already has the discipline content,
but it is scattered across `AGENTS.md`, local operating skills, methodology
skills, rules, and active implementation specs. The refactor should consolidate
that content without creating another decorative checklist.

Target shape:

```text
Canonical discipline doc
  -> maps principles to anti-patterns
  -> maps anti-patterns to required skill routes
  -> maps routes to evidence and gates
  -> referenced by AGENTS.md, methodology skills, and review specs
  -> later enforced by review-governance fixtures and skill_usage evidence
```

Proposed canonical doc:

`docs/agent-runtime/agent-coding-discipline.md`

Authority level: agent operating discipline and planning/governance sidecar, not
stable runtime behavior and not completion evidence.

The doc should not be a slogan list. It should be a normalized rule catalog with
these fields:

- `rule_id`
- `principle`
- `dishonored_behavior`
- `honored_behavior`
- `required_skill_route`
- `required_artifact`
- `acceptance_evidence`
- `failure_state`
- `first_enforcement_phase`

Seed rule catalog:

| Rule ID | Principle | Dishonored behavior | Honored behavior | Required skill route | Required artifact | Acceptance evidence | Failure state | First enforcement phase |
|---|---|---|---|---|---|---|---|---|
| `agent-discipline-001` | Interface and API truth | guessing interfaces | inspect docs, schemas, symbols, and source | CodeGraph or `codebase-recon` practice -> evidence gate | source citation or inspected-symbol note | referenced file/schema/symbol plus verification command when changed | `blocked` or `insufficient_evidence` | immediate discipline; Phase 1A negative fixture where applicable |
| `agent-discipline-002` | Requirement alignment | starting from vague intent | frame scope, non-goals, success criteria, and user intent | `intent-framing-gate` -> work-type router | intent/scope note or TaskSpec section | matching work-type route, artifact, and acceptance evidence | `human_required` for unresolved intent | immediate discipline; Phase 1A WorkItem fields |
| `agent-discipline-003` | Domain humility | inventing business rules | cite project docs/rules/evidence or ask a bounded question | context/evidence gate | context snapshot, doc citation, or bounded question | evidence links or explicit missing-context reason | `blocked` or `human_required` | immediate discipline; Phase 1A context artifact rules |
| `agent-discipline-004` | Reuse discipline | adding redundant mechanisms | reuse existing modules, rules, schemas, and skills first | reuse assessment -> evidence gate | reuse note, recon receipt, or scoped design decision | existing asset citation plus reason for any new surface | `blocked` for missing recon/reuse check | immediate discipline; Phase 1A non-goal checks |
| `agent-discipline-005` | Verification completeness | skipping tests or checks | run targeted tests/checks or state blocker and residual risk | `tdd` when coding -> `evidence-driven-acceptance` | test, verifier output, or blocked verification note | command, exit code, and relevant output | `insufficient_evidence` | immediate discipline; Phase 1A required negative tests |
| `agent-discipline-006` | Architecture restraint | broad refactors outside the slice | stay within approved slice and public-surface boundaries | `review-governance-kernel` for Phase 1A -> evidence gate | diff summary and scope statement | changed-path list tied to approved work type | `blocked` for scope expansion | immediate discipline; Phase 1A forbidden top-level object tests |
| `agent-discipline-007` | Honest uncertainty | pretending certainty | mark `blocked`, `insufficient_evidence`, or `human_required` with reason | review/gate decision | decision or report section with reason | missing evidence/context named explicitly | `blocked`, `insufficient_evidence`, or `human_required` | immediate discipline; Phase 1A decision outcomes |
| `agent-discipline-008` | Iterative delivery | bulk uncontrolled edits | stage work into small slices with verification and rollback clarity | `devprocess` practice -> evidence gate | plan slice, diff summary, or cleanup inventory | `git diff --check`, relevant tests, and path-specific summary | `blocked` for unsafe or unclear batch | immediate discipline; cleanup/review workflows |

Refactor phases:

1. Create the canonical discipline doc and link it from `AGENTS.md`,
   `docs/README.md`, `docs/agent-runtime/methodology-skills.md`, this plan,
   `docs/status/status-document-inventory.md`, and
   `docs/status/reviewer-index.md`.
2. Replace duplicated discipline prose in future methodology skills with
   references to rule IDs, not copy-pasted variants.
3. During Phase 1A, represent discipline violations as negative fixture cases
   where possible, especially "run success is not completion", "report is not
   evidence", and "missing context blocks progress".
4. After the kernel exists, allow `skill_usage` evidence to cite discipline rule
   IDs and gate decisions.
5. Only after evidence validation exists, expose discipline compliance in a
   read-only dashboard projection.

Stop lines:

- Do not rewrite every skill before the canonical doc exists.
- Do not treat this sidecar as Phase 1A runtime implementation; only
  documentation/rule-catalog consolidation may happen before or alongside
  kernel coding.
- Do not turn slogans into runtime authority without evidence gates.
- Do not add a parallel lint engine before Phase 1A proves the review/gate
  packet.
- Do not treat "the agent followed the discipline doc" as completion evidence.

### Step 0B: Asset utilization operating chain

This step converts the asset inventory into a work-order plan. It addresses the
low-utilization finding from `asset-utilization-inventory-20260705.md`: assets
are abundant, but the project does not yet have one accounting chain that says
which asset was selected, why it was selected, what it produced, what evidence
accepted it, and whether it should be promoted, quarantined, deprecated, or
rejected.

This is a planning and routing prerequisite before broader asset work. Runtime
ledger implementation waits until the review-governance kernel can validate
evidence and gate decisions.

Operating chain:

```text
asset inventory
  -> work-type router selects required asset chain
  -> asset use produces artifact
  -> evidence cites artifact and claim
  -> review/gate decision accepts, blocks, or marks insufficient evidence
  -> asset utilization record updates promotion state
  -> read-only projection summarizes utilization
```

Priority plan:

| Priority | Slice | Purpose | First artifact | Acceptance evidence | Timing |
|---|---|---|---|---|---|
| P0 | Asset ledger contract | Define the minimum shape for asset accounting without adding a runtime subsystem | Draft asset-utilization evidence shape or fixture fields | Review-governance fixture can cite asset-backed evidence without new top-level objects | During Phase 1A design, implemented only if it fits existing packet objects |
| P0 | Work-type asset route enforcement | Make every non-trivial task name the asset chain it uses | Updated work-type router and next-agent contract | Task report cites route, artifact, and evidence | Immediate discipline |
| P1 | `skill_usage` evidence | Record skill selection only when it points to artifact, evidence, and gate outcome | `skill_usage` payload shape | Negative test rejects skill use as standalone completion evidence | After Phase 1A kernel exists |
| P1 | MCP offline utilization ledger | Make MCP connections/tool calls auditable without requiring a live dashboard | Offline-readable MCP utilization records | MCP result evidence links session, tool, consent, and downstream artifact | After Phase 1A kernel exists |
| P1 | External-review feedback ledger | Normalize accepted/rejected/deferred GPT review feedback | Feedback decision/evidence records | Review bundle verdict maps to local decision without becoming authority | After Phase 1A kernel exists |
| P2 | Plugin and local-skill allowlist/quarantine | Prevent local/plugin abundance from becoming false project capability | Asset intake record | Provenance, license/scope, and rollback are recorded before adoption | After evidence gates exist |
| P2 | Read-only utilization projection | Show asset use, stale assets, and promotion state to humans | Dashboard/read-model projection | Projection derives from evidence and decisions only | After ledger evidence exists |

Minimum asset record fields:

- `asset_id`
- `asset_type`
- `source_tier`
- `selected_for_work_type`
- `selection_reason`
- `produced_artifact`
- `evidence_ids`
- `gate_decision`
- `last_used_at`
- `promotion_state`

Initial asset classes:

| Asset class | First utilization goal | Stop line |
|---|---|---|
| Built-in methodology skills | Prove selected skills produce accepted artifacts | Do not treat trigger resolution as evidence |
| MCP server/tool calls | Link consent, session, tool call, result, and downstream artifact | Do not require live dashboard to audit historical use |
| External-review bundles | Track accepted, rejected, and deferred feedback | Do not treat GPT output as project authority |
| Local skills | Promote only when a concrete work type needs them | Do not import local skill inventory wholesale |
| Plugin cache / marketplace candidates | Maintain allowlist/quarantine status | Do not present cached plugins as project capability |
| Schemas/tests/rules | Count reuse when they validate or block a claim | Do not count file existence as utilization |

Stop lines:

- Do not add a broad asset-management platform before Phase 1A.
- Do not add an asset as a new top-level governance object in Phase 1A unless
  the review-governance implementation spec is deliberately revised.
- Do not measure utilization by presence, cache count, or trigger resolution.
- Do not promote plugin or local assets without provenance and a rollback path.
- Do not let dashboard projections decide asset authority.

### Step 2: Add skill-use evidence after the kernel exists

After Phase 1A can validate evidence and decisions, add a small `skill_usage`
evidence shape. It should record:

- `skill_id`
- `source_tier`
- `version_or_fingerprint` when available
- `trigger_reason`
- `produced_artifact`
- linked evidence IDs
- `acceptance_gate`
- `review_verdict`
- `gate_decision`

The record is valid only when it points to a produced artifact, linked evidence,
the gate that evaluated it, and the reviewer or local decision outcome.
`skill_usage` is not valid as a standalone completion record.

Do not add this before the kernel; otherwise it becomes another unverified log.

### Step 3: Add fingerprints and promotion records

After skill-use evidence exists, add immutable fingerprints and revision records
for project skills. Promotion from local/plugin skill to canonical project skill
must require:

- source provenance,
- license or redistribution check,
- review owner,
- fixture or workflow example,
- rollback path,
- reviewer-index registration.

### Step 4: Project skill dashboard projection

Only after Steps 1-3, expose skill utilization status in the visual/control-plane
surface:

- available project skills,
- recent skill usage,
- stale or unverified skills,
- work-type route coverage,
- external/imported skill quarantine status.

This is a read-only projection layer, not operational authority. The authority
remains the governance object model and acceptance evidence.

## Stop Lines

- Do not auto-load every local or plugin skill into every task.
- Do not treat plugin cache contents as product capability.
- Do not let a skill bypass the review-first governance kernel.
- Do not treat skill selection, trigger resolution, or presence in the registry
  as acceptance evidence.
- Do not build a skill marketplace, UI catalog, or import system before Phase
  1A evidence and decision gates exist.
- Do not use GPT Web approval as final authority; it is a critique source that
  must be grounded back into repository evidence.
- Do not create a parallel skill runtime when existing `skill_registry.py`,
  `methodology_dispatch.py`, `custom_skills.py`, and `visual_state.py` can carry
  the next slice.

## Phase 1A Readiness Checklist

Before any broader skill work starts, Phase 1A is ready for implementation only
if the next agent can point to:

- the matching row in the Work-Type Skill Router, including required skill chain,
  artifact, and acceptance evidence;
- the asset-utilization operating chain when the work uses skills, MCP,
  external-review bundles, plugins, local skills, schemas, or rules as reusable
  assets;
- `docs/status/review-first-governance-kernel-implementation-spec.md` as the
  controlling implementation spec;
- the planned review-governance schema or fixture files named by that spec;
- at least one positive fixture and one negative evidence fixture;
- a negative test where unsupported, missing, or stale evidence blocks
  acceptance;
- public snapshot verification for any public-surface doc or schema change;
- synchronized `docs/README.md`, `docs/status/status-document-inventory.md`,
  and `docs/status/reviewer-index.md` entries when a new public document or
  subsystem appears;
- explicit alignment with the Agent discipline consolidation refactor when the
  work touches agent behavior, methodology skills, or acceptance claims;
- an explicit statement that no fingerprint, dashboard skill view,
  imported-skill governance, or skill telemetry work is being implemented ahead
  of the kernel.

## Example Route Record

Example for this document update:

| Field | Example |
|---|---|
| Work type | Docs-only governance or planning update |
| Skill chain | `intent-framing-gate` spirit -> local `write-docs` practice -> `evidence-driven-acceptance` |
| Artifact | `docs/status/skill-asset-utilization-plan.md` plus synchronized doc indexes |
| Evidence | `git diff --check`, `scripts/verify-public-snapshot.ps1`, external-review bundle validation |
| Gate decision | Conditional external review feedback is applied before claiming the plan is accepted |

## Immediate Next-Agent Contract

Before implementing the next coding slice, the agent should read:

1. `docs/status/review-first-governance-kernel-implementation-spec.md`
2. `docs/status/document-driven-transformation-master-plan.md`
3. `docs/agent-runtime/methodology-skills.md`
4. this file

Then execute the Phase 1A kernel slice with this mandatory skill chain:

`review-governance-kernel` -> `tdd` -> `evidence-driven-acceptance`

The implementation should add only the smallest runtime or schema support needed
to prove the first review/evidence decision loop. Broader skill telemetry,
fingerprints, dashboard views, and imported-skill governance wait until the
kernel can validate them.

## External Review Request

Ask GPT Web to review whether this plan:

1. converts underused skills into governed workflow assets;
2. avoids over-promoting local/plugin skills into product capability;
3. preserves Phase 1A as the immediate implementation priority;
4. identifies any missing P0 or P1 requirement before coding resumes.
