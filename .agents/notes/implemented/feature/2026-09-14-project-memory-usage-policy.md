# Agent Note: The memory usage policy is a global conditional section, shadowed where a scope owns its own memory face

Status: implemented

English | [中文](2026-09-14-project-memory-usage-policy.zh.md)

## Problem

The bounded memory design assigns the usage behavior but names no carrier: recall runs once at the beginning of a project task when enabled, and the controller's final task summary becomes a candidate project note after acceptance. The tools existed in every scope, but nothing taught any agent the behavior, so the deployed vault stayed empty from the first boot. The carriers that fit badly were the ones that looked obvious: the `standard` preset persona is static text in a deployment-independent package, so teaching its tools there would promise memory to deployments that have none, and per-controller scope surgery in the shadow router would grow provisioning machinery for what is, in the design's own words, the model's own behavior across its existing turns.

## Decision

`project-memory` itself carries the policy. Its plugin registers one global prompt section (`project-memory:usage`, order 40) exactly when the resolved spec has a configured Vault — the design's "when enabled". The text teaches the role-aware behavior from the model's perspective: search once at the start of a task and read a full note only when an excerpt is not enough; after the work on a task is accepted, append one short project note with yourself as the source, an observation that is never a confirmed preference; record the human's preferences in `user` scope only on their explicit ask; never copy transcripts, secrets, credentials, or environment dumps; report every memory failure verbatim and continue.

Consumers that compose their own memory face suppress the global text on their scope by shadowing the exact name — the mechanism the scoped prompt service already owns. The Shadow conversation host does this unconditionally (an empty same-name section), because its scope carries its own memory section (`experimental:shadow-memory`) with user-scope semantics, and a scope should carry one memory face, not two.

## Alternatives considered

**Edit the `standard` preset persona.** Rejected: the persona is static text in `agent-presets`, deployment-independent; a deployment without project-memory would carry instructions describing tools that do not exist, and preset edits cannot be conditional on anything.

**Register a scoped section from the shadow router's controller provisioning.** Rejected for this round: the router would have to probe the memory tools and register guidance into every provisioned controller's scope — new provisioning machinery for text a global layer already distributes, and workers (whom the design allows to read) would get nothing.

**Host-owned injection instead of prompt guidance** (inject a recall result into the task's opening turn, append the summary from the completion gate). Deferred: the design forbids a separate reflection conversation, and the steering-shaped behavior needs no new session events, receipts, or failure plumbing; if steering proves insufficient in practice, the completion gate is the honest place to revisit.

## Consequences

Bought: in a configured deployment, every session that sees the memory tools is taught the design's usage behavior — controllers recall at task start and record accepted summaries; workers recall; the Shadow alone keeps its own face. In an unconfigured deployment the prompt carries nothing about memory, matching tools that honestly report `MEMORY_UNAVAILABLE`.

Cost: the section's fixed text joins every request's prompt in configured deployments (one bounded paragraph, prefix-stable); the guidance steers rather than enforces — the trust-label rules still live in the tool descriptions and the host's screening; and the section name `project-memory:usage` is a cross-package contract the Shadow host shadows by a string literal with a cross-reference comment, because one constant is not worth a dependency edge between the two experimental families.

## Testing

`plugin.spec.ts` pins the section's presence through the assembled prompt with a configured Vault, its absence without one, and its removal with the plugin fiber's dispose. `shadow-agent.host.spec.ts` pins the shadow suppression: with the global section registered, the Shadow's assembled request carries its own memory guidance and not the global policy's text.

## Related

[The Shadow persona teaches the memory tools only when the deployment mounts them](2026-09-14-shadow-memory-guidance.md) owns the Shadow's own section; the policy text realizes [the bounded memory design](../../../../docs/detailDesign-part3.md).
