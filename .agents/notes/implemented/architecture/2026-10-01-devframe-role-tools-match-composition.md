# Agent Note: DevFrame inherited role tools follow the mounted providers

Status: implemented

English | [中文](2026-10-01-devframe-role-tools-match-composition.zh.md)

## Problem

An inherited role allow list is validated against the global tool registry when a bound Agent is published or restored. Names for absent browser, image-generation, external-worker, or project-controller providers prevent publication and can abort Desktop startup. Parsing the profile or booting it with only unbound Agents does not exercise this failure.

## Decision

The [DevFrame profile](../../../../packages/experimental/devframe-profile/cordis.patch.yml) gives controller and lead only the global dispatch, expert-team, memory, and library tools supplied by its own providers. The [Desktop overlay](../../../../apps/desktop-host/config/desktop.cordis.patch.yml) replaces the complete hierarchy configuration and adds the project-controller tools it mounts. Both retain the empty worker inherited allow list and empty lead plugin scopes.

The [hierarchy policy](2026-09-05-agent-hierarchy-policy-package.md) and `tools.restrict()` remain strict: an unknown configured global name fails rather than disappearing from the policy. Agent-local tools are scoped registrations, not entries that the inherited global allow list must enumerate. Additional deployment providers and their permissions are configured together.

## Alternatives considered

**Silently filter unknown names against the live registry.** This hides provider omissions and misspellings, and turns a declared capability into an unavailable tool without a configuration error.

**Install every optional provider to satisfy the list.** Browser, image-generation, and external-worker providers introduce dependencies and deployment requirements that the default profile does not own. A permission entry alone does not authorize their installation or activation.

## Consequences

The Loader composition test reads the shipped hierarchy configuration and publishes bound controller and lead Agents without optional providers. The Desktop composition test checks that its allow lists extend the profile lists only by the mounted project-controller tools. Permission-list changes are tested through publication rather than only YAML parsing; the independent policy and Shadow allowlist decisions remain active.
