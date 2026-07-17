# Evaluation, Feedback, And Learning Governance Plan

Lifecycle state: Historical plan; scheduling superseded by `HANDOFF.md`

Reader: DevFrame maintainers implementing provider-neutral evaluation and controlled improvement workflows

Post-read action: Implement the contract and correctness baseline first, then prove one public-test comparison profile before enabling learning promotion or model routing

Related docs: [Context-Led Model Performance Control Plan](context-led-model-performance-control-plan.md), [Runtime Governance And Evidence Closure Transformation Plan](runtime-governance-and-evidence-closure-transformation-plan.md), [Context Management Architecture Plan](context-management-architecture-plan.md), [Context Noise Governance And Automation Plan](context-noise-governance-and-automation-plan.md), [Project And Cross-Project Memory Harness Governance Plan](project-and-cross-project-memory-harness-governance-plan.md), [Workflow Consolidation And Command Plan](workflow-consolidation-and-command-plan.md)

Promotion target: `docs/agent-runtime/evaluation-and-learning-governance.md` after one evaluation profile and one governed promotion cycle are proven

## Purpose

This plan defines the layer after runtime state and evidence governance.

State and evidence answer whether one run actually happened and whether its
claims are trustworthy. Evaluation answers how well a run performed, why it
succeeded or failed, and whether it is comparable with other runs. Learning
governance decides whether those findings are strong enough to change a Skill,
workflow, context policy, test suite, model route, or project memory.

The target is not autonomous self-modification. The target is a controlled
feedback loop in which every proposed improvement has evidence, a regression
case, an owner, an approval boundary, and a rollback path.

## Position In The Architecture

The project mainline becomes:

```text
Skill
  -> Workflow
  -> Context
  -> Documentation Governance
  -> Runtime State And Evidence
  -> Evaluation And Feedback Learning
  -> Governed Promotion
  -> Updated Skill / Workflow / Context / Tests
```

Three loops must remain separate:

| Loop | Question | Output |
|---|---|---|
| Acceptance loop | Can this individual delivery be trusted? | ReviewRecord and FinalVerdict |
| Evaluation loop | How well did one or more comparable runs perform, and why? | Scorecard, observations, comparison report |
| Learning loop | What should change, and has that change earned promotion? | ImprovementProposal and PromotionDecision |

An evaluation score must never override a blocked FinalVerdict. A successful
single run must never be treated as proof that a Skill or model route is better.

## Audit Snapshot

Audit date: 2026-07-03.

The assessment used CodeGraph and direct inspection of:

- TestFrame aggregation, regression reporting, quality gates, and verdict
  generation;
- control-plane model-provider, go-run, methodology dispatch, custom Skill,
  run-default, visual-state, and test surfaces;
- agent-runtime execution, test, failure, memory-update, review, evidence, and
  final-verdict schemas;
- paper-domain retrieval and local quality-evaluation implementations;
- the evidence-driven acceptance Skill and deterministic @go finalizer.

Focused verification command:

```powershell
python -m pytest `
  packages/control-plane/tests/test_model_providers.py `
  packages/control-plane/tests/test_go_model_provider.py `
  packages/control-plane/tests/test_custom_skills.py `
  packages/control-plane/tests/test_run_defaults.py `
  tests/test_go_evidence.py -q
```

Observed result: `43 passed in 0.59s`.

The result confirms that model-provider selection, methodology metadata,
custom Skill routing, run defaults, and evidence finalization have working test
foundations. These tests do not exercise TestFrame. A direct import probe of
the TestFrame regression reporter failed because its internal `schema` package
is absent from the current public snapshot
(`ModuleNotFoundError: No module named 'schema'`). The focused pass therefore does not
establish a working TestFrame package or a general evaluation system.

## Current Real Capabilities

### TestFrame Contains A Useful Evaluation Substrate, But The Public Package Is Incomplete

TestFrame already provides:

- profile-driven orchestration;
- adapters and normalized test results;
- stage-level pass, fail, blocked, and skipped signals;
- aggregate regression reports;
- environment blocker detection;
- quality-gate input;
- Allure-compatible output and fallback manifests;
- machine-readable TestExecutionReport semantics;
- real, synthetic, dry-run, and blocked-environment profiles.

This is enough source-level capability to justify repairing and retaining
TestFrame as the execution and normalization substrate for `/rdtest`. It should
not be replaced by a new generic evaluation framework before that repair is
assessed.

Current boundary:

- several modules import `schema.canonical` and `schema.stage_results`, but no
  matching package exists in the current public snapshot;
- importing the regression reporter currently raises `ModuleNotFoundError`;
- the package metadata does not declare an external dependency that provides
  these project-specific modules;
- its report vocabulary is test-oriented rather than a general model/Skill
  evaluation contract;
- it does not require a canonical ContextPacket, subject version, or rubric;
- comparison across models, Skills, workflows, and context policies is not a
  first-class run type;
- report verdict logic has no dedicated focused test suite in the inspected
  repository paths.

### One TestFrame Verdict Is Currently Unsafe

The regression report currently assigns:

```text
codeReview = PASS
```

without consuming a real code-review result. This is a direct contradiction of
the project's independent-review discipline.

This must be treated as a P0 evaluation-integrity issue:

- absent review must be `NOT_EVALUATED`, `BLOCKED`, or equivalent;
- it must never default to `PASS`;
- the report must state whether a dimension is measured, inferred, unavailable,
  or not applicable;
- focused tests must cover missing, malformed, blocked, failed, and passing
  review inputs.

No generalized evaluation layer should consume this verdict until that
behavior is corrected.

### Go Runs Already Capture Valuable Experimental Variables

Go-run and agent metadata can already carry:

- model provider;
- worker command, which may contain the selected model for built-in workers;
- methodology metadata;
- input, output, and total tokens;
- cost;
- tool calls;
- worker status;
- changed files;
- verification summary;
- session and isolation information.

These fields are a strong starting point for evaluation observations. Their
population is backend-dependent, so missing values must remain unknown rather
than being converted to zero or a positive signal.

Current boundary:

- there is no immutable snapshot tying a run to the exact Skill contents,
  model identifier, workflow definition, prompt, context packet, tool policy,
  and code revision;
- provider registry fields such as speed, cost, and reliability are descriptive
  configuration labels, not measured historical metrics;
- no statistical or repeated-run comparison is built on top of the metadata.

### Methodology Skills Are Routable But Not Experiment-Versioned

The control plane can discover built-in methodology Skills, load global and
project custom Skills, resolve triggers, and store the selected methodology on
runs and visual projections.

Current boundary:

- methodology records have an ID and source path but no content fingerprint;
- custom Skill records have no immutable version or promotion history;
- a Skill may change while retaining the same ID, making historical comparison
  ambiguous;
- there is no link from an evaluation finding to a proposed Skill revision and
  its regression evidence.

### Evidence And Failure Contracts Are Strong But Not Evaluation Contracts

The repository already has useful schemas for:

- TestExecutionReport;
- ExecutionReport;
- EvidenceManifest;
- GateResult;
- FailureRecord;
- ReviewRecord;
- FinalVerdict;
- MemoryUpdateRecord;
- audit events.

These contracts correctly preserve blocked and failed states and separate test
evidence from final acceptance.

Current boundary:

- FailureRecord does not yet identify evaluation suites, cases, dimensions, or
  improvement proposals;
- ExecutionReport's fallback failure taxonomy is narrow and operational;
- there is no EvaluationSuite, EvaluationCase, EvaluationRun, Observation,
  Scorecard, ComparisonReport, ImprovementProposal, or PromotionDecision
  contract;
- evidence completeness and performance quality are not clearly separated.

### Domain Evaluations Exist As Valuable Isolated Patterns

The repository contains domain-specific examples such as:

- a Minimax observation schema with strengths, weaknesses, error patterns, and
  reliability score;
- paper evidence packs with per-dimension review results;
- deterministic local paper-RAG quality evaluation with retrieval coverage,
  duplicates, low-confidence counts, source consistency, privacy flags, and
  evidence fingerprints.

These implementations demonstrate useful evaluation dimensions and fail-closed
domain gates.

Current boundary:

- they use domain-specific field names and status vocabularies;
- they do not share one evaluation identity, rubric, observation envelope, or
  comparison protocol;
- some are not covered by focused tests in the inspected test directories;
- they cannot yet feed a governed cross-domain improvement process.

### Memory Governance Is Safe But The Learning Loop Stops At Proposal

MemoryUpdateRecord permits only `proposed` status for agent-created records.
Project memory has a runtime store and visual editing surface.

This is a good safety boundary. It prevents agents from writing their own
success story into durable memory.

Current boundary:

- the proposal contract is memory-specific;
- project memory entries do not carry source evidence, observed-at time,
  freshness, confidence, or supersession links;
- there are no parallel proposal types for Skill, workflow, context policy,
  rubric, regression case, or model route changes;
- there is no governed promotion state machine from proposal to shadow test,
  human review, activation, monitoring, and rollback.

### Visual State Can Display Inputs But Not A Learning History

The visual model already exposes model provider, methodology, tool calls,
tokens, cost, run state, evidence, and review information.

Current boundary:

- it does not expose evaluation suites, comparable cohorts, dimension scores,
  confidence, regressions, improvement proposals, or promotions;
- the view should consume a future evaluation read model rather than calculate
  scores itself.

## Critical Findings

### P0: The TestFrame Evaluation Path Is Not Import-Complete

The current public package cannot be treated as an executable evaluation
substrate until its missing internal schema dependency is resolved.

Required correction:

- determine whether the schema package was accidentally omitted, renamed, or
  expected from another repository;
- restore it as a public, packaged module or replace imports with an existing
  canonical contract package;
- add a wheel/install import smoke test;
- add a real report-generation probe after installation;
- do not copy private or submodule-only source into the public repository
  without Recon, licensing, and publication review.

### P0: Missing Evaluation Must Not Become PASS

The unconditional code-review PASS is the first semantic issue to fix after the
package can be imported. A platform cannot learn from measurements if
unmeasured dimensions are silently positive.

Required invariant:

```text
missing != pass
unknown != zero
not_applicable != skipped
blocked != failed
evaluation_score != acceptance_verdict
```

### P0: The System Must Not Grade And Promote Its Own Change

The executor that changes a Skill, workflow, rubric, context policy, or route
must not be the sole evaluator or promoter of that change.

Required boundary:

- executor produces artifacts and evidence;
- evaluator produces observations and a scorecard;
- reviewer challenges the evaluation and checks evidence;
- governance or a human produces the PromotionDecision;
- rollout monitoring may trigger automatic rollback, but not automatic
  promotion.

### P1: Comparisons Are Not Fair Without Subject Snapshots

A comparison is not credible unless it records the exact variables that differ
and the variables that were held constant.

Required snapshot fields:

- task and evaluation-case version;
- model provider and model ID;
- Skill ID and content fingerprint;
- workflow ID and version;
- ContextPacket ID and hash;
- prompt or TaskSpec hash;
- tool and policy profile;
- repository commit and dirty-state summary;
- environment profile;
- random seed or nondeterminism note where relevant.

### P1: Acceptance, Quality, And Efficiency Need Separate Results

A run may be trustworthy but mediocre, or high quality but too expensive, or
blocked before quality can be measured.

Required separation:

- acceptance: whether claims can be trusted;
- quality: correctness and usefulness;
- safety: policy and boundary compliance;
- efficiency: time, tokens, cost, tool calls, and human review effort;
- reproducibility: whether the result can be regenerated;
- confidence: strength and amount of supporting evaluation evidence.

### P1: Failure Records Need Causal Attribution

Current failures can describe what went wrong, but the learning loop also needs
to distinguish likely causes:

- task specification;
- context selection or freshness;
- context noise, stale-source leakage, or misleading retrieval;
- memory retrieval, stale memory, cross-project contamination, or missing
  isolation;
- Skill instructions;
- workflow orchestration;
- model capability;
- model/provider availability;
- tool behavior;
- environment;
- evidence or reviewer process;
- implementation regression;
- human ambiguity.

Causal attribution must allow `unknown` and multiple contributing factors. It
must not force one confident explanation from weak evidence.

### P1: Historical Skill Results Are Not Reproducible Without Fingerprints

Skill ID alone is insufficient. A Skill content hash and source revision are
required before Skill-level comparison or promotion.

### P2: Domain Evaluations Should Become Profiles, Not Be Rewritten

Paper RAG quality checks, public-test package review, code regression, and UI
runtime tests need different rubrics. They should emit common observation and
scorecard envelopes while retaining domain details.

### P2: Model Routing Must Be Delayed

The current model-provider registry is suitable for configuration and preview,
not evidence-based automatic routing. Routing should remain explicit until the
system has comparable cohorts, minimum sample policies, confidence estimates,
and failure-rate monitoring.

## Target Evaluation Model

### Core Records

| Record | Purpose |
|---|---|
| EvaluationSuite | Versioned collection of cases, rubrics, invariants, and execution policy |
| EvaluationCase | One reproducible task, fixture, expected properties, and required evidence |
| SubjectSnapshot | Immutable description of the model, Skill, workflow, context, tools, code, and environment being evaluated |
| EvaluationRun | Links one suite/case to one or more canonical runtime runs |
| Observation | One deterministic, human, model-graded, or derived measurement with provenance |
| Scorecard | Dimension-level results, confidence, missing measurements, and hard-gate outcomes |
| ComparisonReport | Fair comparison of subjects under declared controlled variables |
| FailurePattern | Repeated failure cluster with evidence and confidence |
| ImprovementProposal | Proposed bounded change derived from observations and regression cases |
| PromotionDecision | Human/governance decision to reject, shadow, activate, roll back, or supersede a proposal |

These records should link to the canonical RunRecord, ContextPacket,
EvidenceManifest, ReviewRecord, FinalVerdict, and FailureRecord defined by the
runtime-governance plan.

### Observation Types

Every observation must state how it was produced:

| Type | Examples | Trust Boundary |
|---|---|---|
| deterministic | schema validation, tests, hashes, counts, latency | strongest when implementation is reviewed and fixtures are versioned |
| human | usefulness rating, qualitative review, ambiguity judgment | requires reviewer identity and rubric version |
| model_graded | structured critique or pairwise preference | advisory unless calibrated against humans |
| derived | aggregate score, rate, trend, cost/quality ratio | must cite source observations and formula |
| imported | Promptfoo, OpenAI Evals, benchmark, external test report | must preserve tool version and raw result reference |

No model-graded observation may create a FinalVerdict by itself.

### Scorecard Dimensions

The common scorecard should support a small stable core:

1. correctness;
2. completeness;
3. evidence credibility;
4. context sufficiency and use;
5. safety and policy compliance;
6. reproducibility;
7. user usefulness;
8. efficiency;
9. reviewer effort;
10. regression impact.
11. context-noise resistance.

Domain profiles may add dimensions. They may not remove hard safety and evidence
gates.

Each dimension must include:

```text
dimension_id
status: measured | blocked | missing | not_applicable
raw_value
normalized_value (optional)
unit (optional)
weight (optional)
confidence
observation_ids
rubric_version
limitations
```

Missing dimensions must remain visible. Aggregate scores are allowed only when
the suite declares a formula and all required dimensions are measured.

### Evaluation Status

Evaluation needs its own vocabulary:

```text
phase:
  created | prepared | collecting | scoring | review_pending | closed

result:
  comparable | partially_comparable | not_comparable |
  blocked | failed

promotion_eligibility:
  not_assessed | ineligible | candidate | shadow_ready
```

These fields do not replace runtime outcome or acceptance state.

### Fair Comparison Contract

A ComparisonReport must classify variables as:

- controlled: intentionally identical;
- treatment: intentionally different;
- observed: recorded but not controlled;
- unknown: unavailable;
- confounded: different in a way that prevents a strong conclusion.

For model comparisons, ContextPacket equivalence is a hard requirement for a
strong comparative claim. Provider-side hidden compression or undisclosed tool
differences must produce a limitation or `partially_comparable` result.

### Improvement Proposal Contract

An ImprovementProposal should include:

```text
proposal_id
target_type: skill | workflow | context_policy | rubric |
             regression_case | model_route | project_memory
target_id
baseline_fingerprint
proposed_change_ref
trigger_observations
failure_pattern_ids
expected_effect
known_risks
regression_cases
rollback_plan
owner
status: proposed
```

Agent-created proposals remain `proposed`. They do not modify active Skills,
workflows, routes, or memory.

### Context-Noise Learning

Noise-related failures should be evaluated as context failures before they are
treated as model failures.

Examples:

- stale plan treated as current authority;
- old handoff overriding an active planning record;
- disposable export cited as source of truth;
- duplicated logs crowding out the actual failing evidence;
- semantically related retrieval result distracting from the answer;
- memory cited without freshness, source scope, or authority level;
- excluded context later discovered to be required.

The learning loop may propose:

- a stronger context profile;
- a new exclusion rule;
- a reranking or freshness rule;
- a regression fixture with distractor context;
- a warning in the projection layer;
- a change to the context packet schema.

Those proposals remain candidates. They do not automatically change default
context selection until evidence, review, and promotion rules are satisfied.

### Memory-Harness Learning

Memory-related failures should be evaluated separately from model reasoning
failures.

Examples:

- project memory omitted when required;
- cross-project memory retrieved into the wrong project;
- stale memory treated as current;
- user preference overriding project policy;
- memory without source refs treated as evidence;
- contradictory memories merged without a warning;
- memory proposal promoted by the same agent that produced it.

The learning loop may propose a memory update, memory deprecation, retrieval
rule, isolation rule, regression fixture, or promotion candidate. It must not
write authoritative memory or weaken project rules without evidence, review, and
policy or adoption decision.

### Promotion Decision Contract

PromotionDecision is governance-owned and should support:

```text
rejected
needs_more_evidence
approved_for_shadow
approved_for_activation
rolled_back
superseded
```

Activation requires:

- accepted implementation evidence;
- independent evaluation;
- no open P0/P1 findings;
- declared regression coverage;
- comparison with the active baseline;
- rollback instructions;
- human or governance authorization.

## Controlled Learning Loop

```text
1. Observe accepted, blocked, and failed runs
2. Normalize measurements into observations
3. Score with a versioned rubric
4. Compare only comparable cohorts
5. Classify failures and uncertainty
6. Propose a bounded improvement
7. Add or select regression cases
8. Run baseline and candidate in shadow
9. Obtain independent review
10. Promote, reject, or request more evidence
11. Monitor the activated version
12. Roll back on regression
```

Blocked and failed runs are valuable learning inputs. They must not be deleted
from evaluation cohorts merely because they reduce a score.

## First Evaluation Profile

The first profile should be `public-test-artifact-comparison`.

This matches the repository's evidence-driven acceptance Skill and the real
four-model package-review workflow already exercised by the user.

### Inputs

- one shared task and prompt;
- two or more model delivery packages;
- screenshots or declared missing screenshots;
- shared rubric;
- ContextPacket or an explicit legacy-context limitation;
- package hashes and inventory;
- model/provider identity where available;
- execution metadata where available.

### Controlled Variables

- task wording;
- acceptance rubric;
- package-audit procedure;
- evaluator version;
- required evidence categories;
- scoring formula;
- human-review procedure.

### Treatment Variables

- model or provider;
- model-generated implementation and evidence;
- time, tokens, cost, and tool calls when available.

### Required Outputs

- EvaluationRun;
- SubjectSnapshot per model;
- package/evidence inventory;
- dimension observations;
- Scorecard per model;
- ComparisonReport;
- failure patterns;
- human-readable Chinese evaluation text;
- explicit limitations;
- no automatic routing or Skill mutation.

### Initial Dimensions

1. implementation reality;
2. test and probe credibility;
3. negative-path coverage;
4. report-to-files consistency;
5. production-path integration;
6. context adherence;
7. safety boundary compliance;
8. reviewer usability;
9. delivery efficiency;
10. overclaiming risk.

The scorecard should preserve the user's practical distinction between project
quality and screenshot presentation. Screenshot quality can affect reviewer
usability, but must not substitute for project quality.

### Fixtures

Do not put private public-test packages or local runtime outputs into the public
repository. Create small synthetic fixtures that represent:

- strong implementation and strong evidence;
- useful implementation with incomplete review evidence;
- polished report with weak implementation;
- lab-only coverage presented as production;
- missing context;
- inconsistent manifest and archive;
- duplicate evidence;
- blocked environment honestly reported;
- screenshot-rich but substance-poor delivery.

## Open-Source Reuse Position

The project should keep TestFrame as its execution and normalization substrate.
External projects are optional adapters or design references:

- [OpenAI Evals](https://github.com/openai/evals) demonstrates versioned eval
  registries, reusable templates, private task data, and custom evaluation
  logic. DevFrame should borrow the suite/case registry shape, not require an
  OpenAI API key or provider-specific runtime.
- [Promptfoo](https://github.com/promptfoo/promptfoo) provides local declarative
  model matrices, automated assertions, CI use, and side-by-side provider
  comparisons. It is a good optional adapter for prompt/model/RAG comparisons,
  but it does not replace DevFrame's artifact, evidence, reviewer, and final
  verdict governance.
- [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) supports
  treating evaluation as part of wider trustworthiness and risk management.
  DevFrame should use that principle for risk coverage, not copy the entire
  enterprise framework into a local development tool.

No new dependency should be added before a Recon Receipt compares reuse,
adapter, and native options for the exact evaluation profile.

## Phased Implementation Plan

### Phase 0: Recon And Semantic Boundaries

Goal: prevent evaluation from becoming another name for acceptance or testing.

Actions:

1. create a Recon Receipt for evaluation and learning governance;
2. inventory current TestFrame verdicts, domain quality reports, model metadata,
   Skill metadata, and memory proposal semantics;
3. document acceptance/evaluation/learning boundaries;
4. classify current score and status vocabularies;
5. identify private-data and benchmark-licensing constraints;
6. define which evaluation artifacts may enter the public repository.

Exit criteria:

- one glossary covers acceptance, observation, score, comparison, confidence,
  proposal, promotion, and rollback;
- every existing domain evaluator has a keep, adapt, supersede, or defer
  disposition;
- no implementation is authorized without the Recon Receipt.

### Phase 1: Correct The Measurement Baseline

Goal: eliminate false-positive evaluation semantics before adding abstractions.

Actions:

1. resolve the missing TestFrame schema package through a Recon-backed public
   implementation or import migration;
2. add installed-package import and report-generation smoke tests;
3. replace TestFrame's unconditional codeReview PASS with explicit review input;
4. represent missing review as not evaluated or blocked;
5. add focused verdict tests;
6. require report dimensions to declare measured/missing/not-applicable status;
7. add focused tests for the paper local quality evaluator or mark it as an
   unverified planning input;
8. prevent static model-provider labels from being surfaced as measured
   historical performance.

Required real-path regression:

- install or load TestFrame from the public package and generate a minimal
  report without missing-module errors;
- generate a TestFrame report without review evidence and prove codeReview is
  not PASS.

Exit criteria:

- missing measurements cannot improve a score;
- the installed public TestFrame package can import its orchestrator,
  normalizers, collector, and reporter;
- blocked and failed remain distinct;
- report generation and CLI output preserve limitations;
- existing TestFrame report consumers remain compatible or receive a versioned
  migration path.

Hard stop:

- do not build comparison ranking on the current unconditional verdict.

### Phase 2: Evaluation Contracts And Fingerprints

Goal: define the provider-neutral data model.

Actions:

1. add EvaluationSuite, EvaluationCase, SubjectSnapshot, EvaluationRun,
   Observation, Scorecard, ComparisonReport, ImprovementProposal, and
   PromotionDecision schemas;
2. add content fingerprints to methodology Skill snapshots;
3. define rubric versioning and aggregate-score rules;
4. extend FailureRecord linkage without breaking existing records;
5. define deterministic, human, model-graded, derived, and imported observation
   types;
6. add positive and negative fixtures.

Required negative fixtures:

- missing context presented as comparable;
- missing dimension counted as zero;
- evaluator promotes its own change;
- Skill ID present but fingerprint absent;
- aggregate score with missing required dimensions;
- model-graded result presented as final acceptance;
- candidate compared against a different task or rubric version.

Exit criteria:

- all schemas pass Draft 2020-12 validation;
- invalid self-promotion and unfair comparison fixtures fail;
- existing run, evidence, review, and final-verdict schemas remain authoritative
  for their original roles.

### Phase 3: Read-Only Evaluation Registry

Goal: build evaluation records from existing canonical runtime data without
changing execution.

Dependencies:

- canonical RunRecord and ContextPacket from the runtime-governance plan;
- explicit evidence and review references.

Actions:

1. implement a local evaluation registry outside the repository;
2. ingest canonical runs and legacy adapters through one interface;
3. create immutable SubjectSnapshots;
4. normalize TestFrame, go-run, paper quality, and human-review signals into
   Observation records;
5. preserve raw artifact references and provenance;
6. expose inspect/list commands only.

Exit criteria:

- one evaluation run can cite all source runtime runs and evidence;
- replay produces the same observations;
- unknown fields remain unknown;
- no active Skill, workflow, memory, or model route is modified.

### Phase 4: Public-Test Comparison Pilot

Goal: prove one real user-facing evaluation profile.

Actions:

1. implement `public-test-artifact-comparison` over the evidence-driven
   acceptance methodology;
2. create explicit context and rubric packets;
3. ingest multiple package inventories and screenshots;
4. generate deterministic package/evidence observations;
5. collect human qualitative observations with reviewer identity;
6. emit per-model Scorecards and one ComparisonReport;
7. generate concise Chinese feedback separately from machine records;
8. test synthetic strong, partial, polished-but-weak, and blocked cases.

Exit criteria:

- four packages for one task can be compared under one declared rubric;
- the report explains controlled, treatment, unknown, and confounded variables;
- screenshot presentation cannot override implementation evidence;
- no ranking is produced when comparison is not credible;
- human-readable feedback cites machine observations and limitations.

### Phase 5: Failure Patterns And Improvement Proposals

Goal: turn repeated evidence into bounded proposals rather than free-form
lessons.

Actions:

1. add causal categories and multi-cause attribution;
2. group repeated failures only when evidence and context are comparable;
3. produce FailurePattern records with confidence and counterexamples;
4. generate ImprovementProposal records for Skill, workflow, context, rubric,
   regression, route, or memory changes;
5. require at least one regression case and rollback plan per proposal;
6. keep all agent-created proposals in proposed state.

Exit criteria:

- proposals cite observations and failure patterns;
- speculative causes are labeled low confidence;
- a proposal cannot directly edit its target;
- duplicate proposals can be linked or superseded without deleting history.

### Phase 6: Shadow Evaluation And Promotion Gate

Goal: prove improvements before activation.

Actions:

1. run active baseline and candidate against the same suite and context policy;
2. compare correctness, safety, evidence, efficiency, and reviewer effort;
3. require independent evaluation review;
4. issue a governance-owned PromotionDecision;
5. support shadow-only activation;
6. record active version, activation time, owner, and rollback target;
7. monitor post-activation regressions.

Exit criteria:

- no candidate is promoted from a single self-evaluated run;
- all required dimensions meet profile thresholds;
- hard safety or evidence regressions block promotion regardless of aggregate
  score;
- rollback can restore the prior Skill, workflow, rubric, context policy, or
  route.

### Phase 7: Regression Bank And Continuous Evaluation

Goal: preserve lessons as executable tests.

Actions:

1. promote accepted failure examples into versioned EvaluationCases;
2. separate public synthetic fixtures from private local cases;
3. add scheduled or release-triggered evaluation for stable suites;
4. detect baseline drift and score changes;
5. preserve historical results by subject fingerprint;
6. establish retention and pruning rules for raw artifacts.

Exit criteria:

- every promoted P0/P1 fix has a real-path regression case;
- changed rubrics create a new score series rather than rewriting history;
- private evaluation data never enters the public snapshot;
- failures remain inspectable after summary pruning.

### Phase 8: Evidence-Based Model Routing

Goal: use accumulated evidence to recommend models and providers.

Actions:

1. define routing objectives by domain and risk;
2. require profile-specific minimum sample and confidence policies;
3. separate recommendation from automatic execution;
4. account for quality, safety, latency, cost, availability, and variance;
5. retain explicit user override;
6. fall back safely when the preferred provider is unavailable;
7. monitor route performance and rollback on regression.

Exit criteria:

- recommendations cite comparable evaluation cohorts;
- insufficient evidence produces no recommendation;
- risky workflows still require human confirmation;
- no provider's marketing/static registry label is treated as measured proof.

Hard stop:

- do not implement automatic routing before Phases 4-7 produce trustworthy
  historical evidence.

### Phase 9: Evaluation View And Optional Adapters

Goal: make evaluation understandable without moving authority into the UI.

Actions:

1. add evaluation-suite, comparison, failure-pattern, proposal, and promotion
   projections to the canonical read model;
2. show measured versus missing dimensions and confidence;
3. show baseline/candidate fingerprints and controlled variables;
4. expose raw evidence and reviewer links;
5. add optional Promptfoo or OpenAI Evals import adapters only after Recon;
6. keep imported results advisory until mapped to DevFrame evidence contracts.

Exit criteria:

- every displayed score can be traced to observations;
- the view cannot promote a proposal or create acceptance facts;
- optional adapters can be absent without breaking core evaluation.

## Recommended Delivery Batches

### Batch A: Measurement Integrity

Scope:

- Recon Receipt;
- terminology and evaluator inventory;
- TestFrame missing-schema resolution and packaging smoke;
- TestFrame codeReview false-PASS correction plan and tests;
- missing-measurement semantics.

Verdict target: pass only when a report without review evidence cannot show a
passing code-review result.

### Batch B: Contracts And Fingerprints

Scope:

- evaluation schemas;
- Skill and subject fingerprints;
- rubric versioning;
- negative fixtures.

Verdict target: pass only when self-promotion and unfair comparison fixtures are
rejected.

### Batch C: Read-Only Registry

Scope:

- run ingestion;
- observation normalization;
- replay and provenance;
- inspect/list commands.

Verdict target: accepted with limitation; no mutation or promotion exists.

### Batch D: Public-Test Pilot

Scope:

- four-package comparison profile;
- scorecards;
- comparison report;
- human-readable feedback;
- synthetic fixtures.

Verdict target: accepted with limitation until human calibration is completed.

### Batch E: Governed Learning

Scope:

- failure patterns;
- improvement proposals;
- shadow evaluation;
- promotion and rollback.

Verdict target: pass only after a candidate and baseline are independently
evaluated on the same suite.

## Verification Strategy

Every implementation batch must include:

1. schema-positive and schema-negative fixtures;
2. deterministic unit tests;
3. real-path report or CLI tests for P0/P1 semantics;
4. replay tests for evaluation results;
5. baseline-versus-candidate comparison tests;
6. missing, blocked, failed, and not-applicable cases;
7. evaluator independence checks;
8. exact artifact and evidence paths in the Reviewer Index;
9. public-snapshot verification;
10. explicit privacy and licensing review for evaluation data.

Critical scenarios:

| Scenario | Required Result |
|---|---|
| Installed TestFrame report import | succeeds without private or undeclared modules |
| No code-review evidence | not evaluated or blocked, never pass |
| Same Skill ID, different content | different SubjectSnapshot fingerprints |
| Same model, different context | partially comparable or confounded |
| Missing required dimension | no aggregate score |
| Model grader disagrees with deterministic test | disagreement visible; deterministic gate preserved |
| Candidate improves quality but violates safety | promotion blocked |
| Candidate reduces cost but increases failure variance | limitation or rejection |
| Executor evaluates its own change | independent review required |
| One successful run | insufficient for automatic route promotion |
| Private fixture selected for public pack | publication blocked |

## Metrics

Evaluation integrity:

- false-pass rate for missing measurements;
- percentage of scores with source observations;
- percentage of comparisons with complete SubjectSnapshots;
- context-equivalence coverage;
- evaluator disagreement rate;
- deterministic replay agreement;
- rubric-version coverage.

Learning quality:

- proposals with regression cases;
- proposals promoted, rejected, or returned for evidence;
- post-promotion regression rate;
- rollback success rate;
- repeated failure recurrence after promotion;
- low-confidence causal claims later disproven.

Operational efficiency:

- evaluation time and cost;
- human review time;
- token and tool usage per accepted result;
- duplicated evaluation work;
- time from failure observation to executable regression case;
- time from proposal to reviewed promotion decision.

Metrics must be interpreted by profile. A global leaderboard across unrelated
domains would be misleading.

## Documentation And Data Governance

- stable evaluation contracts belong under agent-runtime documentation after
  implementation;
- active design and rollout evidence stays under status documents;
- synthetic public fixtures may live in the repository;
- private prompts, papers, customer artifacts, browser state, and public-test
  packages remain outside the public repository;
- benchmark licenses and redistribution rights must be recorded;
- changing a rubric creates a new version and does not rewrite old scores;
- summaries may be pruned, but source hashes, verdicts, limitations, and
  promotion history must remain traceable.

## Explicit Non-Goals

This plan does not authorize:

- replacing TestFrame;
- importing a leaderboard as truth;
- using one aggregate score for every domain;
- allowing model graders to issue final acceptance;
- allowing agents to self-approve memory or Skill updates;
- automatic model routing before comparable evidence exists;
- publishing private evaluation inputs;
- treating tokens, file count, ZIP size, or screenshot density as quality;
- rewriting historical results after rubric or Skill changes;
- adding Promptfoo, OpenAI Evals, or another framework without a Recon Receipt.

## Open Decisions

1. Which evaluation records belong in the root agent-runtime schema family?
2. Should Skill fingerprints use file hash only or include bundled references?
3. Which dimensions are mandatory for every serious evaluation profile?
4. How should human ratings be calibrated across reviewers?
5. What minimum evidence is required before generating a comparative ranking?
6. How should repeated nondeterministic model runs be sampled and summarized?
7. Which proposal targets may support automatic rollback?
8. How should private evaluation cases be indexed without exposing their
   content?
9. Which imported evaluator versions are allowed in release gates?
10. When should evaluation history be summarized or pruned?

## Immediate Next Slice

The next implementation slice is Batch A only.

Deliverables:

1. `recon-receipt-evaluation-feedback-learning.md`;
2. evaluation terminology and current-evaluator inventory;
3. a TestFrame schema-dependency disposition and installed-package smoke test;
4. a focused TestFrame regression proving missing code-review evidence cannot
   become PASS;
5. explicit measured/missing/not-applicable dimension semantics;
6. a draft SubjectSnapshot and EvaluationRun contract outline;
7. an updated Reviewer Index with the new evidence paths.

Do not yet:

- implement scoring leaderboards;
- add external evaluation dependencies;
- modify active Skills or project memory;
- create automatic model routing;
- publish private test packages;
- build evaluation UI;
- treat planning documents as implemented runtime.

This sequence fixes the measurement instrument before using it to judge models,
Skills, workflows, or context policies. That is the smallest credible step from
evidence collection toward a system that can learn without teaching itself the
wrong lessons.
