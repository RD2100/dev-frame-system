# Agent Note: Memory notes anchor to entities through host-canonicalized tags

Status: implemented

English | [中文](2026-09-14-memory-entity-anchoring.zh.md)

## Problem

The vault's recall was pure body-substring matching, so the queries that matter most for an agent's memory — "everything about this project", "what do I know about this subject" — had no good answer: notes referring to one subject by different names (a path, a short name, a Chinese description) never matched, and bilingual corpora split further. The full cure observed in the field (mem0's graph-era designs, Zep/Graphiti) is a knowledge graph, but its costs — an extraction LLM call per note, a graph database, relation edges between entities — are exactly what the bounded-memory design refuses to pay before a measured need.

## Decision

Entity anchoring without graph infrastructure. `memory_append` accepts optional model-proposed `entities` tags; the host canonicalizes them (trim, whitespace-collapse, lowercase, single-subject shape of at most 64 characters, at most 8 per note, secret-screened like bodies) and stores them as one front-matter line. A project-scope note always carries its workspace tag — the one deterministic entity the host already knows. `memory_search` gains an optional `entity` filter, canonicalized the same way, so "everything about X" is one deterministic lookup over the existing bounded candidate walk; hits carry the note's tags so the model can pivot. The supersession chain remains the validity window, and the usage-policy and Shadow sections teach the reuse-a-tag-per-subject discipline.

The flat corpus stays the source of truth: no separate index file exists, the candidate walk is the index, and the tags graduate to real entity nodes (summaries, aliases, relation edges) only when the corpus grows enough to measure the need.

## Alternatives considered

**BM25 keyword scoring first.** Deferred: it needs Chinese segmentation or bigram indexing to work at all in this deployment's bilingual corpora, and it answers relevance, not scope — the "everything about X" question stays unanswered. Text relevance re-enters later, on the already-narrowed entity-filtered result set, if note counts per entity grow.

**A real entity graph (Graphiti-style extraction, entity nodes with evolving summaries, relation edges).** Deferred, not rejected: each piece is a scale-driven upgrade of this same schema — tags become node ids, aliases join a registry, edges appear when relation queries are actually asked. Nothing here forecloses it.

**LLM extraction of tags at recall time.** Rejected: it puts an LLM call on the write path for structure the writing model already knows, and the design's notary model wants the model proposing candidates while the host derives authoritative metadata — exactly what canonicalization does.

## Consequences

Bought: "everything about X" is a deterministic bounded lookup across bilingual notes; project notes are auto-anchored to their workspace with zero model effort; tags ride the existing screening, so a tag cannot smuggle what a body cannot. Costs: the append tool schema grows one optional parameter, hits grow one optional field, and tag discipline (reuse the same tag per subject) is steering, not enforcement — the alias problem is solved only as far as the writing model stays consistent, since no alias-merging registry exists in this version.

## Testing

`append.spec.ts` pins the canonicalization round trip (trim/lowercase/dedupe plus the automatic workspace tag), the entity-filtered search with tags on hits, and the loud rejections for secret-bearing, malformed, and over-cap tags. The plugin and shadow prompt texts teach the tagging discipline.

## Related

[The memory usage policy is a global conditional section](2026-09-14-project-memory-usage-policy.md) owns the guidance this extends; the entity anchoring realizes the retrieval shape of [the bounded memory design](../../../../docs/detailDesign-part3.md).
