# Agent Note: Stable profile identities and the source-checkout DevFrame template

Status: implemented

English | [中文](2026-09-04-profile-identity-and-devframe-template.zh.md)

## Problem

Profile composition needs a durable identity that launcher and profile-aware plugins can use, while malformed manifests and bundle patch paths must fail before Cordis mounts the profile. DevFrame remains experimental and must compose through the existing profile boot path without adding another application entry point.

## Decision

Store `dsh.profile.id` in the profile package manifest as a UUID v4 branded `ProfileId`. `ensureProfileIdentity()` creates it under the existing manifest lock, preserves it across launches, and returns it with the configured profile name. The CLI provides that identity before boot mounts the profile. Manifest readers validate owned object types, bundle arrays, duplicate names, reload modes, profile IDs, and bundle patch paths; a patch must be a relative existing file inside its bundle package directory. The `devframe` template explicitly composes `@deepseek-ai/dsh-base`, `@deepseek-ai/dsh-headless`, and the private `@deepseek-ai/dsh-experimental-agent-team-profile` layer with startup patch reload.

## Alternatives considered

- **Derive identity from the profile name or directory.** Renaming or copying a profile would change the identity and would not distinguish two profiles with the same configured name.
- **Add a dedicated DevFrame CLI binary.** This duplicates the supported profile launcher and would make an experimental composition look like a separate application surface.
- **Discover bundles by scanning package metadata.** Implicit graph discovery hides composition order and makes malformed or unintended package references harder to reject at load time.

## Consequences

- Concurrent first launches converge on one persisted profile identity, and later launches can correlate work with the same profile.
- `devframe` is available as a source-checkout profile only; release bundles must not silently pull the private experimental Agent Teams layer.
- Profile and bundle metadata errors are reported before application startup, and callers must keep patch files inside their declared package roots.
- The identity is a profile-boot value; it does not change session persistence or define the DevFrame controller, worker, or reviewer runtime policies.
