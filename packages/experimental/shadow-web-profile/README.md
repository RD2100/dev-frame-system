---
description: "Add the resident Shadow entry card to a source-checkout Web profile beside the Shadow status controller."
kind: "package-bundle"
---

# @deepseek-ai/dsh-experimental-shadow-web-profile

English | [中文](README.zh.md)

## Summary

`dsh-experimental-shadow-web-profile` is the private Web layer for the [Shadow entry card](../client-ui-shadow-entry/README.md). Add it after `@deepseek-ai/dsh-web-app` to mount the resident sidebar entry. The card reads the `shadow` Remote namespace, so apply this layer beside a composition that also mounts the [shadow-controller](../shadow-controller/README.md) host row — the [DevFrame profile layer](../devframe-profile/README.md) carries it next to its shadow-router row. On a composition without the router the card still mounts and reads the honest not-mounted state. Official releases exclude this package, so it is available only from a source checkout.

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

From this repository checkout, add the Web Shadow layer to an initialized `web` profile whose composition also carries the DevFrame (or equivalent shadow-controller) layer:

```sh
pnpm dsh plugin --profile web add ./packages/experimental/shadow-web-profile
```

Removing the package with `dsh plugin --profile web remove @deepseek-ai/dsh-experimental-shadow-web-profile` removes the card and leaves the rest of the composition unchanged.

### What you get

The sidebar footer gains the resident Shadow entry above Settings. [`@deepseek-ai/dsh-experimental-client-ui-shadow-entry`](../client-ui-shadow-entry/README.md) owns the browser behavior and mounts the generated Remote namespace used to read the status.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

The package's runtime content is [`cordis.patch.yml`](cordis.patch.yml). Applied after `dsh-web-app`, its single `insert` entry adds the `ui-shadow-entry` row for `@deepseek-ai/dsh-experimental-client-ui-shadow-entry`. The inserted Client plugin owns the generated Remote assembly and the entry card; this static bundle holds no mutable state and installs no runtime invariant.

| File | Role |
|---|---|
| [`cordis.patch.yml`](cordis.patch.yml) | Ordered Web patch containing the `ui-shadow-entry` row |
| [`src/index.ts`](src/index.ts) | Empty module entry; the patch is the runtime content |
| — | No runtime invariant companion is published; the package carries only a static profile patch. The Remote assembly and entry card own their activation requirements. |

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [Experimental packages](../README.md) — incubation status and release exclusion.
- [Shadow Web entry](../client-ui-shadow-entry/README.md) — the card this layer mounts.
- [DevFrame profile layer](../devframe-profile/README.md) — the host composition carrying the shadow-router and shadow-controller rows.
- [Web bundle](../../bundle/web-app/README.md) — the stable browser layer this patch extends.

-----

<a id="model-experience"></a>
## Model Experience

None. This Web bundle adds no model request content; the Shadow domain has no model-facing face.

#### KV Cache effect

None — the bundle contributes no prompt, tool, or schema content.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

- **Ordered composition** — `dsh-base`, `dsh-web-app`, the shadow-controller host layer (DevFrame profile or equivalent), and this package must remain in that order.
- **Source-checkout only** — official CLI, Web, npm, and Python release payloads exclude this private package.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
