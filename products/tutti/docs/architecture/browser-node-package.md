# Browser Node Package

This document records the package direction for sharing the Browser Node
capability between the open-source desktop and TSH.

The intent is to align both products on one reusable browser runtime while
keeping product-specific business capabilities in thin host adapters.

## Direction

The implementation uses one deep package:

```text
@tutti-os/browser-node
```

Repository path:

```text
packages/browser/workbench-node
```

This path introduces the `packages/browser/*` group. The `workbench-node`
directory name clarifies that this package owns the Workbench Browser Node
surface, not every possible browser integration.

## Design Decisions

The initial package direction uses these decisions:

- Package name: `@tutti-os/browser-node`.
- Repository path: `packages/browser/workbench-node`.
- Runtime preview proxy: package-owned and optional. Hosts provide loopback
  preview target resolution and fallback policy; the package owns Electron
  session proxying, HTTP forwarding, WebSocket forwarding, and redirect
  rewriting.
- Bridge namespace: host-defined only. The package must not provide a default
  namespace because TSH and Tutti expose different guest globals.
- Address search provider: host-defined only. The package normalizes ordinary
  navigation URLs, but a host decides whether a non-URL address bar input turns
  into a search URL and which provider to use.
- Runtime errors: package events carry structured error codes and optional
  diagnostics. React surfaces map those codes through package i18n resources
  instead of rendering IPC strings as user-visible copy.

## Design Goal

The package should be large internally and small externally.

Business hosts should consume a Browser Node capability, not copy a set of TSH
or Tutti implementation files. The package owns browser behavior; each host
only provides product adapters.

## Package Entry Points

The package should use multiple exports from one package rather than several
small packages:

```text
@tutti-os/browser-node
@tutti-os/browser-node/react
@tutti-os/browser-node/workbench
@tutti-os/browser-node/electron-main
@tutti-os/browser-node/electron-preload
@tutti-os/browser-node/bridge
@tutti-os/browser-node/i18n
```

Recommended internal shape:

```text
packages/browser/workbench-node/
  src/core/
  src/react/
  src/workbench/
  src/electron-main/
  src/electron-preload/
  src/bridge/
  src/i18n/
```

## Package Ownership

The Browser Node package owns:

- browser node state and lifecycle
- navigation, back, forward, reload, close, and URL normalization
- address bar rendering and generic input resolution
- session, profile, and incognito partition logic
- React body and optional header surface
- workbench node definition helpers
- Electron webview registration and unregistration coordination
- Electron guest `webContents` state synchronization
- webview security policy
- guest preload bridge framework
- guest `window.open` and link interception
- generic runtime preview proxy mechanics
- default package i18n resources for generic browser behavior

The host owns:

- product i18n runtime composition
- product logging adapter
- product diagnostics policy
- address search provider policy
- IPC channel registration and preload global wiring
- external URL opening policy
- loopback preview target resolution
- bridge namespace, such as `__tsh` or `__tutti`
- bridge methods, such as TSH agent/game/share actions or future Tutti actions
- product authorization and host allowlist policy
- daemon or server clients
- any business mutation triggered by a guest page

## Host Interface Shape

The package should be configured through a host capability object. The exact
types can evolve during implementation, but the public shape should feel like:

```ts
import { createBrowserNodeFeature } from "@tutti-os/browser-node";

const browserNodeFeature = createBrowserNodeFeature({
  hostApi: desktopApi.browser,
  i18n,
  resolveSearchUrl(query) {
    const searchUrl = new URL("https://www.google.com/search");
    searchUrl.searchParams.set("q", query);
    return searchUrl.toString();
  }
});
```

Workbench registration should stay thin:

```ts
import { createBrowserNodeDefinition } from "@tutti-os/browser-node/workbench";

const browserNode = createBrowserNodeDefinition({
  defaultUrl: "https://www.google.com/",
  feature: browserNodeFeature,
  typeId: "browser"
});
```

Electron main registration should also be thin:

```ts
import { registerBrowserNodeElectronMain } from "@tutti-os/browser-node/electron-main";

registerBrowserNodeElectronMain({
  channels,
  getOwnerWindow,
  logger,
  openExternal,
  resolveWebContents,
  registerHandler
});
```

Hosts that need guest-page bridge injection should keep the package-owned
security baseline and provide the host-owned preload path through the webview
security installer:

```ts
import { installBrowserWebviewSecurity } from "@tutti-os/browser-node/electron-main";

installBrowserWebviewSecurity({
  contents: ownerWindow.webContents,
  openExternal,
  resolvePreload: () => browserGuestPreloadPath
});
```

The installer clears any guest-supplied preload first and applies the host
resolver only after Browser Node partition and URL validation succeeds.

Guest preload installation should not hardcode a product namespace:

```ts
import { installBrowserNodeGuestBridge } from "@tutti-os/browser-node/electron-preload";

installBrowserNodeGuestBridge({
  call,
  methods,
  namespace: "__tutti"
});
```

## TSH Migration Mapping

TSH currently has the Browser Node behavior spread across renderer, preload,
main, and shared contracts.

Move into package:

- `WebsiteNode` body and generic header behavior
- `useWebsiteNodeWebview`
- website runtime store
- website URL helpers
- website session partition helpers
- generic website window DTOs
- generic bridge result and API tree builders
- host allowlist matching helpers
- webview security enforcement
- guest `webContents` state listeners
- `WebsiteGuestManager` after renaming and dependency injection
- runtime preview proxy mechanics after decoupling service discovery
- generic bridge debug and link interception utilities

Keep in TSH host adapter:

- `__tsh` namespace selection
- agent/game/share bridge methods
- `DesktopShellService` dependencies
- room ID lookup
- TSH runtime service discovery implementation
- TSH event emission
- TSH-specific diagnostics messages when not generic
- any product copy that is not generic browser behavior

## Tutti Initial Integration

Tutti should first consume the package as a workbench node type:

1. Add a Browser Node definition to the workspace workbench host service.
2. Keep workbench node layout and persistence in the existing workbench
   snapshot path.
3. Add a narrow desktop host API for Browser Node commands through preload.
4. Register Electron main handlers as host capabilities, not business flows.
5. Keep direct `tuttid` backend tokens out of guest pages.
6. Add package i18n resources to the renderer app-level i18n runtime.

The first slice can support ordinary HTTP and HTTPS navigation before enabling
runtime preview routes.

## Security Invariants

The Browser Node package must preserve these invariants:

- guest pages never receive daemon or control-plane bearer tokens by default
- guest pages receive only explicitly registered bridge methods
- bridge methods are filtered by host allowlist before invocation
- webview preload path is package or host controlled, never guest controlled
- `nodeIntegration` stays disabled for guest pages
- `contextIsolation` stays enabled for guest pages
- `sandbox` stays enabled for guest pages
- `allowpopups` is denied by default
- navigation is limited to HTTP and HTTPS unless a host explicitly extends it
- local preview proxying is optional and routed through host-provided policy

## Why One Deep Package

Browser Node behavior crosses renderer, preload, and main. Splitting it into
many small packages would make the public interface nearly as complex as the
implementation. One package with multiple entry points keeps locality for
browser lifecycle fixes while keeping host integration explicit.

The package is deep when callers can register a browser workbench node, main
handlers, and guest bridge with a small amount of product adapter code.

## Phased Plan

1. Extract pure contracts and helpers: DTOs, URL parsing, session partitioning,
   bridge result types, and host allowlist helpers.
2. Extract renderer state and React surface behind an injected
   `BrowserNodeHostApi`.
3. Add workbench definition helpers for multi-instance browser nodes.
4. Extract Electron main guest manager, loopback preview proxy, and webview
   security policy behind injected logger, loopback preview routing policy,
   external-open, and IPC adapters.
5. Extract generic guest preload bridge with configurable namespace and method
   registry.
6. Rewire TSH to consume the package through a TSH adapter.
7. Add Tutti desktop integration with a minimal browser node.
8. Enable optional runtime preview routing after token and route policy review.

## Resolved Questions

The initial open questions are resolved by the design decisions above. Revisit
them only if the first extraction reveals a concrete integration issue.
