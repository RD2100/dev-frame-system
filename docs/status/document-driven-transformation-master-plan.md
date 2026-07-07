# Document-Driven Transformation Master Plan

Lifecycle state: Draft active master plan

Plan status: Accepted as the coordinating plan for phase-one design and
implementation planning, not yet a stable runtime contract.

Reader: DevFrame maintainers who need to turn the current planning documents
into an ordered platform transformation without losing evidence, authority
boundaries, or public-repo clarity.

Post-read action: first read [Review-Governance Kernel Completion Status](review-governance-kernel-completion-20260706.md),
then execute only the current pending contracted slice. Reject runtime,
coordinator, RDCode, memory, routing, or UI work that bypasses the object model,
rules spec, evidence gates, or current status record.

Related docs: [Status Document Inventory](status-document-inventory.md), [Governance Spine And Document Coordination](governance-spine-and-document-coordination.md), [Current Coverage Audit Evidence](current-coverage-audit-evidence-20260704.md), [Design Coverage Gap Remediation Plan](design-coverage-gap-remediation-plan.md), [Review-Governance Kernel Completion Status](review-governance-kernel-completion-20260706.md), [Unified Object Model Decision Record](unified-object-model-decision-record.md), [Governance Contradiction Matrix](governance-contradiction-matrix.md), [Governance Rules Spec](governance-rules-spec.md), [Context Noise Governance And Automation Plan](context-noise-governance-and-automation-plan.md), [Model Knowledge Gap Governance Plan](model-knowledge-gap-governance-plan.md), [Project And Cross-Project Memory Harness Governance Plan](project-and-cross-project-memory-harness-governance-plan.md), [Goal-Bound Evidence Gate Plan](goal-bound-evidence-gate-plan.md), [Paper Claim Integrity Gate To Cluster Plan](paper-claim-integrity-gate-to-cluster-plan.md), [Human Attention Governance And Automation Maturity Plan](human-attention-governance-and-automation-maturity-plan.md), [Early Adopter User Asset Governance Plan](early-adopter-user-asset-governance-plan.md), [Competitive Moat And User Demand Critical Review](competitive-moat-and-user-demand-critical-review.md), [Review-First Governance Kernel Contraction Plan](review-first-governance-kernel-contraction-plan.md), [Review-First Governance Kernel Implementation Spec](review-first-governance-kernel-implementation-spec.md), [Reuse-First Constraint Governance Implementation Plan](reuse-first-constraint-governance-implementation-plan.md), [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Evaluation, Feedback, And Learning Governance Plan](evaluation-feedback-learning-governance-plan.md), [Total-Control Policy Engine And Human Escalation Governance Plan](total-control-policy-engine-and-human-escalation-governance-plan.md)
Related deferred modules: [Browser Automation Transport Roadmap](browser-automation-transport-roadmap.md), [Paper Knowledge Base Iteration MVP Plan](paper-knowledge-base-iteration-mvp-plan.md), [Graph Projection And Knowledge Canvas Plan](graph-projection-knowledge-canvas-plan.md)

## Implementation Must-Read Pack

The next coding agent should treat the detailed implementation spec as the
source of field-level truth. Read these three files before editing code or
schemas:

1. [Review-First Governance Kernel Implementation Spec](review-first-governance-kernel-implementation-spec.md)
2. [Governance Rules Spec](governance-rules-spec.md)
3. [Unified Object Model Decision Record](unified-object-model-decision-record.md)

Use this master plan and the contraction plan as boundary documents, not as
field catalogs. All other active plans are reference material until the
review-first kernel proves the first lifecycle.

## Terminology Freeze

Use these terms consistently in phase one:

| Term | Phase-one meaning |
|---|---|
| `Decision` | The only persisted authority-bearing judgment in phase one |
| `DecisionRequest` | A non-authoritative request from a shell or UI; DevFrame may reject, transform, or convert it into a `Decision` |
| Human approval | UI wording only; it is not a top-level object |
| Policy-handled continuation | A continuation recorded as a gate decision or work item rationale, not as an activation object |
| User Workflow Asset | A user-provided prompt, skill, MCP config, rule, evidence recipe, checklist, or workflow candidate |
| Governed Asset State | The scoped, validated, dry-run, policy/adoption state of a user workflow asset |
| Context Snapshot | Immutable `Artifact(kind=context_snapshot)`, not chat memory |
| Context noise gate | A context-snapshot and ledger check that records included, excluded, stale, disposable, background, and high-impact omitted context |
| Knowledge-gap check | A context-snapshot payload and evidence/rationale check, not a new top-level object |
| Cross-project memory | A low-authority hint from another project until current project evidence, evaluation, and decision prove applicability |
| Memory harness | The control layer that evaluates memory retrieval, isolation, freshness, contamination, and promotion |
| Intent Framing Gate | A triggered pre-work check that turns recurrence, completeness, ambiguity, or "why did the agent miss this" cues into an explicit problem frame before execution |
| Literal request | The user's surface instruction, such as "add two directory entries" |
| Systemic concern | The durable problem implied by the request, such as "future agents cannot discover project capabilities" |
| Goal-bound continuation gate | A gate decision that decides whether a work item may continue under current goal, evidence, policy, and context boundaries |
| GoalContractPayload | A payload on an existing work item or run snapshot, not a phase-one top-level object |
| SupervisionTickPayload | A payload on `Decision(kind=gate)`, not a standalone supervision record |
| Run | Execution observation; never completion authority |
| RDCode Projection | Derived shell view and request surface; never source of completion truth |

## Purpose

This master plan turns the current planning set into one document-driven
transformation path.

It is not a replacement for the detailed plans. It is the control document that
states the order, dependencies, proof requirements, and stop lines.

The target is a platform where:

- documentation states intent and authority;
- runtime records what happened;
- evidence supports or rejects claims;
- decisions, not reports or UI state, finalize authority;
- human attention is treated as scarce: routine work continues under policy,
  and interruptions happen only when actionable, scoped, and resumable;
- continuation is evidence-gated, policy-bounded, and audit-replayable rather
  than driven by worker claims, UI status, or cross-project memory;
- automated context management reduces accidental noise before dispatch and
  records excluded context instead of relying on hidden provider compression;
- knowledge-dependent judgments must declare checked sources, unresolved gaps,
  and freshness before they can guide implementation;
- recurrence, completeness, ambiguity, and meta-agent failure cues are framed
  before execution so a literal patch does not hide the systemic concern;
- memory is project-owned first; cross-project memory is a candidate signal
  that must be scoped, evaluated, and promoted before becoming a default;
- experienced users can bring existing skills, prompts, MCP tools, rules,
  evidence recipes, and workflows into governed project assets;
- RDCode and other clients project DevFrame governance instead of becoming
  separate sources of truth.

## Current Truth

DevFrame already has useful pieces:

- command routing and control-plane entrypoints;
- rdgoal contracts, dispatch packets, backup checks, worker reports, and runtime
  digests;
- team runtime and workflow event records;
- evidence finalization and review discipline;
- visual state, dashboard, T3, and client projection surfaces;
- recon receipts for several mature capability areas;
- planning documents for workflow, context, documentation, runtime, evaluation,
  learning, and total-control policy.

The missing piece is not more isolated capability. The missing piece is one
authoritative lifecycle:

```text
Project
  -> WorkItem
  -> DocumentRevision and context snapshot
  -> Run
  -> Artifact and Evidence
  -> Decision
  -> Projection
```

The current system should therefore be treated as strong substrate, not as the
finished governance platform.

## Current Coverage Audit

Audit date: 2026-07-04.

Evidence record: [Current Coverage Audit Evidence - 2026-07-04](current-coverage-audit-evidence-20260704.md).

Gap remediation plan: [Design Coverage Gap Remediation Plan](design-coverage-gap-remediation-plan.md).

External review status: the gap remediation plan received ChatGPT v2 `PASS`
on 2026-07-04 for the audited source set. Remaining P0 and P1 blockers for
accepting the remediation plan were reported as none. This was not evidence, at
that snapshot date, that Phase 1A was implemented and did not relax
deferred-module stop lines.

Current implementation progress after that audit is tracked in
[Review-Governance Kernel Completion Status](review-governance-kernel-completion-20260706.md).
Historical Phase 1A gap rows are not current state; the current record marks
P3-2 local GPT-equivalent review PASS and still requires commit/release
evidence before release-readiness claims.

This audit is a current-worktree reality check for the master plan. It is not a
clean release claim and not a replacement for implementation evidence. The
evidence record captures the inspected branch, commit, dirty worktree boundary,
CodeGraph status, file-existence checks, focused import probe, targeted tests,
and public-snapshot verification.

Current implemented substrate:

- `packages/control-plane` contains the main product code: CLI routing, rdgoal,
  dispatch packets, workflow/team runtime, visual state, dashboard, T3 bridge,
  browser/CDP helpers, external review bundles, custom skills, rules, scoped
  config, run defaults, and MCP/ACP/OpenCode probes. This is a code-structure
  observation, not a claim that the review-governance lifecycle is implemented.
- methodology and custom skill management are real code paths. Built-in skills
  are listed from repository assets; custom skills can be stored in runtime
  scope, resolved through the methodology dispatcher, and folded into
  deny-overrides run constraints. Focused tests for custom skill behavior pass
  in the evidence record.
- the external-brain bundle path is partly implemented: explicit sources,
  required roles, manifests, SHA-256 validation, sensitive path blocking,
  nested archive blocking, and tamper detection are tested.
- the persistent browser launch path is partly implemented: a dedicated
  profile, CDP endpoint reuse, login-once profile policy, and no destructive
  browser kill behavior have focused tests.
- `packages/ai-workflow-hub` contains useful paper-domain substrate and tests,
  but it is not the same thing as the deferred Paper KB workspace contract.
- `packages/test-frame` contains an evaluation-oriented substrate, but it is not
  yet a reliable public evaluation package.

Existing substrate is reusable vocabulary and code. It is not evidence that the
review-governance lifecycle has been implemented.

Historical mainline gaps in the 2026-07-04 audit:

- in that snapshot, the Phase 1A review-governance kernel was not implemented.
  The expected schema, fixtures, test file, and optional helper were all absent:
  `schemas/review_governance_kernel.schema.json`,
  `schemas/examples/review-governance/*.json`,
  `packages/control-plane/tests/test_review_governance_kernel.py`, and
  `packages/control-plane/control_plane/review_governance_kernel.py`. The
  evidence record includes the file-existence check output.
- the existing evidence, review, verdict, run, skill, and paper schemas provide
  vocabulary, but no single packet yet proves the required lifecycle:
  context snapshot -> run -> artifact -> evidence -> review decision -> gate
  decision -> read-only projection.
- TestFrame importability remains a blocker for evaluation governance, not for
  Phase 1A review-governance kernel schema, fixtures, and negative tests. A
  direct import with `packages/test-frame` on `PYTHONPATH` still fails with
  `ModuleNotFoundError: No module named 'schema'`; the evidence record includes
  the command shape and observed output.
- skill management is discoverable and executable, but it does not yet provide
  immutable skill content fingerprints, revision history, or promotion linkage
  suitable for evaluation and learning.
- external-brain bundles can prove package integrity, but the broader review
  loop still needs first-class evidence that the submitted context was
  sufficient, the web response was captured, and the response did not become
  authority without a local decision.
- graph projection, Paper KB iteration, and multi-browser transport are now
  discoverable as deferred module plans. They must remain behind Phase 1A and
  projection derivation.

Historical coverage decision:

In the 2026-07-04 audit, the next repository slice was Phase 1A. Current agents
must read the completion status record first and continue from the current
pending item. Do not spend the next coding pass on graph UI, Paper KB runtime
commands, multi-browser selection, model routing, or generalized learning unless
the completion status record authorizes that bounded pending item.

## Guiding Thesis

DevFrame should not depend on model cleverness as the reliability boundary.

The project should depend on constraints that models, agents, CLIs, dashboards,
and humans must pass through:

```text
Model proposes or executes
Project constraints validate
Evidence supports or rejects
Decision finalizes
Projection displays
```

The model may be smart, but the project must remain correct when the model is
incomplete, overconfident, stale, or persuasive without proof.

This is the main reason the first implementation target is not a smarter
coordinator. The first target is a constraint-backed review kernel.

The longer-term purpose is attention governance. DevFrame should automate
repeatable context gathering, checking, routing, and evidence work so human
attention is reserved for ownership, judgment, risk acceptance, and policy gaps,
not for approving routine work that already satisfies declared standards.

The early product assumption is that first users are not blank beginners. They
are likely to be experienced agent users with existing workflow assets. RDCode
should help them migrate and govern those assets before it tries to become a
general plugin marketplace.

The model-assumption assumption is stricter: product, architecture, competitor,
dependency, provider, or acceptance judgments cannot rely on model common sense
alone when current external reality or project-specific facts matter.

## Transformation Principles

### 1. Document first, but evidence decides implementation truth

Planning documents may authorize direction. They do not prove runtime behavior.
Runtime claims need tests, probes, artifacts, and decisions.

### 2. One object model before many features

New workflows, dashboards, model routes, and coordinator powers must map to the
phase-one object model before they are treated as platform behavior.

The phase-one object kernel precedes all implementation. Any new workflow, UI,
asset, policy, or evaluation capability must map to the eight phase-one objects
before work begins.

### 3. Review first, autonomy later

The first slice should prove review, evidence, and decision boundaries before
expanding into broad autonomous execution.

### 4. Projection is not authority

RDCode, T3, dashboards, and browser surfaces may display and request action.
They must not own evidence validity, document authority, policy grants, or final
verdicts.

### 5. Learning is advisory until activated by policy or adopted

Evaluation and learning may propose improvements. Adoption requires evidence,
decision, and rollback.

Hermes-style learning loops are useful inspiration: repeated work can become a
candidate skill, evidence recipe, workflow blueprint, or failure lesson.
DevFrame should learn this growth pattern, but not the idea that generated
skills automatically gain authority.

Workflows may grow from use; authority never grows by use alone.

For routine, low-risk personal behavior, governance may be a predefined policy
that allows activation after validation and dry-run. For shared defaults,
expanded authority, weakened evidence, or project policy changes, adoption must
remain explicit and reviewable.

### 6. Constraints before cleverness

The platform should achieve reliability by making invalid states hard or
impossible, not by assuming the model will remember every rule.

Examples:

- schema rejects unknown top-level governance objects;
- tests reject run success as completion;
- gate decisions require evidence;
- projection status is derived from facts;
- policy-like decisions are explicit, scoped, and reviewable.

### 7. Reuse before hand-rolling

Mature open-source systems should inform the design before DevFrame invents a
local version.

The current reuse stance is:

- borrow structured-output discipline from Outlines, Guardrails AI, Guidance,
  and LMQL;
- borrow policy-as-code discipline from Open Policy Agent, Cedar, and OpenFGA;
- borrow durable workflow discipline from Temporal and LangGraph;
- borrow provenance discipline from in-toto, SLSA, OpenLineage, and MLMD;
- keep the phase-one implementation local and thin until tests reveal a real
  dependency gap.

External libraries may strengthen a boundary. They must not become the source of
truth for DevFrame governance.

### 8. Test-first contraction

The next implementation must start with fixtures and negative tests.

The first code package should prove:

- missing context blocks readiness;
- run success does not complete work;
- report-only output is insufficient evidence;
- gate pass requires evidence;
- projection cannot mark completion by itself.

This is how discussion becomes document-driven development instead of another
round of architecture prose.

### 9. Knowledge gaps are governed before judgment

Models can reason well from bad premises. Any claim that depends on current
ecosystem reality, project-local facts, library behavior, provider capability,
or competitor state must carry source refs and unresolved-gap notes before it
guides implementation.

This is why "import skills" is not treated as a moat by default. A capability
already common in AGENTS.md, Agent Skills, OpenHands Skills, Cline Memory Bank,
Continue rules, Context7, or Hermes-style loops is table stakes until evidence
shows an underserved gap.

### 10. Context noise is filtered before model work

High-frequency automation depends on the system preparing context without
constant human curation.

That automation must perform reduction, not accumulation. Before dispatch, the
context workflow should classify stale plans, disposable exports, old handoffs,
duplicated logs, semantically related distractors, and low-authority memory so
the model is not guided by accidental noise.

The context packet should show selected context to the model. The context ledger
should show reviewers what was excluded and why.

If a high-impact source is excluded, or if two current authority sources
conflict, the workflow should warn, block, or ask the smallest necessary human
question instead of silently continuing.

### 11. Human attention is a scarce governed resource

Automation should reduce avoidable human attention, not create a noisier
supervision queue.

The default should be:

```text
If policy and evidence are sufficient, continue and record why.
If policy or evidence is insufficient, ask the smallest necessary human
question.
```

Every human interruption should state:

- the exact decision needed;
- why automation cannot continue safely;
- which evidence and context support the request;
- what happens if the human approves or rejects;
- how the workflow resumes.

Repeated human decisions may become automation proposals. They must not become
rules without evidence and either policy activation or an adoption decision.

### 12. Goal-bound continuation is a gate, not a supervisor

The project should support goal-aware continuation, but not by making a broad
Goal Supervisor the next mainline.

The phase-one form is a gate decision:

```text
Given a WorkItem goal, a Run context snapshot, evidence refs, and policy,
produce policy_continue, blocked, human_required, hard_stop, or pause.
```

That decision must not be bypassed by a worker's completion claim, a dashboard
state, a shell projection, model confidence, or cross-project memory. It must be
written as an auditable decision payload using existing objects.

`policy_continue` means only that the next pre-declared low-risk step is allowed
inside the same goal, action class, evidence recipe, and context boundary. It
does not mean autonomous free-form work may continue.

Persistent supervisors, automated resume, durable schedulers, and broad
workflow runtimes are deferred until the gate itself is proven.

### 13. Intent framing is a triggered gate, not mind reading

DevFrame should not rely on agents to intuit hidden user intent from every
message. It should make a small set of high-signal cues trigger an explicit
framing step before execution.

Trigger the Intent Framing Gate when the user asks about:

- whether a directory, map, plan, or capability is complete;
- whether a similar problem will happen next time;
- why the agent only did the literal instruction;
- whether a fix should become a general mechanism;
- ambiguity, under-specification, scope uncertainty, or repeated misses.

The gate must name:

- the literal request;
- the inferred systemic concern;
- whether the concern is one-off, recurring, or unknown;
- which durable project asset may need to change: documentation map, skill,
  rule, schema, test, evaluation record, or runtime policy;
- whether the agent can continue under a low-risk assumption or must ask one
  focused question.

This is not permission to expand scope silently. If the systemic concern
requires code, schema, policy, or authority changes beyond the approved task,
the gate should propose the expansion and wait for approval.

Open-source systems suggest the same direction: repository maps, repository
instructions, skills, and human-in-the-loop agent frameworks reduce hidden
context failures by externalizing context and routing. Recent ambiguity and
clarification research points to the same rule: "ask when needed" should be a
measured mechanism, not a personality trait.

### 14. User assets before generic plugins

Extensibility should start from what experienced users already have:

- skills;
- prompts;
- MCP tools;
- scripts;
- command aliases;
- rules;
- workflow templates;
- context profiles;
- evidence recipes;
- report templates;
- model and agent preferences.

These assets should be imported, classified, scoped, dry-run, and governed. They
should not become active project authority merely because they were imported.

Low-risk personal assets may be enabled by policy after validation and dry-run.
Project, team, and organization defaults require stronger evidence and an
explicit activation or adoption path.

Generic plugin APIs and marketplaces are deferred until governed asset import
works.

### 15. Differentiate on governed assets, not generic extension count

Competitors already provide agents, MCP, workflows, plugins, templates, and
tool connectors. DevFrame should not compete by having a longer integration
list.

The differentiator should be that imported assets become:

- scoped;
- testable;
- dry-runnable;
- evidence-aware;
- governed by policy activation or decisions;
- blocked from bypassing project authority.

Features that do not strengthen this chain are likely distractions in phase
one.

## Consolidation Rule For Future Discussion

Future planning discussions should be folded back into this master plan when
they change one of these things:

1. the core thesis;
2. the object model;
3. the phase order;
4. the dependency/reuse stance;
5. the stop lines;
6. the first vertical slice;
7. the definition of done.
8. the early-adopter or user-asset strategy.
9. the competitive moat or real-vs-false user need classification.
10. the model knowledge-gap or assumption-risk boundary.
11. the automated context-noise or context-selection boundary.
12. the goal-bound continuation or supervisor boundary.
13. the intent-framing, ambiguity, or recurring-failure boundary.

## Governance Contraction Patch Lines

These lines constrain the next implementation pass:

1. Phase one implements only the review-first governance kernel.
2. User assets are limited to one `evidence_recipe` or `review_checklist`
   placeholder fixture.
3. Human approval, policy activation, attention request, and decision request do
   not become new phase-one top-level objects.
4. RDCode may request; DevFrame backend decides.
5. Context snapshots stay artifacts, but their payload must be thick enough for
   reproduction, audit, gate decisions, and future model comparison.
6. Knowledge-dependent judgments must be checked before they become planning or
   implementation authority.
7. Context noise decisions are recorded in the context snapshot or ledger; they
   do not become a new phase-one top-level object.
8. Cross-project memory may be referenced as a low-authority hint, but it
   cannot support a final gate without current project evidence.
9. Intent framing may expand the problem frame, but it cannot expand authorized
   implementation scope without an explicit approval or decision.
9. External review packages are disposable exports, not sources of truth.
10. Goal-bound continuation is represented through existing `WorkItem`, `Run`,
    `Artifact`, `Evidence`, and `Decision` payloads; do not add phase-one
    top-level `GoalContract`, `SupervisionPlan`, `WorkLoop`, `Checkpoint`,
    `EvidenceReview`, `Resume`, or `GoalSupervisor` objects.
11. `policy_continue` is allowed only for the next pre-declared low-risk step
    in the same goal, action class, evidence recipe, and context boundary.
    Missing evidence or missing context means blocked.

If a discussion only adds detail to a phase, write or update a phase-specific
status document and link it here. If it changes the direction, update this
master plan directly.

This keeps the project from growing a second unofficial master plan in chat,
handoffs, or side documents.

## Next Agent Contract

The next implementation agent has one job:

```text
Implement the review-governance kernel contract slice.
```

This is a schema, fixture, and negative-test slice only. It must not migrate
runtime storage, create a full `/rdreview` command, add coordinator autonomy,
wire RDCode writeback, introduce model routing, build memory infrastructure, or
add a new top-level governance object.

Allowed files for the first implementation package:

- `schemas/review_governance_kernel.schema.json`
- `schemas/examples/review-governance/success.json`
- `schemas/examples/review-governance/blocked.json`
- `schemas/examples/review-governance/insufficient-evidence.json`
- `schemas/examples/review-governance/missing-context.json`
- `packages/control-plane/tests/test_review_governance_kernel.py`

Optional only if schema-only validation becomes awkward:

- `packages/control-plane/control_plane/review_governance_kernel.py`

The first package must prove these negative cases:

- missing context snapshot cannot become ready;
- `Run.status=succeeded` cannot complete a work item without a gate decision;
- a review report without evidence references becomes `insufficient_evidence`;
- projection cannot mark a work item `completed` without backend decisions.

Verification commands:

```powershell
python -m pytest packages/control-plane/tests/test_review_governance_kernel.py -q
powershell -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1
```

Existing `rdgoal`, `WorkflowEngine`, `TeamRuntime`, visual state, and T3 records
are compatibility references for this slice. They are not migration targets in
the first implementation package.

## Phase Classification Rule

Not every capability should be phased in the same way.

Use this classification before adding work to a phase:

| Class | Meaning | Examples | Phase rule |
|---|---|---|---|
| Hard constraint | A rule that prevents false authority or false completion | run success is not completion; projection is not authority; reports are not evidence; summaries are not proof | Apply from the first implementation slice |
| Minimal contract | A small schema, fixture, or payload field needed to preserve a future boundary | context snapshot fields; knowledge-gap fields; noise-filter fields; memory refs; decision kinds; source refs | Add early, keep values small |
| Staged capability | A behavior that needs runtime proof before expansion | context packet generator; retrieval connectors; RDCode consumption; document authority projection; evaluation registry; memory harness; goal-bound continuation gate; policy-gated promotion | Implement after the prior lifecycle is proven |
| Triggered check | A check that runs only when the task needs it | competitor research; dependency freshness; licensing risk; high-impact context exclusion; human escalation; intent framing for completeness, recurrence, or ambiguity cues | Do not run for every task; activate by profile, risk, or claim type |
| Deferred platform | A broad system that is attractive but not needed to prove phase one | vector memory platform; cross-project memory database; plugin marketplace; model auto-routing; LangGraph or Temporal migration; OPA/OpenFGA adoption | Defer until a local fixture or test proves the need |
| Non-goal | Work that would weaken the governance kernel or create false confidence | UI-only completion; chat-only approval; automatic self-promotion; arbitrary plugin execution; status-folder mass rewrite | Do not place in any phase without a new decision |

The key distinction:

```text
constraints are not phases;
capabilities are phased;
platform breadth is deferred.
```

If a feature is needed to keep the first review lifecycle honest, implement the
smallest contract or fixture now. If it mainly improves convenience, scale,
autonomy, or market breadth, it must wait for the preceding evidence path.

## Target Governance Spine

The platform should converge on this spine. The unified object model and
governance rules are prerequisites for implementation, not late-stage feature
work:

```text
Workflow and command consolidation
  -> Intent framing and ambiguity governance
  -> Context management
  -> Context noise governance
  -> Model knowledge-gap governance
  -> Documentation governance
  -> Runtime governance and evidence closure
  -> Evaluation and feedback learning
  -> Project and cross-project memory harness
  -> Total-control policy and human escalation
  -> Goal-bound continuation gate
  -> Human attention governance
  -> User customization asset governance
  -> Review-first vertical slice
  -> Stable runtime documentation
```

This order matters. If implementation jumps directly to coordinator autonomy,
model routing, or client writeback, it will recreate the same fragmentation in a
new layer.

## Phase 0: Documentation Control Baseline

Status: in progress.

Goal: make the planning surface navigable and prevent old documents from acting
as hidden authority.

Required artifacts:

- status document inventory;
- governance spine coordination record;
- unified object model decision record;
- contradiction matrix;
- governance rules spec;
- human attention governance and automation maturity plan;
- early adopter user asset governance plan;
- competitive moat and user demand critical review;
- this master plan.

Acceptance evidence:

- all current status files are classified in the inventory;
- new planning documents are linked from the documentation map;
- reviewer index includes the active planning set;
- local markdown links resolve.

Stop line: do not archive, move, or delete old status files until the master plan
has been reviewed.

## Phase 1: Review Governance Kernel Contract

Goal: prove the smallest machine-consumable review-governance packet before any
runtime migration, command UX, coordinator autonomy, memory, routing, or client
writeback work.

Phase 1 is split so coding agents can stop at a real handoff boundary instead
of expanding the first package.

### Phase 1A: Schema, Fixtures, And Negative Tests

Status: historical 2026-07-04/05 next implementation target. Current progress
is tracked in [Review-Governance Kernel Completion Status](review-governance-kernel-completion-20260706.md).

Goal: define and validate one fixture-level packet that proves the phase-one
object model can prevent false completion.

Scope:

- `Project`;
- `WorkItem`;
- `DocumentRevision`;
- `Run`;
- `Artifact`;
- `Evidence`;
- `Decision`;
- `Principal`;
- `Artifact(kind=context_snapshot)`;
- `Decision.kind=review|gate|adopt`.

Expected outputs:

- `schemas/review_governance_kernel.schema.json`;
- four fixtures under `schemas/examples/review-governance/`;
- `packages/control-plane/tests/test_review_governance_kernel.py`;
- optional helper module only if tests would otherwise duplicate schema-derived
  status logic.

Acceptance evidence:

- schema or contract validation passes for example fixtures;
- examples show `Run.success` does not complete a work item without a decision;
- missing context blocks readiness;
- report-only output becomes `insufficient_evidence`;
- projection examples derive status from backend facts;
- `scripts\verify-public-snapshot.ps1` still accepts the public snapshot.

Explicitly deferred from Phase 1A:

- full `/rdreview` command UX;
- runtime storage migration;
- document authority projection beyond what a fixture needs;
- human attention request workflow;
- goal-bound continuation fixture;
- user-asset import or activation fixture;
- coordinator, RDCode, model routing, memory, or LangGraph/Temporal work.

### Phase 1B: Minimal Helper And Projection Derivation

Status: deferred until Phase 1A passes.

Goal: add the smallest helper or projection derivation needed to avoid
duplicated fixture interpretation.

Allowed outputs:

- helper functions that derive status from the validated packet;
- tests that prove projection status cannot override decisions.

Stop line: do not create runtime persistence or a command surface in Phase 1B.

### Phase 1C: Prepare-Only Review Flow Skeleton

Status: deferred until Phase 1A and Phase 1B pass.

Goal: create the smallest prepare-only review flow that emits the kernel packet
for one local example.

Allowed outputs:

- a local driver or internal function that writes a draft review packet;
- tests or probes showing the packet still requires review and gate decisions.

Stop line: do not treat this as a finished `/rdreview` product command.

Stop line: do not introduce new top-level governance objects until they pass the
object admission test.

Additional stop line: do not add a third-party dependency because it is
conceptually attractive. Add one only after a local fixture or test exposes a
gap that the dependency actually solves.

Additional stop line: do not add a generic plugin API before governed user-asset
import has a fixture, scope model, and activation boundary in a later phase.

Additional stop line: do not prioritize a feature merely because competitors
have it. Prioritize it only if it supports the review kernel, governed user
assets, evidence decisions, or attention reduction.

Additional stop line: do not implement a broad Goal Supervisor, WorkLoop, or
automated resume runtime before the goal-bound continuation gate has fixtures
and negative tests in a later phase.

## Cross-Cutting Plan: Intent Framing Gate

Status: planned as a lightweight governance mechanism. It must not displace
Phase 1A.

Goal: prevent narrow literal execution when the user's wording signals a
recurring, structural, ambiguous, or governance-level problem.

Problem it addresses:

- an agent may patch the requested line but miss that the directory, map, rule,
  or workflow is incomplete;
- an agent may answer "yes, this is enough" without checking whether the next
  agent can actually discover the relevant subsystem;
- an agent may treat user frustration about a miss as conversational feedback
  rather than evidence of a process gap;
- an agent may either over-ask or over-expand because ambiguity is not handled
  as a scoped mechanism.

Research-informed stance:

- use repository maps and durable project instructions to reduce hidden-context
  failures;
- use explicit skills or routing metadata to make task modes visible;
- separate uncertainty detection from execution when possible;
- ask focused questions only when the answer changes scope, authority, or risk;
- evaluate both missed framing and unnecessary interruption.

Trigger profile:

- completeness: "is this full", "is the map enough", "can we ensure";
- recurrence: "next time", "similar problem", "avoid this again";
- meta-agent failure: "you only did what I said", "why did you not notice";
- ambiguity: "what did I really mean", "underlying intent", "not just the
  literal edit";
- governance cues: "directory", "skill", "rule", "workflow", "general
  mechanism", "handoff", "review", "evidence".

Required framing output:

1. Literal request.
2. Inferred systemic concern.
3. Recurrence class: one-off, recurring, unknown, or policy-risk.
4. Affected durable asset: documentation map, skill, rule, schema, test,
   evaluation record, runtime policy, or human attention workflow.
5. Action level: answer-only, documentation update, skill/rule update,
   schema/test proposal, or runtime-policy proposal.
6. Ask-or-continue decision with one focused question only when needed.

Implementation slices:

### Intent Slice A: Documentation And Skill Contract

Status: can proceed before runtime integration.

Outputs:

- add this gate to the master plan;
- add or update a methodology skill for explicit `@intent-frame` use;
- link the gate from the documentation map and methodology-skill registry;
- add a short next-agent rule: recurrence/completeness cues require intent
  framing before execution.

Acceptance evidence:

- a fresh agent can find the gate from the documentation map;
- the skill registry exposes the explicit trigger;
- the documented trigger profile covers the failure that led to this plan;
- no implementation scope is expanded without approval.

### Intent Slice B: Fixture-Level Contract

Status: deferred until Phase 1A passes.

Outputs:

- represent intent framing as payload on existing objects, not as a new
  top-level phase-one object;
- add one positive fixture where a "directory completeness" question becomes a
  systemic documentation-map review;
- add one negative fixture where a trivial edit does not trigger the gate;
- add one blocked fixture where the inferred concern would require unauthorized
  scope expansion.

Acceptance evidence:

- validation rejects framing output that lacks literal request or systemic
  concern;
- validation rejects silent scope expansion;
- projection can show that a framing gate happened without treating it as final
  acceptance.

### Intent Slice C: Prepare-Only Runtime Hook

Status: deferred until the review-first vertical slice is proven.

Outputs:

- add a pre-dispatch classifier that only emits a framing recommendation;
- allow explicit `@intent-frame` to force the gate;
- allow the coordinator to continue without interruption when the gate selects a
  low-risk documentation or answer-only path;
- require a human question only when the missing answer changes authority,
  risk, or write scope.

Acceptance evidence:

- existing direct tasks do not become noisy;
- recurrence/completeness prompts produce the required framing output;
- the hook cannot grant write authority or mark work complete;
- evidence records distinguish "framing performed" from "implementation
  accepted".

### Intent Slice D: Evaluation And Feedback Learning

Status: deferred until evaluation proposal flow exists.

Metrics:

- missed-framing rate: later review finds the agent treated a systemic concern
  as a literal edit;
- unnecessary-question rate: the agent asked when project context was enough;
- scope-expansion safety: the agent proposed expansion instead of silently
  editing outside the approved task;
- user-confirmed usefulness: the framing changed the work in a way the user
  accepted.

Promotion rule:

Intent framing may become default total-control policy only after repeated
examples show reduced missed systemic concerns without making routine tasks
substantially noisier.

Non-goals:

- no hidden mind-reading claim;
- no broad autonomous planner;
- no automatic scope expansion;
- no requirement to run the gate for every small task;
- no new top-level governance object before the review kernel proves object
  admission.

## Phase 2: Review-First Vertical Slice

Goal: prove the lifecycle with a low-risk prepare-only `/rdreview` or equivalent
review-first flow after the kernel packet and projection derivation are proven.

Why this slice:

- it exercises context, artifacts, evidence, review, gate decision, and
  projection;
- it does not require broad autonomous coding or release mutation;
- it can validate the object model before expanding total-control powers.

Minimum behavior:

1. create or select a project;
2. create a review `WorkItem`;
3. produce an immutable context snapshot artifact;
4. record one run with named principal and tool boundary;
5. attach output artifacts and evidence;
6. record `Decision(kind=review)`;
7. record `Decision(kind=gate)`;
8. project status as in progress, blocked, insufficient evidence, waiting for
   human, or completed.
9. if human attention is needed, surface a precise decision request with evidence
   and resume semantics.
10. if routine continuation is allowed, record it as an evidence-backed
    `Decision(kind=gate)` payload under the same goal and evidence recipe.

Routine low-risk continuations should not require human approval when policy and
evidence already allow them. The first slice may record this as a policy-handled
gate decision instead of a chat approval.

Acceptance evidence:

- fixtures cover success, blocked, and insufficient-evidence paths;
- tests prove a run cannot complete the work item without a decision;
- tests prove missing context blocks readiness;
- tests prove report-only output does not pass the gate;
- projection output is derived from governance facts.
- dependency adoption gate is either not triggered or is documented with a
  concrete local failure.
- human-needed state is represented as a decision or projection state, not as
  chat-only feedback.
- policy-handled continuation cannot pass without current evidence, a context
  snapshot, and a pre-declared next step.

Stop line: do not treat the coordinator, dashboard, or RDCode shell as complete
because they can display the slice. Display is not authority.

## Phase 3: Documentation Authority And Promotion

Goal: connect document governance to runtime decisions.

Scope:

- document revision identity;
- activation or adoption decision;
- supersede/archive decision if needed after phase two;
- active document projection;
- lifecycle labels for old status documents touched during the work.

Expected outputs:

- document authority projection;
- adoption fixture for one status document;
- promotion rule for moving proven plans into stable runtime docs;
- contradiction handling rule for conflicting documents.

Acceptance evidence:

- a newer document revision does not become authoritative without policy
  activation or adoption;
- a promoted document points back to evidence and decision;
- stale handoff material is marked as handoff or consumed into a newer plan.

Stop line: do not mass-rewrite historical status records just to make the folder
look clean. Preserve traceability.

## Phase 4: Projection Consumption And RDCode Boundary

Goal: let RDCode or another shell consume the governance lifecycle without
owning it.

Scope:

- project picker;
- work item list;
- review work item details;
- run/evidence/decision summary;
- human-required action display;
- user asset library display for draft, quarantined, enabled, and adopted assets;
- narrow decision request writeback.

This phase should stay shell-consumption oriented. It should verify whether
existing helper and projection surfaces are enough for real use before reopening
broad dashboard or LangGraph-style redesign.

Acceptance evidence:

- projection shows backend-computed status;
- projection cannot directly mark work complete;
- writeback creates governed requests or decisions, not untracked UI facts;
- blocked, insufficient-evidence, and waiting-for-human states are visible.
- imported user assets are visible as governed assets, not raw trusted plugins.

Stop line: do not make RDCode the governance database.

Additional stop line: do not make projection convenience a reason to weaken
backend-derived status or evidence rules.

Additional stop line: do not let RDCode enable a personal asset as project or
team default without policy activation or adoption. Also do not ask for repeated
human approval when a personal, low-risk asset already satisfies policy,
validation, and dry-run checks.

## Phase 5: Evaluation And Learning Loop

Goal: connect evaluation and feedback learning after the review lifecycle works.

Scope:

- comparable context snapshots;
- scorecard or evaluation observation;
- improvement proposal;
- policy activation or adoption decision for promoted changes;
- rollback path.

Acceptance evidence:

- evaluation cannot override a blocked gate;
- model comparison states whether context was equivalent;
- learning proposal cannot update defaults without policy activation or
  adoption;
- promoted change has rollback or a documented exception.

Stop line: do not add model routing or long-term memory as core authority before
the review and evidence slice is proven.

## Phase 6: Total-Control Policy And Human Escalation

Goal: enable higher-power coordinator behavior under explicit authority.

Scope:

- policy decision payloads;
- human escalation requests;
- blocked self-promotion cases;
- high-power action classification;
- attention routing rules;
- audit projection.

Acceptance evidence:

- coordinator can propose high-power action without silently executing it;
- human-required decision shows reason and consequence;
- self-promotion is blocked by default;
- policy confidence does not grant authority.
- repeated human decisions become automation proposals, not adopted rules unless
  a policy activation or adoption path allows promotion.
- goal-bound continuation is a gate decision, not a persistent autonomous
  supervisor.

Stop line: do not equate a first-class coordinator conversation with finished
coordinator runtime. Persistent behavior, shared memory, and real collaboration
need separate proof.

## Phase 7: Stable Runtime Promotion

Goal: promote proven behavior out of `docs/status` into stable runtime
documentation.

Promotion candidates:

- runtime governance;
- evidence and decision lifecycle;
- document authority rules;
- projection and RDCode boundary;
- evaluation and learning governance;
- total-control escalation.

Acceptance evidence:

- every promoted stable doc links back to implementation evidence or tests;
- status plans are marked as planning history or superseded where appropriate;
- reviewer index remains aligned with the public snapshot.

Stop line: do not promote a plan because it is well written. Promote only proven
behavior.

## Implementation Order

The historical planning order was:

Before using this order, read
[Review-Governance Kernel Completion Status](review-governance-kernel-completion-20260706.md)
and skip items already marked PASS. Continue only from the current pending item;
P3-2 is already local-review PASS and remains pending only for commit/release
evidence.

1. finish and review this master plan;
2. keep Intent Slice A as a documentation and skill-contract sidecar, not a
   replacement for Phase 1A;
3. use the completion status record before reopening Phase 1A work from the
   Next Agent Contract;
4. validate the review-governance schema and four fixtures;
5. prove the required negative tests;
6. run the public snapshot verification gate;
7. only then consider Phase 1B helper/projection derivation;
8. only then consider Phase 1C prepare-only review flow skeleton;
9. after the review-first lifecycle is proven, add document authority projection;
10. after document authority is proven, add evaluation proposal flow;
11. after evaluation proposal flow is proven, add policy and human escalation;
12. after policy and escalation are proven, add goal-bound continuation fixtures;
13. after repeated human decisions have evidence, add governed user-asset import;
14. after evaluation shows repeated missed-framing examples, promote intent
    framing from explicit skill to default total-control policy;
15. promote proven docs to stable runtime docs.
16. only after the stable CDP-family path has repeatable evidence, consider the
    deferred browser transport module for Edge, Chromium-compatible browsers,
    and WebDriver BiDi experiments.
17. only after the review-governance kernel Phase 1A passes, consider the
    deferred Paper KB workspace contract as paper-domain fixtures under that
    kernel; do not start it as a parallel schema or runtime command.
18. only after the review-governance kernel and basic projection derivation are
    proven, consider the deferred graph projection module as a read-only
    context-navigation projection; do not start with graph UI, graph database,
    annotation writeback, or automatic extraction.

## Dependency Adoption Gate

Before adding a new third-party dependency to this governance path, require:

1. the local fixture or test gap it solves;
2. why existing project code or standard validation is insufficient;
3. license and public-repo suitability;
4. adapter boundary;
5. fallback if the dependency is removed;
6. tests proving DevFrame rules still own final decisions.

Candidate dependency families remain deferred until a concrete need appears:

| Need | Candidate family |
|---|---|
| Constrained model output | Outlines, Guardrails AI, Guidance, LMQL |
| Complex policy evaluation | Open Policy Agent, Cedar, OpenFGA |
| Durable long-running workflow | Temporal, LangGraph |
| Multi-system provenance | in-toto, SLSA, OpenLineage, MLMD |

## Explicit Deferrals

These are out of scope until the review-first lifecycle is proven:

- broad autonomous coordinator execution;
- full RDCode write authority;
- platform-wide event sourcing;
- Zanzibar/OpenFGA-style authorization graph;
- long-term memory promotion;
- model-provider auto-routing;
- full LangGraph migration;
- large status-folder archival or rewrite.
- dependency adoption without a failing local test or documented gap.
- generic plugin marketplace before governed user-asset import works.
- visual workflow builder or broad marketplace parity work before the review
  kernel and user asset governance prove their value.
- multi-browser transport selection before the CDP-family path, adapter schema,
  and browser evidence requirements are proven.
- Paper KB workspace contracts, Obsidian writeback, local RAG product commands,
  external-brain paper submission, and skill-candidate extraction before the
  review-governance kernel Phase 1A passes and the Paper KB contract is
  expressed as a domain fixture under that kernel.
- Graph projection UI, graph database adoption, knowledge-canvas annotation
  writeback, broad graph extraction, or graph-driven code changes before the
  review-governance kernel and basic projection derivation prove that
  projection cannot override evidence-backed decisions.

## Review Checklist

Before accepting any implementation proposal under this master plan, check:

1. Which phase does it serve?
2. Which object-model entities does it create or consume?
3. What evidence proves it?
4. What decision finalizes it?
5. Does it keep projection separate from authority?
6. Does it avoid treating a run, report, score, or transcript as final truth?
7. Does it preserve public-repo cleanliness?
8. Does it reuse existing project substrate before introducing a new dependency?
9. If it adds a dependency, did it pass the dependency adoption gate?
10. If it asks for human attention, is the request actionable, scoped, and
    resumable, and is it truly necessary rather than already decidable by
    policy?
11. If it imports or enables a user asset, is the asset scoped, dry-run, and
    prevented from bypassing evidence, policy activation, or adoption decisions?
12. Is this a real early-adopter need, or only competitor-parity theater?
13. If the user asked about completeness, recurrence, ambiguity, or a previous
    agent miss, did the proposal run the Intent Framing Gate before choosing a
    literal implementation?

If the proposal cannot answer those questions, it is not ready.

## Master Plan Completion Criteria

This master plan is complete for phase-one planning when:

- it is linked from the documentation map, status inventory, governance spine,
  and reviewer index;
- it names the first vertical slice;
- it defines phase order and stop lines;
- it preserves the boundary between planning authority and runtime proof;
- it keeps RDCode as projection until backend governance grants narrow
  writeback.

It becomes eligible for promotion only after at least the review-first vertical
slice is implemented, tested, and reviewed with evidence.
