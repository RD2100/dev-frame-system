---
description: "Private DevFrame profile layer over the web profile, for source-checkout users who want the hierarchy stack: session identity, shadow routing, project memory, goal binding, and dispatch."
kind: "package-bundle"
---

# @deepseek-ai/dsh-experimental-devframe-profile

English | [中文](README.zh.md)

## Summary

`dsh-experimental-devframe-profile` is a private profile layer that mounts the DevFrame stack over the web profile (`dsh-base` + `dsh-web-app`). Its patch inserts the session-identity, shadow-router, project-memory, and command-goal-binding rows plus the three-role agent-hierarchy policy and the agent-dispatch consumption face. Add it explicitly to an initialized source-checkout profile; official releases exclude this package.

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

### Install into a profile

From this repository checkout, apply the layer as one more `--patch` overlay over the web profile, then run a task that asks the controller to dispatch a lead:

```sh
pnpm dsh --profile web --patch ./packages/experimental/devframe-profile/cordis.patch.yml --no-open
```

The profile must already contain the web bundle layers, whose webserver row this layer leaves untouched. A deployment narrows the safe machine-neutral defaults through a later `--patch` overlay (authorizedRoots, vaultRoot, shadowSessionId, workspace identity), not by editing this file.

This layer's patch inserts its six rows; it does not target existing rows. Do not also mount these rows through their own package layers (for example `dsh plugin --profile <name> add @deepseek-ai/dsh-experimental-project-memory`): two inserts of one row id fail the boot with a duplicate-id loader error. Narrow a row's defaults with a later id-targeted `--patch` entry (`- id: project-memory, config: …`) instead — a patch entry replaces the target row's whole configuration, with the last write winning per row; the [base bundle README](../../bundle/base/README.md) owns the override semantics.

### What you get

The layer inserts the identity, routing, memory, and goal-binding rows with unconfigured, read-only defaults: shadow-router installs no `project_*` tools until authorized roots are declared, and project-memory keeps its tools read-only until a real vaultRoot is supplied. The hierarchy row starts the worker face empty (fail closed) and preallocates no lead plugin scopes; the dispatch row mounts the `agent_dispatch` consumption face.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

The package's runtime content is [`cordis.patch.yml`](cordis.patch.yml). Applied after the web bundle layers, the patch inserts the six rows above with their safe defaults; it configures nothing else.

| File | Role |
|---|---|
| [`cordis.patch.yml`](cordis.patch.yml) | Ordered patch over the web profile |
| [`src/index.ts`](src/index.ts) | Empty module entry; the patch is the runtime content |
| — | No runtime invariant companion is published; the package carries only a static profile patch. The mounted packages own the mutable relationships it activates. |

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [Experimental packages](../README.md) — incubation status and release exclusion.
- [Agent dispatch](../agent-dispatch/README.md) — the consumption face this layer mounts.
- [Agent hierarchy](../agent-hierarchy/README.md) — the role policies and plugin scopes this layer configures.

-----

<a id="model-experience"></a>
## Model Experience

### DevFrame rows

#### What the model sees

The model-visible faces belong to the mounted packages: the `project_*` tools to shadow-router, the memory tools to project-memory, `/devframe-start` and its goal commands to command-goal-binding, and `agent_dispatch` to agent-dispatch. This bundle changes composition only; it adds no prompt text or tool schema of its own.

#### Token effect

The bundle adds whatever prompt text and schemas the six mounted rows contribute; it adds none itself.

#### KV Cache effect

The bundle's composition is prefix-stable while its patch and the mounted rows' configs remain unchanged.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

- **Source-checkout only** — this private package is not present in official npm, CLI, Web, or Python release payloads.
- **Web profile required** — the patch depends on row ids supplied by the web bundle layers; it is not a standalone profile.
- **Fail-closed defaults** — shadow-router, project-memory, and the worker tool face stay inert until a deployment configures them; this layer ships no preconfigured roots, vault, or scopes.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
