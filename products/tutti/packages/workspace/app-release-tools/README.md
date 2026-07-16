# @tutti-os/app-release-tools

Command-line tools for publishing Tutti workspace apps into App Center release metadata.

## Commands

```sh
build-tutti-app-release --app-id vibe-design --package-dir dist/tutti-app/vibe-design --base-url https://cdn.example.test/tutti-app-releases
build-tutti-app-catalog --release-file ./apps/vibe-design/latest.json --output ./catalog.json
build-tutti-app-catalog --existing-catalog ./catalog.json --release-file ./apps/vibe-design/latest.json --output ./catalog.json
verify-tutti-app-release-artifacts --release-file ./apps/vibe-design/latest.json
verify-tutti-app-release-artifacts --catalog-file ./catalog.json --release-file ./apps/vibe-design/latest.json
```

The release command validates a complete Tutti app package, creates a zip,
writes immutable `release.json`, and writes mutable `latest.json`. When the
manifest declares `localizationInfo`, the release metadata includes the
referenced manifest locale files so App Center can localize uninstalled remote
apps without downloading the package.

The catalog command merges one or more release files into `tutti.app.catalog.v1`.
Pass `--existing-catalog` to preserve existing catalog apps and update only the
apps represented by the release files. With `--existing-catalog`, release files
are optional, which allows rewriting an existing catalog without changing its app
set.

The verify command checks release and catalog metadata against the referenced
artifact downloads. When both `--catalog-file` and `--release-file` are passed,
catalog entries for those apps must exactly match the latest release metadata
before artifact SHA-256 and size checks run.
