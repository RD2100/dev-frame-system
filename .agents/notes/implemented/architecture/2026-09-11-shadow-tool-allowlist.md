# Agent Note: The Shadow conversation host enforces the design tool allowlist on its composed scope

Status: implemented

English | [中文](2026-09-11-shadow-tool-allowlist.zh.md)

## Problem

The designated Shadow session is created through the ordinary agent registry, so it inherited the deployment's whole global toolset — shell, file, session-control, and plugin tooling included — and the shadow router's `markShadow` installed its four model-facing `project_*` tools into the same agent scope beside the conversation host's four `shadow_*` tools, leaving two project tool faces on one session. The design ([detailDesign-part2.md](../../../../docs/detailDesign-part2.md), Project tools) demands the opposite: the Shadow's model-facing allowlist contains only its routing tools and explicitly enabled user-memory access, with no arbitrary filesystem/shell execution, raw session-control tools, plugin self-modification, or unrestricted MCP access. Nothing in shadow-controller enforced any of it, and the README recorded the coexistence as a known limitation deferred to a router-contract follow-up.

## Decision

The conversation host's factory setup (`shadowSetup` in `shadow-agent.ts`) enforces the allowlist on the scope it composes, after installing the four conversational tools and the persona section, with three effect-scoped registrations that all unwind with the agent scope:

1. `agentCtx.tools.restrict({ allow: enabledMemoryTools })` hides every inherited deployment tool except the memory tools the project-memory plugin actually mounted (`memory_search`, `memory_read`, `memory_append`), probed against the global layer at setup time because `restrict()` fails loud naming an unknown global tool. An empty allow list is legal and hides the whole inherited face; allow-list (not deny-list) semantics keep later-registered globals hidden too.
2. `agentCtx.tools.presentAs('native')` pins the presentation so a PTC-mode deployment can neither collapse the face to `run_code` nor hand the Shadow arbitrary program execution.
3. `agentCtx.tools.guard(shadowAllowlistGuard)` denies, monotonic and fail-closed, every execution on the designated agent whose name is outside the allowlist (the four conversational names plus the three memory names). Guards run before dispatch for every ready execution, so the denial also covers names restricted away or never registered.

The allowlist names are fixed strings — a design security invariant, not a deployment tunable.

### Why a guard is part of the mechanism

`tools.restrict()` filters only what a scope inherits — the global layer and ancestor scopes — because the registry deliberately exempts a scope's OWN registrations so a delegated child keeps the tools it answers through (and `restrict()` fails loud naming a scope-local name). The router registers `project_*` into the designated agent's own layer (`agent.ctx`), the same layer the conversation host registers its tools into, so no restriction can hide them. The guard closes the execution path that remains visible: a model calling `project_open` would supply its own `request_id`, dodging the host-minted request custody the conversational face and the design reserve for the host, even though the router would authorize the designated caller.

## Alternatives considered

**Restrict alone.** Rejected: the own-layer exemption leaves the router's `project_*` face fully visible and executable, which is exactly the duplication this change converges; restrict also fails loud when the allow list names scope-local tools, so the conversational four cannot even be listed.

**The subagent persona/toolFilter mechanism.** Rejected after reading it: `SubagentStartRequest.toolFilter` is applied as `childCtx.tools.restrict(...)` in the child's creation window (`applyChildComposition`) — the same semantics with no additional filtering power — and `AgentOptions` carries no tool filter field at all.

**Hiding `project_*` by pre-registering the same names in the host setup.** Rejected: the router's later registration would throw "already registered in this scope", `installShadowTools` would roll back and rethrow, and the synchronous `agent/created` listener failure vetoes agent publication — the designated session could never be created in a router-designated deployment.

**Persona-only steering (the prompt names the four tools).** Rejected: prompts describe behavior but cannot enforce tool permissions (the [native-development proposal](../../proposed/feature/2026-09-02-devframe-dsh-native-development.md) records the same conclusion), and a visible, executable `project_open` is a bypass a model can take regardless of what the persona prefers.

**Converging on the router's `project_*` face instead.** Rejected for this host: the conversational tools exist to keep request-id custody, bounded text, and the conversation surface host-owned; the design's caller-cannot-choose-session and host-retained-request-id rules are enforced by the conversational face, so it is the one that wins on the composed designated scope.

## Consequences

Bought: the composed designated scope's inherited face is exactly the explicitly enabled memory access; presentation cannot drift to PTC; execution on the scope is fail-closed to the allowlist through the executor (pinned by the real-composition suite with and without memory tools, the `project_open` denial, the untouched global and sibling faces, and the disposal unwind). Other agents and the global registry are untouched, and resume re-composes the same face.

Cost and remaining gap: the router's four `project_*` schemas remain visible in the designated scope's `schemas()` — same-layer own registrations are exempt from restrictions by design — so the model still sees them while their execution is denied. Removing the visibility residual requires the router-side contract change (one tool face per designated session); the shadow-router README's "the designated Shadow scope gains exactly four tools" claim and this package's Known Limitations entry now describe the same fact from both sides. Two smaller costs: memory tools mounted after the session exists stay hidden (the allow list compiled at setup — fail-closed), and on the designated scope an unknown tool name denies with the allowlist message rather than the generic unknown-tool error.
