# Agent Note: The Capability center unifies independently owned pages

Status: implemented

English | [中文](2026-09-25-capability-center.zh.md)

## Problem

A sidebar action labelled Expert mode does not describe Skills, Connectors, and the memory library. A separate memory entry also fragments related local capabilities.

## Decision

The sidebar entry and its shared modal are labelled Capability center and contain four tabs: Experts, Skills, Connectors, and Library. The Experts tab retains the mounted-expert catalog. The inventory package contributes Skills and Connectors to the root-keyed `capabilities.center.tab` slot and reuses the management callbacks also used by Settings. The project-memory UI package contributes Library to that slot; it lists, searches, and previews the configured Vault, copies absolute paths, and adds file references to the conversation draft. The Vault remains read-only. The center renders only the selected contribution and shows an explicit unavailable state when its owner is not mounted. Each domain package continues to own its services and behavior.

The delivery boundary is the plugin packages themselves. The center does not require a Desktop or Host patch; the profile bundle names its published data-pack dependencies, and `expert-team` resolves those package names from its installed dependency closure instead of using `process.cwd()`. The UI packages remain public and use optional peer links for cross-page slot types, so a DSH upgrade can replace the host while the plugin packages continue to mount through the documented Remote and slot contracts.

## Alternatives considered

**Keep the Expert mode label and add tabs.** Rejected: the name would describe only one of four equally visible destinations.

**Keep Library as a separate sidebar entry.** Rejected: users would still need separate entry points to find related local capabilities.

**Move every capability implementation into the center package.** Rejected: doing so would duplicate ownership of Host-backed management and Vault behavior.

## Consequences

Users reach the four pages through one resident entry while each provider retains its existing data and mutation path. An absent provider produces a clear unavailable state instead of invented content. Only the selected page is mounted, so its local view state resets when users leave that tab; the library reads the Vault only after its tab mounts and never writes Vault files.

## Testing

The focused suites cover the four-tab shell, slot dispatch and fallback, keyboard navigation, Skills and Connectors management, Library loading, unavailable state, stale asynchronous results, and file references. The three affected package suites pass 66 tests across nine files.

## Related

[The expert catalog note](2026-09-16-expert-center-ui.md) owns mounted-expert discovery; [the summon handoff note](2026-09-16-expert-center-summon.md) owns the new-conversation flow. [The Capability center package](../../../../packages/experimental/client-ui-expert-team/README.md), [Skills and connector management](../../../../packages/client/ui-settings-plugin-inventory/README.md), and [the Library page](../../../../packages/experimental/client-ui-project-memory/README.md) document their user-facing behavior.
