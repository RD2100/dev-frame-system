# Agent Note: Desktop production runtime carries the DevFrame profile closure

Status: implemented

English | [中文](2026-09-24-desktop-devframe-runtime-closure.zh.md)

## Problem

The general dsh release family excludes `packages/experimental`, while the Desktop product is expected to ship the DevFrame expert, memory, Shadow, team, and schedule surfaces. A development workspace symlink made those rows appear during local work, but a packaged Desktop runtime had no profile bundle, expert pack data, or installed package paths.

## Decision

Desktop packaging adds a product-specific experimental closure after packing the general dsh family. The closure starts at the DevFrame profile, the Shadow browser entry, and experimental dependencies declared by the Desktop Host, then follows local dependency, optional-dependency, and peer-dependency edges. The package-set descriptor requires the DevFrame profile, and the generated runtime manifest activates `dsh-base`, `dsh-web-app`, and `dsh-experimental-devframe-profile`.

The Desktop Host overlay supplies the Shadow bridge and browser entry, mounts the project-controller task/integration/delivery faces and agent-evidence, and replaces Expert Team source-checkout pack paths with the installed `expert-pack-paper` and `expert-pack-dev` package directories. Experimental names stay out of the published CLI and Host runtime dependency surfaces; Desktop's generated runtime manifest supplies the local closure. The general dsh release family remains unchanged and continues to exclude experimental packages for non-Desktop consumers.

## Alternatives considered

**Keep experimental packages out of the Desktop tarballs.** Rejected because the packaged profile would resolve neither its rows nor its expert data, leaving the documented Desktop capabilities absent.

**Add every experimental package to the general dsh release family.** Rejected because it changes the official release boundary for all consumers; Desktop needs a product-specific closure instead.

**Keep source-checkout paths in the Host overlay.** Rejected because a prepared runtime contains installed package directories, not the repository's `packages/experimental` tree.

## Consequences

Desktop preparation packs the transitive DevFrame closure and fails loudly when a required local package is missing. The production profile now activates DevFrame services, UI rows, and project workflow faces, and Expert Team reads data from installed package paths. Project faces remain inert until a deployment supplies a real workspace and Shadow binding. The Desktop package is larger and still requires a complete package preparation run; general dsh package consumers do not receive the experimental closure.

## Testing

Desktop package-set, profile, and package-target tests pass; Desktop and Desktop Host TypeScript builds pass; Cordis configuration verification passes. The general dsh release verifier reports 247 members at `0.1.6-alpha.1`. Full Windows package preparation reached the tarball stage but remains environment-sensitive when nested Node processes cannot resolve the `pnpm` command.
