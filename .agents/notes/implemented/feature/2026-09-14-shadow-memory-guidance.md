# Agent Note: The Shadow persona teaches the memory tools only when the deployment mounts them

Status: implemented

English | [中文](2026-09-14-shadow-memory-guidance.zh.md)

## Problem

The design admits the memory trio (`memory_search`, `memory_read`, `memory_append`) into the Shadow's model face as explicitly enabled user-memory access, and the conversation host's allowlist wiring already probes and admits whatever the deployment mounts — but nothing ever taught the model when to use them. The tool descriptions carry the trust-label policy, yet the Shadow's persona never mentioned memory, so the model had no behavioral guidance to search on prior-context references or append what the human asks to keep. The deployed vault stayed empty from the first boot: the tools were reachable, and no model had any reason to call them.

## Decision

The conversation host registers one more scoped prompt section — `experimental:shadow-memory`, order 11, beside the persona — only when `enabledMemoryTools` returns the whole trio. The section's rules mirror the design's usage policy: search once when the human refers to prior context and before claiming nothing is on record; append only what the human asks to keep, recording the human as the source and never promoting the Shadow's own inference to a confirmed preference; report every memory failure verbatim and continue, because memory is optional context. The registration is conditional on the full trio because the text names all three tools: a partial probe gets silence rather than a promise about tools that are not there, and a deployment without project-memory keeps the unchanged persona and prompt shape.

## Alternatives considered

**Fold the memory rules into the persona text unconditionally.** Rejected: the persona is static while the memory face is deployment-dependent — a deployment without project-memory would carry instructions describing tools that do not exist, and every other deployment would pay the tokens for guidance aimed at a face it lacks.

**Let project-memory contribute the guidance as its own prompt section.** Rejected: a package-level section would reach every agent scope that inherits the global prompt, while the design scopes user-memory access to the Shadow's face; the guidance belongs to the scope the allowlist composes, where the probe already knows the truth.

**Wait for the controller-side memory behavior (recall at task start, append the final summary after acceptance) and ship both together.** Deferred, not rejected: the controller behavior lives with the presets and the dispatch flow, changes every controller session's tokens, and needs its own decision; the Shadow guidance stands alone and unblocks the human's standing conversation today. The controller side has since landed as [the global usage-policy section](2026-09-14-project-memory-usage-policy.md), which this scope shadows by name.

## Consequences

Bought: a deployment that mounts project-memory gets a Shadow that searches on prior-context references and records what the human asks to keep; a deployment without it sees no change at all. The guidance, the three memory schemas, and the persona share one request prefix, so KV-cache reuse survives while the mount state stays fixed.

Cost: the designated session's prompt grows by the section whenever memory is mounted, and the guidance steers rather than enforces — the trust-label rules still live in the tool descriptions and the host's screening, so a model that ignores the section gains nothing it could not already call.

## Testing

`shadow-agent.host.spec.ts` pins both faces through the assembled model request: with the trio mounted the request carries the guidance ("Memory holds durable facts only"), and without it neither the guidance nor the tool names appear anywhere in the request.

## Related

[The Shadow conversation host enforces the design tool allowlist](../architecture/2026-09-11-shadow-tool-allowlist.md) owns the probe and the allowlist this registration rides on; the usage policy itself is [the bounded memory design](../../../../docs/detailDesign-part3.md).
