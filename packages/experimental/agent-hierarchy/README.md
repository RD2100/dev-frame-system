---
description: "Role policy, creation-entry guard, plugin-scope validation, and cold recovery for the pluginized agent hierarchy."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-agent-hierarchy

English | [中文](README.zh.md)

## Summary

`dsh-experimental-agent-hierarchy` mounts `ctx.agentHierarchy`, the policy service of the pluginized agent hierarchy. It unifies the role policy into the three states `controller` / `lead` / `worker` (the retired `reviewer` deny semantics merged into the lead and worker faces), installs one monotonic pre-execute guard on the root tool registry that covers every agent-creation entry — the delegation seam (spawn/fork), the Team spawn/task-control tools, and any further creation surface the host declares — validates a lead's delegated plugin scope against the host's approved sets, enforces the absolute delegation-depth budget of 2 as a second, independent refusal path beside the seam's `SubagentDepthError`, and rebuilds roles and per-agent restrictions from the durable binding registry on cold recovery. The guard resolves each execution's role live from `ctx.agentBindings`, so a binding written or restored after activation is honored immediately; a session without a role binding that reaches a controlled tool is denied fail closed with the missing role named.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Mount the service after the session-identity registry in a composition that also mounts the agent registry and the tool registry; it hard-injects `ctx.agentBindings`, `ctx.tools`, and `ctx.agents` and fails at activation when any is absent.

```yaml
- name: '@deepseek-ai/dsh-experimental-session-identity'
- name: '@deepseek-ai/dsh-experimental-agent-hierarchy'
  config:
    roleToolPolicies:
      controller: { inheritedTools: ['project_read', 'subagent', 'send_message'] }
      lead: { inheritedTools: ['project_read', 'subagent', 'send_message'] }
      worker: { inheritedTools: ['project_read', 'send_message'] }
    leadPluginScopes:
      lead-1: ['plugin-a']
```

### Role policy

Each role keeps the global tools its `inheritedTools` list names (an empty list denies every global tool for that role) plus optional host `denyScopedTools` extras. The package adds its own fixed deny faces: the lead loses the Team spawn/task-control tools, and the worker loses every tool that can create an agent. `send_message` stays deliberately allowed for workers — it is the authorized reporting route toward the lead. A session with no role binding that calls any controlled tool is denied with `missing role`; unbound sessions keep executing non-controlled tools.

### Lead plugin scopes

A lead delegating through a spawn/fork tool must carry a `pluginId` binding that sits in the approved set `leadPluginScopes[<agentId>]` from the host config. An unlisted lead, a lead without a plugin scope binding, and an out-of-set scope are all refused fail closed. A depth-2 session delegating at all — whatever its bound role — is refused by the depth budget, independently of the role face.

### Programmatic creation

Tool executions are guarded automatically. Every non-tool creation entry (host services, SDK bridges) must call `ctx.agentHierarchy.evaluateCreation(creatorRecord, intent)` before the child exists; it applies the same policy to a P00 `CreationIntent`.

The evaluator permits a controller to create only a lead. It rejects requests for another controller or a worker; a lead creates workers only within its approved plugin scope. Returning an allowed decision does not create or bind an agent: the caller must enforce the decision before performing creation.

`createChildAgent(parent, request, options)` validates the live parent, role, depth, task, and worktree ownership, then persists the binding during Agent factory setup before publication. Every child requires an explicit plugin scope. The caller supplies a registry-validated worktree and setup that mounts the required preset. Matching parent/task retries return the live child; conflicting requests and occupied worktrees reject. A reserved child that is unavailable requires explicit recovery. The method activates the Agent without sending a prompt. Hosts may allocate its SessionID beforehand to configure the lead's approved plugin scopes.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design decisions behind the feature and points at the code that realizes them; the observable behavior is fully covered in [Use this package](#use-this-package).

### Design decisions

- **The guard is the authority; restrictions are defense in depth.** Role, deny face, depth, and scope resolve per execution from the live binding registry and the exact agent identity, so a stale or unbound identity can never borrow a record. The per-agent inherited restriction only narrows prompt visibility; it installs lazily at first enforcement, on `agent/created` for bound agents, and from the init-time cold pass, and it lifts on agent disposal.
- **Double-insurance depth.** The delegation seam refuses a child beyond `maxDepth` with `SubagentDepthError`; this package's guard independently refuses any delegation from depth 2. The budget is a fixed security invariant, not a configuration field.
- **Cold recovery without a registry event.** The binding registry persists records but emits no events, so the service rebuilds from three paths: the init pass over restored records whose agents are live again, the `agent/created` listener for agents created after activation, and the guard's per-execution lookup, which needs no event at all.
- **Fail loud at load, fail closed at enforcement.** Configuration validates once at construction; guard denials are plain reason strings naming the role, missing role, scope, or depth.

### Source map

| File | Role |
|---|---|
| [`src/service.ts`](src/service.ts) | The `ctx.agentHierarchy` service: guard install, listeners, cold pass, disposal |
| [`src/guard.ts`](src/guard.ts) | The monotonic pre-execute guard over identity, role, depth, and scope |
| [`src/policy.ts`](src/policy.ts) | The three-role lookup table, deny faces, and the depth budget |
| [`src/creation.ts`](src/creation.ts) | The programmatic creation-face evaluator over `CreationIntent` |
| [`src/config.ts`](src/config.ts) | The zod-validated host configuration |
| [`src/errors.ts`](src/errors.ts) | `AgentHierarchyError` and its stable code union |
| [`src/index.ts`](src/index.ts) | Package entry and default export |

### Invariant

No runtime invariant companion is published: every denial is derived from the single binding registry and the live agent registry at execution time, and the guard is the only enforcement authority — the installed restrictions are projections of the same configuration, so no independent observation exists that could diverge.

</details>

-----

<a id="model-experience"></a>
## Model Experience

### Role policy and creation guard

#### What the model sees

A denied tool call returns a pre-execution error result naming the reason — the bound `controller` / `lead` / `worker` role, `missing role`, the plugin scope, or the depth budget — and the tool body never runs; no post-execute listener can overturn the denial. A tool restricted away by the inherited allow face disappears from the prompt and reads as an unknown tool.

#### Token effect

No fixed per-request cost. The inherited allow face can shrink a role's tool list, which reduces prompt tokens for the affected agents; a lazy restriction install changes the tool list from the next request onward.

#### KV Cache effect

A restriction installed or lifted between requests changes the affected agent's tool prompt prefix and therefore breaks that agent's provider cache reuse for the next request. Guards and denials never touch request content.

## Known Limitations and Deferred Work

These limits define when the service is a poor fit or needs special operational care. They are current package constraints, not a task backlog.

- **Tool face only.** The guard covers model-facing tool executions; programmatic creation entries must call `evaluateCreation` themselves. An automatic SDK-face interception is deferred until a consumer wave defines it.
- **Binding writes emit no events.** A freshly bound agent's restriction installs at its first guarded execution or on the next announcement, not at bind time; enforcement is never delayed because the guard reads roles live.
- **No unbind.** Records are durable facts; a disposed agent's stale identity is refused by the identity check rather than by record removal, and a removed role has no lifecycle path yet.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

The devframe `RolePolicy` (controller/worker/reviewer) is the deployment this package supersedes; its migration is a later wave and this package does not import devframe. The depth budget mirrors `DEVFRAME_DELEGATION_DEPTH_BUDGET` on purpose; the seam's own `SubagentDepthError` path stays the first refusal half.

</details>
