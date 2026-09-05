---
description: "Per-workspace git worktree registry (ctx.worktreeRegistry) for hosts choosing, mounting, or debugging managed second checkouts of a workspace's repository."
kind: "package-reference"
---

# @deepseek-ai/dsh-worktree-registry

English | [中文](README.zh.md)

## Summary

`dsh-worktree-registry` gives a host a durable, per-workspace registry of git worktrees: second checkouts of a workspace's repository that the product created, tracked, and can remove again. With it, a consumer can create a clean or isolated checkout for one of its workspaces, list the checkouts that belong to each workspace across restarts, observe whether each checkout is clean and which branch it carries, remove it — removal deletes the checkout through git and then the registration, never the other way round — and reconcile the registrations against what `git worktree list` reports. The package is host-side only: the model, tools, and agent loop never see it, so it adds no tokens, prompts, or request context. It needs the workspace registry, a subprocess provider, and the storage rows mounted alongside it; setup is a few composition rows.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Further Exploration](#further-exploration)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Use this package when the product manages second checkouts of a workspace's repository — a clean tree to build in while the workspace holds uncommitted work, an isolated tree for an experiment, a parallel tree for background work. The package registers and tracks those checkouts; it is invisible to the model and adds no token or request cost. Skip it when the product never creates worktrees; nothing else in the harness needs it.

### When to use it

The provider declares hard injections on `ctx.workspaceRegistry`, `ctx.subprocess`, and `ctx.storageDomain`, so it mounts only in compositions that also mount the workspace stack — the web-app bundle mounts it beside the workspace row. A composition that wants worktrees without workspaces fails at activation rather than silently storing unanchored rows.

### Setting up

The provider takes an optional Config with five validated fields — `gitPath`, `timeoutMs`, `maxTimeoutMs`, `graceMs`, `maxOutputBytes` — whose defaults serve local git. A minimal web-layer composition:

```yaml
- name: '@deepseek-ai/dsh-storage'
- name: '@deepseek-ai/dsh-storage-json'
  config:
    root: dshHomePath('storages')
- name: '@deepseek-ai/dsh-storage-domain'
  config:
    backend: json
- name: '@deepseek-ai/dsh-workspace'
- name: '@deepseek-ai/dsh-worktree-registry'
```

Every git invocation goes through the mounted `ctx.subprocess` provider; the base bundle's `@deepseek-ai/dsh-subprocess-local` supplies it. The rows live in the `worktree_registry` storage domain and survive restarts.

### Creating and inspecting worktrees

Create a worktree for a workspace: give the workspace id and the target directory, and the package runs `git worktree add` from the workspace directory, records the canonical path and the branch git actually created, and returns the registration. Inspect it at any time; a checkout whose directory was deleted outside the product reports `directoryExists: false` instead of failing:

```text
// Host consumer code, after the composition above is loaded:
const worktree = await ctx.worktreeRegistry.create({ workspaceId, path: '/path/to/wt' })
ctx.worktreeRegistry.list(workspaceId) // that workspace's registrations, stable order
await ctx.worktreeRegistry.status(worktree.id) // { directoryExists, branch, clean }
```

### Removing worktrees

Remove a registration when the checkout is no longer needed: the package runs `git worktree remove` first and deletes the durable row only after git succeeded. A checkout with modified or untracked files refuses to go without `force: true`, which passes `--force` to git. Removal never touches the workspace record or the repository's history.

### Reconciling registry and git

Registration rows and git's own metadata can drift apart: a directory deleted outside the product leaves a row without a checkout, a worktree deleted behind git's back leaves git tracking a dead path, and a worktree created outside the product is unknown to the registry. `reconcile(workspaceId)` compares the workspace's rows with `git worktree list` and reports the difference — `dangling` rows (`directory-missing` or `git-unknown`) and `unregistered` git-tracked worktrees — without changing anything:

```text
const report = await ctx.worktreeRegistry.reconcile(workspaceId)
// { dangling: [{ id, path, reason }], unregistered: [{ path, branch? }], removedRows: [], adoptedPaths: [] }
```

Two opt-in actions act on the report. `pruneRows: true` drops the dangling rows (never directories or files) and runs `git worktree prune` once when a dropped row's directory was missing, so git stops listing the dead admin entry. `adoptUnregistered: true` registers each unregistered worktree with its canonical path and the branch observed in it (`HEAD` when detached) — a repository's main worktree and any worktree already registered under another workspace are never adopted or reported. Detection is point-in-time and serialized with create/remove on the provider's operation chain.

### Failure kinds, retry semantics, and link shells

git refusals the provider recognizes are classified into four kinds; each error is a `WorktreeGitOperationError` carrying the invocation facts, git's stderr, and the remediation:

| Kind | git refuses because | Remediation the error carries |
|---|---|---|
| `path-exists` | the target directory exists and is not empty | choose a different target, or reuse or clear the existing one |
| `branch-conflict` | a branch with the requested name already exists | choose a different branch name, or reuse the branch without `-b` |
| `dirty-tree` | the worktree holds modified or untracked files | repeat the removal with `force: true`, or clean the worktree |
| `path-length` | the path exceeds this git configuration's path-length limit | choose a shorter path, or `git config core.longpaths true` |

Retry semantics: nothing auto-retries. A refused operation is deterministic — retrying without changing the parameters fails again. A failed attempt never leaves a registration row and never leaves a worktree behind (`remove` deletes its row only after git succeeded), so a corrected retry starts clean. On a `path-length` refusal git may leave empty leading directories on disk; the registry never records them and never deletes them.

Link-shell contract (symlinks and junctions): the registry never creates symlinks or junctions. Every path it records is canonicalized through `fs.realpath` after the directory exists, so a worktree reached through a junction or symlink spelling is registered under its physical target, and the same directory through two spellings is one registration — creating a worktree through the alias of an existing one fails as already registered instead of doubling. `reconcile` canonicalizes git-reported paths the same way before comparing, so metadata that stored a link spelling still matches its row. Windows path comparisons fold case; git's forward-slash output compares equal to the recorded backslash paths.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design decisions behind the feature and points at the code that realizes them; the observable behavior is fully covered in [Use this package](#use-this-package).

### Design philosophy

- **The uuid is the anchor, the path is a fact.** Worktree paths are rewritten by normalization and by git itself, so rows are keyed by a generated `WorktreeId` and store the canonical path observed after creation.
- **An independent domain, not a WorkspaceRecord field.** Worktree lifecycle is git mechanics, not workspace session accounting; the rows live in this package's `worktree_registry` domain, and the ownership link is a `workspaceId` field validated at operation time through `ctx.workspaceRegistry`.
- **Observed facts over assumptions.** The stored branch is read back from the new worktree, the stored path is the post-creation `fs.realpath`, and `status` reports only what git reports now.
- **The registry is the authority for registrations.** `list` answers from durable rows; where git's own metadata disagrees, `reconcile` reports the difference and repairs it only on request.
- **Reconcile is registry-side by default.** Dropping rows never deletes directories or files, and adopting never rewrites a worktree — the actions only bring the product's records in line with what already exists.
- **Removal is git-first.** The durable row is deleted only after `git worktree remove` succeeded, so a failed removal never hides a real checkout.

### API behavior

The seam splits into the abstract `WorktreeRegistry` Service Definition and the `GitWorktreeRegistry` provider loaded by composition. Per-method contracts live in the code — see [src/registry.ts](src/registry.ts) and [src/git-provider.ts](src/git-provider.ts). The provider serializes its own mutations on one operation chain; row writes queue on the domain's write chain.

### Source map

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | Package entry: exports, the `WorktreeId` factory, default export of the provider |
| [`src/registry.ts`](src/registry.ts) | The abstract Service Definition and the `ctx.worktreeRegistry` key |
| [`src/git-provider.ts`](src/git-provider.ts) | Local git provider: config validation, git over `ctx.subprocess`, the five operations |
| [`src/porcelain.ts`](src/porcelain.ts) | `git worktree list --porcelain -z` parsing and the reconcile path comparison |
| [`src/spec.ts`](src/spec.ts) | Domain declaration: record schema and `defineDomain` spec |
| [`src/types.ts`](src/types.ts) | Public vocabulary: `WorktreeId`, request, worktree, status, and reconcile types |

### Durable shape

The provider opens the `worktree_registry` domain (version 1): one `worktrees` table keyed by `WorktreeId`, with `workspaceId`, canonical `path`, observed `branch`, and ISO-8601 timestamps. There is no global state — the list order is derived from record fields on every read.

### Lifecycle

On start, the provider opens its domain and ties the handle's lifetime to its fiber. On disposal the domain closes, and the service is unmounted from the context, so a later composition boots over the stored rows from scratch. No bootstrap exists: a fresh domain is simply an empty registry.

### Failure and recovery

Unknown workspaces, non-git workspace directories, already-registered paths, and git's own refusals all reject with git's stderr attached; nothing is swallowed. The two-step remove has one acknowledged window — git removed the worktree but the row delete failed — which surfaces as a loud error naming both facts while `status` reports the missing directory; `reconcile` with `pruneRows` recovers the stale row.

### Invariant

No runtime invariant companion is published: the provider holds no second cache (reads resolve the durable table directly), the domain schema re-validates rows on reopen, and no independent observation exists that could diverge.

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [Worktree registry Agent Note](../../../.agents/notes/implemented/architecture/2026-09-05-worktree-registry.md) — the seam design: identity, durable-state ownership, session-event analysis, and the git command mapping including reconcile.
- [Worktree tools Agent Note](../../../.agents/notes/implemented/feature/2026-09-05-worktree-tools-and-reconcile.md) — the consumer package's authorization and schema decisions.
- [Capability seams](../../../docs/architecture.md) — the Service Definition / Service Provider / Consumer model this package follows (the "Capability seams" section).
- [Workflow package map](../README.md) — the group's packages and their repository positions.

-----

<a id="model-experience"></a>
## Model Experience

### Worktree registrations

#### What the model sees

Nothing. `ctx.worktreeRegistry` serves host-side consumers only: the package registers no tools, injects no prompts, and writes no session events, so no request field ever carries this package's data.

#### Token effect

Zero direct tokens on every request.

#### KV Cache effect

Independent of live requests: the package never touches a request prefix, so it cannot invalidate provider cache reuse.

## Known Limitations and Deferred Work

These limits define when the registry is a poor fit or needs special operational care. They are current package constraints, not a task backlog.

- **No consumer yet** — the model-facing `worktree_*` tool and any host UI are future work; the shipped composition mounts the provider, but nothing calls it, so the feature has no product surface beyond the service API.
- **Reconcile never deletes trees** — dropping rows and adopting registrations are the only actions; a worktree that should be physically deleted still goes through `remove` (or the user's own hands).
- **Remove needs its owner** — the owner workspace registration must still exist when a worktree is removed; deleting the workspace wedges its worktree rows' removal until the workspace is re-registered or the row is dropped through reconcile.
- **Adoption trusts git's list** — an adopted worktree records the branch observed in it; a detached HEAD is recorded as `HEAD`, and the registry does not resolve what the detached HEAD points at.
- **One removal failure window** — if the row delete fails after git removed the worktree, the row remains and reports a missing directory; a later `reconcile` with `pruneRows` recovers it.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
