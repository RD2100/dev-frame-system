# Design Coverage Gap Remediation Plan

Lifecycle state: Accepted active remediation plan

Plan status: External-brain review v2 PASS on 2026-07-04. This is a
gap-driven companion to the master plan, not a stable runtime contract.

Implementation status note (2026-07-07): this document preserves the reviewed
2026-07-04 gap snapshot and remediation order. For current execution progress
after implementation work began, use
`review-governance-kernel-completion-20260706.md` as the bounded status record.
In that newer record, P1/P2/P3-1 are marked PASS and P3-2 is locally
code-complete but still pending external GPT review and commit evidence.

Reader: DevFrame maintainers and coding agents who need to know what the current
design document set covers, what it does not cover yet, and which repair slices
should be implemented first.

Post-read action: use the remediation order below as a historical review
baseline, then check
`review-governance-kernel-completion-20260706.md` before choosing the next
pending item. Do not use this plan to reopen completed items or skip current
review gates.

Related docs: [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md), [Current Coverage Audit Evidence](current-coverage-audit-evidence-20260704.md), [Status Document Inventory](status-document-inventory.md), [Reviewer Index](reviewer-index.md), [Review-First Governance Kernel Implementation Spec](review-first-governance-kernel-implementation-spec.md)

External review record: ChatGPT v2 review returned `PASS`, with no remaining
P0/P1 blockers for accepting this plan within the audited source set and
evidence snapshot. The review also preserved the stop line: this plan does not
prove Phase 1A is implemented, and it does not authorize deferred Paper, graph,
or multi-browser work to start early.

## Purpose

The current documentation set is now broad enough that the main risk is not
missing ideas. The main risk is losing the difference between:

- planned direction;
- implemented substrate;
- reviewable evidence;
- deferred module work;
- stable runtime behavior.

This plan turns the current design-document review into a concrete remediation
queue. It answers the user's intended question: after reading the design system
as a whole, which missing pieces still prevent the project from moving from
planning to a trustworthy working system?

## Assessment Basis

This plan uses a mixed evidence basis:

- `docs/README.md` as the public functional map;
- `status-document-inventory.md` as the active/deferred/evidence classification
  map;
- `document-driven-transformation-master-plan.md` as the phase order;
- `current-coverage-audit-evidence-20260704.md` as the current repo-evidence
  snapshot;
- the active and deferred plan set listed in `status-document-inventory.md`;
- direct source documents included in the external-brain review bundle for the
  reviewed iteration.

This plan does not claim a clean release state. The evidence snapshot is a dirty
current-worktree snapshot. Full cross-document completeness is limited by the
source documents available in the review bundle for a given review round. When a
row is derived from inventory or master-plan summaries rather than direct source
text, the `Basis` column must say so.

The coverage matrix below is intentionally retained as the original reviewed
gap snapshot. Do not read rows such as "Phase 1A files are absent" as the latest
implementation status without also checking the newer completion status record.

## Coverage Matrix

| Area | Covered by design docs | Current real state | Gap | Priority | Basis |
|---|---|---|---|---|---|
| Documentation navigation | `docs/README.md`, `status-document-inventory.md`, `reviewer-index.md` | Functional map and status inventory now exist | Needs automated docs-link and inventory drift check | P1 | Direct source docs plus public snapshot gate |
| Review-governance kernel | master plan, contraction plan, implementation spec | Phase 1A files are absent | Schema, fixtures, negative tests, and optional status helper are missing | P0 | Direct implementation spec plus file-existence evidence |
| Evidence and decision lifecycle | runtime governance plan, evidence docs, master plan | Existing evidence schemas and bundle evidence exist | No single packet proves context -> run -> artifact -> evidence -> decisions -> projection | P0 | Master plan plus evidence record; runtime governance details require direct review before implementation |
| Projection vs authority | visual control plane docs, master plan, graph plan | Dashboard/T3/read-model substrate exists | No review-kernel-derived projection contract yet | P0/P1 | Master plan plus graph deferred plan; visual-control details require direct review before implementation |
| External-brain workflow | web AI adapter contract, external-brain skill, bundle tests | Bundle integrity and CDP submission path are partly proven | Browser response capture and local decision ingestion are not first-class evidence | P1 | Direct external-brain skill plus focused tests and browser review evidence |
| Browser automation transport | browser transport roadmap | CDP-family path works for current Chrome profile | Adapter schema, stable runbook, and multi-browser evidence are deferred | P2 | Deferred roadmap plus current CDP evidence; adapter design still requires separate review |
| Skill and methodology governance | methodology skills docs, skill registry code, custom-skill tests | Built-in/custom skill resolution works | No immutable skill fingerprint, revision history, or promotion linkage | P1 | Functional map plus focused custom-skill tests; skill docs need direct review before schema changes |
| Context and knowledge-gap governance | context plans, model-knowledge-gap plan | Context ideas are documented | No shared context snapshot fixture tied to review decisions yet | P0/P1 | Master plan and implementation spec; detailed context docs need direct review before fixture field changes |
| Evaluation and learning | evaluation-feedback-learning plan | TestFrame exists but import probe still fails on missing `schema` | Measurement integrity and missing-measurement semantics are not repaired | P2 | Evidence record import probe plus inventory summary; evaluation plan may need redacted/direct review |
| Goal-bound continuation | goal-bound evidence gate plan, master plan | Planned as gate decision payload | Fixture exists only as planned review-kernel example | P1 | Master plan and implementation spec; goal-bound plan requires direct review before broadening |
| Policy and human escalation | total-control policy plan, human attention plan | Planned concepts exist | No phase-one policy decision fixtures or escalation evidence | P2 | Inventory and master-plan phase order; policy docs require direct review before implementation |
| User workflow assets | early adopter asset governance plan | Custom skills exist | No governed asset import/promotion lifecycle | P2 | Inventory plus custom-skill tests; asset plan requires direct review before lifecycle design |
| Paper domain | rdpaper docs, paper plans, Paper KB plan | Paper substrate exists | Paper KB workspace contract must wait for review-kernel fixtures | P3 | Deferred Paper KB plan and master-plan stop lines |
| Graph projection and canvas | graph projection plan | Plan externally reviewed | Contract/UI/writeback remain deferred until review-kernel and projection derivation pass | P3 | Deferred graph plan and prior external-brain PASS |

## Critical Gaps

### P0-1: Review-Governance Kernel Is Still Missing

Problem: the project has many useful components, but no small machine-checkable
packet that proves the core lifecycle.

Repair:

1. Create `schemas/review_governance_kernel.schema.json`.
2. Create these fixtures under `schemas/examples/review-governance/`:
   `success.json`, `blocked.json`, `insufficient-evidence.json`, and
   `missing-context.json`.
3. Add `packages/control-plane/tests/test_review_governance_kernel.py`.
4. Add `packages/control-plane/control_plane/review_governance_kernel.py` only
   if schema-only tests create duplication or unclear derived status logic.

Acceptance:

- all fixtures validate;
- missing context blocks readiness;
- run success alone cannot complete work;
- report-only output becomes insufficient evidence;
- gate pass requires evidence IDs;
- projection cannot mark work complete without gate decision.

### P0-2: Evidence Lifecycle Exists As Vocabulary, Not As One Proven Chain

Problem: schemas and docs already mention evidence, reviews, final verdicts, and
runtime reports, but no first slice ties them into one reviewable chain.

Repair:

1. In Phase 1A fixtures, require explicit links between context snapshot,
   run, output artifact, evidence, review decision, gate decision, and
   projection status.
2. Keep context snapshot as `Artifact(kind=context_snapshot)`, not a new
   top-level object.
3. Add negative cases for missing evidence refs, mutable context, and worker
   completion claims.

Acceptance:

- a reviewer can inspect one JSON packet and understand why it is completed,
  blocked, insufficient, or not ready;
- no run, report, transcript, projection, or score can become final authority
  without a decision.

### P0-3: Context-Gap Claims Need Fixture-Level Enforcement

Problem: context and model-knowledge-gap governance are documented, but the next
implementation could still ignore them unless the review kernel makes them
testable.

Repair:

1. Add required context snapshot payload fields for source refs, selected items,
   omitted high-impact context, selection rationale, content hash, checked
   sources, unresolved gaps, and freshness.
2. Add a fixture where knowledge-dependent claims are blocked because checked
   sources or unresolved gaps are missing.

Acceptance:

- context omission is visible as evidence or blocker, not hidden in prose;
- a knowledge-dependent review cannot pass with unresolved required gaps.

## Important Gaps

### P1-1: External-Brain Review Needs A Local Decision Ingestion Path

Problem: the bundle generator proves package integrity, and CDP can submit to
ChatGPT, but the browser response is still mostly runtime evidence outside the
public repo. The project needs a local pattern for turning web feedback into a
non-authoritative artifact plus a local decision.

Boundary: this does not block starting Phase 1A. Phase 1A should only enforce
context snapshot and knowledge-gap requirements inside review-kernel fixtures.
External-brain response ingestion is the next evidence-shape repair after the
kernel can already reject report-only and evidence-free claims.

Repair:

1. Add an external-brain review result evidence shape or reuse existing evidence
   schemas with an `external_review_response` artifact kind.
2. Record bundle ID, manifest hash, submitted prompt hash, response capture
   timestamp, reviewer verdict, accepted feedback, rejected feedback, and local
   decision.
3. Add tests proving web feedback cannot directly pass a gate or adopt a doc.

Acceptance:

- external feedback is traceable;
- skipped or incomplete context audit is recorded as weak feedback;
- accepted edits require local evidence and a decision.

### P1-2: Skill Governance Needs Fingerprints And Promotion History

Problem: methodology and custom skills are executable, but evaluation and
learning cannot compare them safely without immutable versions.

Repair:

1. Add a skill content fingerprint record that includes `SKILL.md` and relevant
   bundled references.
2. Add revision and promotion metadata for custom/project skills.
3. Tie future evaluation findings to proposed skill revisions, not just skill
   IDs.

Acceptance:

- the same skill ID with changed content has a different fingerprint;
- a learning proposal cannot update a skill without regression evidence and a
  promotion decision.

### P1-3: Documentation Governance Needs Drift Checks

Problem: the directory was previously incomplete. Manual rules now exist, but
the system can drift again.

Repair:

1. Add a lightweight docs consistency check that verifies every `docs/status/*.md`
   file appears in `status-document-inventory.md`.
2. Check that master-plan companion docs appear in `docs/README.md` and
   `reviewer-index.md` when they affect implementation.
3. Keep warnings targeted; do not require `docs/README.md` to list every
   historical status file.

Acceptance:

- adding a public subsystem, evidence record, or deferred module without
  inventory/reviewer visibility fails a local check or produces a clear warning.

### P1-4: Goal-Bound Continuation Should Become A Fixture, Not A Supervisor

Problem: the plan correctly rejects a broad Goal Supervisor, but the positive
replacement still needs a small fixture.

Repair:

1. Add optional `goal-bound-continuation.json` only after required Phase 1A
   fixtures pass.
2. Represent continuation as a `Decision(kind=gate)` payload and work-item
   governance payload.
3. Require same goal, same context boundary, evidence refs, and low-risk next
   step.

Acceptance:

- continuation cannot happen without evidence refs and a context snapshot;
- no supervisor, scheduler, checkpoint, or broad work loop appears as a
  top-level object.

## Deferred Gaps

### P2-1: Evaluation And Learning Integrity

Problem: TestFrame is promising but currently not importable as a reliable
public evaluation package, and missing measurements must never default to pass.

Repair after Phase 1:

1. Fix the missing `schema` package/import boundary or record a replacement
   disposition.
2. Add tests proving absent code-review evidence is `NOT_EVALUATED`, `BLOCKED`,
   or equivalent, never `PASS`.
3. Add subject snapshots, rubric versions, evaluation runs, observations,
   scorecards, improvement proposals, and promotion decisions only after the
   review lifecycle works.

Acceptance:

- TestFrame report import succeeds in the public snapshot or the missing module
  is explicitly removed from the path;
- no missing dimension contributes to an aggregate score;
- evaluation cannot override a blocked gate.

### P2-2: Policy And Human Escalation

Problem: policy, authority, and human attention are well planned but not yet
fixture-backed.

Repair after Phase 1 and document authority projection:

1. Add policy decision payload fixtures.
2. Add human-required and blocked-self-promotion cases.
3. Add escalation evidence requirements.

Acceptance:

- a worker, browser, dashboard, model score, or external review cannot grant
  itself authority;
- human-required states name the exact decision requested.

### P2-3: Browser Transport Adapter Boundary

Problem: CDP is the current stable family, but multi-browser support is only a
deferred plan.

Repair after CDP path has repeatable evidence:

1. Define a transport adapter schema.
2. Keep Chrome/CDP stable first.
3. Add Edge/Chromium CDP probes only after adapter schema tests pass.
4. Treat WebDriver BiDi as experimental until it passes the same submit, wait,
   extract, and evidence tests.

Acceptance:

- manual mode cannot be reported as automated success;
- experimental adapters cannot satisfy stable browser evidence;
- Firefox is not described as CDP-compatible.

## Later Domain Gaps

P2 and P3 gaps are tracked so the project does not forget them. They are not
acceptance blockers for starting or completing Phase 1A unless a specific
negative fixture is required by the review-governance kernel.

### P3-1: Paper KB Workspace Contract

Problem: paper workflow substrate exists, but Paper KB iteration must not become
a parallel runtime or schema family before review-governance Phase 1A.

Repair:

1. After Phase 1A, add paper workspace fixtures under the review-governance
   kernel.
2. Block whole-vault scans, path traversal, source-root-equals-vault-root, and
   unaudited Obsidian writeback.
3. Keep scheduler, browser submission, PDF conversion, and skill extraction out
   of the first Paper KB slice.

Acceptance:

- paper workspace facts are represented through existing governance objects;
- Paper KB cannot bypass evidence or local decisions.

### P3-2: Graph Projection And Knowledge Canvas

Problem: graph/canvas work is valuable, but it is a projection layer and must
not create source truth.

Repair:

1. After Phase 1A and projection derivation, add a graph projection contract
   fixture.
2. Keep the first graph slice read-only: no UI, graph database, broad
   extraction, writeback, or graph-driven code changes.
3. Only later add visual graph UI and annotations as proposals or artifacts.

Acceptance:

- inferred edges cannot become source truth;
- annotations cannot become decisions;
- graph context can seed context selection only with cited, authority-labeled
  nodes.

## Remediation Order

1. P0-1: implement review-governance kernel schema, required fixtures, and
   negative tests.
2. P0-2: prove one evidence and decision lifecycle packet through those
   fixtures.
3. P0-3: enforce context and knowledge-gap requirements inside the fixtures.
4. Pre-merge documentation check: verify this plan and its evidence record are
   visible from `docs/README.md`, `status-document-inventory.md`,
   `reviewer-index.md`, and the master plan.
5. P1-3: add automated docs inventory/reviewer drift checks so the directory
   stays reliable.
6. P1-1: add external-brain response ingestion as non-authoritative evidence
   plus local decision.
7. P1-2: add skill fingerprints and promotion history.
8. P1-4: add goal-bound continuation fixture.
9. P2-1: repair evaluation/TestFrame measurement integrity.
10. P2-2: add policy and human escalation fixtures.
11. P2-3: define browser transport adapter boundary.
12. P3-1: add Paper KB workspace contract fixtures.
13. P3-2: add graph projection contract fixtures.

## Stop Lines

- Do not build graph UI before Phase 1A and projection derivation pass.
- Do not build Paper KB runtime commands before Paper KB is expressed as
  review-kernel fixtures.
- Do not add multi-browser selection before CDP evidence and adapter-schema
  tests exist.
- Do not implement model routing or long-term learning before evaluation
  measurement integrity is repaired.
- Do not allow external-brain output, browser state, dashboard state, model
  score, worker report, or graph annotation to become authority without a local
  decision.

## Completion Criteria

This remediation plan is accepted when:

1. the external-brain reviewer says the plan is sufficient for prioritizing
   missing work;
2. no P0 gap is missing within the audited source set and evidence snapshot;
3. any claim of full cross-document completeness is backed by an expanded
   review bundle or a separate full-doc coverage evidence record;
4. each gap has a repair path and acceptance evidence;
5. the plan preserves the 2026-07-04 Phase 1A priority as historical review
   context while pointing current readers to the completion status record;
6. the plan is linked from the documentation map, status inventory, reviewer
   index, and master plan.
