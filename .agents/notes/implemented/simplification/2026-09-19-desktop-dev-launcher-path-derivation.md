# Agent Note: Desktop dev launcher derives machine paths and guards package-set deletion

Status: implemented

## Problem

The unpackaged Desktop development launcher (`apps/desktop/scripts`) carried two
classes of machine-specific assumptions that broke on any checkout other than the
author's machine:

- `development-project.ts` hardcoded `D:/dsh-devframe` as the DevFrame repo root,
  `C:/Users/25313/.dsh` as the harness home, `D:/shadow-trial` as an extra
  authorized root, and a fixed `cloudflared.exe` path. It also pinned every
  experimental dependency to a single version string instead of reading each
  source package's real version.
- `prepare-package-set.ts` recursively deleted its `--out` directory before
  copying tarballs, with no check that the path lived inside the workspace, so a
  typo or a misconfigured default could delete an arbitrary directory.

## Decision

`development-project.ts` now gates the whole DevFrame overlay behind an opt-in
`devframeOverlay: true` option (off by default, so generic callers and the
shared-link unit tests do not require a DevFrame checkout; `dev:desktop` opts
in). When enabled it derives `devframeRoot` as two levels above `apps/cli`,
reads `DSH_HOME` (falling back to `~/.dsh`), and reads each experimental
package's version from its own `package.json`. The deployment narrowing patch is
built by `buildDevFrameDeploymentPatch()`, which injects the derived repo/vault
paths and only appends the extra authorized root and `cloudflaredPath` lines when
the corresponding environment variables are set. `@dsh-mobile/pairing` remains
pinned because it is a vendored external package.

`prepare-package-set.ts` exports `assertPackageSetOutLocation(output,
allowOutsideWorkspace)`, called before `rmSync`. By default it requires `--out`
to live under the repository's `.desktop-build` directory or the system temp
directory. The `--force-out` flag (or `DSH_ALLOW_OUTSIDE_WORKSPACE_OUT=1`) opts
out of workspace confinement, but never lifts the refusal of a filesystem root
(a Windows drive root or POSIX `/`) or the home directory.

A cross-file consistency test (`tests/host-protocol-constants.spec.ts`) reads the
read-only Host `wire.ts` and pins its shared literals against the Desktop side's
exported constants; the Desktop-only control IPC fd is deliberately excluded
from that contract.

## Alternatives considered

**Derive `devframeRoot` unconditionally from `cliDir`.** Rejected because the two
existing generic tests build a temporary project root where the overlay's link
targets do not exist; an opt-in flag keeps them green without weakening the
derivation for the real launcher.

**Move the six vendor junctions to a one-time setup script.** Deferred as
out-of-scope conservatism: the junction block stays in place, only its root is
derived. A follow-up can extract it.

**Inline the guard into `prepareDesktopPackageSet` without a separate export.**
The guard is exported so the unit tests can assert the positive/negative cases
without packing real tarballs.

## Consequences

The launcher no longer names the author's machine, and a misplaced package-set
`--out` fails loud instead of deleting an arbitrary directory. The Host wire
contract now has a regression test that breaks CI on either side drifting.

`profile-mcp.spec.ts` retains 22 `no-unsafe-*` oxlint diagnostics. The minimal
experiment (refresh app-boot `d.ts`, then annotate the imported symbols) did not
clear them: oxc-typescript cannot resolve the deep `@deepseek-ai/cordis-plugin-*`
type chain behind `@deepseek-ai/dsh-app-boot`, so the imported functions
collapse to `error` and the call sites are flagged. Clearing them requires either
touching `packages/boot/app-boot` source or `as any` / `oxlint-disable`, both
out of scope; this is left as a documented open item.

The `profile-mcp.spec.ts` runtime assertion itself now fails against the parallel
`apps/desktop-host` overlay, which no longer carries the `@deepseek-ai/dsh-mcp-resources`
row. That is a cross-boundary dependency on the in-progress Host work, not a
regression from these changes.
