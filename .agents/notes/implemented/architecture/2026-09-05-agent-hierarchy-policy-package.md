# Agent Note: Give the pluginized agent hierarchy its own policy package

Status: implemented

English | [中文](2026-09-05-agent-hierarchy-policy-package.zh.md)

## Problem

The pluginized hierarchy (P00 contracts, P01 session-identity) had durable roles and bindings but no enforcement: a worker could still call the spawn tool, a lead could delegate outside any approved scope, and a cold-restored binding had no guard behind it. The devframe `RolePolicy` covers a different, closed single-project profile — controller/worker/reviewer with host-selected tool lists — and cannot express lead plugin scopes, creation-entry coverage, or the P01 cold-recovery identity caveat.

## Decision

`packages/experimental/agent-hierarchy` is the enforcement package for the pluginized hierarchy. It mounts `ctx.agentHierarchy`, hard-injects the binding registry, the tool registry, and the agent registry, and enforces one policy at two faces:

- **Tool face.** One monotonic pre-execute guard on the root tool registry resolves the executing agent's exact live identity and binding record per execution, then denies in order: stale identity, missing role on any controlled tool (fail closed), the role's deny face, any delegation from depth 2 (the absolute budget beside the seam's `SubagentDepthError` path), and a lead delegating outside the plugin scopes the host config approved for its agent id. Denials are reason strings; no post-execute path can overturn them.
- **Creation face.** `evaluateCreation(creatorRecord, intent)` applies the same policy to P00 `CreationIntent`s for programmatic creation entries.

`createChildAgent` applies this policy before invoking the Agent factory: controllers create only leads, leads create approved-scope workers, and workers create nothing. Its setup persists identity through `bindPreparedSession` before publication while the factory owns Session creation and teardown. The host supplies an explicit plugin scope, registered worktree, and preset composition; creation rejects a missing scope. Parent/task retries return the existing live child; conflicting identities and unavailable reserved children require explicit recovery. This extends the [Agent lifecycle ownership contract](2026-06-18-agent-lifecycle-and-ownership-contracts.md) without changing factory publication rules.

The role policy is a three-state lookup table (`controller`/`lead`/`worker`); the retired `reviewer` semantics merged into the lead and worker deny faces, with `send_message` deliberately kept off both — it is the worker's authorized reporting route. Per-role inherited allow lists come from the zod-validated host config and install as scoped restrictions (lazy at first enforcement, on `agent/created`, and from the init-time cold pass over restored bindings); they are defense in depth only — the guard is the sole enforcement authority, so the package publishes no invariant companion. Cold recovery needs no registry events: the init pass covers live restored agents, `agent/created` covers later agents, and the guard's per-execution lookup covers everything regardless of timing.

Depth budget 2, the deny faces, and the closed role union are security invariants and stay fixed; the deployment-varying choices (tool names, per-role tool lists, per-lead approved scopes) are validated `Config` fields.

## Alternatives considered

**Extend devframe's `RolePolicy`.** It hardcodes the reviewer role, has no scope concept, and assigns roles through an explicit host call; repurposing it would couple the experimental DevFrame profile to the pluginized contracts and keep the wrong home.

**Enforce in the subagent seam.** The seam owns delegation mechanics, not hierarchy policy; teaching it about roles would spread policy across every creation provider and still miss Team and SDK surfaces.

**Emit binding events and subscribe.** The binding registry intentionally stays a quiet durable authority. Events would only serve the restriction half, which the guard's live lookups already cover.

**Create a live Session before creating its Agent.** `createBoundSession` enters the SessionStore, so a later factory call rejects the live identity. Binding in unpublished setup preserves one lifecycle owner and makes the role available to publication observers.

## Consequences

Wave P02 gives P03 (controller) and later waves an enforcement seam they compose rather than rebuild: create bindings, configure the approved scope sets, and creation is policed at every model-facing entry. Deployments must state per-role tool lists explicitly — an empty `inheritedTools` denies every global tool for that role — and misconfiguration fails loud at load. The devframe `RolePolicy` remains untouched until its migration wave.
