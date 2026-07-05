# Document-Driven Transformation Final Plan

Lifecycle state: externally reviewed final draft

Last updated: 2026-07-05

Reader: a coding agent or engineer taking over implementation after the planning
cleanup.

Post-read action: implement only the Phase 1A review-first governance kernel
slice, unless a later evidence-backed decision explicitly changes the order.

Related docs: [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md), [Review-First Governance Kernel Implementation Spec](review-first-governance-kernel-implementation-spec.md), [Skill Asset Utilization Plan](skill-asset-utilization-plan.md), [Agent Coding Discipline](../agent-runtime/agent-coding-discipline.md), [Asset Utilization Inventory](asset-utilization-inventory-20260705.md), [Status Document Inventory](status-document-inventory.md), [Reviewer Index](reviewer-index.md)

External review status: ChatGPT coding-agent review source set received `PASS`
on 2026-07-05. A refreshed v2 review after adding coding-agent execution
constraints also received `PASS`, with no remaining P0 or P1 blockers for this
final draft.

## Final Decision

The planning work is sufficiently consolidated for coding to resume, but the
platform is not implemented.

The next coding slice is still the review-first governance kernel. Every other
topic in the planning set is either:

- a prerequisite discipline or routing sidecar;
- reference context for the kernel;
- a deferred module that must wait for kernel evidence;
- an evidence record proving what was inspected.

The system should not grow by adding a smarter coordinator, more tools, a
dashboard, a marketplace, or a graph UI first. It should grow by proving one
small lifecycle:

```text
Project
  -> WorkItem(kind=review)
  -> Artifact(kind=context_snapshot)
  -> Run
  -> Artifact(output)
  -> Evidence
  -> Decision(kind=review)
  -> Decision(kind=gate)
  -> Projection(read-only)
```

If that lifecycle cannot distinguish `completed`, `blocked`,
`insufficient_evidence`, and `human_required`, no later automation is
trustworthy.

## Current Truth

The repository already has useful substrate:

- public documentation maps and status inventories;
- governance rules and object-model decisions;
- methodology skill discovery and dispatch;
- custom-skill storage paths;
- MCP server, consent, live probe, and Web-AI result recording code;
- external-review bundle tooling with manifest, ledger, redaction, and
  validator checks;
- browser/CDP binding for logged-in ChatGPT review sessions;
- visual/read-model projection code;
- many schemas, tests, and recon receipts.

The repository does not yet have the runtime proof that turns this substrate
into a governed platform:

- no accepted `skill_usage` or asset-utilization evidence shape;
- no offline MCP utilization ledger;
- no fingerprint/promotion lifecycle for skills or plugin assets;
- no stable dashboard authority.

**Phase 1A review-first governance kernel — COMPLETED (2026-07-05):**

- [x] review-governance kernel schema (`schemas/review_governance_kernel.schema.json`) — 44 static constraints under draft-07
- [x] 4 fixture payloads (success, blocked, insufficient-evidence, missing-context)
- [x] 55 contract tests (`test_review_governance_kernel.py`) — all passing
- [x] Semantic validator (`review_governance_validator.py`) — 12 cross-object constraints
- [x] External review loop completed — ChatGPT returned GO on round 7
- [x] Post-GO suggestions addressed (Round 7 feedback: latest_decision_id target_ref binding + reverse inconsistency check)

The kernel validates the full lifecycle:
```text
Project
  -> WorkItem(kind=review)
  -> Artifact(kind=context_snapshot)
  -> Run
  -> Artifact(output)
  -> Evidence
  -> Decision(kind=review)
  -> Decision(kind=gate)
  -> Projection(read-only)
```

Therefore the correct implementation stance is: governance kernel proven,
substrate ready for Phase 1B.

## Operating Invariants

These invariants are final for the next coding slice:

| Invariant | Meaning for coding agents |
|---|---|
| Evidence decides implementation truth | Reports, chat summaries, run success, and GPT feedback are not completion evidence by themselves |
| Decisions carry authority | A passing review or gate must be a `Decision`, not a dashboard label or worker claim |
| Context snapshots are artifacts | Context must be selected, cited, immutable, and auditable |
| Projection is read-only | UI, RDCode, graph views, and dashboards may display status but must not create authority |
| Skills are routed assets | Skill selection, trigger resolution, or registry presence is not acceptance evidence |
| Assets need accounting | MCP, plugins, local skills, schemas, and review bundles count only when they produce artifacts accepted by evidence and gates |
| External GPT review is a mandatory critique loop | A bounded coding package is not ready to close until local verification passes and the web review loop reaches `PASS`, unless a human owner records an explicit exception decision |
| Human attention is scarce | Ask humans only for authority gaps, not for routine work that policy and evidence can decide |
| Reuse precedes hand-rolling | Client, runtime, provider, MCP, review, evidence, UI, browser, and multi-agent surfaces need recon/reuse checks before new implementations |

## Final Architecture

The target architecture is a document-driven governance loop:

```text
Planning docs define intent, authority, non-goals, and stop lines.
Runtime records runs, artifacts, evidence, and decisions.
Review/gate decisions validate whether work may continue or complete.
Read-only projections expose state to humans, shells, and clients.
Evaluation and asset promotion happen only after evidence-backed outcomes.
```

This is not a generic autonomous-agent platform yet. It is a constrained
governance spine for making agent work auditable.

## Phase Order

### Phase 0: Sidecars Already Accepted

These items are prerequisites for reliable implementation, not competing runtime
features:

| Sidecar | Status | Purpose |
|---|---|---|
| Skill router | accepted plan | Maps work types to skill chains, artifacts, and evidence |
| Agent coding discipline | accepted seed catalog | Gives rule IDs for interface truth, requirement alignment, reuse, verification, scope restraint, uncertainty, and incremental delivery |
| Asset utilization operating chain | accepted plan | Defines how skills, MCP, plugins, schemas, rules, and review bundles become accountable assets |
| External-brain review workflow | implemented tooling | Packages context for GPT review without making GPT project authority |
| CDP browser binding | implemented support path | Uses a persistent logged-in Chrome profile for web review automation |

These sidecars may be used immediately as discipline. Their deeper runtime
enforcement waits for Phase 1A evidence and gate validation.

### Phase 1A: Review-First Governance Kernel

This is the first coding target.

Create the smallest public package that proves:

- immutable context snapshot artifact;
- succeeded run does not complete work;
- report artifact is not evidence by itself;
- evidence records support or reject specific claims;
- review decision cites evidence;
- gate decision decides completion or blocker;
- projection is derived from packet facts;
- missing context and insufficient evidence block progress.

Expected package:

| Surface | Purpose |
|---|---|
| review-governance schema | Validate the kernel packet |
| positive fixture | Evidence-backed review and gate pass |
| blocked fixture | Evidence-backed failure or blocker |
| insufficient-evidence fixture | Report exists but evidence is missing or inconclusive |
| missing-context fixture | Work item cannot become ready |
| contract tests | Validate fixtures and forbidden shortcuts |
| optional helper | Derive status only if schema tests need reusable logic |

Phase 1A must stay schema, fixtures, negative tests, and optionally a small
helper. It must not become a full command, UI, coordinator runtime, asset
registry, marketplace, graph database, or memory system.

### Phase 1B: Derivation Helper And Projection Proof

Only after Phase 1A fixtures pass, add a small helper if needed to derive
`blocked`, `reviewing`, `insufficient_evidence`, and `completed` from packet
facts.

This phase may expose a read-only projection, but the projection must not invent
authority.

### Phase 1C: Prepare-Only Review Flow

Only after the kernel packet and derivation are proven, consider a prepare-only
review driver or `/rdreview` skeleton.

It may emit a sample review packet. It must not run autonomous coordinator work
or write public runtime state without explicit request.

### Phase 2: Documentation Authority And Promotion

Connect document lifecycle states to evidence-backed decisions. A document is
not authoritative because it is polished; it becomes authoritative when a
decision adopts it.

### Phase 3: RDCode / Client Projection Boundary

Let shells and clients consume governance state without becoming the governance
database. RDCode may request, display, and propose. It must not finalize
completion, adoption, or policy.

### Phase 4: Evaluation, Feedback, And Asset Utilization

After review/evidence decisions are real, add:

- `skill_usage` evidence;
- asset-utilization records;
- MCP offline utilization ledger;
- external-review feedback ledger;
- skill fingerprints and promotion state;
- plugin/local-skill allowlist and quarantine.

None of these should exist as standalone authority. They must point to artifacts,
evidence, and decisions.

### Phase 5: Policy, Attention, And Goal-Bound Continuation

After gates work, introduce higher-power continuation only as explicit gate
decisions under declared scope, policy, evidence, and context boundaries.

Goal-bound continuation is not a persistent supervisor.

### Phase 6: Deferred Domain Modules

Paper knowledge-base iteration, graph projection, multi-browser transport, and
larger agent-team UX are deferred modules. They can become domain fixtures or
read-only projections only after the kernel proves authority boundaries.

## Immediate Coding Contract

The next implementation agent must:

1. Read the review-governance implementation spec first.
2. Read the governance rules and object-model decision record for terms and
   authority boundaries.
3. Use the skill router row for Phase 1A:
   `review-governance-kernel -> tdd -> evidence-driven-acceptance`.
4. Apply the agent coding discipline rules for interface truth, requirement
   alignment, reuse, verification, scope restraint, uncertainty, and incremental
   delivery.
5. If reusable assets are used, name the asset route and resulting artifact.
6. Implement only the smallest schema, fixture, test, and optional helper needed
   to prove the first review lifecycle.
7. Update public indexes when adding public schemas, examples, tests, or docs.
8. Run targeted tests and public snapshot verification.
9. After each bounded implementation package, prepare an external review bundle
   and submit it through the project CDP/browser path.
10. Do not mark a package complete until the web review loop returns `PASS`, or
   a human owner records an explicit local decision explaining why a non-`PASS`
   review result is being deferred or overridden.

Expected verification shape:

```powershell
python -m pytest packages/control-plane/tests/test_review_governance_kernel.py -q
powershell -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1
git diff --check
```

If test commands differ, the implementation report must explain why.

Expected review-loop shape for each bounded coding package:

```text
local implementation package
  -> targeted tests + public snapshot verification
  -> context-pack-builder selects exact sources
  -> external-brain prepares review bundle
  -> validate-review-bundle must be ready_for_review
  -> bind-chrome / CDP-hosted ChatGPT submission
  -> GPT review returns PASS / CONDITIONAL PASS / NO-GO
  -> if not PASS, revise locally and resubmit
  -> close package only after PASS or explicit human exception decision
```

Minimum review bundle roles for a coding package:

- `plan`
- `implementation_spec`
- `schema` or `fixture` when changed
- `test`
- `diff`
- `evidence`
- `rules`

The review question must ask the web reviewer to audit context first, then
return `PASS`, `CONDITIONAL PASS`, or `NO-GO` with P0/P1 issues. The web review
is a mandatory critique gate for package closure, but it is still not project
authority by itself. Local acceptance requires evidence-backed decisions.

## Hard Stop Lines

Do not implement any of these before Phase 1A passes:

- broad autonomous coordinator execution;
- full RDCode write authority;
- dashboard or projection authority;
- graph UI, graph database, or annotation writeback;
- Paper KB runtime commands or Obsidian writeback;
- multi-browser transport selection beyond the current stable CDP path;
- plugin marketplace or local-skill bulk import;
- skill telemetry, fingerprints, or promotion records without evidence gates;
- MCP active-use platform that cannot be audited offline;
- model-provider auto-routing;
- long-term memory promotion;
- LangGraph/Temporal migration;
- authorization graph expansion;
- persistent goal supervisor.

Do not claim any bounded package is complete when:

- local tests or public snapshot verification have not passed;
- the review bundle was not validated as `ready_for_review`;
- the browser submission did not use the project CDP path;
- the latest web review result is still `CONDITIONAL PASS` or `NO-GO`;
- the only reason for closure is that the coding agent believes the work is
  good enough.

## Acceptance For This Final Plan

This final plan is accepted as a planning document only when:

- it is linked from the documentation map, status inventory, and reviewer index;
- it identifies Phase 1A as the next coding target;
- it preserves sidecars as discipline, not runtime proof;
- it names deferred modules and stop lines;
- it is reviewed by external GPT with no remaining P0/P1 blockers;
- local public snapshot verification still passes.
- it constrains the implementation agent to a package-by-package local
  verification plus web-review-until-pass loop.

It does not become stable runtime documentation until implementation evidence
exists.

## What Changes After This Plan

After this final plan is accepted, planning should stop expanding horizontally.
New work should either:

- implement Phase 1A;
- fix a P0/P1 blocker found by review;
- update an index or evidence record required for traceability;
- explicitly defer a tempting module behind the kernel.

Any proposal that starts with UI, dashboard, plugin import, graph canvas, paper
workspace runtime, multi-browser support, or model routing should be treated as
out of order unless it directly serves the Phase 1A kernel proof.
