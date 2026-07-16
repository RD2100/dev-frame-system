# Workspace Issue Manager

Reusable workbench issue-manager feature for workspace-scoped issue, task, and
run workflows.

This package owns host-agnostic contracts, i18n defaults, React-facing feature
types, and workbench registration helpers. Hosts provide backend, identity,
file, agent runner, and optional share adapters.

Hosts that want the package-owned default dock or empty-state visual can import
it explicitly from
`@tutti-os/workspace-issue-manager/assets/workspace-dock-task.png`.

See [docs/architecture/workspace-issue-manager.md](../../../docs/architecture/workspace-issue-manager.md)
for the current shared architecture and host-adapter model.
