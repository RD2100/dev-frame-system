# Recon Receipt: RD-Code bridge data completeness (M8.1)

> Governs write-capable work on the reused visual client (T3 Code fork = RD-Code)
> and the DevFrame T3 bridge, both mature capability domains, per `rules/recon.md`
> recon-001/002/003/005/009 and `rules/open-source-reuse.md`. Pairs with the
> roadmap (M8.1) and `docs/status/recon-receipt-t3-rebrand-i18n.md`.

## Target
- user_goal: Stop the RD-Code settings panels (Providers, Source Control,
  Archived threads, Connections) from spinning/blank forever when the client is
  pointed at the DevFrame read-only bridge.
- target_repo_or_kb: the local T3 Code checkout (RD-Code fork) at
  `.devframe-runtime/external/t3code/` (outside the public repo per reuse-005)
  and the DevFrame bridge code in `packages/control-plane/control_plane/`.
- current_slice_goal: M8.1 — make the bridge a "complete enough" read model so
  those panels resolve to honest content instead of infinite loading.
- requested_outcome: real read-only data where DevFrame has it; honest,
  localized "unavailable in read-only bridge mode" empty states where it does
  not. No fake green.
- date: 2026-06-26 | planner_agent_id: kiro

## Resource Map
- repository_roots: `d:\dev-frame-system` (public repo); the T3 fork lives in
  the gitignored `.devframe-runtime/external/t3code/`.
- bridge_service_entrypoints:
  - `packages/control-plane/control_plane/dashboard.py` — the loopback HTTP
    server (`do_GET`), serves `/t3-shell.json`, `/.well-known/t3/environment`,
    `/api/auth/session`, `/client-manifest.json`, etc.
  - `packages/control-plane/control_plane/t3_adapter.py` — projects DevFrame
    state into the T3 shell envelope (`build_t3_client_shell*`).
  - `packages/control-plane/control_plane/t3_bridge_bundle.py` — generates the
    bridge files installed into the T3 checkout (catalog/shell/threads patches +
    `devframeShellBridge.ts`).
  - `packages/control-plane/control_plane/client_launcher.py` — launch plan /
    endpoints.
- client_ui_entrypoints (fork, out of public repo):
  - `apps/web/src/connection/catalog.ts` — registers DevFrame as a primary
    environment (`devFrameConfig = readDevFrameShellBridgeConfig()`); fakes a
    `connected` supervisor state.
  - `apps/web/src/devframe/devframeShellBridge.ts` — `readDevFrameShellBridgeConfig()`
    (the authoritative bridge-mode signal: `VITE_DEVFRAME_T3_SHELL_URL` set) and
    the shell envelope fetchers.
  - panels: `components/settings/SettingsPanels.tsx`
    (`ProviderSettingsPanel`, `ArchivedThreadsPanel`),
    `components/settings/ProviderInstanceCard.tsx`,
    `components/settings/SourceControlSettings.tsx`,
    `components/settings/ConnectionsSettings.tsx`,
    `components/settings/providerStatus.ts`.
  - i18n catalogs: `apps/web/src/i18n/locales/{en,zh-CN}.ts`.
- state_storage_locations: DevFrame runtime state under `.devframe-runtime/`
  (outside repo); `build_visual_control_plane_state()` is the read model.
- license_files_found: T3 `LICENSE` (MIT) + `NOTICE.devframe.md` retained in the
  fork.

## Core Concepts / data flow (verified by inspection)
- The T3 client talks to a "primary environment" over two transports:
  - HTTP (REST) for a few endpoints (`GET /api/auth/session`, auth/pairing).
  - WebSocket RPC (`WS_METHODS.*`, `ORCHESTRATION_WS_METHODS.*`) for almost
    everything else, routed through `EnvironmentSupervisor.session`.
- The DevFrame bridge is HTTP-only and read-only: it serves `/t3-shell.json`
  (active projects/threads) and `/api/auth/session` (read scope), and has **no
  WebSocket server**. `catalog.ts` fakes a `connected` state, but there is no
  real session, so every WS-backed query/subscription never resolves.

## Capability Matrix (the 4 panels)
- Providers — `ProviderSettingsPanel` reads `primaryServerProvidersAtom`
  (WS subscribe `subscribeServerConfig`). location: SettingsPanels.tsx:1020 +
  ProviderInstanceCard.tsx:404 (`getProviderSummary`). maturity: WS-only.
  reusable_as_is: NO. DevFrame has governance provider *bindings*, NOT local
  CLI install/auth status — mapping one onto the other would be fake green.
- Source Control — `SourceControlSettingsPanel` reads
  `sourceControlEnvironment.discovery` (WS `serverDiscoverSourceControl`).
  location: SourceControlSettings.tsx:444. reusable_as_is: NO. The read-only
  bridge performs no server-side git/hosting discovery.
- Archived threads — `ArchivedThreadsPanel` reads
  `orchestrationEnvironment.archivedShellSnapshot` (WS
  `getArchivedShellSnapshot`). location: SettingsPanels.tsx:1466. reusable_as_is:
  NO. This is a *different* source from `/t3-shell.json` (which is the active
  snapshot); the bridge has no archived projection.
- Connections — `ConnectionsSettings` reads `usePrimarySessionState()`
  (HTTP `GET /api/auth/session`, already served, read scope) plus
  `authEnvironment.accessChanges` (WS `subscribeAuthAccess`). location:
  ConnectionsSettings.tsx:1976/2090. The HTTP session already reports
  `scopes: ["orchestration:read"]` (no write scope) so the web path hides
  access-management. Risk: under the Electron desktop bridge,
  `currentSessionScopes` becomes administrative and the WS `accessChanges`
  subscription would spin. Guard needed.

## Reuse Candidate List / Build-vs-Buy Decision
- must_reuse: T3 client + its existing empty-state primitives (`Empty*`,
  `SettingsRow`) and the existing `readDevFrameShellBridgeConfig()` signal +
  react-i18next catalogs. We add only thin bridge-mode branches.
- must_build_new: localized "read-only bridge" empty-state strings
  (`settings.bridge.*`) and four small bridge-mode guards in the fork.
- must_NOT_build: a fake provider/git/archived data projection. **Investigated
  and rejected**: DevFrame has no truthful read-only data for provider install
  status, server git discovery, or archived snapshots. Inventing it violates the
  "no fake green" rule. The honest M8.1 outcome is real data where it exists
  (none of these four) and honest empty states everywhere else.
- backend change: none required. `/api/auth/session` already returns read-only
  scopes; the shell envelope already carries the only real read-only data
  (active projects/threads). The fix is client-side honest empty states.

## Integration Risk Table
- risk: presenting honest empty states could read as "broken". type: ux.
  severity: low. mitigation: explicit localized copy naming "DevFrame read-only
  bridge mode" so the user understands it is intentional, not a failure.
- risk: editing the fast-moving T3 fork. type: maintenance. severity: medium.
  mitigation: changes are minimal, gated on `readDevFrameShellBridgeConfig()`,
  and confined to presentation; no client-runtime edits (AGENTS.md reuse rule).
- risk: vendoring T3 source into the public repo. type: license. severity: high.
  mitigation: ALL fork edits stay in `.devframe-runtime/external/t3code/`;
  dev-frame-system stores only this receipt. `verify-public-snapshot.ps1` green.

## Recommended Next Slice (this receipt unlocks)
- smallest_safe_increment: add `settings.bridge.*` strings (en + zh-CN); in the
  fork, branch the four panels on `readDevFrameShellBridgeConfig() !== null`:
  - ProviderInstanceCard: when no live provider, show localized read-only
    headline/detail instead of "Checking provider status…".
  - SourceControlSettingsPanel: skip the initial-scan skeleton; render a
    localized read-only empty section.
  - ArchivedThreadsPanel: skip the loading spinner; render localized read-only
    empty copy.
  - ConnectionsSettings: guard the `accessChanges` WS subscription with
    `&& !bridge` so it never spins under the desktop bridge.
- worker_type_needed: planner-implemented presentation change + reviewer.
- files_in_scope: the four fork panels + `i18n/locales/{en,zh-CN}.ts`; this
  receipt.
- files_out_of_scope: client-runtime; public dev-frame-system source; any new
  backend endpoint (none needed).
- evidence_required_for_completion: `pnpm --filter @t3tools/web typecheck`
  (changed files clean; the 3 pre-existing bridge errors are baseline);
  `python -m pytest -q` green; `scripts/verify-public-snapshot.ps1` exit 0;
  independent review; user click-through confirms no infinite spinners.
- review_gate_definition: reviewer confirms (1) no fake data, (2) honest
  localized copy, (3) no client-runtime edits, (4) no T3 source vendored.
