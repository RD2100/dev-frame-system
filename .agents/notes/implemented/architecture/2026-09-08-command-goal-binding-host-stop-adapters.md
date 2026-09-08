# Agent Note: The apply face mounts real host stop adapters by default

Status: implemented

English | [中文](2026-09-08-command-goal-binding-host-stop-adapters.zh.md)

## Problem

The stop chain composition left the three host faces — the project tree, the captured descendant processes, and the writer release — as constructor injection points with no real wiring: `apply` passed only the required-checks store, so every standard-profile deployment ran the chain fail-closed (`inventoryUnverified`, unwired release) no matter what the fiber carried. The faces were real only for tests that built their own adapters, which is exactly the gap the stop-chain note deferred to a host wiring slice. The stop chain also had no resume-side admission: after a drain fenced an owner nothing re-opened it, and nothing re-took the released writer.

## Decision

The apply face resolves the stop store from the fiber through `resolveHostStopAdapters`. The tree face mounts when the fiber carries the agent registry; the release face additionally requires the configured worktree root and the workspace and worktree registries; the registries are read with the optional `ctx.get(name)` read, never the property proxy, because the plugin does not declare them as injections and a topology-sensitive read would throw on fibers that mount them elsewhere.

The tree face is dispatch lineage: the receiving root plus every live agent whose session header `parentSession` chain — walked through the live agent registry, cycle-bounded — reaches the root. The root identity arrives at call time: the chain supplies the invoking agent, which is also the owner-gate scope the release face needs. Lineage is the project boundary — an independent-worktree worker with an explicit parent binding belongs, and a lineage that leaves the live registry is unprovable and excluded — so sessions of the same repository outside the lineage are never drained.

The configured workspace id selects the workspace; the canonical worktree path selects its target row, so linked worktrees need not equal the workspace anchor. The release face performs the owner gate and awaits the registry's asynchronous `unbind`: the worktree must be a registered row of the workspace that owns the configured root, an unbound row is an already-completed release (repeat-tolerant), and a bound row releases only when its holder is the session id of a live tree agent — a foreign writer is never released and a throw retains the writer. Because the release settles inside the stop primitive's bounded window, a pending or rejected release reports `needs_attention` with the writer held; the durable registry row is the release truth, and the repeat stop re-enters the release and reconciles against it.

The process face consumes the host subagent runtime and the terminal ownership directory described in [Terminal host ownership](2026-09-08-terminal-host-ownership.md). Each live lineage owner yields at most one subagent and one terminal drain entry; the directory covers every isolated terminal instance and fences future spawns even when no instance exists. `prepareResumeResources` preserves the directory batch preflight, revalidates the original live owner tree, and prepares the subagent owners before committing. A changed tree, directory, or owner drain generation leaves admission fenced.

The release face has a resume counterpart: `createHostWriterAcquire` re-takes the single-writer binding under the same workspace and row gates with a live receiving-root gate of its own, and the registry's `bind` accepts an unbound row or the same holder while refusing to displace a foreign writer. The authorized resume re-takes the writer before reopening resources, so a foreign-held worktree fails the resume without stealing the lock and the durable row stays the truth. When the host carries a project controller, the resource commit also opens its stopped request admission before native Goal continuation activates; preparation rejects pending stop states and commit rechecks the captured lifecycle.

Cold stop restores a matching projected binding into an empty process store without resuming the native Goal; a projection for another Goal remains insufficient.

## Alternatives considered

**Sync-bridging the async unbind with a logged rejection.** Handing the checked release to the registry and logging a late rejection reports the stop result while the release is still unproven. A controlled counterexample against the real registry showed the damage: the result landed `stopped` while the `unbind` promise was still pending, and the later rejection only warned — a false success the composition contract forbids. Awaiting the release inside the bounded window is the honest form: `stopped` only after the binding is provably cleared.

**Deriving the tree from worktree cwd instead of session lineage.** The cwd-equal filter is a project boundary only for sessions that live in the configured worktree. It excludes an explicitly parent-bound worker whose own cwd is an independent worktree — the same counterexample proved the exclusion — and keeping it would split the chain's tree from the host's real dispatch tree. Lineage through the live registry is the ownership fact the chain can verify, and the receiving-root argument keeps it from widening into "every session of the repository".

**Declaring the registries as plugin injections.** That would make the plugin refuse to load on fibers without the worktree stack and force the stop-vocabulary-only deployments to mount services they never call. Optional reads keep the faces absent — and the chain fail-closed — instead of failing the load.

## Consequences

Standard-profile `stopChain` deployments drain real owned resources through the bounded window, and an authorized resume re-takes the writer and re-opens admission without widening either fence. Deployments without the registries keep the previous fail-closed behavior byte-identically. A release that never settles still returns bounded: the pending timeout names `writer:release`, the writer stays held, and the repeat stop re-enters the release over the durable row.
