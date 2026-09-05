---
description: "Composition smoke for the web client: mount one feature plugin over the jsdom bench's real slot, renderer, session, and locale stack, then assert the assembled surface."
kind: "package-library"
---

# @deepseek-ai/dsh-composition-smoke

English | [中文](README.zh.md)

## Summary

`dsh-composition-smoke` assembles the production client stack around one feature plugin. `mountComposition()` creates the [client test runtime](../client-runtime/README.md) bench — a real Cordis `Context`, the renderer-owned `SlotRegistry`, the UI renderer, and the `ui-session` adapter over typed Controller doubles — lets a spec provide the plugin's remaining services, and mounts the plugin on a live fiber. The smoke suite then asserts the assembled surface: slot-ledger registrations, the locale registry, and the rendered DOM. It is not part of the product plugin graph (no `dsh.client`); consumer packages depend on it in devDependencies only.

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

This package is the one-call assembly over the bench: mount a feature plugin, drive the composed surface, and dispose on one axis — with no second implementation of production logic.

### Mounting one composition

`mountComposition(plugin, options)` assembles the bench and mounts the plugin in one call. The `provide` callback runs between assembly and the mount, so the mount's service precheck sees every injected service: provide the plugin's remaining services on `runtime.ctx`, script Remote namespaces through `TestRemote`, pin the locale, or release a bench default the feature replaces (`releaseWorkspaceSource()` before a plugin that provides its own root workspace hook). The returned runtime is the [client test runtime](../client-runtime/README.md) bench — declare slots, render, and dispose through it:

```text
const runtime = await mountComposition({ inject, apply }, {
  provide: (bench) => {
    bench.releaseWorkspaceSource()
    // provide('locale', ...), new TestRemote(bench.ctx, { ... })
  },
})
await runtime.declare({ 'feature-slot': {} })
const view = runtime.renderSlot('feature-slot', owner)
await runtime.dispose()
```

### What can go wrong

- **A declared service is not provided** — the mount precheck fails loud with the missing names; provide them in `options.provide`.
- **A root-hook provider mounted over the bench default** — call `releaseWorkspaceSource()` in `provide` first; the bench installs its workspace hook at assembly time, before any plugin fiber starts.

-----
<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design of the assembler; the observable behavior is fully covered in [Use this package](#use-this-package).

### Design

The package copies no production or bench logic: it orders the calls the composition needs — bench assembly, spec-owned service provisioning, the mount's fail-loud service precheck, then the live fiber — behind one function whose return value is the already-documented bench.

### Source map

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | `mountComposition` assembly and the `provide` customization point |
| — | No runtime invariant companion is published; this test-support package owns no production event stream or mutable data; consuming smoke suites exercise the assembled surface. |

### Lifecycle

`mountComposition` awaits bench assembly, runs the `provide` callback, and awaits the plugin fiber through the bench's act wrapper. Disposal stays on the bench: `runtime.dispose()` unmounts views, disposes feature fibers, releases registrations, and clears persisted state, idempotently.

</details>

-----
<a id="further-exploration"></a>
## Further Exploration

- [client-runtime](../client-runtime/README.md) — the bench this package assembles and the doubles it exposes.
- [Testing policy](../../../docs/testing.md) — the coverage tiers the assembled smoke complements.
- [Test-support group map](../README.md) — sibling harnesses and support packages.

-----
<a id="model-experience"></a>
## Model Experience

None, as this package is browser-side test infrastructure; nothing here reaches a model request.

#### KV Cache effect

None; this package neither assembles nor sends a provider request.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

- **Vitest and jsdom only** — the composition runs the same in-process bench as the client test runtime; wire carriage, real Host answers, and browser-grade behavior stay in the browser snapshot lane.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
