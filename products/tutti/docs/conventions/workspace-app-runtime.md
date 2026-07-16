# Workspace App Runtime

Workspace App Center apps and daemon-managed ACP npm adapters run against a
daemon-managed runtime baseline. App packages must not bundle or declare
Python/Node versions; Tutti injects the managed runtime paths at launch.

## Runtime Baseline

The baseline runtime is componentized. The default baseline profile contains the
Python and Node components, but each component is published as a separate
platform-specific zip so tuttid can download them in parallel:

```text
python component zip:
  python/bin/python3

node component zip:
  node/bin/node
  node/bin/npm
  node/bin/npx
```

Windows runtime artifacts, when added, must use the Windows executable names expected by tuttid:

```text
python/bin/python.exe
node/bin/node.exe
node/bin/npm.cmd
```

Catalog platform keys must use Go runtime names because tuttid resolves them with `runtime.GOOS` and `runtime.GOARCH`. Use `darwin-amd64` and `linux-amd64`, not Node's `darwin-x64` or `linux-x64` download labels.

## Release Ownership

Runtime artifacts are released independently from desktop packages. Do not publish runtime artifacts from `.github/workflows/desktop-release.yml`.

The runtime release source of truth is:

```text
config/tutti.app-runtime.lock.json
```

When Python, Node, uv, supported platforms, or artifact layout changes, update the lock and run the runtime release workflow once. Fixed versions do not require rebuilding on every product release.

The workflow is:

```text
.github/workflows/publish-tutti-app-runtime.yml
```

The workflow:

1. Installs the pinned uv version.
2. Uses uv to install the pinned Python baseline.
3. Downloads the pinned Node release for each platform and verifies it against Node's `SHASUMS256.txt`.
4. Assembles separate Python and Node zips per platform.
5. Writes metadata for each platform's runtime components.
6. Uploads immutable component zips to S3.
7. Builds and uploads `catalog.json`.

Runtime artifacts should be uploaded under a dedicated S3 prefix, normally:

```text
tutti-app-runtimes/<runtimeVersion>/<platform>/python/tutti-app-runtime-python-<platform>-<runtimeVersion>.zip
tutti-app-runtimes/<runtimeVersion>/<platform>/node/tutti-app-runtime-node-<platform>-<runtimeVersion>.zip
tutti-app-runtimes/catalog.json
```

The public artifact base URL must point at the same prefix, usually through CloudFront:

```text
https://<cloudfront-domain>/tutti-app-runtimes
```

When `TUTTI_APP_RUNTIME_CATALOG` is unset, tuttid uses the default published runtime catalog:

```text
https://d1x7gb6wqsqmnm.cloudfront.net/tutti-app-runtimes/catalog.json
```

Artifacts are immutable and should use long cache headers. The catalog is mutable and should use a short cache header.

## Catalog Shape

The runtime catalog consumed by tuttid has this shape:

```json
{
  "schemaVersion": "tutti.app.runtimes.v2",
  "runtimes": {
    "darwin-arm64": {
      "version": "2026.06.0",
      "components": {
        "python": {
          "version": "3.12.13",
          "artifactUrl": "https://cdn.example.test/tutti-app-runtimes/2026.06.0/darwin-arm64/python/tutti-app-runtime-python-darwin-arm64-2026.06.0.zip",
          "artifactSha256": "64-char-sha256",
          "artifactSizeBytes": 123
        },
        "node": {
          "version": "22.22.3",
          "artifactUrl": "https://cdn.example.test/tutti-app-runtimes/2026.06.0/darwin-arm64/node/tutti-app-runtime-node-darwin-arm64-2026.06.0.zip",
          "artifactSha256": "64-char-sha256",
          "artifactSizeBytes": 456
        }
      },
      "profiles": {
        "baseline": ["python", "node"],
        "node-static": ["node"]
      }
    }
  }
}
```

tuttid resolves the `baseline` profile by default when launching apps, and may
preload smaller profiles such as `node-static` during daemon startup or an
explicit runtime-preparation workflow before first launch. Listing App Center
apps must not preload runtimes as a side effect. App manifests must not declare
a runtime kind. Apps that only need Node may declare
`runtime.profile: "node-static"` so launch does not require the Python
component. If runtime requirements need to become more selective later, add a
capability list such as runtime component requirements rather than restoring a
single-kind manifest field.

## Runtime Overrides

Supported daemon overrides:

- `TUTTI_APP_RUNTIME_CATALOG`: HTTP(S) URL or local file path for the runtime catalog. Set it to an empty string to disable the default runtime catalog.
- `TUTTI_APP_RUNTIME_CACHE_ROOT`: cache root for platform-specific runtime directories.
- `TUTTI_APP_RUNTIME_ROOT`: exact prepared runtime root, mainly for tests and local debugging.

App packages must not set these variables. The runner injects `TUTTI_APP_PYTHON`, `TUTTI_APP_NODE`, `TUTTI_APP_NPM`, and `PATH` for app processes.
Agent provider installers may also use the managed `TUTTI_APP_NPM` path to
install ACP npm adapters into daemon-owned per-agent prefixes instead of npm
global locations.

Runtime artifacts must make `node/bin/npm` and `node/bin/npx` standalone
wrappers that execute the packaged Node binary with npm's packaged CLI scripts.
Do not rely on Node release symlinks surviving zip packaging.

## Validation

### App package bootstrap validation

On Linux/macOS, the manifest `runtime.bootstrap` path is used directly. The file
must be executable.

On Windows, the runner resolves the bootstrap according to a sibling convention:

- `.ps1` bootstrap: executed via `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File`.
- `.exe` bootstrap: executed directly (native).
- `.sh` bootstrap: the runner looks for a `.ps1` sibling beside the `.sh` file
  and uses that. If no `.ps1` sibling exists, the launch fails with an
  actionable error asking the package author to add a `bootstrap.ps1`.
- `.cmd` and `.bat` bootstraps are rejected on Windows.

A cross-platform package can include both `bootstrap.sh` and a sibling
`bootstrap.ps1`. The manifest names `bootstrap.sh`; the runner picks the
correct file per platform.

On Windows, validate a package by running PowerShell directly:

```powershell
$env:TUTTI_APP_NODE = "node.exe"  # must be discoverable or absolute
$env:TUTTI_APP_HOST = "127.0.0.1"
$env:TUTTI_APP_PORT = "8787"
$env:TUTTI_APP_PACKAGE_DIR = "."
$env:TUTTI_APP_RUNTIME_DIR = "$env:TEMP\tutti-app-runtime"
$env:TUTTI_APP_DATA_DIR = "$env:TEMP\tutti-app-data"
$env:TUTTI_APP_LOG_DIR = "$env:TEMP\tutti-app-logs"
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\bootstrap.ps1
```

After runtime release changes, run:

```bash
node --test ./tools/scripts/build-tutti-app-runtime-catalog.test.mjs
pnpm lint:ts
```

After downloader or runner changes, also run:

```bash
cd services/tuttid && go test ./service/workspace ./service/eventstream
pnpm --filter @tutti-os/workspace-app-center test
pnpm --filter @tutti-os/desktop typecheck
```

## Windows Packaged Node Runtime

On Windows, the desktop package bundles a self-contained Node runtime so a
fresh machine without Node/npm can still use the `node-static` profile. The
runtime is prepared during packaging, not at daemon startup.

### Lock file

The source of truth for the bundled Windows Node runtime is:

```text
config/tutti.windows-node-runtime.lock.json
```

Schema version `tutti.windows-node-runtime-lock.v1`. The `node` entry
contains the version, download URL, and SHA-256 of the official Node.js
Windows x64 zip distribution. Update the lock when the bundled Node version
changes; a version bump invalidates the previous cached archive and staging
root.

### Layout

The vendor script produces the standard runtime resolver layout under
`apps/desktop/build/app-runtime`:

```text
app-runtime/
  node/
    .tutti-runtime-marker
    LICENSE
    bin/
      node.exe
      npm.cmd
      npx.cmd
      node_modules/
        npm/
          bin/
            npm-cli.js
```

The marker file contains `tutti-windows-node-runtime-<version>` and is used
by the validation step in the after-pack hook and daemon environment
resolution. A root missing any required file or with a wrong/missing marker
is treated as corrupt and falls back to the managed-runtime catalog path.

### Build command

The vendor step runs as part of Windows packaging:

```bash
pnpm --filter @tutti-os/desktop build:win
```

To prepare the runtime alone (development/layout verification):

```bash
node apps/desktop/scripts/vendor-windows-node-runtime.mjs
```

### Validation marker

The `tuttidManager.ts` daemon environment resolver validates the packaged
root against the marker and required files before setting
`TUTTI_APP_RUNTIME_ROOT`. The marker is a defense against partial or
stale staged roots; without it the daemon treats the root as missing and
falls back to the managed-runtime cache path, producing a visible catalog
error on Windows. Explicit `TUTTI_APP_RUNTIME_ROOT` or
`TUTTI_APP_RUNTIME_CACHE_ROOT` overrides always win over the packaged root.
