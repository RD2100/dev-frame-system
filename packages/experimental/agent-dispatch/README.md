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

No runtime invariant companion is published: every guarantee the adapter makes
(worktree registration, path/branch match, lock exclusivity, scope approval) is
derived from the same authoritative registry rows and engine evaluation it
calls, and the rejections are observable at the `AgentDispatchError` surface
those calls return, so no independent observation exists that could diverge.

## Known Limitations and Deferred Work

- Evidence state: the real-Loader composition suite proves tool registration
  and the controller/lead/worker visibility faces; the real model round
  proved the service face and one real dispatch round (worker artifact).
  The shipped opt-in overlay is wired — its candidate-profile verification
  (explicit `--patch`, isolated home) is the remaining acceptance step.
- Recovery of an interrupted creation reuses the engine's
  `recoverChildAgent` semantics (typed `SessionPersistenceNotFoundError`
  restores the original id; corruption and cancellation do not fall back); the
  adapter adds only durable identity lookup and never re-dispatches a prompt
  on identity reuse.
