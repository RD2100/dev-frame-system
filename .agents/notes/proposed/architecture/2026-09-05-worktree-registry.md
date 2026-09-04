# Agent Note: Per-workspace git worktree registry capability seam

Status: proposed

English | [中文](2026-09-05-worktree-registry.zh.md)

## Problem

An agent working inside a workspace needs second checkouts of the same repository: a clean tree to run the build while the workspace holds uncommitted work, an isolated tree for an experimental refactor, a parallel tree for a background task. Git already has the mechanism — linked worktrees — but nothing in the harness owns it:

- Every consumer would shell out through the shell capability and hand-parse `git worktree` output. No package records which worktrees exist, which workspace each belongs to, or which are safe to remove, so state lives only in the caller's conversation and dies with the session.
- Nothing ties a worktree to a `WorkspaceId`. The workspace entity is the product's anchor for "the directory the user works in"; worktrees are per-workspace facts, and a future model-facing surface needs that link to present and bound them.
- Nothing swaps the execution world. A worktree created through a sandboxed or remote provider must obey the same registry contract as a local one.

This note proposes the smallest seam that owns those facts: a per-workspace registry of git worktrees with create/list/status/remove, a local git provider, and a durable home for the rows.

## Proposal

New package `packages/workflow/worktree-registry` (`@deepseek-ai/dsh-worktree-registry`) combining the seam's roles in one package for this slice. It follows the `dsh-shell` template: an abstract Service Definition declares the interface, a concrete provider class implements it, and the package's default export is the provider the Loader mounts.

| Role | Element | Notes |
| --- | --- | --- |
| Service Definition | `WorktreeRegistry` (abstract, named export) | Declares create/list/status/remove, the record vocabulary, and the `ctx.worktreeRegistry` key. |
| Service Provider | `GitWorktreeRegistry` (default export) | Runs `git` through `ctx.subprocess` and owns the durable rows. One provider per context; a second registration fails loud through cordis' duplicate-service rule. |
| Consumer | none in this slice | The model-facing `worktree_*` tool and any host UI are the next change; the service API above is their stable base. Per docs/architecture.md a seam is complete only with a consumer, so the consumer surface is designed here (git mapping below) and deferred as one unit. |

### Identity

`WorktreeId = Branded<'WorktreeId'>` from `@deepseek-ai/dsh-brand`, minted as a generated uuid. The path is never the key: worktree paths are rewritten by normalization and by git itself, and a reference anchor must stay stable — the same rationale that gave `WorkspaceId` its uuid. The brand lives in this package because this package mints and consumes it.

### Durable state: an independent KvTable, not WorkspaceRecord

The registry opens its own storage domain `worktree_registry` (version 1) with one table `worktrees` keyed by `WorktreeId`. A record carries `workspaceId` (the owner anchor), `path` (canonical, from `fs.realpath` observed after `git worktree add` succeeds), `branch` (observed HEAD at create, not the caller's assumption), `createdAt`, and `updatedAt`.

Rows deliberately do not extend `WorkspaceRecord`:

- **Ownership cohesion.** Worktree lifecycle is git and workflow mechanics. The workspace domain answers "which sessions ran in this directory"; a worktree row answers "which second checkout exists for this workspace". Different questions, different writers, different evolution clocks.
- **Single-writer discipline.** `dsh-workspace` keeps one writer for its records — its registry. Hanging worktree rows off `WorkspaceRecord` would give a second package a write surface into another capability's durable format, or force every worktree change to route through the workspace registry.
- **Independent schema versioning.** The `worktree_registry` domain stamps its own version, so worktree format changes never bump the workspace domain and vice versa.

The cost is the absence of a cross-domain transaction: a create touches the workspace registry only for reads, and a remove touches only this domain plus git. The worktree row is the authority for registered state and git is the authority for worktree existence; no invariant spans both media, so no transaction is owed.

The `workspaceId` anchor is opaque to this package's schema — the validation that it names a real workspace happens in the operations through `ctx.workspaceRegistry` (below), which is the earliest resolvable point.

### Service surface

```ts
export type WorktreeId = Branded<'WorktreeId'>
export function WorktreeId(id: string): WorktreeId

export interface WorktreeCreateRequest {
  workspaceId: WorkspaceId   // owner anchor; resolved through ctx.workspaceRegistry
  path: string               // target checkout directory, any spelling; created by git
  branch?: string            // new branch name; omitted lets git derive it from the path
}

export interface Worktree {
  readonly id: WorktreeId
  readonly workspaceId: WorkspaceId
  readonly path: string      // canonical
  readonly branch: string    // observed HEAD branch at create time
  readonly createdAt: string
  readonly updatedAt: string
}

export interface WorktreeStatus {
  readonly directoryExists: boolean
  readonly branch?: string   // observed now; undefined when the directory is missing
  readonly clean?: boolean   // `git status --porcelain` empty; undefined when missing
}

export abstract class WorktreeRegistry extends Service {
  create(request: WorktreeCreateRequest): Promise<Worktree>
  list(workspaceId: WorkspaceId): readonly Worktree[]
  status(id: WorktreeId): Promise<WorktreeStatus>
  remove(id: WorktreeId, options?: { force?: boolean }): Promise<void>
}
```

Semantics every provider must honor:

- **create** resolves the owner workspace through `ctx.workspaceRegistry` and fails loud on an unknown `workspaceId`. It rejects a path this registry already holds, then runs git; git's own refusals (existing directory, already-checked-out branch, not a repository) propagate as descriptive failures. The returned record reflects observed facts — canonical path via `fs.realpath` after the directory exists, branch read back from the new worktree.
- **list** validates the workspace id the same way and returns that workspace's rows ordered by `createdAt` then id. It reads durable rows only; it does not shell out to `git worktree list`, because the registry — not the git metadata — is the authority for what this product registered. Reconciliation against git belongs to status and the future prune.
- **status** is the one observation surface: a missing directory reports `directoryExists: false` without invoking git (an observation, not a failure); a present directory reports the live branch and cleanliness and fails loud if git itself errors.
- **remove** runs `git worktree remove` (with `--force` when requested) and deletes the row only after git succeeded, so a failed remove never hides an existing worktree. A missing directory fails loud and names the stale git metadata, because un-registering it is prune's job and prune does not exist yet.

Registry mutations run on one operation chain inside the provider, and row writes go through the domain's write chain, so concurrent operations serialize exactly as in `dsh-workspace`.

### git command mapping

| Seam operation | git invocation | cwd |
| --- | --- | --- |
| create | `git worktree add [-b <branch>] <path>` | owner workspace path |
| list | none — durable rows are the answer | — |
| status | `git rev-parse --abbrev-ref HEAD`, `git status --porcelain=v1` | the worktree path |
| remove | `git worktree remove [--force] <path>` | the worktree path (a linked worktree resolves the shared repository itself) |
| prune | deferred | — |

`prune` is deliberately outside this slice. It is destructive against git's worktree metadata, and its registry half needs a policy this seam should not guess: whether pruning also drops rows whose directories vanished, and how the result is reported to a future consumer. It lands with the consumer change that first needs it.

### Session events: none in this slice

Nothing in this slice reaches a model request — no tool, no prompt injection, no model-visible rendering — so the model-visible-means-logged invariant adds no `SessionEventMap` member. When the consumer tool lands, its results are tool call/result events, which the session log already carries; no new event type is owed for that either. A new event becomes required only if worktree state must be reconstructable outside a tool exchange, for example a host UI card rendered from the log after replay; that decision belongs to the change that introduces the surface. Host-side change observation in the meantime rides `domain/changed` from the storage domain, which is process-local by design.

### Configuration

The provider's Config is a validated schemastery object with defaults, changeable from cordis.yml: `gitPath` (default `git`), `timeoutMs` (default 60000), `maxTimeoutMs` (default 600000), `graceMs` (default 3000), `maxOutputBytes` (default 64000). Validation refuses non-positive or non-finite values and a `graceMs` above the timer ceiling at construction — the pwsh-local pattern. No deployment-varying value is hardcoded outside these fields; git protocol constants (flag spellings) stay fixed.

### Composition

The provider declares `static inject = ['workspaceRegistry', 'subprocess', 'storageDomain']`: the workspace registry to resolve owner anchors, the subprocess seam for git, and the storage domain for rows. Because of the first injection, the provider mounts only where `dsh-workspace` mounts; this slice mounts it in the web-app bundle beside the workspace row. A composition that wants worktrees without workspaces cannot mount this provider — the correct failure is at activation, not a silently unanchored row. A remote or sandboxed provider would substitute its own execution world behind the same Definition and keep the registry contract.

## Alternatives considered

- **Hang the rows off `WorkspaceRecord`** (extend the workspace domain with a worktree list per workspace): rejected above in Durable state — cross-package write surface, coupled schema versions, and a second writer inside `dsh-workspace`'s one-writer record.
- **Spawn git with `node:child_process` directly**: rejected. The repository convention routes every spawn through `ctx.subprocess` (bounded output collection with spill, tree-scoped termination, scrubbed environment, deadline fusion); hand-rolling deletes those guarantees and duplicates their tests. `dsh-shell` and both executors spawn through the seam.
- **Key rows by path**: rejected — the path is rewritten by normalization, casing, and git itself; the stable anchor is a uuid, the same decision as `WorkspaceId`.
- **`list` shells out to `git worktree list --porcelain`**: rejected for this slice. The registry would then report facts it never recorded (worktrees created outside the product), which the consumer surface is not yet designed to present; the durable-row contract stays honest and prune/reconciliation arrives with a consumer that can state its policy.
- **Ship the model-facing tool in the same change**: rejected for scope. A tool brings schema, presentation, snapshot coverage, and the model-visible contract; folding it in would couple the storage and seam decisions to UI decisions. The four-method service is the stable base the tool consumes.
- **A session event per registry mutation**: rejected — nothing model-visible exists, and writing host-side state into every session log without a model consumer would put workspace-scoped facts under session ownership.

## Acceptance criteria

- Behavior tests cover create (observed canonical path and branch), list filtering and order, status clean/dirty/missing-directory, remove with and without `force`, and the fail-loud paths: unknown workspace, non-git workspace directory, duplicate registration, removing a dirty worktree without `force`.
- Disposal: disposing the provider's fiber closes the storage domain, and a later operation fails loud instead of silently reopening.
- A real Loader composition boots the provider beside `dsh-workspace`, and rows survive a cold restart over the json storage backend.
- `pnpm exec vitest run packages/workflow/worktree-registry` and `pnpm run typecheck` are green; no snapshot changes are owed because no model-visible surface exists.

## Risks

- **Two-step remove.** git removes the worktree, then the row is deleted; a storage failure between the steps leaves a row whose directory is gone. The failure surfaces as a loud error naming both facts, and status reports the missing directory — but recovery needs the future prune.
- **External deletion.** A user who deletes a worktree directory outside the product wedges `remove` until prune lands; the error says exactly that.
- **Remove from inside the worktree.** `git worktree remove` with the target as cwd relies on a linked worktree resolving the shared repository; if a git version refuses, the provider switches cwd to the owner workspace path — a provider-local fix, not a seam change.
- **Git output parsing stays minimal.** status reads `--porcelain=v1` emptiness and `rev-parse --abbrev-ref HEAD`; richer facts (locked, prunable, detached) are deferred so this slice never half-parses porcelain output it does not model.
