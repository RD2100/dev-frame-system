# Agent Note: desktop-host boots through the materialized profile fallback, not the upstream runtime PluginPackages hook

Status: implemented

English | [中文](2026-09-19-desktop-host-materialize-profile-fallback.zh.md)

## Problem

`apps/desktop-host/src/index.ts` was copied verbatim from upstream, but this repo has not ported upstream's `profile-resolution` module. Two imported names the file relied on do not exist in `@deepseek-ai/dsh-app-boot`:

- `createProfileResolutionGeneration` (imported at the top of the file)
- `PluginPackages` (a Cordis service plugin mounted in the `boot` prepare callback)

A third hard prerequisite was also missing: `src/index.ts` resolves `../config/desktop.cordis.patch.yml` through `loadOverlayPatches`, which throws on a missing file, yet the entire `apps/desktop-host/config/` directory did not exist.

Porting upstream's resolver verbatim is blocked at runtime: `resolver.ts` top-level `require('node-addon-require-builtin')`. That native addon is a legal dependency of `apps/cli`, but it is outside `app-boot`'s resolution scope (absent from the root `node_modules` top level and from `app-boot`'s declared dependencies), and the repo's `allowBuilds` list explicitly forbids building it. The type side resolves fine (vendored `loader` exports the loader types), so a verbatim port would pass typecheck and then die on `MODULE_NOT_FOUND` at first boot.

## Decision

Option B — keep `packages/boot/app-boot` untouched and rewrite desktop-host onto this repo's existing materialized path:

- Drop the two unported imports (`createProfileResolutionGeneration`, `PluginPackages`) and their sole usage points (the `createProfileResolutionGeneration({...})` call and `hostCtx.plugin(PluginPackages, { generation })`).
- Call the already-exported `healProfilesModuleFallback({ installAnchor, profile })` immediately before `boot(...)`. This materializes the shared dependency closure under `$DSH_HOME/profiles/node_modules` and the bundle-only links into the profile's `node_modules` (the Electron `projectDir`), so the Loader can resolve bare bundle plugin names off `ctx.baseUrl`. The call order matches the original resolution-hook site: both run before `boot`.
- Restore `apps/desktop-host/config/desktop.cordis.patch.yml` verbatim from upstream. Every `insert` row uses a bare workspace package name (`@deepseek-ai/dsh-host-directory-picker-native`, `@deepseek-ai/dsh-client-ui-directory-picker-native`), both already in `apps/desktop-host/package.json` dependencies, so no path rewrite is needed.

The boot prepare callback drops its `async` modifier once the only `await` (`hostCtx.plugin(...)`) is gone; `boot`'s `prepare` parameter accepts `(ctx) => Promise<void> | void`.

## Alternatives considered

**Port upstream `profile-resolution` verbatim (Option A).** Rejected on three grounds: (1) runtime hard block — `node-addon-require-builtin` is outside `app-boot`'s resolution scope and the repo forbids building it, so the port would move the P0 from "import mismatch" to "native module unresolvable"; (2) boundary risk — upstream has already diverged `healProfilesModuleFallback` to return a generation table instead of materializing to disk, and realigning it would disturb the currently-green `profile.spec.ts` / `app-boot.spec.ts` surface; (3) no downstream consumer — a repo-wide grep shows `PluginPackages` / `ctx.pluginPackages.packageOf` has exactly one caller, the desktop-host file itself.

## Consequences

Bought: desktop-host boots through this repo's existing symlink-materialization path, the same one the CLI profile launcher already uses. `$DSH_HOME/profiles/node_modules` symlinks are a pre-existing launcher side effect, not a new disk pattern.

Deferred (recorded here, not done): upstream chose the runtime hook to avoid disk writes inside a packaged executable. This repo's desktop-host is a plain Node child process spawned by Electron (`isPackagedExecutable()` is false), so materialization is correct today. If a future packaged release makes `~/.dsh` read-only and bundle-only plugin resolution fails, the work is to add `node-addon-require-builtin` as a second native addon under `native/` and port the four resolver files verbatim.

## Local deviation in the overlay yml

The restored `desktop.cordis.patch.yml` drops two rows that upstream ships preemptively disabled:

- `id: open-in-app / disabled: true`
- `id: ui-open-in-app / disabled: true`

This repo's base composition does not contain either entry (these packages are not shipped locally). `composeEntries` warns "entry not found" for disabled rows whose target id is absent from the base, polluting the otherwise clean overlay. The two rows are removed as a deliberate local deviation from the verbatim upstream copy, following the same P0.2 principle that internal references be rewritten to local reality. The remaining six disabled rows (`web-startup`, `webserver`, `web-runtime`, `client-hmr`, `directory-picker`, `connection`) target entries that do exist in the local base combination.

## Handler reconciliation (follow-up completed)

The verbatim `index.ts` carried two pre-existing interface divergences against this repo's already-evolved client packages, surfaced by `tsc --noEmit` but not by the P0 import mismatch. Both are now reconciled against the repo's real APIs:

- `requestBodyMode: () => 'buffered'` returned by `assetHandler` / `remoteStreamHandler` — removed. This repo's `ConnectionFetchHandler` (packages/client/connection rpc.ts:198) declares only `fetch(request)`, and its consumer (rpc-host.ts:123-129) never reads `requestBodyMode`.
- `ctx.clientModules.fetchBundle(request)` in `assetHandler` — removed. This repo's `ClientModuleRegistry` (packages/client/modules:585-588) registers `/plugins` as a webServer prefix route itself (`ctx.webServer.register({ kind: 'prefix', path: '/plugins', handler: this.serveBundle })`); the upstream `fetchBundle(request)` was the old manual byte-pipe forward, superseded by that webServer route. The asset handler now owns only dist static files; a comment records the delegation.
