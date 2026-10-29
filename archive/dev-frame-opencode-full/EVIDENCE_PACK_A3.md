# Evidence Pack: PAPER-CONTEXT-RETRIEVAL-MVP-A3

## Task Identity
- Task ID: PAPER-CONTEXT-RETRIEVAL-MVP-A3
- Project: dev-frame-opencode
- Date: 2026-06-11
- Predecessor: PAPER-CONTEXT-INGEST-MVP-A2 (accepted)

## A3 TaskSpec (from GPT A2 Review)

GPT recommended A3 scope:
1. metadata filter
2. keyword search
3. simple scoring
4. top-k selection
5. retrieval trace
6. retrieved_sources written into source_manifest
7. generated context pack contains only top-k, not all allowed fixtures

Goal: parsed sources -> local retrieval -> scored candidates -> selected sources -> context pack -> retrieval evidence

No vector DB, no embeddings. Metadata keyword/FTS-based retrieval only.

## Implementation Evidence

### New Module: context_layer/retrieval/

Created 5 new files under `ai-workflow-hub/src/ai_workflow_hub/context_layer/retrieval/`:

1. **__init__.py** — exports `retrieve_sources`, `RetrievalResult`

2. **metadata_filter.py** — Metadata-based relevance scoring
   - `_chapter_match()`: chapter relevance (exact=1.0, null/universal=1.0, mismatch=0.0)
   - `_tag_overlap()`: tag-keyword overlap ratio
   - `_status_score()`: active=1.0, archived=0.3, deprecated=0.0
   - `_type_bonus()`: task-type-specific note type bonuses (draft/revise/review)
   - `score_metadata()`: weighted combination → [0.0, 1.0]
   - `filter_by_metadata()`: threshold-based filtering, sorted by score

3. **keyword_scorer.py** — Keyword extraction + text matching
   - `extract_keywords()`: extracts from task_spec chapter/section/constraints/criteria
   - Chinese bigram + English word tokenization
   - Stop word filtering (Chinese + English stop word sets)
   - `score_keywords()`: keyword frequency in source body/title, capped per-keyword

4. **topk_selector.py** — Final scoring + selection + trace
   - `compute_final_score()`: weighted metadata(40%) + keyword(60%) combination
   - `select_topk()`: selects top-k sources above min_score threshold
   - `_build_retrieval_trace()`: structured audit trail with selected/rejected entries and reasons

5. **retriever.py** — Pipeline orchestrator
   - `RetrievalResult` dataclass: holds selected sources, trace, privacy result, keywords
   - `retrieve_sources()`: full pipeline: privacy → keywords → metadata → keyword score → top-k
   - `source_manifest_entries` property: includes retrieval_score and retrieval_method

### Schema Update: paper_context_pack.schema.json

Added two new optional fields:
- `source_manifest` items now accept `retrieval_score` (number) and `retrieval_method` (string)
- `retrieval_trace` (object) with: total_candidates, total_selected, total_rejected, k, selected_entries, rejected_entries, pipeline

### Builder Update: paper_context_pack_builder.py

- `build_context_pack()` now calls `retrieve_sources()` before populating pack fields
- Only SELECTED (top-k) sources enter the context pack
- `retrieval_trace` attached to pack for full auditability
- `source_manifest` now includes retrieval scores from `RetrievalResult.source_manifest_entries`
- New `top_k` parameter (default=5)

## Test Evidence

### New Test File: tests/test_retrieval_pipeline.py (39 tests)

- TestMetadataFilter: 18 tests (chapter match, tag overlap, status, type bonus, scoring, filtering)
- TestKeywordScorer: 8 tests (extraction, stop words, scoring, empty cases)
- TestTopKSelector: 6 tests (final score, selection, min score, trace structure, empty)
- TestRetriever: 7 tests (basic pipeline, privacy-first, top-k limit, trace pipeline, manifest scores, all sensitive, metadata filter)

### Updated Test File: tests/test_paper_context_pack_builder.py (+6 new tests)

- TestRetrievalIntegration: 6 tests (trace present, pipeline stages, manifest scores, top-k limits, keywords, schema validation)

### Full Regression Results

```
224 passed, 1 skipped, 0 failures
```

- A1 (schemas + fixtures): no regression
- A2 (parsers + privacy + builder): no regression
- A3 (retrieval pipeline): 45 new tests, all passing

## Validation Evidence

### A3 Validation Script: scripts/validate_paper_context_retrieval.py

10/10 checks passed:
1. Build from fixtures (with retrieval) — PASS
2. Schema validation — PASS
3. retrieval_trace present — PASS
4. Pipeline stages complete — PASS (privacy_filter, metadata_filter, keyword_scoring, topk_selection)
5. source_manifest has retrieval scores — PASS (4 entries)
6. Keywords extracted — PASS (20 keywords)
7. Privacy filter passed — PASS
8. Content fields populated — PASS (rules=1, lit=1, bad=1)
9. Generated file re-validates — PASS
10. Trace entry structure valid — PASS (selected=4, rejected=0)

### Generated Context Pack Evidence

File: `domains/paper/fixtures/generated/paper_context_pack.generated.json`

Key retrieval evidence:
- total_candidates: 4, total_selected: 4, total_rejected: 0, k: 5
- Source scores:
  - rule-001-cssci-education-style: final=0.358 (metadata=0.85, keyword=0.03)
  - zhang2024policy: final=0.238 (metadata=0.58, keyword=0.01)
  - lit-2024-zhang-policy-evaluation: final=0.212 (metadata=0.50, keyword=0.02)
  - bad-example-001-template-expression: final=0.204 (metadata=0.45, keyword=0.04)
- All sources selected (4 < k=5, no rejection with this small fixture set)
- Pipeline trace shows: 3 Obsidian + 1 Zotero input, all passed privacy, all passed metadata filter

## Boundary Compliance

- No real data accessed
- No external models called
- No vector DB or embeddings
- No real Obsidian vault or Zotero library
- All retrieval is keyword/FTS-based (metadata filter + keyword scoring + weighted scoring + top-k)
- Schema changes are backward-compatible (new fields are optional)

## A3 vs A2 Delta

| Aspect | A2 (Ingest) | A3 (Retrieval) |
|--------|-------------|-----------------|
| Source selection | All allowed fixtures | Top-k by relevance score |
| source_manifest | type + id + confidentiality | + retrieval_score + retrieval_method |
| retrieval_trace | Not present | Full pipeline audit trail |
| Builder flow | parse → privacy → classify | parse → privacy → metadata → keyword → top-k → classify |
| Scoring | None | metadata(40%) + keyword(60%) weighted |
| New modules | parsers, privacy, builder | + retrieval/ (5 files) |
| Tests | 28 new | +45 new (total 73 context layer tests) |

## Known Limitations (A4/A5 scope)

1. Keyword extraction uses CJK bigrams — limited compared to proper NLP tokenization
2. No vector DB or semantic similarity — pure keyword/metadata matching
3. Scoring weights are hardcoded — no learning or user feedback
4. Only 4 fixtures in test set — top-k rejection not exercised with default fixtures
5. No Better BibTeX or real Zotero library support (A4)
6. No WriteLab adapter (A5)
