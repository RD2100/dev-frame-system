# Agent Note: M4 hardening and release readiness for the expert-team plugin

Status: implemented

English | [中文](2026-09-15-expert-team-m4.zh.md)

## Problem

M1 shipped the core plugin with pipeline orchestration, M2 added phases 5-8 and project-memory recording, and M3 added hierarchical mode with hierarchy bindings. M4's scope is hardening and release readiness: multi-pack composition evidence, measured token/KV effects, the cross-process resume decision, run-history observability, and projection of the user-facing guide.

## Decision

**Multi-pack composition** is proven by two new loader-composition tests: one mounts both the shipped paper pack and the shipped dev pack together and asserts both teams list correctly with their full phase chains, hierarchy roles, and gate declarations; the other executes a hierarchical dev-team run (controller → worker) alongside the mounted paper pack, proving the two packs coexist without interaction. The fixture hierarchical pack is also mounted alongside the pipeline fixture pack in the same composition.

**Cross-process resume** is explicitly rejected. Run state is authoritative in memory; `run-state.json` is a mirror, not a recovery point. The decision is recorded in a dedicated Agent Note ([expert-team-no-cross-process-resume](../feature/2026-09-15-expert-team-no-cross-process-resume.md)) with rationale: no current consumer needs it, memory + file mirror + project-memory persistence is sufficient, and resume semantics would require a new storage seam with significant complexity.

**Run-history observability** is implemented as an in-memory run index mirrored to `<artifactsDir>/run-index.json` at each persist point. The index carries lightweight metadata per run (runId, teamId, mode, status, createdAt, completedAt) and is exposed through `TeamOrchestrator.listRuns()`. This gives deployments a programmatic view of run history without requiring a database or external store. The index is not loaded on startup (runs do not resume); it accumulates for the lifetime of the process and is overwritten at each update.

**Measured token/KV effects** are deferred. Measuring requires a real model backend with token counting; the existing mock-adapter test infrastructure cannot produce meaningful measurements. This is deferred until a recording scenario is available (snapshot tier).

**User-facing guide projection** is deferred. The website projection follows the repo's existing VitePress pipeline; expert-team content belongs in the website's content tree and is not part of the package's release readiness.

## Alternatives considered

**Implement cross-process resume.** Rejected: no deployment has requested it; the complexity (storage seam, session recovery, gate replay, consistency verification) does not match current demand.

**Use run-state.json as a recovery point.** Rejected: it is a mirror, not a checkpoint; upgrading it to a recovery point would require recording additional runtime state, contradicting the "memory is authoritative" design.

**Measure token/KV effects with synthetic benchmarks.** Rejected: synthetic benchmarks do not reflect real model behavior; measurements require a recording scenario with a real provider key.

## Consequences

Gained: multi-pack composition is proven through a real Loader — paper and dev packs mount together and execute independently; run history is programmatically queryable via `listRuns()` with the index file persisted at the artifacts root; the cross-process resume decision is recorded and documented. Cost: token/KV measurement and user-facing guide projection are deferred until a recording scenario is available; process restart loses in-progress runs (recorded as README known limitation).

## Testing

- Multi-pack composition: two new loader-composition tests prove paper + dev packs mount together and a hierarchical dev-team run executes alongside the paper pack.
- Run index: existing orchestrate tests implicitly verify the index is written (artifactsDir now contains `run-index.json` alongside run directories).
- Cross-process resume: decision recorded in Agent Note, no runtime support implemented.
