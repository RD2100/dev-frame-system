# Agent Note: The apply face mounts real host stop adapters by default

Status: implemented

English | [中文](2026-09-08-command-goal-binding-host-stop-adapters.zh.md)

## Problem

The stop chain composition left the three host faces — the project tree, the captured descendant processes, and the writer release — as constructor injection points with no real wiring: `apply` passed only the required-checks store, so every standard-profile deployment ran the chain fail-closed (`inventoryUnverified`, unwired release) no matter what the fiber carried. The faces were real only for tests that built their own adapters, which is exactly the gap the stop-chain note deferred to a host wiring slice.

## Decision

The apply face now resolves the stop store from the fiber through `resolveHostStopAdapters`. The captured process inventory is always mounted and reachable through `hostStopInventoryOf(ctx)`, so a dispatch face that takes ownership of a descendant process has a capture point without reaching into the composition. The tree and release faces mount when the fiber carries the agent, workspace, and worktree registries and the configuration names a worktree root; the registries are read with the optional `ctx.get(name)` read, never the property proxy, because the plugin does not declare them as injections and a topology-sensitive read would throw on fibers that mount them elsewhere.

The tree face is cwd-identity: every live agent whose session header cwd canonically equals the configured worktree, compared through `fs.realpath` with the Windows case dispatch. Worktree identity is the project boundary — an agent of another worktree is never drained — and the chain adds its own live-identity owner filter on top.

The release face performs the full owner gate synchronously: the worktree must be a registered row of the workspace that owns the configured root, an unbound row is an already-completed release (repeat-tolerant), and a bound row releases only when its holder is the session id of a live tree agent — a foreign writer is never released and the throw retains the writer. The registry's `unbind` is asynchronous while the stop primitive's release face is synchronous by contract, so the checked release is handed to the registry and a rejected unbind is logged loudly: the durable registry row is the release truth, the writer stays bound, and the repeat stop re-enters the release and reconciles against the row. The owner gate is what the synchronous contract protects; the async remainder rides the existing interrupted-flow convergence.

## Alternatives considered

**Declaring the registries as plugin injections.** That would make the plugin refuse to load on fibers without the worktree stack and force the stop-vocabulary-only deployments to mount services they never call. Optional reads keep the faces absent — and the chain fail-closed — instead of failing the load.

**Making the release await the registry.** The stop primitive's release face is synchronous by contract (`a throw must retain the writer`); changing that means reshaping the reliability primitive, which this slice does not own. The logged-async remainder keeps the durable truth honest and recoverable without widening the seam.

**Deriving the tree from session lineage instead of cwd.** A lineage walk needs the root identity the tree face does not have (the chain supplies the invoking agent itself), and lineage without worktree identity would drain foreign sessions that happen to fork from a project session. The cwd boundary is the fact the host can verify without either.

## Consequences

Standard-profile `stopChain` deployments get a real tree, a real inventory, and a real writer release without extra host code, while deployments without the registries keep the previous fail-closed behavior byte-identically. The captured-process inventory starts empty — no product dispatch face captures descendant subprocess handles yet — so the process drain still has nothing to drain until a capture feed lands; the wiring is the seam, not the feed. The release truth for an async failure surfaces through the warning log and the repeat stop, not through the stopped record.
