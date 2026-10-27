---
description: Handoff for completing standalone capability-center plugins and verifying compatibility with DSH upgrades.
---

# Capability-center plugin compatibility handoff — 2026-09-26

English | [中文](capability-center-plugin-compatibility-handoff-2026-09-26.zh.md)

## Purpose

This handoff records the remaining work for the Capability center plugin packages. The user set the boundary: deliver plugins that can be installed independently and continue working as DSH updates; do not repair or extend the DSH Desktop or Host applications, or the core module loader. This document is the next agent's entry point for that follow-up.

## Current state

The four-tab Capability center is composed from separate providers: [client-ui-expert-team](../../packages/experimental/client-ui-expert-team/README.md) owns the Experts shell, [ui-settings-plugin-inventory](../../packages/client/ui-settings-plugin-inventory/README.md) contributes Skills and Connectors, and [client-ui-project-memory](../../packages/experimental/client-ui-project-memory/README.md) contributes Library. Their data and actions remain with their owning plugins.

The Host [expert-team package](../../packages/experimental/expert-team/README.md) accepts installed data-pack package names and resolves them from its own installation closure. Its configuration no longer needs the caller's current directory when a package name is used.

The working tree contains uncommitted changes across those plugin packages, their paired documentation, the capability-center Agent Note, the lockfile, and the experimental-package workspace constraint. No Desktop, Host app, core client loader, or Desktop delivery files are part of this change. Review the current diff before editing; do not reset or clean the shared worktree.

## Evidence and limits

| Check | Result |
|---|---|
| `pnpm exec tsc -b tsconfig.client.json --pretty false` | Passed for the current client source tree. |
| Bundles for inventory, client-ui-expert-team, and client-ui-project-memory | All three package bundle commands completed successfully. The Host expert-team package has no `bundle` script. |
| Local package archives | `pnpm pack` produced archives for the three client plugins, Host expert-team, and both shipped expert packs. This proves local packing only. |
| Expert-team package reference probe | Resolving `@deepseek-ai/dsh-experimental-expert-pack-paper` from the repository returned its installed workspace package directory. A clean external consumer was not tested. |
| Named bilingual-pair check and `git diff --check` | Seven document pairs passed; the diff check reported only a CRLF-to-LF warning for `LibraryCard.tsx`. |
| `scripts/check-workspace-constraints.ts` | Fails on pre-existing Desktop/Host release metadata and `files` policies for expert-pack-dev, expert-pack-paper, and project-controller. These failures are not evidence that the plugin archives cannot be packed. |

The package peer ranges in the packed metadata currently resolve from `workspace:^` to `^0.1.6-alpha.1`. Local packing does not prove that DSH upgrades remain compatible, and no registry publication or clean-profile runtime installation was performed. A prior Agent Note records focused UI suites passing 66 tests, but those results predate the current tree and are not current acceptance evidence; no tests were run during this closeout.

## Remaining work for the next agent

1. Define the supported compatibility contract from public Remote and slot APIs, and document which DSH versions the plugins support. The user wants the plugins to survive DSH updates; do not claim compatibility across a breaking public API change without evidence.
2. Install the locally packed plugin archives in a clean consumer profile with no repository workspace links. Verify dependency resolution, the four tabs, and the Host Remote calls without changing DSH app or loader code.
3. Check the same plugin set against the current DSH release and a newer DSH version when available. Record the exact package versions and observed behavior; keep any compatibility adjustment inside plugin packages and their published dependency metadata.
4. Review the workspace constraint change. It permits any experimental package with `publishConfig.access: public` to be non-private; narrow or justify that policy while preserving independently publishable plugin packages.
5. Run focused tests for changed plugin behavior and packaging checks after the incoming agent has reviewed the current diff. Do not use a Desktop rebuild or host patch as a substitute for plugin consumer evidence.

The older [Desktop product delivery handoff](desktop-product-delivery.md) records a broader Desktop integration effort; its app dependency changes are outside this follow-up's scope. The [Capability center Agent Note](../../.agents/notes/implemented/feature/2026-09-25-capability-center.md) records the feature's ownership decisions.

## Handoff instructions

Take ownership of the plugin compatibility work only. Preserve the current shared-worktree changes, avoid edits under `apps/desktop`, `apps/desktop-host`, and `packages/client/modules`, and do not publish packages or create a release. The acceptance result is a clean-consumer installation plus recorded compatibility evidence for the chosen DSH versions.
