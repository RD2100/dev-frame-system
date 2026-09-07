# Agent Note: Bound automatic summary truncation failures

Status: implemented

English | [中文](2026-09-07-compaction-truncation-budget.zh.md)

## Problem

A token-capped summary leaves conversation pressure unchanged. Retrying it before every model step repeatedly consumes generation time without committing a checkpoint; ordinary conversation progress does not repair the summary output cap.

## Decision

`compaction-basic` limits consecutive automatic `MAX_TOKENS` failures per live Session and effective summary strategy with `maxAutomaticSummaryFailures`, defaulting to one. Exhaustion pauses automatic summaries across steps and turns while preserving model-free pruning. A committed summary or a changed summary provider, model, output cap, or failure budget restores admission. Manual attempts remain available; failed or empty attempts do not restore admission. Cancellation does not consume this budget, and overflow recovery still requires durable surface progress before retrying the original request.

## Alternatives considered

**Reduce `compactionRetries`.** That field bounds successful reductions which remain above threshold; it does not bound failed summaries across steps.

**Reset after a normal response or each turn.** Neither establishes that the summarizer can finish, so both recreate the repeated cost. A time-based cooldown also retries an unchanged failing strategy without recovery evidence.

**Accept a truncated checkpoint.** A partial checkpoint can omit pending work and constraints. The existing fail-closed summary transaction remains authoritative.

## Consequences

The budget is process-local, so backend reconstruction grants a fresh budget. Exhaustion produces one warning with the route and recovery instructions; it adds no model input or session event type. Real-loop tests cover truncation limits, cross-turn retention, independent sessions, effective-route recovery, manual success, cancellation, and preservation of overflow errors. The authored `compaction-truncation-budget` keyless scenario supplies an explicit replay override for the failed auxiliary stream, then compares the real headless profile's persisted log: one failed compaction bracket, two tool results, three completed model steps, no summary checkpoint, and a completed turn. Cross-turn retention is covered by the real-loop test. Prefix-cache reuse and checkpoint language remain owned by their existing notes.
