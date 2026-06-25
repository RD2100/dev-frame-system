# Recon Receipt: Paper PDF Full-Text Segmentation

## Target

- user_goal: Build the real PDF full-text segmentation foundation for the paper module, prioritizing open-source reuse.
- target_repo_or_kb: repo root
- current_slice_goal: Add a local adapter that can turn an authorized PDF into page/section/chunk segment records and a minimized report.
- requested_outcome: Reusable backend boundary, deterministic segmentation report, tests, and @go evidence.
- date: 2026-06-25
- planner_agent_id: codex-controller

## Resource Map

- repository_roots: repo root
- important_dirs: `packages/ai-workflow-hub/src/ai_workflow_hub/context_layer/adapters`, `packages/ai-workflow-hub/tests`, `schemas`, `.devframe-runtime/atgo-runs`
- docs_read: `AGENTS.md`, `rules/recon.md`, `rules/open-source-reuse.md`
- packages_apps_modules: `local_paper_rag_pipeline.py`, `public_research_kb_pilot.py`, `paper_pdf_redacted_excerpt_pilot.py`, `cli.py`
- runtime_entrypoints: `aihub paper ...` commands in `packages/ai-workflow-hub/src/ai_workflow_hub/cli.py`
- state_storage_locations: caller-provided runtime directories and ignored `.devframe-runtime/atgo-runs`
- external_integrations: public arXiv/OpenAlex metadata, Obsidian Local REST API, optional local PDF parser backends
- notable_generated_or_vendor_paths: no vendored external code; evidence stays under `.devframe-runtime/atgo-runs`
- license_files_found: repo package declares MIT; external parser libraries must remain adapter dependencies or optional backends, not copied source.

## Core Concepts

- concepts: authorized local PDF, PDF backend, extracted page text, section segmentation, chunk segmentation, minimized evidence report
- domain_terms: page, section, chunk, heading, section_kind, fingerprint, raw text store
- architecture_style: thin adapter around reusable parser backends; DevFrame owns privacy/report/schema, not PDF parsing internals
- execution_model: local deterministic command or library call; no cloud calls
- review_model: @go executor/reviewer/finalizer plus external Web GPT check when packaged
- evidence_model: report contains fingerprints and counts; raw text is excluded from reports and evidence packs

## Capability Matrix

- PDF extraction:
  - location: new adapter boundary
  - maturity: mature open-source libraries exist
  - reusable_as_is: `pypdf` for text PDFs; GROBID/Docling for richer later backends
  - reusable_with_adapter: yes
  - not_reusable: hand-written PDF parsing
  - notes: `pypdf` is permissive and lightweight but not OCR; GROBID is best for scholarly TEI but requires service runtime.
- Section/chunk segmentation:
  - location: DevFrame adapter
  - maturity: product-specific privacy/evidence shape
  - reusable_as_is: no direct local module yet
  - reusable_with_adapter: future GROBID TEI headings can feed the same segment schema
  - not_reusable: whole-text reports that leak private paper content
  - notes: heuristic sectioning is acceptable for the foundation; team-agent analysis can improve later.

## Reuse Candidate List

- candidate: GROBID
  - source: https://github.com/grobidOrg/grobid
  - exact_scope_to_reuse: scholarly PDF to structured TEI, references, header, and full-text sections
  - expected_adapter_work: run service locally, call REST `processFulltextDocument`, map TEI to segment schema
  - blocking_constraints: Java/service runtime and heavier setup
  - decision: defer as P1 backend after local segment schema stabilizes
- candidate: pypdf
  - source: https://pypdf.readthedocs.io/
  - exact_scope_to_reuse: pure-Python text extraction from digital PDFs
  - expected_adapter_work: optional dependency/import, page text extraction, no OCR claims
  - blocking_constraints: not OCR and weak layout semantics
  - decision: preferred first lightweight backend
- candidate: Docling
  - source: https://github.com/docling-project/docling
  - exact_scope_to_reuse: advanced PDF/document conversion and structured output
  - expected_adapter_work: optional backend mapping Docling output to DevFrame segments
  - blocking_constraints: heavier model/runtime dependencies
  - decision: defer as P1/P2 advanced backend
- candidate: Unstructured
  - source: https://github.com/Unstructured-IO/unstructured
  - exact_scope_to_reuse: partition PDF into document elements
  - expected_adapter_work: optional backend mapping elements to segment schema
  - blocking_constraints: heavier optional dependencies and OCR/layout setup
  - decision: defer
- candidate: PyMuPDF
  - source: https://pymupdf.readthedocs.io/
  - exact_scope_to_reuse: fast local text extraction when installed
  - expected_adapter_work: optional manual backend
  - blocking_constraints: AGPL/commercial license boundary; do not add as dependency
  - decision: optional local-only backend, not default and not vendored

## Integration Risk Table

- risk: raw PDF full text leaks into report/evidence
  - type: privacy
  - severity: P0
  - mitigation: report only hashes/counts; raw text store must be explicit and kept out of evidence ZIPs
  - owner: DevFrame adapter
- risk: parser dependency license mismatch
  - type: license
  - severity: P1
  - mitigation: prefer `pypdf` first; keep PyMuPDF optional/manual; do not vendor
  - owner: planner/reviewer
- risk: heuristic sectioning mislabels scholarly sections
  - type: quality
  - severity: P2
  - mitigation: expose backend and confidence fields; later GROBID TEI backend
  - owner: paper module

## Build-vs-Buy Decision

- must_reuse: PDF text extraction backend
- should_adapt: `pypdf` first, GROBID/Docling later
- can_spike: optional PyMuPDF local smoke only
- must_build_new: DevFrame segment schema, minimized report, privacy boundary, CLI wiring
- rationale: Parsing PDFs from scratch is not worthwhile; evidence and privacy boundaries are product-specific.

## Unknowns / Questions

- unanswered_items: exact production parser choice for scanned/OCR PDFs
- required_verification: synthetic digital PDF tests, injected extractor tests, report leak scan
- experiments_needed: later real public arXiv PDF smoke with `pypdf` or GROBID backend

## Recommended Next Slice

- smallest_safe_increment: adapter with injected extractor tests plus optional `pypdf` default backend and CLI command
- worker_type_needed: coding worker plus independent reviewer
- files_or_modules_in_scope: `paper_pdf_fulltext_segments.py`, focused tests, schema, CLI command, optional dependency metadata
- files_or_modules_out_of_scope: GROBID service client, Docling backend, OCR, multi-agent analysis team
- evidence_required_for_completion: diff, tests, safety report, independent review, finalizer
- review_gate_definition: block on raw text in report, fake-green extraction, missing schema tests, or hard dependency on AGPL backend
