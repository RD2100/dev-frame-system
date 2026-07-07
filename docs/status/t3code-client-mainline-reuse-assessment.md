# T3Code Client Mainline Reuse Assessment

Date: 2026-06-24
Status: `assessment_recorded`

This note records the local T3Code reference inspection for the Local Agent
Control Plane visual-client direction. It is intentionally public-safe: the
reference checkout was inspected outside this repository and no T3Code source,
assets, lockfiles, or local runtime state were vendored into dev-frame-system.

## Scope

The user correction is part of the boundary: `/go` is the planner/reviewer
delegation loop for coding agents. It is not a product button and not the
client objective. The reusable client candidate is T3Code / T3 Code; the
devframe-owned objective remains the Local Agent Control Plane.

Inspected reference:

| Project | Source | Revision | License | Local status |
|---|---|---:|---|---|
| T3 Code | `https://github.com/pingdotgg/t3code` | `4abf8b4` | MIT | Non-vendored local reference checkout; local bridge experiments were present but not imported here. |

## How To Run The Actual T3Code Client

T3Code has two practical run paths:

- Published user path: `npx t3@latest`, or install the desktop app from its
  release/package manager channel.
- Source development path: install Vite+ (`vp`), run `vp i`, then use the root
  scripts.

The root package is a pnpm/Vite+ monorepo. The useful source commands are:

```powershell
pnpm dev
pnpm dev:web
pnpm dev:server
pnpm dev:desktop
pnpm start
```

The root `dev` script delegates to `node scripts/dev-runner.ts dev`, which
starts the contracts, web app, and `t3` server in parallel. Its default
development ports are derived from:

- server: `T3CODE_PORT`, default base `13773`;
- web: `PORT`, default base `5733`;
- web-to-server URLs: `VITE_HTTP_URL` and `VITE_WS_URL`;
- runtime home: `T3CODE_HOME`, defaulting to the user's T3 data directory.

The packaged CLI is the `t3` package under `apps/server`; its `bin` points to
`dist/bin.mjs`. Source `apps/server/src/bin.ts` defines `t3`, `t3 start`,
`t3 serve`, `t3 auth`, `t3 project`, and conditional cloud connect commands.

## Likely Client Shell

The mainline reuse target is `apps/desktop` (`@t3tools/desktop`):

- it is the native T3 Code desktop client and the Codex-like wrapper around the
  embedded web shell;
- it packages the T3 experience as a standalone desktop/native client we should
  validate for acceptance;
- it is the primary product surface for T3 Code desktop/native client reuse.

`apps/web` (`@t3tools/web`) is the embedded reusable UI shell implementation
inside T3 desktop/web:

- it is the React/TanStack Router visual app;
- it owns the project, thread, session, terminal, diff, browser preview, and
  right-panel interaction surfaces;
- it consumes `@t3tools/client-runtime` state atoms and `@t3tools/contracts`;
- it can run separately with `pnpm dev:web` when pointed at a compatible
  backend through `VITE_HTTP_URL` and `VITE_WS_URL`.

`apps/server` (`t3`) is the native T3 runtime/server and the published CLI
package. It is valuable as a reference for transport, provider adapters, and
startup behavior, but it should not become the source of devframe governance
truth.

For the current devframe slice, the smallest good target is: validate
`@t3tools/desktop` as the mainline client wrapper, reuse `@t3tools/web` as its
embedded UI shell, feed it a devframe-owned read-only shell snapshot, and keep
writes behind devframe human gates.

## Reuse Directly

These T3Code surfaces are good direct reuse candidates, subject to normal
license and attribution review before any source import:

- Web client layout and interaction model for projects, threads, sessions,
  composer, model/provider selection, terminal drawer, diff views, browser
  preview, right panels, command palette, and keyboard ergonomics.
- `@t3tools/client-runtime` concepts for client-side connection/session state,
  durable subscriptions, shell/thread projections, and atom-based view state.
- `@t3tools/contracts` shapes as an adapter target for project/thread/shell
  snapshots, without treating them as devframe's canonical domain model.
- `apps/desktop` (`@t3tools/desktop`) as the native desktop wrapper around the
  embedded web shell; validate this as the mainline client surface.
- Launch/env wiring pattern from `scripts/dev-runner.ts`: deterministic ports,
  explicit `VITE_HTTP_URL`/`VITE_WS_URL`, isolated runtime home, and web-only
  mode.
- ACP/client protocol ideas from `packages/effect-acp` and provider-adapter
  ideas from `apps/server`, especially for future executor integration.

## Devframe-Owned Boundary

These must remain devframe-owned and must not be delegated to T3Code:

- `/go` planner/reviewer/coding-agent delegation semantics.
- Project contracts, task specs, allowed roots, memory policy, and role scope.
- Provider-neutral `DevFrameSession` and Local Agent Control Plane state.
- Evidence ledger, verification records, review verdicts, acceptance gates,
  safety gates, privacy gates, and release gates.
- Decision records: continue, revise, stop, escalate, or ask a human.
- Public-surface redaction rules and summary-only import behavior.
- Any write action from the visual client into local files, providers,
  terminals, browsers, or executors. Those actions need devframe policy and
  human-gate enforcement first.

The integration rule is: T3Code can render and route the client experience;
devframe owns the meaning, permissions, gates, and durable state.

## Bridge Shape

The local reference already showed a plausible bridge shape:

- start a devframe local read-only HTTP surface on loopback;
- expose `client-plan.json`, `client-manifest.json`, and `t3-shell.json`;
- launch T3 Web with `VITE_DEVFRAME_T3_SHELL_URL` and the normal T3
  `VITE_HTTP_URL`/`VITE_WS_URL` variables;
- project devframe state into T3-compatible projects, threads, and thread
  details;
- poll or subscribe read-only until a write-safe protocol exists.

That bridge should be generated or launched by devframe tooling, not manually
patched into a public T3Code checkout. A local fork or source import would need
the full `rules/open-source-reuse.md` RULE reuse-004 review first.

## Zero-config Acceptance

Zero-config acceptance should prove that a reviewer can inspect the product
surface without hand-editing T3Code env files or copying reference source into
this repository.

Minimum acceptance:

1. From `<repo-root>`, run one devframe command that starts the
   read-only Local Agent Control Plane endpoints and launches the T3
   desktop/native client pointing at the devframe shell snapshot.
2. The command prints the local URL, the source of the T3 shell snapshot, and
   confirms the desktop/native client launched successfully.
3. Opening the URL shows a DevFrame Local Agent Control Plane environment in
   T3's project/thread surface.
4. The first viewport includes project identity, active agent/session threads,
   evidence or gate status, and the next governed action.
5. The UI is read-only unless a devframe-owned human gate explicitly enables a
   write action.
6. A browser check confirms desktop and narrow viewport rendering with no
   page-level horizontal overflow.
7. A repo check confirms no external reference tree, submodule, generated
   runtime state, or vendored T3Code source entered the public repo.

Until devframe has a packaged launcher, an acceptable development probe can be:

```powershell
# terminal 1, from dev-frame-system
devframe dashboard --host 127.0.0.1 --port 8790

# terminal 2, from a non-vendored T3Code checkout
# primary acceptance path: desktop/native client
node devframe.t3desktop.mjs --shell-url http://127.0.0.1:8790/t3-shell.json

# auxiliary development fallback/probe: T3 Web shell
node devframe.t3web.mjs --shell-url http://127.0.0.1:8790/t3-shell.json
```

The production-quality acceptance target is a single devframe command that
wraps both steps, launches the T3 desktop/native client as the primary
acceptance surface, and keeps the T3 reference checkout outside the public repo.
T3 Web remains available only as an auxiliary development fallback/probe.

## Decision

Use T3Code mainline as the primary client reuse candidate. Validate
`@t3tools/desktop` as the native desktop/native client wrapper first; reuse the
embedded `@t3tools/web` shell inside it as the UI implementation, not as the
standalone mainline target. Keep devframe's Local Agent Control Plane as the
source of truth and adapt its read model into T3-compatible client snapshots.
This is the narrowest path that avoids hand-rolling another agent UI while
preserving devframe's review, evidence, and gate semantics.
