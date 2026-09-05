# Agent Note: Per-agent worktree single-writer bindings and the agent-worktree consumer

Status: implemented

English | [中文](2026-09-05-per-agent-worktree-single-writer-seam.zh.md)

## Problem

The worktree registry seam and its workspace-facing tools treat a worktree as shared infrastructure: any session of the owning workspace can create, observe, and remove any registration. The pluginized agent hierarchy needs the opposite promise for its own sessions — a task's checkout that exactly one writer owns — and three gaps made the shared surface unusable for that:

- Nothing recorded ownership. Two agent sessions handed the same worktree could both write it, and either could remove it under the other.
- Removal raced with hand-off. A session finishing its task removed the worktree while a peer still needed it; there was no way to hold a worktree against everyone else's cleanup.
- Recovery destroyed ownership silently. `reconcile` with `pruneRows` was the only path that could retire a registration, and nothing said what a binding would mean there.

## Decision

Two pieces land together, because the binding only means something once a model-facing consumer uses it:

- **The registry owns the binding mechanism** (`packages/workflow/worktree-registry`): `bind(id, holder)` and `unbind(id, holder)` join the service surface — seven operations now — and the durable record gains the optional `lockedBy`/`lockedAt` pair (storage domain version 2; old media reject at open per the pre-release stance). The holder value is an opaque branded `WorktreeLockHolder`; equality is the whole contract. Re-binding by the current holder is idempotent, every other bind refuses with `already-locked`, an unbind by anyone else refuses with `holder-mismatch`, an unbind of an unbound worktree refuses with `not-locked`, and `remove` refuses while bound — `force` never overrides the binding. `pruneRows` drops a stale row together with its binding: a binding guards a live checkout, not a vanished directory.
- **The consumer binds creation itself** (`packages/experimental/agent-worktree`, `@deepseek-ai/dsh-experimental-agent-worktree`, private and experimental): the `AgentWorktree` Service Definition on `ctx.agentWorktree` composes create+bind so a worktree is bound from its first observation, exposes a workspace-authorized `status`, and serves `worktree_remove`, which refuses other holders and releases the caller's own binding before git runs. Its Consumer role registers exactly three tools — `worktree_create`, `worktree_status`, `worktree_remove` — plus a fixed guidance section. With the registry absent the plugin fiber stays pending and contributes nothing; it activates when the registry arrives. Mounting it beside `tool-worktree` double-registers the shared tool names and fails loud.

### The holder is the session's durable id

The consumer mints `WorktreeLockHolder(String(agent.session.id))` — the durable session id, not a per-turn or per-process value — so a recovered agent still matches its binding after a restart. The registry never interprets the marker; the identity choice belongs to the consumer, and a different consumer could mint holders differently against the same registry.

### Authorization mirrors the workspace tools

Every operation resolves the caller's workspace from the immutable session header cwd — never from a model-supplied id — and an id the workspace holds no row for is reported exactly like an unknown one. `status` stays observational: any session of the owning workspace may observe the binding facts, while removal stays holder-exclusive.

### Registry-level branch uniqueness

`create` now refuses an explicit branch that another worktree of the same workspace already holds, raising the classified `branch-conflict` kind before git runs; git remains the cross-workspace backstop, so two different workspaces may still hold worktrees on branches of the same name.

## Alternatives considered

- **Binding inside the consumer's own storage** (a private table of holder→worktree rows): rejected — the exclusivity promise must gate the registry's `remove`, which every other consumer reaches; a consumer-side table would be advisory and drift from the rows it points at.
- **`force` overrides the binding**: rejected — a force flag that silently broke the one promise the binding makes would make the binding theater; the holder's unbind is the explicit, logged way out.
- **A lock timeout or break-lock operation**: rejected — a timer that expires a binding re-introduces the race the binding exists to remove; a stale holder wedges removal until the holder returns, another authority unbinds with the holder value, or reconcile drops the vanished row.
- **Separate create and bind tools** for the model: rejected — an unbound worktree between the two calls is exactly the window the seam exists to close; the consumer composes the pair and keeps the model vocabulary at three tools.
- **Reusing the `worktree_*` tool names under different schemas**: not applicable — the names are stable model-facing contracts, so the consumer keeps them identical and relies on the loud double-registration refusal to keep the two consumers apart in one composition.

## Consequences

An agent session's worktrees are exclusive by default: create binds, other sessions observe but cannot remove, removal releases the holder's own binding in the same call, and the promise survives restarts in the registry's durable rows. What it cost:

- **A stale binding wedges removal.** A session that abandons its worktree without removing it blocks every other session's removal until the holder acts or the row is dropped through reconcile after its directory vanished; there is no timeout and no third-party break-lock.
- **The binding is a product promise.** It is enforced at the registry's `remove` only; git commands run outside the registry ignore it entirely.
- **Domain version 2 has no migration.** Media written by version 1 reject at open; deployments must re-create their worktree registrations or accept the rejection, per the pre-release stance.
- **The experimental package is a second model surface for the same names.** Its tools ship in no bundle, but a composition that mounts both consumers fails loudly at load rather than shipping ambiguous tools.

## Verification

- `pnpm exec vitest run packages/workflow/worktree-registry` — the binding lifecycle (`tests/agent-lock.spec.ts`): create→bind→status→reconcile→remove, idempotent re-bind, every unbind refusal, locked `remove` refusing with and without `force`, `pruneRows` dropping a bound row whose directory vanished, concurrent same-path create failing exactly once, same-workspace duplicate-branch refusal with no directory created, and cross-workspace branch sharing still allowed.
- `pnpm exec vitest run packages/experimental/agent-worktree` — the consumer (`tests/agent-worktree.spec.ts`): the three tool schemas, create→bound row, per-session status perspective, removal refusals by holder and workspace, the pending-without-registry fiber that activates when the registry mounts, and HMR dispose/reinstall through the plugin fiber.
- `pnpm run gen-tool-catalog` catalogs the three schemas with stand-in registries, as for `tool-worktree`; `pnpm run gen-cordis-catalog` covers the extended registry and the new `ctx.agentWorktree` surface in the [subsystem pages](../../../../docs/subsystems/agent-worktree.md).
