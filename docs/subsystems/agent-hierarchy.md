# Agent hierarchy policy

English | [中文](agent-hierarchy.zh.md)

The agent-hierarchy subsystem is the policy service of the pluginized agent hierarchy: it unifies the role policy into the three states `controller` / `lead` / `worker`, installs one monotonic pre-execute guard on the root tool registry that covers every agent-creation entry, validates a lead's delegated plugin scope against the host's approved sets, and enforces the absolute delegation-depth budget of 2 as an independent second refusal path beside the delegation seam's `SubagentDepthError`. The [package README](../../packages/experimental/agent-hierarchy/README.md) owns the mount configuration and the model experience.

## Service surface

`ctx.agentHierarchy` is the policy service. Its core operations:

- The guard covers model-facing tool executions automatically; denials name the bound role, `missing role`, the plugin scope, or the depth budget, and the tool body never runs.
- `roleOf` — resolves an agent's bound role from the live binding registry.
- `evaluateCreation` — every non-tool creation entry (host services, SDK bridges) must call it with the creator's binding record and a P00 `CreationIntent` before the child exists.
- `createChildAgent` — validates and creates a child through factory setup, persisting its identity before publication. `CreateChildAgentRequest` carries the required task, plugin scope, and registered worktree; `CreateChildAgentOptions` carries host setup, routing options, cancellation, and an optional allocated SessionID. `CreatedChildAgent` returns the live Agent and durable binding, without sending a prompt. The service owns the Agent lifecycle.

- `recoverChildAgent` — resumes a reserved identity or republishes the same SessionID when its durable log is absent. Corruption and setup failures never fall back to creation; recovery delivers no prompt.
- Configuration validates once at construction: per-role `roleToolPolicies` (each role keeps the global tools its `inheritedTools` list names) and per-lead `leadPluginScopes`.

## Contracts

Load-time failures carry a stable `HIERARCHY_*` code on `AgentHierarchyError` (`HIERARCHY_INVALID_CONFIG`, `HIERARCHY_ROLE_UNKNOWN`); guard denials are plain reason strings, fail closed, and no post-execute listener can overturn them. The fixed deny faces add to the config: the lead loses the Team spawn/task-control tools, the worker loses every tool that can create an agent, and `send_message` stays deliberately allowed as the worker's authorized reporting route. The depth budget is a fixed security invariant, not a configuration field; a depth-2 session delegating at all is refused whatever its bound role. The service keeps no storage domain of its own: roles resolve per execution from `ctx.agentBindings`, so a binding written or restored after activation is honored immediately, and per-agent restrictions are projections installed lazily and lifted on disposal.

## Boundaries

The registry it reads is documented at [session identity bindings](session-identity.md). The delegation seam ([subagent](subagent.md)) keeps the first refusal path with `SubagentDepthError`; this guard is the second, independent one. The Team spawn and task-control tools the lead loses belong to [agent teams](agent-team.md), and the guarded tool registry is the [tools](tools.md) subsystem. Unbound sessions keep executing non-controlled tools.

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxagentdispatch--agentdispatch"></a>

### `ctx.agentDispatch` — `AgentDispatch`

The host daily-dispatch entry. Hard-injects the real creation engine (`ctx.agentHierarchy`), the role authority (`ctx.agentBindings`), and the worktree registry whose rows make the worktree proof real, and fails at activation when any is absent. Denials raised here are AgentDispatchErrors; the engine's own denials — including the reserved-child recovery refusal for an identity whose session is no longer live — propagate unchanged.

```ts cordis-catalog
/**
 * Find the durable identity an earlier dispatch returned for one parent
 * task, if any. The matching rule is the engine's own dedupe key
 * (`parentSessionId` + `taskId`). A retry reuses the identity only by
 * passing `record.agentId` back as `options.sessionId`; reuse never
 * re-delivers a prompt, and a child whose session is no longer live keeps
 * its engine-owned recovery lane instead of a replacement child.
 * @param parent - The dispatching parent the child was created for.
 * @param taskId - The task the child was created for.
 * @returns The durable identity and its live state, or `undefined` when
 *   no dispatched child exists for the pair.
 */
findDispatchedChild(parent: Agent, taskId: TaskId): DispatchedIdentity | undefined

/**
 * Validate one dispatch request at the entry and, when it holds, create the
 * child through the real hierarchy engine. The authoritative registry rows
 * prove registration before any live observation runs; a git failure whose
 * refusal carries the registry's classified kind rethrows unchanged. A
 * parent task that already has a child refuses with
 * `DISPATCH_IDENTITY_EXISTS` until the caller passes the returned agent id
 * back as `sessionId` — the engine's own dedupe then answers with the same
 * child.
 * @param parent - The exact live dispatching agent.
 * @param request - The child creation request; `worktree` is required at
 *   this entry because the dispatched child owns one registered worktree.
 * @param options - Factory setup, route, cancellation, preallocated
 *   identity, the owner workspace anchoring the registry proof, and the
 *   optional initial prompt delivered after publication.
 * @returns The published child and its durable binding record.
 */
async createChildAgent( parent: Agent, request: CreateChildAgentRequest, options: DispatchAgentOptions, ): Promise<CreatedChildAgent>

/**
 * Recover one reserved child through the engine's fixed recovery lane after
 * the same entry proof the creation path runs. The caller must pass the
 * reserved identity back as `sessionId`; recovery reuses the same host
 * assembly as creation — the preset composition join and the registered
 * worktree's single-writer binding are re-established by the composed
 * setup on the recovered session — and never delivers a prompt (the type
 * omits one). The engine decides between resuming the existing session
 * and, only on a typed missing-log result, republishing under the same
 * identity. Corruption, cancellation, and foreign-identity failures
 * propagate unchanged — no replacement child.
 * @param parent - The exact live dispatching agent recorded by the reservation.
 * @param request - The original creation request, unchanged.
 * @param options - The reserved identity, the owner workspace anchoring the
 *   registry proof, and the factory setup, route, and cancellation to
 *   reinstall with the recovered session.
 * @returns The recovered child and its unchanged durable binding record.
 */
async recoverChildAgent( parent: Agent, request: CreateChildAgentRequest, options: RecoverDispatchAgentOptions, ): Promise<CreatedChildAgent>

/**
 * The durable acknowledgment for one dispatched task: what the child's own
 * log proves about the briefing this entry delivered, backed by the
 * session store's flush barrier. The derivation is durable by
 * construction — delivery splice, claiming splice, and the claiming
 * turn's `turn/end` are all durable session events — and `durable` is
 * claimed only when a durability listener participates in the barrier. A
 * barrier refusal or a durability failure never hides the primary
 * dispatch outcome behind an exception: the ack reports `durable: false`
 * with `degraded: true`, so a broken backend is visible exactly where the
 * parent looks, and the child's own turn checkpoints fail loud on their
 * own boundaries.
 * @param parent - The exact live dispatching agent the child was created for.
 * @param taskId - The task the child was created for.
 * @returns The acknowledgment, or `undefined` when no dispatched child
 *   exists for the pair.
 */
async taskAck(parent: Agent, taskId: TaskId): Promise<DispatchTaskAck | undefined>
```

Types: [Agent](core.md) · [DispatchTaskAck](../../packages/experimental/agent-dispatch/README.md)

Source: [`packages/experimental/agent-dispatch/src/service.ts`](../../packages/experimental/agent-dispatch/src/service.ts)

<a id="ctxagenthierarchy--agenthierarchy"></a>

### `ctx.agentHierarchy` — `AgentHierarchy`

The pluginized-hierarchy role and creation policy service. Hard-injects `ctx.agentBindings` (the role authority), `ctx.tools` (the guard and restriction surface), and `ctx.agents` (the exact-identity check the P01 cold-recovery caveat requires) and fails at activation when any is absent.

```ts cordis-catalog
/**
 * Resolve the hierarchy role of one exact live agent.
 * @param agent - Candidate agent identity.
 * @returns The bound role, or `undefined` when the identity is stale or unbound.
 */
roleOf(agent: Agent): AgentRole | undefined

/**
 * Evaluate a programmatic creation intent against the creator's binding
 * and this host's approved plugin scopes. Tool executions reach the same
 * policy through the installed guard; every non-tool creation entry must
 * call this before the child exists.
 * @param creator - The durable binding of the creating session.
 * @param intent - The recorded creation attempt.
 * @returns The verdict with a denial reason when refused.
 */
evaluateCreation(creator: AgentBindingRecord, intent: CreationIntent): CreationDecision

/**
 * Create a child through the Agent factory with its role persisted in setup.
 * The caller supplies a registered, independently owned worktree. This
 * operation does not allocate a worktree or send a prompt.
 * Persistence failures retain the session-identity registry's recovery semantics.
 * Matching parent/task retries reuse the stored binding; changed requests and
 * occupied worktrees reject. A persisted child whose Session is unavailable
 * requires recovery rather than replacement.
 * @param parent - Exact live delegating Agent with a durable role binding.
 * @param request - Child role plus required task, explicit plugin scope, and registered worktree.
 * @param options - Factory composition, model options, and cancellation signal.
 * @returns The published Agent and its durable binding.
 */
async createChildAgent( parent: Agent, request: CreateChildAgentRequest, options: CreateChildAgentOptions = {}, ): Promise<CreatedChildAgent>

/**
 * Recover one reserved child without replacing its identity or replaying a task.
 * Existing durable history is resumed; only a missing durable log permits
 * fresh publication under the same reserved identity.
 * @param parent - Exact live parent recorded by the reservation.
 * @param request - Original role, plugin, task, cwd and worktree binding.
 * @param options - Reserved Session identity and explicit host setup and route.
 * @returns The recovered child and its unchanged durable binding.
 */
async recoverChildAgent( parent: Agent, request: CreateChildAgentRequest, options: CreateChildAgentOptions & { sessionId: SessionId }, ): Promise<CreatedChildAgent>
```

Types: [Agent](core.md) · [SessionId](core.md)

Source: [`packages/experimental/agent-hierarchy/src/service.ts`](../../packages/experimental/agent-hierarchy/src/service.ts)
<!-- END GENERATED cordis-surface -->
