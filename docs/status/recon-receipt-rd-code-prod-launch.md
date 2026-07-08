# Recon Receipt — RD-Code production launch mode (startup + memory)

Status: ACCEPTED to proceed.
Domain: client runtime / desktop launch behavior (mature capability area →
recon gate required by `rules/recon.md`; reuse assessment required by
`rules/open-source-reuse.md`).
Date: 2026-06-29.

## Problem

RD-Code is launched via `scripts/launch-editor.ps1` →
`devframe client t3desktop` → `node devframe.t3desktop.mjs` → `pnpm dev:desktop`.

That is the upstream **Vite dev** path. It:

- recompiles the entire renderer on every launch (slow startup, ~1 minute by
  the script's own note), and
- keeps a Vite dev server plus file watchers and a dev-build Electron resident
  (high memory).

This is appropriate for editing the fork source, but it is the root cause of
the two reported product problems: slow startup and high memory use.

## Reuse assessment (open-source-reuse.md)

- **Production run path:** REUSE T3Code's own upstream production scripts
  `build:desktop` (`vp run --filter @t3tools/desktop --filter t3 build`) and
  `start:desktop` (`node scripts/start-electron.mjs`, which launches Electron
  against the prebuilt `apps/web/dist` renderer + `apps/desktop/dist-electron`).
  No new build system, no new Electron bootstrap. We only add a thin launcher
  that chooses build-once-then-start.
- **Env injection:** the existing DevFrame Vite variables (client plan /
  manifest URLs, polling realtime mode) are inlined at **build time** by setting
  them in the launcher child env before `build:desktop`. Same variables already
  used by the dev launcher; only the timing (build-time vs dev-server-time)
  differs, which is exactly how Vite expects `import.meta.env.VITE_*` to work.
- **Launcher generation:** REUSE the existing bridge bundle generator
  (`t3_bridge_bundle.py`) that already emits `devframe.t3desktop.mjs` /
  `devframe.t3web.mjs`; we add a sibling `devframe.t3desktop.prod.mjs` through
  the same `_write_bridge_files` path and schema. No new install mechanism.
- **CLI:** REUSE the existing `devframe client t3desktop` command; add an opt-in
  `--prod` flag selecting the prod launcher. Dev remains the default of the
  underlying command for backward compatibility; the user-facing
  `launch-editor.ps1` defaults to prod and exposes `-Dev` for fork development.

Conclusion: additive composition over T3Code's own production scripts and
DevFrame's existing bundle/CLI surface; no hand-rolled runtime layer.

## Safety contract

- No behavior change to the read-only / human-gate model: the production build
  loads the same renderer; the DevFrame bridge server (loopback 8788) is still
  started by `serve_t3_desktop_client`.
- The prod launcher only runs two upstream pnpm scripts (`build:desktop`,
  `start:desktop`) in the local checkout; it spends no tokens and makes no
  network mutations.
- `--prod` is opt-in; the default underlying command path is unchanged, so no
  existing automation regresses.

## Slices

- **Slice 1 (this turn, engine/public-repo, fully tested):**
  - `t3_bridge_bundle.py`: add `devframe.t3desktop.prod.mjs` launcher +
    `t3DesktopProdCommand` launch metadata + file entry; `render_t3_desktop_prod_launcher_source`.
  - `client_launcher.py`: `serve_t3_desktop_client(..., mode="dev"|"prod")`
    selects which launcher to run.
  - `cli/_client.py` + `_usage.py`: `--prod` flag.
  - `schemas/t3_bridge_bundle.schema.json`: allow `t3DesktopProdCommand`.
  - tests updated; full suite green (577 passed, 1 skipped).
- **Slice 2 (runtime, needs human relaunch + visual acceptance):**
  `scripts/launch-editor.ps1` defaults to `--prod`; a fresh production build was
  produced (with all current fork fixes baked in). User relaunches and confirms
  faster startup and lower memory.

## Acceptance

- Build once, then `start:desktop` opens the editor with no Vite dev server and
  no file watchers resident.
- `scripts/launch-editor.ps1` (no args) → production; `-Dev` → dev server;
  `-Rebuild` → force a fresh production build first.

## Follow-up fix — production showed "Connect an environment" (no projects)

First production launch landed on T3's hosted-static onboarding surface
("Connect an environment to get started") with an empty project list instead of
the native local editor.

Root cause: the bridge `environment` includes `VITE_HOSTED_APP_CHANNEL=nightly`.
`isHostedStaticApp()` returns `true` whenever a hosted channel is configured and
no backend URL is set. In dev that var is harmless because the dev server
injects `VITE_HTTP_URL` (a configured backend) which short-circuits the check;
the production build has no such backend URL, so the baked channel forced
hosted-static mode and hid the desktop's own spawned local server
(`apps/server/dist/bin.mjs`).

Fix: `render_t3_desktop_prod_launcher_source` strips `VITE_HOSTED_APP_CHANNEL`
from the build-time env (keeps the `VITE_DEVFRAME_*` vars). With the channel
unset, `isHostedStaticApp()` is `false`, the desktop boots its local backend,
and projects + the native editor return. The production app was rebuilt with
the corrected env.

Also removed the coordinator pane's top-right close button, which overlapped the
OS window controls (the "XX" in the user's screenshot). The coordinator is a
main-pane view; navigating away or pressing Escape closes it.

## Follow-up fix — `&` showed "No matching cluster target" in production

In the production desktop the `&` composer popup listed no targets. The backend
`GET /api/t3/cluster-targets` returned the roster correctly (verified via curl),
but the renderer's fetch was blocked.

Root cause: the production renderer is served from a custom Electron protocol
scheme, so its Origin is `t3code://app` (dev: `t3code-dev://app`), not a loopback
http origin. The dashboard's origin helpers (`_is_loopback_origin` for CORS echo,
`_loopback_origin_allowed` for the cluster-run POST gate) only accepted
http/https loopback origins, so the cross-origin GET was CORS-blocked (empty
list → "No matching cluster target") and the run POST would 403. In dev the
renderer ran at `http://127.0.0.1:5733`, which already passed.

Fix: trust the DevFrame-owned native client desktop origins
(`_DEVFRAME_DESKTOP_ORIGINS = {t3code://app, t3code-dev://app}`) in both origin
helpers. The loopback client-IP check (`_client_is_loopback`) remains the
primary boundary. This is a control-plane (Python) change only — no renderer
rebuild needed; the user relaunches so the dashboard restarts with the fix.
