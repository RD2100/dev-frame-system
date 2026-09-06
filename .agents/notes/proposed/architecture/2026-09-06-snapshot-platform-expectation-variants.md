# Agent Note: Snapshot Platform Expectation Variants

Status: proposed

English | [中文](2026-09-06-snapshot-platform-expectation-variants.zh.md)

## Problem

The `minimal-preset` web snapshot scenario fails on Windows hosts with `unknown tool "bash"` (2 occurrences in the lib-mode snapshot run). The shipped minimal preset intentionally gates its persistent shells by platform — `persistent-bash` disabled on `win32`, its `persistent-pwsh` twin disabled everywhere else (the preset's own header states the design: "the persistent shell (`bash` on POSIX, `pwsh` on win32)") — while the scenario's authored corpus was recorded under POSIX semantics and its pinned `tool-schemas.expected.json` expects a `bash` tool card. The composition face and the expectation face drift apart per host platform, and the corpus — the single source of truth a replay is compared against — has no way to say "this dimension differs by platform". Evidence: `.agents/devframe/p22/shipped-profile-defects.md`, defect 2 (defect family B).

## Proposal

Add a scenario-level platform expectation configuration field to the snapshot scenario manifest: an optional root-level `expectations.variants` mapping in `snapshot.yml`, keyed by the platform families `win32` and `posix`, over the pinned sidecar kinds `system-prompt` and `tool-schemas`:

```yaml
expectations:
  variants:
    win32:
      - tool-schemas
```

- `parseSnapshotManifest` validates the field fail-loud: it is admitted only on a `header.pin: true` manifest, the platform keys and kind members are closed vocabularies, declarations must be non-empty and unrepeated, and unknown fields are rejected as everywhere else in the parser. Manifests without the field behave exactly as before.
- A new `resolveExpectationPath` seam (packages/test-support/session-snapshot/src/expectations.ts) resolves which committed expected file the reading host compares against: a variant declared for the host's platform family selects `<stem>.<win32|posix>.expected.<ext>` beside the base sidecar; every other case selects the base file; a declared variant whose file is missing throws, naming the scenario directory and the variant file name.
- The web lane's pinned comparison (and its refresh write-back) in apps/web/tests/scaffold.ts consumes the resolver, and `assertFixtureInventory` admits declared variant files automatically, so scenario specs need no inventory edits.

The controller ruling for the defect is to parameterize the expectation face, not to touch the preset/bundle platform mutual exclusion — that exclusion is deliberate design. The reference implementation and its tests live on branch `p/snapplat`; the shared corpus under `snapshots/` is untouched, and hooking the minimal-preset data (the yaml two-liner plus a `tool-schemas.win32.expected.json`) belongs to the corpus owner.

## Key design

- **Two-sided inventory closure.** Declared ⇒ committed: `assertFixtureInventory` requires every declared variant file to exist on every host, not just the reading one. Present ⇒ declared: a variant file on disk that no manifest declares is rejected as an inventory mismatch (orphan rejection). Neither side can rot silently.
- **Explicit platform injection.** `resolveExpectationPath` receives the reading host's `process.platform` as a parameter; nothing reads the global inside the resolver, so win32 and posix behavior are pinnable by tests on any host (the posix fallback is asserted on the win32 development host).
- **One consumed channel today.** Only the web lane consumes the field (pin comparison and refresh write-back). A non-web scenario that declares `expectations` parses but has no consumer, so the interim discipline is: do not declare it outside web scenarios until the headless/sdk/acp suite wiring ships.

## Alternatives considered

**Lift the preset's platform gating so every host mounts both shells.** That changes shipped preset semantics for every platform and every profile to satisfy one test corpus, and the gating is deliberate product design. The controller ruling rejected this; the expectation face is the parameterizable side.

**Skip the scenario on Windows hosts.** A platform skip marker would silence the two failures but abandon Windows coverage entirely and hide future composition drift behind a known-failure list. Parameterizing expectations keeps both platforms asserted against their own committed corpus.

**Branch on platform inside each scenario spec.** Hard-coding `process.platform` conditionals in `apps/web/tests/*.snapshot.ts` scatters platform knowledge across spec files and bypasses the inventory guard's authority; the manifest declaration keeps one declarative owner per scenario and lets the guard admit exactly the declared files.

## Acceptance criteria

- `parseSnapshotManifest` admits `expectations` only on a pinned header and rejects unknown fields, unknown platform keys, unknown or repeated kinds, and empty declarations; manifests without the field parse exactly as before (the session-snapshot corpus gate passes unchanged).
- `resolveExpectationPath` selects a declared variant file for the host's platform family, falls back to the base file otherwise, and throws with the scenario directory and variant file name when a declared variant file is missing; the win32 and posix arms are pinned by unit tests with exact error messages, on fixtures built in temporary directories.
- `assertFixtureInventory` admits declared variant files without spec changes, requires each on every host, and rejects undeclared variant files.
- The reference branch passes the session-snapshot package vitest suite, package `tsc -b`, the repository `pnpm run build`, and the corpus gate.

## Risks

- The headless/sdk/acp suite channels do not consume `expectations` yet; the not-declared-outside-web discipline is the interim guard until the wiring wave, and a premature declaration would be silently inert.
- The corpus gate does not validate variant files; web-side protection comes from `assertFixtureInventory` only.
- Child sidecar variants (`system-prompt.<n>.expected.md`) are not supported; a scenario needing per-child platform variants needs a mechanism extension.
- Refresh write-back goes through the resolved path, so a win32 host refreshes only the win32 variant file; the base (posix) file needs a posix host or manual maintenance.
- The `session.jsonl` script-side variant and inline-snapshot consumption channels are absent; both belong to the B-family mechanism extension wave.
- The platform vocabulary is a closed set (`win32` | `posix`); a new platform family requires extending the parser vocabulary and the mapping seam together.
