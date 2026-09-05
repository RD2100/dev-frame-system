# Agent Note: Per-workspace git worktree registry capability seam

Status: implemented

English | [中文](2026-09-05-worktree-registry.zh.md)

## Problem

An agent working inside a workspace needs second checkouts of the same repository: a clean tree to run the build while the workspace holds uncommitted work, an isolated tree for an experimental refactor, a parallel tree for a background task. Git already has the mechanism — linked worktrees — but nothing in the harness owned it:

- Every consumer would shell out through the shell capability and hand-parse `git worktree` output. No package records which worktrees exist, which workspace each belongs to, or which are safe to remove, so state lives only in the caller's conversation and dies with the session.
- Nothing ties a worktree to a `WorkspaceId`. The workspace entity is the product's anchor for "the directory the user works in"; worktrees are per-workspace facts, and a model-facing surface needs that link to present and bound them.
- Nothing swaps the execution world. A worktree created through a sandboxed or remote provider must obey the same registry contract as a local one.

This note owns the seam that holds those facts: a per-workspace registry of git worktrees with create/bind/list/status/remove/reconcile, a local git provider, a durable home for the rows, and the model-facing consumer packages.

## Decision

Package `packages/workflow/worktree-registry` (`@deepseek-ai/dsh-worktree-registry`) hosts the Service Definition and the Service Provider; package `packages/workflow/tool-worktree` (`@deepseek-ai/dsh-tool-worktree`) is the workspace-facing Consumer and owns the [tool decisions](../feature/2026-09-05-worktree-tools-and-reconcile.md); the experimental package `packages/experimental/agent-worktree` is the per-agent Consumer that binds each created worktree to one writer and owns the [single-writer binding decisions](../feature/2026-09-05-per-agent-worktree-single-writer-seam.md). The registry follows the `dsh-shell` template: an abstract Service Definition declares the interface, a concrete provider class implements it, and the package's default export is the provider the Loader mounts.

| Role | Element | Notes |
| --- | --- | --- |
| Service Definition | `WorktreeRegistry` (abstract, named export) | Declares create/list/status/remove/reconcile, the record vocabulary, and the `ctx.worktreeRegistry` key. |
| Service Provider | `GitWorktreeRegistry` (default export) | Runs `git` through `ctx.subprocess` and owns the durable rows. One provider per context; a second registration fails loud through cordis' duplicate-service rule. |
| Consumer | `tool-worktree` | The workspace-facing `worktree_*` tools; see the [tools and reconcile Agent Note](../feature/2026-09-05-worktree-tools-and-reconcile.md) for the authorization and schema decisions. |
| Consumer | `agent-worktree` (experimental, private) | The per-agent `worktree_create`/`worktree_status`/`worktree_remove` tools over single-writer bindings; see the [binding Agent Note](../feature/2026-09-05-per-agent-worktree-single-writer-seam.md). |

### Identity

`WorktreeId = Branded<'WorktreeId'>` from `@deepseek-ai/dsh-brand`, minted as a generated uuid. The path is never the key: worktree paths are rewritten by normalization and by git itself, and a reference anchor must stay stable — the same rationale that gave `WorkspaceId` its uuid. The brand lives in this package because this package mints and consumes it. The single-writer binding marker is branded the same way (`WorktreeLockHolder = Branded<'WorktreeLockHolder'>`); the registry stores and compares it but never interprets it, so minting it stays the caller's decision.

### Durable state: an independent KvTable, not WorkspaceRecord

The registry opens its own storage domain `worktree_registry` (version 2) with one table `worktrees` keyed by `WorktreeId`. A record carries `workspaceId` (the owner anchor), `path` (canonical, from `fs.realpath` observed after `git worktree add` succeeds), `branch` (observed HEAD at create, not the caller's assumption), `createdAt`, `updatedAt`, and the optional `lockedBy`/`lockedAt` binding pair, which the record schema requires together — a binding is written and read as one fact. Version 2 added the binding pair; a medium stamped version 1 rejects at open per the pre-release stance, with no half-reads under the new schema.

Rows deliberately do not extend `WorkspaceRecord`:

- **Ownership cohesion.** Worktree lifecycle is git and workflow mechanics. The workspace domain answers "which sessions ran in this directory"; a worktree row answers "which second checkout exists for this workspace". Different questions, different writers, different evolution clocks.
- **Single-writer discipline.** `dsh-workspace` keeps one writer for its records — its registry. Hanging worktree rows off `WorkspaceRecord` would give a second package a write surface into another capability's durable format, or force every worktree change to route through the workspace registry.
- **Independent schema versioning.** The `worktree_registry` domain stamps its own version, so worktree format changes never bump the workspace domain and vice versa.

The cost is the absence of a cross-domain transaction: a create touches the workspace registry only for reads, and a remove touches only this domain plus git. The worktree row is the authority for registered state and git is the authority for worktree existence; reconcile is the explicit report-and-act step between the two media, and no invariant silently spans both. The `workspaceId` anchor is opaque to this package's schema — the validation that it names a real workspace happens in the operations through `ctx.workspaceRegistry`, the earliest resolvable point.

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
  readonly lockedBy?: WorktreeLockHolder  // present exactly with lockedAt
  readonly lockedAt?: string
}

export interface WorktreeStatus {
  readonly directoryExists: boolean
  readonly branch?: string   // observed now; undefined when the directory is missing
  readonly clean?: boolean   // `git status --porcelain` empty; undefined when missing
}

export interface WorktreeReconcileReport {
  readonly dangling: readonly WorktreeDanglingRegistration[]
  readonly unregistered: readonly WorktreeUnregisteredWorktree[]
  readonly removedRows: readonly WorktreeId[]
  readonly adoptedPaths: readonly string[]
}

export abstract class WorktreeRegistry extends Service {
  create(request: WorktreeCreateRequest): Promise<Worktree>
  bind(id: WorktreeId, holder: WorktreeLockHolder): Promise<Worktree>
  unbind(id: WorktreeId, holder: WorktreeLockHolder): Promise<Worktree>
  list(workspaceId: WorkspaceId): readonly Worktree[]
  status(id: WorktreeId): Promise<WorktreeStatus>
  remove(id: WorktreeId, options?: { force?: boolean }): Promise<void>
  reconcile(workspaceId: WorkspaceId, options?: WorktreeReconcileOptions): Promise<WorktreeReconcileReport>
}
```

Semantics every provider honors:

- **create** resolves the owner workspace through `ctx.workspaceRegistry` and fails loud on an unknown `workspaceId`. It rejects a path this registry already holds, refuses an explicit branch another worktree of the same workspace already holds (the classified `branch-conflict` kind, raised before git runs), then runs git; git's refusals are classified into the four typed failure kinds (occupied path, branch conflict, dirty tree, oversized path) with remediation text in the error. The returned record reflects observed facts — canonical path via `fs.realpath` after the directory exists, branch read back from the new worktree.
- **bind/unbind** maintain the single-writer binding: `bind` is idempotent for the current holder and refuses every other bind with `already-locked`; `unbind` refuses with `not-locked` when nothing is bound and `holder-mismatch` when another holder asks. Both return the fresh record, and refusals are `WorktreeLockError`s — product decisions, never git stderr.
- **list** validates the workspace id the same way and returns that workspace's rows ordered by `createdAt` then id. It reads durable rows only; it does not shell out to `git worktree list`, because the registry — not the git metadata — is the authority for what this product registered. Reconciliation against git is reconcile's job.
- **status** is the observation surface: a missing directory reports `directoryExists: false` without invoking git (an observation, not a failure); a present directory reports the live branch and cleanliness and fails loud if git itself errors.
- **remove** refuses while the worktree is bound — `force` never overrides the binding — then runs `git worktree remove` (with `--force` when requested) and deletes the row only after git succeeded, so a failed remove never hides an existing worktree. A missing directory fails loud and names reconcile's `pruneRows` action as the recovery for the stale row.
- **reconcile** diffs the rows against `git worktree list --porcelain -z` and only reports by default. `pruneRows` drops stale rows (a row whose directory vanished, or one git no longer tracks) together with their bindings — a binding guards a live checkout, not a vanished directory — and runs `git worktree prune` once when a directory-missing row was dropped, never deleting worktree files; `adoptUnregistered` registers git-tracked worktrees no row claims under any workspace, recording the branch git observes (`HEAD` when detached). The repository's main worktree and the reconciling workspace's own path are never reported as unregistered.

Registry mutations run on one operation chain inside the provider, and row writes go through the domain's write chain, so concurrent operations serialize exactly as in `dsh-workspace`.

### git command mapping

| Seam operation | git invocation | cwd |
| --- | --- | --- |
| create | `git worktree add [-b <branch>] <path>` | owner workspace path |
| list | none — durable rows are the answer | — |
| status | `git rev-parse --abbrev-ref HEAD`, `git status --porcelain=v1` | the worktree path |
| remove | `git worktree remove [--force] <path>` | the worktree path (a linked worktree resolves the shared repository itself) |
| reconcile | `git worktree list --porcelain -z`, `git worktree prune` (directory-missing rows only), `git rev-parse --abbrev-ref HEAD` (adoption) | the owner workspace path, or the adopted entry for its branch |

`git worktree prune` runs only as part of an opted-in `pruneRows` that actually dropped a directory-missing row, and it only removes git's own stale metadata — the registry never deletes worktree directories or files.

### Session events: none

Nothing in this seam reaches a model request beyond the ordinary tool call/result events the session log already carries, so `SessionEventMap` gains no member. The tools' results and errors are tool events; worktree state is reconstructable from those exchanges and from the durable rows. A new event becomes required only if worktree state must be reconstructable outside a tool exchange, for example a host UI card rendered from the log after replay; that decision belongs to the change that introduces the surface.

### Configuration

The provider's Config is a validated schemastery object with defaults, changeable from cordis.yml: `gitPath` (default `git`), `timeoutMs` (default 60000), `maxTimeoutMs` (default 600000), `graceMs` (default 3000), `maxOutputBytes` (default 64000). Validation refuses non-positive or non-finite values and a `graceMs` above the timer ceiling at construction — the pwsh-local pattern. No deployment-varying value is hardcoded outside these fields; git protocol constants (flag spellings) stay fixed. Exceeding `maxOutputBytes` on the porcelain listing fails loud instead of yielding a truncated reconcile.

### Composition

The provider declares `static inject = ['workspaceRegistry', 'subprocess', 'storageDomain']`: the workspace registry to resolve owner anchors, the subprocess seam for git, and the storage domain for rows. Because of the first injection, the provider mounts only where `dsh-workspace` mounts; the base bundle mounts it in the agent plane and the web-app bundle mounts it beside the workspace row with the consumer disabled. A composition that wants worktrees without workspaces cannot mount this provider — the correct failure is at activation, not a silently unanchored row. A remote or sandboxed provider would substitute its own execution world behind the same Definition and keep the registry contract.

## Alternatives considered

- **Hang the rows off `WorkspaceRecord`** (extend the workspace domain with a worktree list per workspace): rejected above in Durable state — cross-package write surface, coupled schema versions, and a second writer inside `dsh-workspace`'s one-writer record.
- **Spawn git with `node:child_process` directly**: rejected. The repository convention routes every spawn through `ctx.subprocess` (bounded output collection with spill, tree-scoped termination, scrubbed environment, deadline fusion); hand-rolling deletes those guarantees and duplicates their tests. `dsh-shell` and both executors spawn through the seam.
- **Key rows by path**: rejected — the path is rewritten by normalization, casing, and git itself; the stable anchor is a uuid, the same decision as `WorkspaceId`.
- **`list` shells out to `git worktree list --porcelain`**: rejected. The durable-row contract stays honest — the registry reports what it recorded — and the diff against git lives in the dedicated reconcile operation, where the policy for reporting and acting on outside-created worktrees is stated instead of leaking into list's answer.
- **Ship the model-facing tool in the same change as the seam**: rejected for scope. A tool brings schema, presentation, and the model-visible contract; folding it in would couple the storage and seam decisions to consumer decisions. The seam landed first, and the consumer landed as [`tool-worktree`](../feature/2026-09-05-worktree-tools-and-reconcile.md) on the stable base.
- **A session event per registry mutation**: rejected — the model sees registry state only through tool exchanges, which the session log already carries; writing host-side state into every session log without a model consumer would put workspace-scoped facts under session ownership.
- **Silent pruning inside remove** (drop a stale row automatically when the directory is gone): rejected. Removal of registry state stays explicit and opt-in inside reconcile, so a surprising directory disappearance is reported before anything is forgotten.

## Consequences

The seam gives the harness a durable, workspace-anchored worktree vocabulary that survives restarts, with the registry as the authority for what this product registered and git as the authority for what exists on disk. The model reaches it through the `worktree_*` tools without any new session event type. What it cost:

- **Two-step remove.** git removes the worktree, then the row is deleted; a storage failure between the steps leaves a row whose directory is gone. The failure surfaces as a loud error naming both facts, status reports the missing directory, and reconcile's `pruneRows` is the recovery.
- **Adoption trusts git's list.** `adoptUnregistered` registers whatever `git worktree list` reports outside the known rows, without human confirmation; a linked checkout of an unrelated repository could be adopted under the reconciling workspace.
- **Reconcile never deletes trees.** A dangling registration is dropped, but the directory behind an unregistered worktree is only ever adopted or reported; bulk cleanup of real checkouts stays a host decision.
- **Git output parsing stays minimal.** reconcile parses the `-z` porcelain listing into path/branch pairs and adoption reads `rev-parse --abbrev-ref HEAD`; richer facts (locked, prunable reasons beyond directory existence) are not modeled, so the parser never half-interprets fields it does not keep.

## Verification

- `pnpm exec vitest run packages/workflow/worktree-registry` covers create/bind/list/status/remove over the memory backend with real git subprocesses, the binding lifecycle and its refusal kinds, the reconcile agreement/detection/prune/adopt matrix, the four git failure dialects against captured stderr, and the Windows long-path refusal on win32 (`packages/workflow/worktree-registry/tests/`).
- Disposal closes the storage domain, and a later operation fails loud instead of silently reopening (`loader-composition.spec.ts`); rows survive a cold restart over the json storage backend.
- `pnpm run gen-cordis-catalog` keeps the generated Cordis API page fresh for the seven abstract methods.
