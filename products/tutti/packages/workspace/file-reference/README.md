# @tutti-os/workspace-file-reference

Reusable workspace file reference contracts, picker state, and optional React UI.

This package owns host-neutral file reference selection behavior for workspace
surfaces that need to browse, search, upload, preview, open, or share file
references. Hosts provide concrete file-system access through package contracts;
desktop preload calls, tuttid transport wiring, host absolute paths, and
product-specific integration stay in the consuming host adapter.

The package uses logical workspace paths and keeps reference picking reusable
across shared workspace features such as the agent GUI and issue manager.
