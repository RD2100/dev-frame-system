# Agent Note: Host-controlled Worker artifact commits through project_commit

Status: implemented

English | [中文](2026-09-08-project-commit-consumer.zh.md)

## Problem

A project Worker writes task artifacts in its linked checkout but cannot commit them: the sandbox keeps the Worker shell away from the anchor repository's `.git/worktrees/*` (writes fail with EACCES), while `project_deliver` requires a clean, committed worktree. The [host worktree commit Service](../architecture/2026-09-08-host-worktree-commit.md) removed the Git-boundary problem, but nothing exposed it to the model, and a naive exposure would reintroduce the risks that Service exists to remove: a dirty-set readback executes checkout-controlled clean filters, a dirty set proves nothing about task ownership, and worker-supplied HEAD, holder, or path values are forged inputs.

## Decision

The delivery consumer registers one more role tool, `project_commit` (`taskId`, explicit relative `paths`, optional single-line `message`), in the same per-task serial chain as `project_deliver` and `project_review`. The host derives every request field from the real binding and one trusted observation; the Worker shell never runs `git commit`. Registration probes the merged commit Service and fails loud at apply time when the loaded provider build predates it.

### Authorization is the deployment's path scope

`commitPathsByTask` — a new optional delivery-consumer Config map, validated and frozen at apply time — registers the artifact paths each task may commit. A task without a scope refuses; requested paths outside the scope refuse with the offending list; nonexistent or non-file paths refuse on the filesystem before anything else runs. The scope is the fact source: the consumer runs no status or dirty scan, because a plain `git status` executes checkout-controlled clean filters and a dirty set cannot distinguish worker output from anything else that touches a path. Requested ⊆ scope, so multi-round commits are legal.

### One read-only observation, on the owner

The only Git command the consumer runs is `rev-parse --verify --end-of-options refs/heads/<branch>` against the owner workspace directory resolved from registry rows — never through the Worker checkout's `.git` pointer, which the checkout can rewrite. The branch ref lives in the anchor, outside the Worker's write boundary. The trimmed output must be a full 40/64-hex object id and travels unchanged as `expectedHead`; the Service re-verifies branch and expected HEAD inside its pinned linked gitdir, so a race or a redirected checkout surfaces as a Service refusal.

### Quiescence is evidence, checked twice, never enforcement

The background-job registry resolves per call (`ctx.get('jobs')`); a composition without one refuses instead of assuming quiet. Any `running` or `stopping` job of the caller refuses the commit, and the gate runs again after the HEAD observation so a job appearing mid-flight still refuses. The tool never kills jobs. The per-task serial chain excludes only the commit/deliver/review family — the job gate is instant evidence, not an operating-system lock; a writer racing the second check surfaces through the Service's own verification or the delivery gate.

### Uncertainty is reported, not classified

A post-commit non-clean tree is a success result whose text names the remaining changes as unverified; delivery still requires a fully clean tree. Erroring there would poison retries with a moved expected HEAD.

## Alternatives considered

- **Dirty-set cross-check as authorization** (the first draft equalled requested paths against `git status` output): rejected — equality proves nothing about ownership, and the readback itself executes checkout-controlled programs; the Config scope replaces it.
- **Observing HEAD through the Worker checkout**: rejected — the checkout owns its `.git` pointer and can redirect it; the owner-side ref read is anchored outside the Worker's write boundary.
- **Injecting the jobs service into the delivery consumer**: rejected — every composition mounting the delivery consumer would have to mount a jobs registry; per-call resolution with an explicit refusal keeps absence loud without forcing the dependency.
- **Killing non-terminal caller jobs before committing**: rejected — destroys user work; refuse-and-retry preserves it.
- **A second loader namespace for the commit tool**: rejected — a separate serial chain would fork the quiescence ordering the commit must share with delivery.

## Consequences

Workers commit exactly the host-registered scope while the worktree stays theirs to write; forged identity, forged HEAD, redirected checkouts, and out-of-scope paths all refuse. What it cost: user edits to a scope path are indistinguishable from worker edits by path alone — the Config scope bounds the blast radius; a writer completing before the Service stages sweeps into the commit (still scope-bounded), and one completing between staging and the clean read lands in the unverified-pending face; compositions without a jobs implementation cannot commit at all. No recorded-session snapshot scenario ships with this slice: the A2 candidate chain's real full run is its acceptance evidence, and the snapshot is deferred until that composition settles.

## Verification

- `node node_modules/vitest/vitest.mjs run packages/experimental/project-controller/tests/commit-consumer.spec.ts` (22 cases) covers real-role authorization (forged arguments inert, non-assigned worker, non-developing task, authority-flip guard), the scope faces (missing, outside, nonexistent, directory, junction containment escape, grammar bounds), quiescence (missing registry, running, stopping, late job after the observation), the owner observation (stale-HEAD interference, vanished worktree row), and the two named counterexamples: a Worker `.git` pointer redirected to another registered worktree refuses with `does not belong`, and an interference commit between observation and Service call refuses with `expected HEAD`.
- `pnpm run gen-tool-catalog` regenerates `project_commit`'s schema; the catalog entry's registry stand-in carries the commit seam because the registration refuses providers without it.
