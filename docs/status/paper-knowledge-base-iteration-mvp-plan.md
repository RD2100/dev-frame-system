# Paper Knowledge Base Iteration MVP Plan

Lifecycle state: External-brain reviewed deferred module plan after v3 PASS

Plan status: Proposed deferred product module. This is not an implementation
claim and must not displace the current review-first governance kernel.

Reader: DevFrame maintainers and coding agents who need to turn the current
paper, Obsidian, local RAG, skill, and external-brain substrate into a practical
paper knowledge-base iteration loop.

Post-read action: preserve this as a paper-domain module behind the
review-first governance kernel. Do not implement Paper KB code until the
review-governance kernel Phase 1A has passed and this plan has been expressed
as domain fixtures under that kernel.

Related docs: [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md), [Paper Claim Integrity Gate To Cluster Plan](paper-claim-integrity-gate-to-cluster-plan.md), [Project And Cross-Project Memory Harness Governance Plan](project-and-cross-project-memory-harness-governance-plan.md), [rdpaper Workflow](../agent-runtime/rdpaper-workflow.md), [Web AI Adapter Contract](../agent-runtime/web-ai-adapter-contract.md), [Browser Automation Transport Roadmap](browser-automation-transport-roadmap.md)

## Goal

Build a small, governed paper knowledge-base iteration loop inspired by the
Codex plus Obsidian workflow:

```text
authorized source material
  -> managed Obsidian notes
  -> local retrieval and review packet
  -> paper insight / issue / skill candidate
  -> evidence-backed writeback
  -> repeated iteration
```

The MVP is not a general personal knowledge-management platform. It is a
paper-focused loop that proves DevFrame can repeatedly turn authorized research
material into reusable, reviewed, and traceable knowledge artifacts.

## Current Reality

The project already has useful substrate:

- `rdpaper` defines a paper-focused external-brain workflow where a web AI
  reviews and coordinates while the local agent prepares privacy-safe packets.
- Paper iteration templates exist for profile, safety, review spec, ledger,
  next task, and web AI adapter state.
- Obsidian REST probe and sync logic exists, including token-not-persisted
  behavior and managed-block preservation.
- Local paper RAG pilots exist for PDF-to-Markdown conversion, scoped Obsidian
  note generation, FAISS/local retrieval smoke, answer preview, and minimized
  evidence reports.
- Paper gates exist for privacy, acceptance, issue ledger, and human decision
  audit patterns.
- External review bundles now provide manifest, context ledger, redaction
  report, review prompt, and validation before web AI review.
- The browser path is converging on CDP-family evidence with a dedicated
  persistent profile launcher for login reuse.

The project does not yet prove:

- a user-facing one-command paper knowledge-base iteration run;
- stable vault layout and managed-note conventions for daily use;
- multi-source intake beyond scoped PDFs and local notes;
- scheduled or repeatable iteration;
- skill-candidate extraction from repeated paper work;
- governed promotion from skill candidate to methodology skill;
- final paper quality acceptance from the knowledge-base loop.

## Product Boundary

The MVP serves one user with one authorized paper knowledge-base workspace.

In scope:

- local authorized PDF or Markdown folders;
- Obsidian vault or vault-like Markdown folder;
- managed note generation and safe sync;
- local retrieval smoke and minimized evidence;
- external-brain review through validated bundles;
- paper insight, issue, and skill-candidate artifacts;
- writeback into managed Obsidian blocks.

Out of scope:

- reading an entire private vault by default;
- automatic web scraping, Twitter, GitHub, Reddit, or video ingestion;
- automatic citation insertion into manuscripts;
- autonomous paper writing or submission;
- multi-agent paper R&D cluster runtime;
- hidden memory promotion;
- storing raw private paper text, browser transcripts, cookies, browser
  profiles, vectors, or unredacted chunks in evidence.

## External-Brain Review Result

External-brain review verdict: conditional pass for direction, no-go for the
original implementation order.

Accepted review findings:

- Paper KB must not become the next coding slice or a parallel governance
  entrypoint.
- The first repository implementation target remains the review-governance
  kernel schema, fixtures, and negative tests.
- Paper KB workspace contracts should later appear as paper-domain fixtures
  under the review-governance kernel, not as a competing schema family.
- External web-AI feedback is evidence or artifact material only. It is never a
  final `Decision`, never an Obsidian write authority, and never a memory or
  skill-promotion authority.
- Skill-candidate extraction must stay deferred until repeated paper iterations
  exist and a separate adoption decision can govern promotion.

## Object Mapping

Do not add a new top-level object family for the MVP.

Use the existing governance spine:

| Concept | DevFrame shape |
|---|---|
| Paper knowledge-base workspace | `Project(type=paper)` plus workspace profile artifact |
| Workspace contract request | `WorkItem(kind=paper_kb_workspace_contract)` |
| Iteration request | `WorkItem(kind=paper_kb_iteration)` |
| Source import, RAG run, review run | `Run` |
| Workspace profile, source manifest, note batch, retrieval report, review bundle | `Artifact` |
| Hashes, redaction report, retrieval smoke, review feedback | `Evidence` |
| Writeback approval, skill promotion, gate result | `Decision` created by DevFrame or a human gate |
| Obsidian/RDCode/dashboard view | `Projection` |

This keeps the paper knowledge-base loop compatible with the master plan rather
than creating a parallel product authority model.

## Phase Plan

### Phase 0: Preserve Current Paper Substrate

Status: current baseline.

Goal: keep existing paper, Obsidian, local RAG, external-brain, and browser
launcher capabilities from regressing while the MVP plan is reviewed.

Acceptance evidence:

- existing paper and Obsidian tests pass;
- external review bundle validation still passes;
- CDP browser launcher can start or reuse the dedicated profile;
- public snapshot verification passes.

Stop line: do not claim a paper knowledge-base product exists merely because
the substrate exists.

### Phase 1A: Paper KB Workspace Contract Fixture

Status: deferred until review-governance kernel Phase 1A passes.

Goal: define the smallest paper-domain fixture that proves one local paper
knowledge-base workspace can be represented inside the review-governance
kernel without weakening evidence, privacy, or decision boundaries.

Precondition:

- `schemas/review_governance_kernel.schema.json` exists and its Phase 1A
  fixtures and negative tests pass.
- Paper KB examples are added under the review-governance example family or a
  direct successor accepted by that kernel.
- The slice does not add runtime commands, browser submission, Obsidian writes,
  PDF conversion, scheduler behavior, or skill promotion.

Expected outputs:

- workspace profile fixture;
- vault layout fixture;
- source manifest fixture;
- managed note policy fixture;
- negative tests for unsafe vault roots, raw private text in evidence, and
  unmanaged writeback.

Minimum contract fields or payload members:

```text
workspace_id
project_id
vault_root_policy
managed_notes_folder
source_roots
allowed_source_kinds
redaction_policy
writeback_policy
external_review_policy
```

Required policy values and failure reasons:

```text
whole_vault_scan = false
source_roots_must_not_equal_vault_root = true
managed_notes_folder_must_be_inside_vault = true
unmanaged_writeback_policy = manual_review_required
external_review_output_authority = artifact_or_evidence_only
forbidden_evidence_fields = [
  raw_text,
  raw_chunks,
  vector_bytes,
  browser_profile_path,
  cookies,
  raw_transcript,
  absolute_private_path
]
```

Acceptance evidence:

- a valid fixture defines one managed notes folder and one authorized source
  root;
- unsafe relative paths are rejected;
- whole-vault scan is rejected by default;
- raw paper text, raw chunks, vectors, browser profiles, and cookies are
  forbidden in evidence;
- empty paths, path traversal, normalized traversal, symlink escape, source
  root equal to vault root, and managed folder outside vault are rejected;
- unmanaged Obsidian notes require manual review before overwrite.
- external review feedback cannot be encoded as a final decision.

Explicitly deferred:

- actual PDF conversion command;
- scheduler;
- external web ingestion;
- browser submission;
- skill promotion;
- UI work.

### Phase 1B: Prepare-Local-Iteration Smoke

Status: deferred until Phase 1A passes.

Goal: prove a no-cloud smoke run from authorized source folder to managed notes
and minimized evidence. This is a pass or blocked report, not a final product
decision.

Minimum input:

```text
paper_kb_workspace.json
authorized PDF or Markdown folder
Obsidian vault root
managed notes folder
```

Minimum output:

```text
source_manifest.json
managed_note_batch_report.json
local_retrieval_smoke_report.json
paper_kb_iteration_evidence.json
```

Required behavior:

- enumerate only authorized source roots;
- generate or update managed notes only under the managed folder;
- default to a synthetic fixture or temporary vault-like Markdown folder;
- preserve user-authored note content outside managed blocks;
- run local retrieval smoke over the generated/allowlisted notes;
- persist only counts, fingerprints, status, and minimized summaries.
- require an explicit human decision before writing to a real Obsidian vault.

Acceptance evidence:

- one command can run on a synthetic fixture;
- generated notes have frontmatter and managed block markers;
- evidence omits raw PDF text, raw note body, raw chunks, vectors, and local
  private paths;
- a blocked report is produced when the vault or source scope is invalid.

### Phase 1C: External-Brain Review Packet Preparation

Status: deferred until Phase 1B passes.

Goal: prepare and validate an external-brain review bundle for the iteration
result without handing it raw private material. Browser submission remains a
separate explicit action.

Expected outputs:

- ready-for-review external bundle containing the workspace contract, source
  manifest, iteration evidence, redaction report, known gaps, and review
  question;
- validation evidence proving the bundle is ready for review.

### Phase 1D: External-Brain Submission And Feedback Ingestion

Status: deferred until Phase 1C passes and the user explicitly authorizes
submission.

Goal: submit the prepared bundle through the CDP-controlled browser path and
ingest the resulting feedback conservatively.

The web AI may produce:

- missing-context critique;
- issue candidates;
- organization suggestions;
- skill-candidate suggestions;
- next-iteration recommendations.

The web AI must not produce:

- final paper acceptance;
- automatic manuscript edits;
- authority-bearing decisions;
- direct memory promotion.

Acceptance evidence:

- `ready_for_review` bundle validation passes;
- CDP-controlled browser submission and response extraction are recorded;
- skipped context and missing context are visible in the context ledger;
- feedback is stored as artifact/evidence, not as a decision.

### Phase 2: Skill Candidate Extraction

Status: deferred until multiple manually reviewed Paper KB iterations exist,
with evidence that repeated patterns are not private-content leakage and
promotion remains decision-gated.

Goal: turn repeated paper work patterns into skill candidates without
auto-enabling them.

Skill candidate examples:

- literature-value judgment checklist;
- citation-risk review checklist;
- writing-style normalization checklist;
- reviewer-response triage workflow;
- domain-specific reading template.

Expected outputs:

- `skill_candidate_record` fixture;
- candidate source refs and evidence refs;
- risk classification;
- dry-run prompt or checklist;
- adoption recommendation.

Acceptance evidence:

- repeated patterns can be proposed as candidates;
- candidates remain disabled by default;
- promotion requires validation, dry-run evidence, and a decision;
- user-authored notes and private paper text are not embedded into skills.

### Phase 3: Iteration Ledger And Daily Review

Status: deferred until Phase 2 has fixtures.

Goal: make the loop useful for repeated use without adding broad automation.

Expected outputs:

- paper KB iteration ledger;
- daily or per-run summary note;
- unresolved issue list;
- next source candidates;
- skill candidate queue.

Acceptance evidence:

- every iteration links to source manifest, retrieval evidence, external review
  evidence if used, and writeback decision;
- stale or superseded findings are visible;
- repeated unresolved issues can become work items;
- no hidden memory write occurs as a side effect of a successful run.

### Phase 4: Optional Scheduler

Status: deferred until manual iteration is useful.

Goal: allow low-risk scheduled runs only after the manual loop is stable.

Allowed scheduled work:

- refresh source manifest;
- regenerate managed summaries for changed authorized files;
- run local retrieval smoke;
- prepare review bundle without submitting it.

Not allowed without explicit human approval:

- upload to web AI;
- read new private folders;
- overwrite unmanaged notes;
- promote skills;
- modify manuscripts.

Acceptance evidence:

- scheduler actions are policy-bounded;
- every scheduled run produces evidence;
- failures are visible and do not silently retry into broader scope.

### Phase 5: Broader Intake And Output Modes

Status: deferred until the core loop is proven.

Goal: add more inputs and outputs after the governed core works.

Candidate inputs:

- curated web pages;
- Zotero exports;
- BibTeX;
- user-selected GitHub issues or docs;
- transcript files explicitly provided by the user.

Candidate outputs:

- structured Obsidian dashboards;
- paper issue reports;
- PPT outline packets;
- visual summary packets;
- reviewer-response plans.

Stop line: do not add these because the reference image includes them. Add them
only after the core loop proves repeated value.

## Deferred Coding Slice

The first coding slice for the repository is not in this document. The next
repository slice remains the review-governance kernel named by the master plan.

After that kernel passes, the smallest acceptable Paper KB slice is:

```text
paper-kb-workspace-contract-v0-under-review-kernel

Add paper-domain workspace fixtures and negative tests under the
review-governance kernel.
No scheduler.
No browser submission.
No PDF conversion.
No skill promotion.
No UI.
```

Suggested files:

```text
schemas/examples/review-governance/paper-kb-workspace-valid.json
schemas/examples/review-governance/paper-kb-workspace-invalid-whole-vault.json
schemas/examples/review-governance/paper-kb-workspace-invalid-source-root-equals-vault-root.json
schemas/examples/review-governance/paper-kb-workspace-invalid-managed-folder-outside-vault.json
schemas/examples/review-governance/paper-kb-workspace-invalid-path-traversal.json
schemas/examples/review-governance/paper-kb-evidence-invalid-raw-private-text.json
schemas/examples/review-governance/paper-kb-external-review-invalid-decision.json
packages/control-plane/tests/test_paper_kb_workspace_contract.py
```

Acceptance:

- schema validates the valid workspace;
- invalid whole-vault scan fails;
- invalid source-root-equals-vault-root and path traversal fail;
- invalid raw text evidence policy fails;
- unmanaged writeback policy requires manual review;
- external review output treated as a decision fails;
- adopted, enabled, or default skill candidates fail in this slice;
- public snapshot verification passes.

## External Review Questions

Ask the external brain:

1. Is this plan correctly scoped as a paper knowledge-base iteration MVP rather
   than a general PKM platform?
2. Does the revised plan clearly prevent Paper KB from bypassing the
   review-first governance kernel?
3. Does the plan reuse existing paper, Obsidian, RAG, skill, and external-brain
   substrate correctly?
4. Does the plan preserve privacy and evidence boundaries?
5. Is skill-candidate extraction placed late enough?
6. Is the deferred Paper KB fixture slice small enough for after the
   review-governance kernel Phase 1A passes?
7. What P0 issues remain before this plan is referenced from the master plan as
   a deferred module?

Expected verdict:

```text
A. Overall verdict: PASS / CONDITIONAL PASS / BLOCKED
B. GO / NO-GO for referencing this plan from the master plan as a deferred module
C. GO / NO-GO for the deferred Paper KB fixture slice after the review kernel passes
D. P0 issues
E. P1 issues
F. Smallest acceptable deferred Paper KB slice
```
