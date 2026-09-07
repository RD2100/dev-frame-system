# Session identity bindings

English | [中文](session-identity.zh.md)

The session-identity subsystem keeps one durable binding record per agent in the pluginized agent hierarchy: it creates native Sessions with exact `cwd` and lineage header metadata for agents the host creates itself, binds agents that other entry points (spawn, fork, Team spawn, SDK) already created, and restores every binding cold on start. The [package README](../../packages/experimental/session-identity/README.md) owns the mount configuration and the model experience; this page records the registry's service surface and contracts.

## Service surface

`ctx.agentBindings` is the durable binding registry of the pluginized hierarchy. Its core operations:

- `createBoundSession` — creates the native Session with exact `cwd`, `parentSession`, and `delegationDepth` header metadata, then writes the complete record — host Session id, parent, and worktree — in one durable write.
- `bind` — registers an agent created by another entry point; an identical rebind is idempotent and a conflicting rebind fails loud.
- `find`, `byRole`, and `list` — answer from the in-process index, so a cold process sees every binding without replaying sessions.

## Contracts

Every failure carries a stable `SESSION_IDENTITY_*` code on `SessionIdentityError`: unknown agent, unknown parent, already bound, invalid request, or persistence. Records live in the `session_identity` [storage domain](storage.md) as JSON documents under the composition's storages root; queries answer from a write-through index that start rebuilds from the domain table, so the table stays the only durable authority. Binding records are durable facts with no removal operation — there is no unbind — and no record value ever reaches a model request, so no session events are added and neither SDK projection changes.

## Boundaries

The registry hard-injects `ctx.sessions` and `ctx.storageDomain` and fails at activation when either is absent. [Agent hierarchy policy](agent-hierarchy.md) resolves every execution's role live from these bindings; [Shadow project router](shadow-router.md) and the [project task controller](project-controller.md) verify roles and identity against them. The shared `AgentBindingRecord` type belongs to the [project-contracts package](../../packages/experimental/project-contracts/README.md).

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxagentbindings--agentbindingregistry"></a>

### `ctx.agentBindings` — `AgentBindingRegistry`

The agent binding registry: durable hierarchy identity per agent.

```ts cordis-catalog
/**
 * Create one native Session with exact cwd and lineage metadata and write
 * its binding record — host Session id, parent session, and worktree — in
 * one durable write. A session whose binding write fails stays live and
 * unbound; the caller owns its disposal.
 * @param request - Creation identity: cwd, role, optional parent/depth/task/plugin/worktree.
 * @returns the live session and the durable binding record.
 */
async createBoundSession(request: CreateBoundSessionRequest): Promise<BoundSession>

/**
 * Bind one agent an existing entry point already created. An identical
 * rebind is idempotent; a different binding for the same agent fails loud.
 * @param request - Binding identity: live agent id, role, and optional fields.
 * @returns the durable binding record.
 */
async bind(request: BindAgentRequest): Promise<AgentBindingRecord>

/**
 * Persist identity during the Agent factory's unpublished setup window.
 * The factory retains Session ownership; this method never enters the store.
 * If later setup fails, the binding remains reserved for explicit recovery.
 * @param session - Factory-owned unpublished Session from the setup context.
 * @param request - Role and ownership; identity and parent derive from the Session.
 * @returns The durable binding, available before Agent publication.
 */
async bindPreparedSession( session: Session, request: Omit<BindAgentRequest, 'agentId' | 'sessionId' | 'parentSessionId'>, ): Promise<AgentBindingRecord>

/**
 * Read one agent's binding from the restored index.
 * @param agentId - Live Agent registry identity selecting the record.
 * @returns the binding, or `undefined` when the agent has none.
 */
find(agentId: SessionId): AgentBindingRecord | undefined

/**
 * Read every binding carrying one role.
 * @param role - Hierarchy role to filter by.
 * @returns the matching records in stable (createdAt, agentId) order.
 */
byRole(role: AgentRole): readonly AgentBindingRecord[]

/**
 * Read every binding in stable (createdAt, agentId) order.
 * @returns all restored or written records.
 */
list(): readonly AgentBindingRecord[]
```

Types: [Session](session.md) · [SessionId](core.md)

Source: [`packages/experimental/session-identity/src/registry.ts`](../../packages/experimental/session-identity/src/registry.ts)
<!-- END GENERATED cordis-surface -->
