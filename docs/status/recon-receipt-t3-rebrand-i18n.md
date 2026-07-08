# Recon Receipt: RD-Code rebrand + i18n (T3 client fork)

> Governs write-capable work on the reused visual client (T3 Code), a mature
> capability domain, per `rules/recon.md` recon-001/003/005/009,
> `rules/open-source-reuse.md` reuse-000/001/002/004/005, and
> `docs/agent-runtime/reuse-depth-review-method.md`. Pairs with the roadmap (M6).

## Target
- user_goal: Ship a product editor ("RD-Code") that is the T3 Code client, fully
  rebranded away from T3 trademarks, with real multi-language support (Chinese +
  English) via a reusable i18n framework, maintained as a fork with incremental
  string coverage (first-screen first).
- target: the local T3 Code checkout at
  `.devframe-runtime/external/t3code/` (outside the public repo per reuse-005).
- current_slice_goal: Phase 1 rebrand (RD-Code identity) + Phase 2 i18n
  framework (react-i18next) with en + zh-CN and first-screen coverage.
- date: 2026-06-26 | planner_agent_id: kiro | approval: human owner approved
  RD-Code, zh-CN+en, fork + incremental i18n, "start automated execution".

## Verified facts
- T3 Code version in checkout: **v0.0.28-nightly.20260623** (desktop 0.0.27),
  from github.com/pingdotgg/t3code, **MIT** (Copyright 2026 T3 Tools Inc.). Last
  commit a4964b3 (2026-06-23, PR #3527). Early 0.0.x, fast-moving.
- **No i18n exists**: a search of every non-node_modules package.json found no
  i18next/lingui/react-intl/formatjs dependency; UI strings are hardcoded in
  `.tsx`. So multi-language must be introduced.
- Branding is centralized: `apps/web/src/branding.ts` (`APP_BASE_NAME = "T3 Code"`)
  plus a desktop-injected `DesktopAppBranding` from `@t3tools/contracts` and the
  desktop app config (productName / appId / window title / icons).

## License / trademark assessment (reuse-004)
- MIT permits commercial use, modification, redistribution, sublicense, and sale.
  Obligation: retain the MIT copyright + permission notice in T3-derived files
  and ship the T3 LICENSE with attribution.
- MIT grants NO trademark rights. "T3", "T3 Code", "T3 Tools" and logos are not
  licensed. The rebrand to RD-Code is therefore both a product choice and a
  trademark-hygiene requirement before commercial distribution. Keep T3's MIT
  notice; remove T3 names/logos/marketing identity from the product surface.
- Before shipping binaries: audit bundled fonts/icons/deps for their own
  licenses (separate follow-up).

## Capability Matrix / Reuse decision (recon-003, reuse-000/001)
- i18n framework
  - reuse candidate: **react-i18next** (+ i18next). Mature, most-adopted React
    i18n, runtime catalogs, language switch/detection, lazy namespaces. Adding a
    language = adding a catalog file.
  - rejected: hand-rolled string map (violates reuse-000; no plural/format,
    poor scale); Lingui (great DX but compile-time extraction macro adds build
    coupling on a vite-plus toolchain we do not control); react-intl (heavier
    API, ICU-first) — react-i18next is the lowest-friction reuse here.
  - decision: REUSE react-i18next; DevFrame/RD-Code owns only the catalogs +
    a thin init + a language switch wired to T3's existing settings.
- visual client: REUSE T3 Code wholesale (reuse-002/003); we own branding,
  catalogs, and a minimal layout-differentiation layer.

## Build-vs-Buy
- must_reuse: T3 Code client; react-i18next for i18n.
- must_build_new: RD-Code branding values/assets; en + zh-CN catalogs; i18n init
  + language switch; first-screen string migration; a reproducible patch/manifest.
- rationale: standing on a proven client + a proven i18n lib; we own only
  identity + translations + a thin switch.

## Integration Risk Table
- risk: fork divergence from a fast-moving upstream (0.0.x, "not accepting
  contributions").
  - severity: medium | mitigation: keep changes minimal and centralized
    (branding module, one i18n init, catalogs, targeted `t(...)` swaps); record a
    patch manifest in dev-frame-system; coverage is incremental and first-screen
    first.
- risk: vendoring T3 source into the public repo (reuse-004/005 violation).
  - severity: high | mitigation: ALL edits live in the t3code checkout outside
    the public repo; dev-frame-system stores only this receipt + a file manifest,
    never T3 source. `verify-public-snapshot.ps1` must stay green.
- risk: i18n incomplete coverage presented as complete.
  - severity: medium | mitigation: honestly scoped as first-screen first; the
    language switch flips covered strings; uncovered strings fall back to English
    (i18next default) and are migrated incrementally.
- risk: adding a dependency requires network install in the T3 workspace.
  - severity: low | mitigation: `pnpm add` in apps/web; verify with typecheck +
    web build.

## Recommended slices (this receipt unlocks)
- Phase 1: rebrand RD-Code (web branding.ts default + desktop branding/productName/
  appId/window title + marketing identity), keep MIT notice; pick an accent that
  matches T3's clean light aesthetic.
- Phase 2: add react-i18next; init + `en`/`zh-CN` catalogs + a settings language
  switch; migrate first-screen strings (titlebar, sidebar, search, empty state,
  settings labels).
- files_in_scope: t3code checkout `apps/web` (branding, i18n, first-screen
  components), `apps/desktop` (branding/identity); dev-frame-system docs only.
- files_out_of_scope: the public dev-frame-system source (no T3 vendoring);
  full string coverage (incremental); deep theme/layout rework (Phase 3).
- evidence_required: T3 web typecheck + build pass; app launches; language switch
  visibly flips first-screen between zh-CN/en; RD-Code identity shown; MIT notice
  retained; `verify-public-snapshot.ps1` green; independent review.

## Deferred (Phase 3+)
- Full string coverage; theme/color + layout differentiation; bundled-asset
  license audit before binary distribution; reproducible patch-bundle automation
  in the DevFrame client-launcher.

## Result (Phase 1 + Phase 2 foundation done)
- **Rebrand (Phase 1):** display identity is RD-Code — `DesktopEnvironment.ts`
  `APP_BASE_NAME`, web `branding.ts` fallback, desktop `productName`, `index.html`
  title + splash labels, and the startup error dialog. Storage dir names left
  unchanged (no user-data migration). T3's MIT `LICENSE` retained; added
  `NOTICE.devframe.md` (attribution + trademark note). Fork tests updated
  (`branding.test.ts`, `DesktopAppIdentity.test.ts`).
- **i18n (Phase 2):** reused **react-i18next** + **i18next** (installed into
  `apps/web`); added `apps/web/src/i18n/` (init + `en` + `zh-CN` catalogs +
  `setLanguage`/`getLanguage` with localStorage persistence + zh auto-detect);
  wired init in `main.tsx`; added a **Language switch** (English / 中文) in
  Settings → General; migrated the first-screen empty state
  (`NoActiveThreadState`) to `t(...)`. Adding a language = add one catalog file.
- **Verification:** `pnpm --filter @t3tools/web typecheck` shows my changed
  files (i18n, branding, NoActiveThreadState, SettingsPanels, main) are
  error-free. The only remaining typecheck errors are 3 PRE-EXISTING ones in
  files this work never touched (`ChatView.tsx`, `connection/catalog.ts`,
  `state/threads.ts`) — they originate from the earlier DevFrame↔T3 bridge
  patches and do not block the vite dev launch. Honest note: those 3 are a
  separate pre-existing issue in the bridge integration, not introduced here.
- Visual acceptance (reuse-006) is the user's click-through: relaunch the
  RD-Code editor, open Settings → General → Language, switch English/中文, and
  confirm the first-screen empty state flips.

## Follow-up round (post first acceptance)
- Root cause of "sidebar still shows T3 Code": the sidebar brand was a hardcoded
  `<T3Wordmark/>` SVG logo + literal "Code" text in `Sidebar.tsx`, NOT the
  `APP_BASE_NAME` constant. Replaced with a two-tone "RD-Code" text wordmark
  (the T3 logo SVG is no longer rendered — trademark hygiene; the now-unused
  `T3Wordmark` function is a dead-code cleanup follow-up).
- Expanded i18n coverage (still incremental, first-screen-out): sidebar chrome
  (Search / Projects / Show more / Settings), Settings header title, and Restore
  defaults are now localized with en + zh-CN. Verified: all changed files
  typecheck clean (only the 3 pre-existing bridge errors remain).
- HONEST scope: comprehensive coverage is still a large ongoing pass — most
  Settings rows, the command palette, chat surface, and dialogs remain English
  and fall back to English until migrated screen-by-screen.

## Settings module fully localized (per user request to do whole visible modules)
- Settings left-nav tabs (General/Keybindings/Providers/Source Control/
  Connections/Archive) + Back (`SettingsSidebarNav.tsx`).
- General panel (`SettingsPanels.tsx`): section titles (General/About), every
  row title + description, and the Theme / Time format / New threads dropdown
  display + item labels, plus Diagnostics / version description / View
  diagnostics. All via en + zh-CN catalogs.
- Verified: all changed files typecheck clean (only the 3 pre-existing bridge
  errors remain). Remaining English in Settings is limited to a few aria-labels
  and the text-generation model picker internals (non-primary text).
