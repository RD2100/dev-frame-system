# Agent Note: The Shadow's production call site is the composition row's config

Status: implemented

English | [中文](2026-09-06-shadow-config-designation.zh.md)

## Problem

`markShadow(agent)` existed but had no production call site: only tests and integration probes invoked it, so a real composition that wanted the four project tools had to write imperative host code outside any registered row, and nothing in the composition declared which session is the Shadow. The whitelist stayed inert unless a caller remembered to invoke the method by hand, which made the shipped fail-closed face indistinguishable from an accidentally unmarked deployment.

## Decision

The production call site is the composition row's config. `ShadowRouterConfig.shadowSessionId` names the Shadow session id, and the router performs the real `markShadow` invocation itself at the earliest resolvable point — immediately when an agent with that id is already live at activation (an init scan through the agent registry), otherwise on its `agent/created` event. Session creation stays host-owned: the router never creates the designated agent, and an id that never becomes live installs nothing, so an unconfigured or never-created mount keeps the fail-closed `SHADOW_CALLER_FORBIDDEN` behavior. Marking is idempotent, and disposal cleanup stays with the existing `agent/disposed` effect, so a disposed designated agent unmarks and a recreated same-id agent re-marks; across a cold restart the designation is re-established in memory while binding rows stay durable.

## Alternatives considered

**Extend the project-contracts role union with a `shadow` role.** Rejected: project-contracts is a closed cross-package type vocabulary outside the Shadow package's seam; growing it couples the whitelist's designation to another package's contract and makes every role consumer carry a fact only the Shadow router consumes.

**Defer the call site to the future P23/S4 toolface slice package.** Rejected: the designation seam belongs to the Shadow whitelist itself — the component that owns the four tools and their fail-closed guard — and a later slice would still have to mark through this same service, so deferring only leaves the production gap open.

**Keep probe-only wiring.** Rejected: tests and probes calling `markShadow` by hand prove the mechanism but are not a production call site; without a declarative face, every real composition ships an unmarked Shadow and fail-closed rejections that look intentional.

## Consequences

A composition designates its Shadow with one config field, the marking follows the declared id across creation, restart, and dispose/recreate, and the fail-closed default is unchanged when the field is absent or the id never appears. The costs: the declared id is trusted composition data, so a typo surfaces only as fail-closed rejections — deliberately the same face as the default, which makes checking the configured id part of composition review — and the router now hard-injects the base-tree agent registry in addition to its other dependencies.
