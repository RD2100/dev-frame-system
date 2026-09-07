# @deepseek-ai/dsh-experimental-agent-dispatch

Host-side dispatch entry over the agent-hierarchy engine. The service
definition exposes `ctx.agentDispatch.createChildAgent(parent, request,
options)` for composition-layer callers; the engine
(`@deepseek-ai/dsh-experimental-agent-hierarchy`) owns child-agent identity and
lifecycle, and this adapter never implements creation itself.

## Entry contract

- Validates the request against authoritative registry rows before the engine
  call: registered worktree id, existing directory, path/branch match, and the
  workspace's lock occupant (`status` reports `directoryExists/branch/clean`;
  path and `lockedBy` come from `worktreeRegistry.list`).
- Reuses the engine's approved-scope contract
  (`config.leadPluginScopes[creator.agentId]`) — the adapter does not re-copy
  role policy; engine rejections propagate unchanged.
- Assembles inside the entry: preset `composeFrom(parent.ctx)`, the
  `worktreeRegistry.bind` single-write lock held by the child session id, then
  the engine's `bindPreparedSession`; an optional `prompt` is delivered through
  `child.agent.followup` only after the engine publishes.
- Caller-provided `setup` runs after the assembly slice and must not be used to
  supply the assembly itself.

## Error surface

`AgentDispatchError` codes: `DISPATCH_WORKTREE_UNREGISTERED`,
`DISPATCH_WORKTREE_MISMATCH`, `DISPATCH_PARENT_UNBOUND`,
`DISPATCH_HIERARCHY_DENIED`. Engine rejections (role, scope, depth, dedupe)
propagate as their own typed errors.

`DispatchAgentOptions` is the adapter options face: the four engine
`CreateChildAgentOptions` fields passed through key-explicit, plus the required
`workspaceId` used for authoritative-row validation and the optional `prompt`.

## Known Limitations and Deferred Work

- The composition tests run with rosterless degradation: preset
  `composeFrom` is an optional-chain no-op without a joined roster, so real
  roster preset join, model-driven dispatch rounds, and shipped-profile
  mounting are not yet verified — the external combined-verification lane owns
  that evidence.
- Recovery of an interrupted creation reuses the engine's
  `recoverChildAgent` semantics (typed `SessionPersistenceNotFoundError`
  restores the original id; corruption and cancellation do not fall back); the
  adapter adds only durable identity lookup and never re-dispatches a prompt
  on identity reuse.
