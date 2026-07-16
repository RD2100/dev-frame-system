# @tutti-os/browser-node

Reusable Workbench Browser Node capability for Electron desktop hosts.

The package owns browser-node mechanics such as URL normalization, session
partitioning, renderer state, React surfaces, webview security, and Electron
guest lifecycle coordination. Product hosts own business bridge methods,
diagnostics policy, loopback preview routing policy, and daemon or server
clients.

The package supports ordinary HTTP and HTTPS browser navigation by default. For
hosts that need local runtime previews, the Electron main integration can also
configure a package-owned loopback preview proxy through
`loopbackPreviewRouting`.

For Workbench hosts, the package also exposes a dock helper through
`@tutti-os/browser-node/workbench`. `createBrowserDockEntry(...)` wires the
dock label, matches Browser nodes back to the dock entry, and restores popup
title, URL subtitle, and preview capture from the Browser runtime state.
Hosts that want the package-owned default dock visual can import it explicitly
from `@tutti-os/browser-node/assets/workspace-dock-website.png`.
