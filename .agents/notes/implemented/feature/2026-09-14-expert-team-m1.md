# Agent Note: Expert teams run persona packs through gated phase subagents

Status: implemented

English | [中文](2026-09-14-expert-team-m1.zh.md)

## Problem

The harness had no way to run a multi-expert pipeline: a research task needs several distinct personas (perspective discovery, literature review, question selection, method design) executed in dependency order, with artifacts passing between phases and a human approving quality at the points that matter. The natural seam — the agent loop — is exactly where new behavior must not go, and the existing subagent machinery (agent-hierarchy dispatch) solves a different problem: role-bound workers on worktrees, not persona-scoped craft sessions with human gates. Without a home for this, each deployment would improvise prompts, artifact handoffs, and review discipline per task.

## Decision

The expert-team plugin mounts persona packs as data and orchestrates pipeline phases over existing agent machinery, no loop change. A pack (`team.yml` plus `experts/<id>.md` plus skills plus result schemas) is validated fail-loud at load — unique phase ids, backward-only `depends_on`, existing expert, schema, and skill files — and every violation carries a stable `EXPERT_TEAM_*` code. Each phase derives a subagent through the agent registry's scoped-create face (`ctx.agents.create` with a `setup` that composes the persona, pack skills, and the expert's tool allowlist as both visibility restriction and executor guard), then drives one turn with `followup()` plus `whenIdle()`.

The phase expert has no write tool. It answers with the artifact as its reply body and a fenced-JSON result object as the last block; the runtime is the single writer — it validates the result against the declared artifact name and the pack's JSON Schema, writes the body atomically only after the contract passes, and re-drives the same session at most twice on a failure so revisions stay in context. A gated phase parks the run (`waiting-approval`); an approval resumes the pipeline, a rejection returns the artifact to the same phase session with the reviewer's comment as revision guidance, and a phase that exhausted its retries parks failed at its gate where approval is refused (nothing accepted exists to pass downstream). An `approved` decision additionally delivers a best-effort post-approval followup to the gated phase's session so the persona's post-acceptance memory note can fire in a real turn; the followup is fire-and-forget, failures are logged by name, and advancing does not block on it. Run state is authoritative in memory and mirrored to `<artifactsDir>/<runId>/run-state.json` at every commit point; runs do not resume in a new process. Recording artifacts into project-memory is delegated to the packs' tool allowlists — an expert declaring `memory_append` may tag its note with the research topic per [the entity-anchoring design](2026-09-14-memory-entity-anchoring.md) — while the orchestrator itself never calls memory.

## Alternatives considered

**Map phases onto agent-hierarchy dispatch.** Deferred, not rejected: dispatch binds roles, worktrees, and a dispatch engine built for delegated task execution, none of which a persona phase needs; a phase session must be a bounded persona, not a role-bound worker. The hierarchical team mode (`mode: hierarchical`) is the seam that would map gates onto dispatch when a real hierarchical pack needs it — the mount refuses to run such teams today rather than improvise semantics.

**Give phase experts write tools and let them persist artifacts.** Rejected: the artifact boundary would depend on every pack author's tool discipline, a half-written file could pass downstream, and schema validation would arrive after persistence instead of before. The reply-body protocol keeps the runtime as the single writer and makes the schema gate part of acceptance.

**Durable run records in a database for cross-process resume.** Deferred: M1's consumers read the mirrored `run-state.json` and no deployment runs teams across restarts yet; a store seam can be added when resume is real. The in-memory record plus file mirror keeps one lifecycle owner per run.

**Core-owned memory writes per artifact.** Deferred: the core would need its own project-memory dependency and an entity-tag source it does not have; the pack allowlist mechanism already gives experts honest, screened memory access, and an unconfigured memory degrades to a reported `MEMORY_UNAVAILABLE` without failing the phase.

## Consequences

Bought: a deployment mounts expert teams as a config row and a data directory; personas, handoff checks, and machine-checkable result contracts live in versioned pack files; the executor enforces gate blocking and approval recording (a gated phase parks, `expert_team_approve` records the decision) while decision provenance — that a human actually spoke — is prompt-pinned by the usage section, with a capability-level approval seam documented as the M2 hardening path; artifacts are files under `<artifactsDir>/<runId>/` that never re-enter the prompt as content. Costs: runs are serial and die with the process (no resume), the hierarchical mode mounts but does not run, the fenced-JSON result protocol asks models to hold a strict reply shape (bounded retries absorb the misses), and expert quality is steering — the gates check the declared contract, not the craft.

## Testing

Catalog unit specs pin mounting, every fail-loud mount failure, and lookups; parser specs pin the expert-md and team.yml contracts; result-protocol specs pin the reply split, contract checks, schema enumeration, and briefing composition. The orchestration spec drives the real plugin mount over a scripted mock adapter: phases in order, contract retry, gate park, in-context revision on rejection, approval resume, consult isolation, and every stable failure code through the tool face. The REAL-composition spec boots a cordis.yml through the actual Loader with the fixture pack and the shipped paper pack mounted, proving the pack format through the product face; the same mount validates the shipped pack's four-phase chain (two human gates) exactly as the design pins it. The recorded-session snapshot tier is deferred: recording a scenario requires a provider key, and none is recorded; the REAL-composition spec carries interim model-visible coverage by driving the same five tools through a mock model adapter.

## Related

[The memory usage policy is a global conditional section](2026-09-14-project-memory-usage-policy.md) and [memory notes anchor to entities through host-canonicalized tags](2026-09-14-memory-entity-anchoring.md) own the memory side this plugin delegates to; the pack format and M1 pipeline scope follow [the expert-team design bluebook](../../../../docs/detailDesign-expert-team.md).
