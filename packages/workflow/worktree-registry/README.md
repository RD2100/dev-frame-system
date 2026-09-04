---
description: "Per-workspace git worktree registry (ctx.worktreeRegistry) for hosts choosing, mounting, or debugging managed second checkouts of a workspace's repository."
kind: "package-reference"
---

# @deepseek-ai/dsh-worktree-registry

English | [中文](README.zh.md)

## Summary

`dsh-worktree-registry` gives a host a durable, per-workspace registry of git worktrees: second checkouts of a workspace's repository that the product created, tracked, and can remove again. With it, a consumer can create a clean or isolated checkout for one of its workspaces, list the checkouts that belong to each workspace across restarts, observe whether each checkout is clean and which branch it carries, and remove it — removal deletes the checkout through git and then the registration, never the other way round. The package is host-side only: the model, tools, and agent loop never see it, so it adds no tokens, prompts, or request context. It needs the workspace registry, a subprocess provider, and the storage rows mounted alongside it; setup is a few composition rows.

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
- **The registry is the authority for registrations.** `list` answers from durable rows; reconciling git's own metadata — including worktrees created outside the product — is the deferred prune's job.
- **Removal is git-first.** The durable row is deleted only after `git worktree remove` succeeded, so a failed removal never hides a real checkout.

### API behavior

The seam splits into the abstract `WorktreeRegistry` Service Definition and the `GitWorktreeRegistry` provider loaded by composition. Per-method contracts live in the code — see [src/registry.ts](src/registry.ts) and [src/git-provider.ts](src/git-provider.ts). The provider serializes its own mutations on one operation chain; row writes queue on the domain's write chain.

### Source map

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | Package entry: exports, the `WorktreeId` factory, default export of the provider |
| [`src/registry.ts`](src/registry.ts) | The abstract Service Definition and the `ctx.worktreeRegistry` key |
| [`src/git-provider.ts`](src/git-provider.ts) | Local git provider: config validation, git over `ctx.subprocess`, the four operations |
| [`src/spec.ts`](src/spec.ts) | Domain declaration: record schema and `defineDomain` spec |
| [`src/types.ts`](src/types.ts) | Public vocabulary: `WorktreeId`, request, worktree, and status types |

### Durable shape

The provider opens the `worktree_registry` domain (version 1): one `worktrees` table keyed by `WorktreeId`, with `workspaceId`, canonical `path`, observed `branch`, and ISO-8601 timestamps. There is no global state — the list order is derived from record fields on every read.

### Lifecycle

On start, the provider opens its domain and ties the handle's lifetime to its fiber. On disposal the domain closes, and the service is unmounted from the context, so a later composition boots over the stored rows from scratch. No bootstrap exists: a fresh domain is simply an empty registry.

### Failure and recovery

Unknown workspaces, non-git workspace directories, already-registered paths, and git's own refusals all reject with git's stderr attached; nothing is swallowed. The two-step remove has one acknowledged window — git removed the worktree but the row delete failed — which surfaces as a loud error naming both facts while `status` reports the missing directory.

### Invariant

No runtime invariant companion is published: the provider holds no second cache (reads resolve the durable table directly), the domain schema re-validates rows on reopen, and no independent observation exists that could diverge.

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [Worktree registry Agent Note](../../../.agents/notes/proposed/architecture/2026-09-05-worktree-registry.md) — the seam design: identity, durable-state ownership, session-event analysis, and the git command mapping including the deferred prune.
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
- **No prune** — a worktree whose directory vanished outside the product cannot be unregistered: `remove` fails loud naming the stale git metadata, and the row stays until prune lands with a reconciliation policy.
- **Remove needs its owner** — the owner workspace registration must still exist when a worktree is removed; deleting the workspace wedges its worktree rows' removal until the workspace is re-registered or the row is handled by the future prune.
- **External creations are invisible** — worktrees created outside the product never appear in `list`; seeing them requires the deferred reconciliation.
- **One removal failure window** — if the row delete fails after git removed the worktree, the row remains and reports a missing directory; recovery waits for prune.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
