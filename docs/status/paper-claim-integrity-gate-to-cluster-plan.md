# Paper Claim Integrity Gate To Cluster Plan

Lifecycle state: Draft active phase plan

Plan status: Proposed as the paper-domain vertical plan for review. This is a
design and sequencing document, not an implementation claim.

Reader: DevFrame maintainers and external reviewers who need to judge when the
paper module should grow from paper review and evidence gates into a real paper
R&D agent cluster.

Post-read action: decide whether the proposed phase order is correct, especially
whether a real multi-agent paper cluster should wait until the claim gate, patch
governance, literature harness, experiment gate, and reviewer issue harness are
proven.

Related docs: [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md), [Goal-Bound Evidence Gate Plan](goal-bound-evidence-gate-plan.md), [Review-First Governance Kernel Implementation Spec](review-first-governance-kernel-implementation-spec.md), [Project And Cross-Project Memory Harness Governance Plan](project-and-cross-project-memory-harness-governance-plan.md), [Evaluation, Feedback, And Learning Governance Plan](evaluation-feedback-learning-governance-plan.md), [Total-Control Policy Engine And Human Escalation Governance Plan](total-control-policy-engine-and-human-escalation-governance-plan.md), [rdpaper Workflow](../agent-runtime/rdpaper-workflow.md)

## Core Answer

A real paper R&D cluster should not be the next implementation target.

The revised split is:

```text
Phase 1: Paper Claim Integrity Gate with minimal role provenance
Phase 7: real multi-agent paper R&D cluster
```

Minimal role provenance means the system records who produced a patch, who
checked evidence, and who made the gate decision. It does not mean the system
launches several autonomous paper agents.

The first hard product surface should be:

```text
Paper Claim Integrity Gate, split into 1A/1B/1C
```

The first version must be deliberately narrow:

```text
Phase 1A: Citation Mechanical Gate
Phase 1B: Claim Diff Gate
Phase 1C: Claim Support Judgment Gate
```

Phase 1A handles only mechanical citation integrity. Phase 1B identifies new or
strengthened claims. Phase 1C judges whether a cited snippet semantically
supports a claim.

The first gate does not write the paper, accept the patch, run experiments, or
simulate a full research team.

## External Review Revision

The external review verdict is accepted:

```text
Direction: PASS
Current plan as first implementation task: BLOCKED until further narrowed
```

The previous Phase 1 bundled too many hard problems at once: diff parsing,
claim-strength detection, and semantic citation support judgment. This document
therefore treats Phase 1 as three separate milestones. A demo may only claim the
capability it actually proves.

## Current Repo Reality

The repository already has useful paper foundations:

- an `rdpaper` workflow contract that uses a web AI as a paper reviewer and
  coordinator while a local agent prepares privacy-safe material and evidence;
- a paper iteration template with profile, state, review spec, safety rules,
  ledger, next task, and web AI adapter files;
- a reference paper review pipeline for synthetic paper review, citation check,
  evidence pack creation, safety checks, and dry-run closure;
- a paper workflow state graph that routes diagnosis, acceptance gate, issue
  ledger ingestion, human gate, and finalizer;
- deterministic paper acceptance logic for privacy failures, blocking issues,
  human-required issues, and insufficient evidence;
- human decision audit records for paper gates;
- a paper issue ledger for tracking review issues and learning frequencies;
- public research knowledge-base tooling for public metadata, Obsidian notes,
  PDF download, local RAG integration, citation lookup, and minimized evidence;
- PDF full-text segmentation with privacy-preserving reports and optional local
  parser backends;
- visual-control-plane projection of paper projects, paper runs, paper gates,
  provider safety gates, paper decisions, and paper reviewer sessions.

The repository does not yet prove:

- manuscript diff parsing for before/after paper sections;
- claim extraction from a patch;
- claim-strength change detection;
- citation support classification against retrieved snippets;
- paper gate decisions such as `eligible_for_human_review`, `blocked`,
  `human_required`, and `hard_stop`;
- producer/checker/decider separation for manuscript patches;
- patch accept/reject decision ledger;
- editor projection for claim risk and evidence;
- experiment number traceability;
- reviewer-comment-to-work-item flow;
- real multi-agent paper R&D collaboration.

This means the current project is past basic paper workflow scaffolding, but
before the Paper Claim Integrity Gate.

## Product Thesis

The product should keep the long-term paper cluster ambition, but the first
valuable proof is patch-level integrity.

The key principle is:

```text
Agents may produce, but they cannot self-certify.
Agents may suggest, but they cannot own academic responsibility.
Agents may collaborate, but they cannot bypass the evidence gate.
```

The first version should therefore prove the responsibility topology:

```text
Patch Producer -> Claim/Citation Checker -> Gatekeeper -> Human PI
```

This topology may be represented by fields and fixtures before it is represented
by real parallel agents.

## Phase Plan

### Phase 0: Current Paper Foundations

Status: partially present.

Purpose: preserve the paper module's existing privacy, RAG, metadata, review,
ledger, and visual projection capabilities as reusable substrate.

Current assets:

- paper review workflow and safety contract;
- paper iteration template;
- public research metadata and note generation;
- citation metadata lookup;
- PDF segmentation;
- paper acceptance gate;
- paper issue ledger;
- human gate audit;
- paper visual projection.

Exit criteria:

- the existing paper tests remain passing;
- public paper capability claims are separated from private-paper or final
  acceptance claims;
- the next implementation does not weaken current privacy boundaries.

### Phase 1A: Citation Mechanical Gate

Purpose: prove that a manuscript patch cannot enter the paper review path with
unresolved, untrusted, or fabricated citation keys.

Minimum input:

```text
section_before.tex
section_after.tex
refs_metadata.json
retrieved_snippets.json
paper_patch_provenance.json
```

Minimum output:

```text
citation_mechanical_report.json
paper_gate_decision.json
```

Required behavior:

- parse changed section text sufficiently to identify citation keys introduced
  or touched by the patch;
- verify citation keys against bibliography metadata;
- distinguish verified metadata, user-provided metadata, model-suggested
  metadata, missing metadata, and fabricated references;
- verify that each required citation has at least one retrieved snippet artifact;
- produce mechanical evidence for citation key existence, metadata source, and
  snippet existence;
- produce a gate decision with evidence refs;
- block missing citation keys, missing snippets, and untrusted metadata;
- hard-stop fabricated references;
- enforce minimal role provenance.

No semantic support judgment is allowed in Phase 1A. A snippet existing does not
mean it supports the claim.

Minimum role fields:

```text
patch_producer_principal_id
checker_principal_id
gatekeeper_principal_id
```

Required validation:

- producer equal to gatekeeper fails validation;
- empty evidence refs result in `blocked`;
- gatekeeper evidence refs that contain only the gatekeeper's own
  natural-language summary result in `blocked`;
- UI or projection state cannot mark a paper patch eligible without a backend
  decision artifact.

Allowed decisions:

```text
Decision.outcome:
  eligible_for_human_review
  blocked
  human_required
  hard_stop

Decision.reason_codes:
  missing_citation
  missing_snippet
  fabricated_reference
```

Stop lines:

- do not auto-accept manuscript patches;
- do not use `policy_continue` for manuscript modification;
- do not start a multi-agent runtime;
- do not let model memory invent references;
- do not infer semantic support from citation proximity;
- do not treat semantic support judgment as mechanical fact.

Exit criteria:

- new citation keys are detected;
- missing keys block;
- missing snippets block;
- untrusted metadata blocks;
- fabricated references hard-stop;
- the decision has evidence refs;
- producer and gatekeeper cannot be the same principal.

### Phase 1B: Claim Diff Gate

Purpose: identify which manuscript sentences became new claims, stronger
claims, central contribution claims, empirical-result claims, or scope-expanding
claims.

Additional input:

```text
paper_goal.yaml
claim_diff_policy.yaml
```

`paper_goal.yaml` is optional for Phase 1A. It becomes required in Phase 1B when
the system judges central contribution, overclaim, or scope expansion.

Minimum output:

```text
claim_diff_report.json
paper_gate_decision.json
```

Required behavior:

- identify added sentences;
- identify modified sentences;
- mark possible claim sentences;
- detect strengthened wording, such as `may` changed to `does`;
- classify ordinary claim, central contribution claim, empirical-result claim,
  or scope-expanding claim;
- route scope judgments to `human_required` when the paper goal is missing or
  ambiguous.

No citation support judgment is allowed in Phase 1B.

Additional reason codes:

```text
scope_judgment
```

Exit criteria:

- strengthened claims are detected without claiming evidence support;
- missing `paper_goal.yaml` prevents scope decisions;
- scope expansion routes to human review instead of automatic eligibility.

### Phase 1C: Claim Support Judgment Gate

Purpose: judge whether a cited snippet semantically supports a specific claim,
while preserving that judgment as evidence instead of treating it as a
mechanical fact.

Additional input:

```text
claim_diff_report.json
citation_mechanical_report.json
retrieved_snippets.json
support_judgment_prompt_version
```

Minimum output:

```text
semantic_judgment_evidence.json
paper_gate_decision.json
```

Required evidence shapes:

```text
MechanicalEvidence:
  citation_key_exists
  metadata_source_verified
  snippet_exists
  citation_appears_near_claim

SemanticJudgmentEvidence:
  claim_text
  citation_key
  snippet_text_or_ref
  support_label
  support_rationale
  confidence
  checker_version
  prompt_version
```

Allowed support labels:

```text
direct_support
background_only
weak_support
unrelated_evidence
contradiction
insufficient_context
```

Additional reason codes:

```text
weak_support
unrelated_evidence
contradiction
```

Required behavior:

- preserve claim text and snippet refs in the evidence artifact;
- never expose only a boolean such as `supports_claim`;
- block weak, unrelated, or insufficient evidence for ordinary claims;
- require human review for weak support on central contribution claims;
- hard-stop contradictions;
- prevent `human_required` from bypassing `hard_stop`.

Exit criteria:

- direct support, background-only relevance, weak support, unrelated evidence,
  and contradiction are separated;
- central contribution claims with weak support route to human review;
- contradiction cannot be downgraded to human review.

### Phase 2: Patch Governance

Purpose: make paper patch responsibility explicit before adding editor UI or
agent orchestration.

Required additions:

- patch artifact identity;
- patch producer principal;
- checker principal;
- gatekeeper principal;
- human PI decision principal;
- `cannot_self_approve` validation;
- patch accepted/rejected decision record;
- reason and evidence refs for every patch decision.

Required negative cases:

- producer and gatekeeper are the same principal;
- gatekeeper cites only its own natural-language judgment;
- patch is accepted without evidence refs;
- weak semantic support is treated as direct support;
- UI state marks patch accepted without a decision.

Exit criteria:

- a reviewer can replay why a patch became eligible for human review;
- a reviewer can prove no role self-approved its own output;
- human acceptance or rejection is recorded as a decision, not chat text.

### Phase 3: Projection Contract

Purpose: prove that RDCode or another editor can project the paper gate without
becoming the source of truth.

Minimum contract fixture:

- manuscript diff;
- claim-risk highlights;
- evidence panel;
- gate decision;
- exact human question when needed;
- links to patch, evidence, and decision artifacts.

Stop lines:

- do not build a full paper workbench yet;
- do not require a real editor UI in Phase 3;
- do not let editor UI accept a patch without backend decision;
- do not expose agent task queues before the gate model is stable.

### Phase 4: Literature Harness

Purpose: reuse retrieval and literature infrastructure to provide candidate
evidence, not automatic writing.

Reuse targets:

- public metadata APIs;
- bibliography metadata lookup;
- local RAG pipeline;
- PDF segmentation;
- Obsidian/Zotero style metadata sources;
- external systems such as PaperQA-style retrieval or OpenScholar-style
  scientific synthesis through adapters if needed.

Required behavior:

- produce candidate evidence with source level and provenance;
- keep public, private, synthetic, and user-authorized sources distinct;
- never auto-insert citations into the manuscript;
- never claim that retrieval alone proves a claim.

Required hard negatives:

- snippet exists but citation key is absent from bibliography;
- top-k retrieved snippet is relevant but belongs to a different citation key;
- metadata is verified but snippet is missing;
- snippet is background-relevant but does not directly support the claim.

Exit criteria:

- Paper Claim Integrity Gate can consume retrieved snippets from the literature
  harness;
- retrieved evidence remains advisory until attached to a gate decision.

### Phase 5: Experiment Number Gate

Purpose: extend paper integrity from citation-supported claims to experiment
numbers, figures, and tables.

Minimum input:

- table or figure artifact;
- metric value;
- experiment run metadata;
- log, script, or config reference;
- source data fingerprint where possible.

Required behavior:

- map numbers to run artifacts;
- detect numbers without source;
- detect metric-name mismatch;
- detect stale or superseded experiment output;
- route expensive reruns or method changes to human review.

Stop lines:

- do not generate formal results from temporary logs;
- do not allow model summaries to replace experiment artifacts;
- do not run expensive experiments without explicit policy.

### Phase 6: Reviewer Issue Harness

Purpose: turn reviewer comments and rebuttal claims into governed work items.

Required behavior:

- parse reviewer issue into work item;
- classify requested change;
- connect rebuttal claim to evidence;
- track promised manuscript change;
- block unsupported rebuttal promises;
- record resolved, accepted-risk, or rejected issue decisions.

Exit criteria:

- rebuttal text cannot make unsupported claims;
- promised changes can be traced to patch decisions.

### Phase 7: Paper R&D Cluster

Purpose: only after the gates above are reliable, introduce real multi-agent
paper collaboration.

Allowed roles:

- Research Planner;
- Literature Agent;
- Patch Producer or Writing Agent;
- Claim/Citation Checker;
- Experiment Agent;
- Critic;
- Gatekeeper;
- Human PI.

Required cluster invariants:

- each agent has a role, principal, scope, and allowed action class;
- no agent can approve its own artifact;
- Gatekeeper does not produce manuscript content;
- Critic cannot hard-stop without evidence or a human question;
- Literature Agent supplies candidate evidence, not manuscript authority;
- Experiment Agent supplies run artifacts, not final conclusions;
- Human PI handles research judgment and final acceptance;
- all cross-agent handoffs become artifacts, evidence, or decisions.

Cluster entry criteria:

- Phase 1 claim gate passes positive and negative cases;
- Phase 2 patch governance proves role separation;
- Phase 4 literature harness produces evidence consumable by the claim gate;
- Phase 5 experiment gate proves numeric traceability;
- Phase 6 reviewer issue harness proves rebuttal governance;
- editor projection can display decisions without owning authority;
- tests prove that self-approval, UI-only acceptance, model-memory citations,
  and missing evidence all fail closed.

If these are not true, implementing the cluster would likely produce busy agent
output without trustworthy paper governance.

## Object Model Boundary

Do not create a separate top-level paper object family in the first phases.

Use DevFrame's governance spine:

```text
Project
WorkItem
Run
Artifact
Evidence
Decision
Projection
```

Paper-specific concepts should be represented through `type`, `kind`, and
payload fields.

Recommended examples:

```text
Project(type=paper)
WorkItem(kind=paper_claim_integrity_gate)
Artifact(kind=latex_section | latex_patch | bibliography | retrieved_snippet)
Evidence(kind=citation_exists | citation_supports_claim | claim_overreach)
Decision(kind=paper_gate)
```

Role provenance belongs on runs, artifacts, evidence, and decisions. It should
not require a multi-agent runtime in Phase 1.

## Decision Shape

Do not create a second acceptance engine for paper claims.

Use the DevFrame decision spine:

```text
Decision.outcome:
  eligible_for_human_review
  blocked
  human_required
  hard_stop

Decision.reason_codes:
  missing_citation
  missing_snippet
  weak_support
  unrelated_evidence
  scope_judgment
  fabricated_reference
  contradiction
```

Mapping rule:

```text
PaperClaimGateDecision.outcome -> DevFrame Decision.outcome
PaperClaimGateDecision.reason_codes -> issue/evidence ledger entries
```

The existing `paper_acceptance_gate.py` pattern may be reused as a higher-level
aggregation reference, but it must not become the primary claim gate. The claim
gate is the primary patch-level decision. The issue ledger is downstream
tracking. The broader acceptance gate aggregates paper workflow state.

## Reuse Strategy

Reuse before hand-rolling:

- reuse existing citation metadata lookup for mechanical citation source checks;
- reuse existing public research KB and local RAG pipeline for candidate
  snippets;
- reuse existing PDF segmentation for authorized full-text preparation;
- reuse existing paper acceptance gate patterns only for aggregation style, not
  as the primary claim gate;
- reuse existing paper issue ledger for unresolved issue tracking;
- reuse existing human decision audit for human gate records;
- reuse editor projection only after patch governance is proven.

Build new:

- manuscript diff parser boundary;
- Phase 1A citation mechanical report;
- Phase 1B claim extraction and claim-strength detection;
- Phase 1C citation support classification against snippets;
- paper gate decision schema or fixture;
- role separation checks for paper patches.

Do not build yet:

- general literature search engine;
- full LaTeX editor;
- autonomous reviewer simulator;
- durable paper agent cluster runtime;
- automatic paper writing or submission flow.

## Review Questions For External GPT

Please review this plan critically. The review is not asking whether the paper
cluster vision is attractive. It is asking whether Phase 1A is narrow enough to
enter an implementation specification.

Required verdict:

```text
GO
NO-GO
```

If the verdict is `NO-GO`, the reviewer must list the exact items that must be
removed, renamed, delayed, or clarified before implementation-spec work starts.

Review questions:

1. Is Phase 1A, Citation Mechanical Gate, small and mechanical enough to be the
   first implementation task?
2. Are Phase 1A, Phase 1B, and Phase 1C truly decoupled, or is there hidden
   coupling between citation mechanics, claim diffing, and semantic support
   judgment?
3. Does the shared decision model,
   `eligible_for_human_review | blocked | human_required | hard_stop`, plus
   reason codes avoid state explosion while preserving enough detail?
4. Are the minimal role provenance fields,
   `patch_producer_principal_id`, `checker_principal_id`, and
   `gatekeeper_principal_id`, enough to prevent self-certification?
5. Does the distinction between `MechanicalEvidence` and
   `SemanticJudgmentEvidence` prevent a vague boolean `supports_claim` from
   becoming authority?
6. Is it correct that `paper_goal.yaml` is optional for Phase 1A but required
   for Phase 1B or Phase 1C when scope, central contribution, or overclaim
   judgment is involved?
7. Is Phase 3 correctly reduced to a Projection Contract fixture rather than a
   real editor UI?
8. Does the plan avoid misusing existing paper acceptance, RAG, citation
   metadata lookup, and issue ledger components?
9. Are the required negative tests enough to cover real risks? Which key
   counterexamples are still missing?
10. If the first implementation task must be shrunk further, what should be
    cut from Phase 1A?
11. From the current repository state, is this plan ready to move into a first
    implementation specification? Give a clear `GO` or `NO-GO`.
12. Does this route genuinely serve a trustworthy paper R&D cluster, or does it
    overcomplicate ordinary paper review?

Expected output format:

```text
A. Overall verdict: PASS / CONDITIONAL PASS / BLOCKED
B. GO / NO-GO for first implementation specification
C. Top 3 risks
D. P0 issues that must be fixed
E. P1 issues that should be fixed
F. P2 issues that can wait
G. Final recommendation for Phase 1A
H. Smallest implementation demo the reviewer would accept
```

The key pressure point is:

```text
Can Phase 1A GO now?
If not, what must be cut before it can GO?
```

## Minimum Demo Recommendation

The first credible demo is Phase 1A only:

```text
Input:
  section_before.tex
  section_after.tex
  refs_metadata.json
  retrieved_snippets.json
  paper_patch_provenance.json

Output:
  citation_mechanical_report.json
  paper_gate_decision.json
```

The demo succeeds only if it proves:

- new citation keys are recognized;
- missing citation keys block;
- untrusted metadata blocks;
- missing snippets block;
- fabricated references hard-stop;
- the gate decision cites evidence refs;
- producer and gatekeeper cannot be the same principal.

Demo 2 may then add Phase 1B and Phase 1C:

```text
claim_diff_report.json
semantic_judgment_evidence.json
paper_gate_decision.json
```

## Required Negative Tests

Before claiming the gate is reliable, these cases must fail closed:

1. Citation key exists in bibliography, but the retrieved snippet belongs to
   another paper.
2. Snippet is only background-relevant but is marked as `direct_support`.
3. Claim has no citation, but a previous nearby sentence has a citation; the
   system must block or require human review, never auto-inherit.
4. Patch deletes a qualifier, such as `may` becoming `does`; the system detects
   a strengthened claim.
5. Local conclusion becomes generalized scope; the system detects scope
   expansion.
6. DOI metadata is verified, but snippet is missing; the system blocks with
   `missing_snippet`.
7. Citation metadata comes only from model suggestion; the system blocks or
   hard-stops.
8. Gatekeeper uses its own summary as the only evidence; the system blocks.
9. UI projection marks eligible, but backend decision is absent; validation
   fails.
10. Weak support plus central contribution results in `human_required`, not
    `eligible_for_human_review`.
11. Contradiction plus `human_required` cannot bypass `hard_stop`.
12. Missing `paper_goal.yaml` cannot produce a `scope_judgment` decision.

This is the foundation of a trustworthy paper R&D cluster. The cluster should be
built only after claim integrity, patch governance, literature evidence,
experiment-number traceability, and reviewer-issue governance are proven by
positive and negative tests.
