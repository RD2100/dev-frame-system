# Workspace Terminal

This document records the intended frontend and host boundary for workspace
terminal nodes shared by the personal Tutti desktop and the collaborative TSH
desktop.

The key architectural decision is:

- the terminal workbench experience is shared
- the terminal execution substrate is host-specific

Tutti should run local host terminals. TSH should keep running terminals in its
managed VM/runtime path.

## Decision Summary

This migration has three parallel goals for the current Tutti landing:

1. preserve TSH terminal behavior as reference material by porting first into a
   package-internal quarantine
2. extract only host-agnostic terminal behavior into
   `@tutti-os/workspace-terminal`
3. prove the shared package through the Tutti local-terminal vertical before
   treating the package API as stable

Decisions already made:

| Topic              | Decision                                                                                            |
| ------------------ | --------------------------------------------------------------------------------------------------- |
| Shared scope       | Share terminal UI/runtime mechanics, not process execution.                                         |
| Tutti execution    | Run local pty sessions through `services/tuttid`.                                                   |
| TSH execution      | Keep VM, guest-agent, relay, room, and collaboration behavior in TSH adapters.                      |
| Session identity   | A terminal workbench node cannot switch to another `sessionId`. New process means new session/node. |
| Close semantics    | Close terminates the terminal session; if work is running, ask through close guard first.           |
| Minimize semantics | Minimize hides the node and keeps the session running.                                              |
| Agent terminal     | Agent terminal is a specialization/wrapper around terminal, not a branch in terminal core.          |
| WebGL renderer     | Omit from V1; reserve only a future narrow option if an active host needs it.                       |
| Drag/drop          | Shared UI exposes a hook; host decides accepted payloads, path mapping, and shell quoting.          |
| Diagnostics        | Shared package emits product-neutral events; hosts decide logging sinks.                            |

The current landing stops at the Tutti local-terminal vertical. TSH adoption is
documented only as a future integration shape, not as work required before this
branch can be considered complete.

The Tutti landing now has implementation and verification evidence. Future
work should reopen these architecture decisions only when implementation or
runtime evidence exposes a concrete mismatch.

## Context

Both Tutti and TSH are expected to use the shared workbench surface as their
workspace shell. They differ in where terminal commands actually execute:

| Host  | Product mode                    | Execution authority                                                         |
| ----- | ------------------------------- | --------------------------------------------------------------------------- |
| Tutti | personal local-first desktop    | the user's local machine, shell, environment, and default working directory |
| TSH   | collaborative workspace desktop | the managed VM/runtime and guest-agent terminal stream                      |

The shared code should therefore sit above the execution boundary. It should own
the terminal node experience and state machine, but not the process launcher.

## Layer Model

```text
packages/workbench/surface
  WorkbenchHost, dock, frame, layout, shell snapshot, instance resolution,
  intent routing, and external-state render plumbing.

packages/workspace/terminal
  Shared terminal contracts, xterm surface, renderer runtime state, hydration,
  scrollback, input queue, default terminal copy, and workbench node helpers.

apps/desktop terminal adapter
  Tutti-specific workbench registration, tuttid client wiring, local pty
  session creation, file-link handling, app i18n merge, and user-facing host
  integration.

apps/tsh-desktop terminal adapter
  TSH-specific workbench registration, desktopd client wiring, VM transport,
  room/collaboration metadata, runtime-lost projection, and agent/room behavior.

services/tuttid terminal service
  Local host pty session lifecycle, output replay, snapshots, resize/write,
  and WebSocket attach for Tutti.

tsh desktopd/runtime
  VM, guest-agent, relay, routing, and collaborative terminal execution.
```

`packages/workbench/*` must not learn about terminal semantics.
`WorkbenchHost` can own generic shell behavior such as node instance resolution,
intent targeting, frame layout, dock state, and shell snapshot persistence. It
should only consume terminal behavior through host-provided
`WorkbenchHostNodeDefinition` objects and optional `externalStateSource`
lookups.

`packages/workspace/terminal` should not learn whether a session is backed by a
local pty, VM stream, remote SSH session, or another host-owned source.

## Current Execution State

The Tutti vertical is implemented and verified. The package, daemon API, and
desktop adapter exist, and the terminal node is a real xterm surface registered
in `apps/desktop`. Electron runtime passes have verified the local terminal
path, including the idle and foreground-command close semantics.

| Area                    | State                         | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ----------------------- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Package skeleton        | Done                          | `packages/workspace/terminal` exports contracts, React, workbench, i18n, and CSS entrypoints.                                                                                                                                                                                                                                                                                                                                                                     |
| TSH quarantine          | Removed                       | The temporary copied TSH terminal renderer source has been deleted after the Tutti V1 shared package surface landed.                                                                                                                                                                                                                                                                                                                                              |
| Ledger                  | Folded back                   | Durable package-boundary decisions now live in this document instead of a package-internal quarantine ledger.                                                                                                                                                                                                                                                                                                                                                     |
| Shared contracts        | Done                          | Transport, launch, close guard, diagnostics, link, drop, output transform, limits, theme, and external state contracts exist.                                                                                                                                                                                                                                                                                                                                     |
| Pure shared helpers     | Done for V1                   | Scrollback, string overlap, dimensions, session projection, link detection, close flow, and screen cache helpers have package-local tests.                                                                                                                                                                                                                                                                                                                        |
| tuttid HTTP routes      | Implemented for V1            | OpenAPI, generated clients, and handlers exist for list/create/get/terminate/close-guard/resize/snapshot.                                                                                                                                                                                                                                                                                                                                                         |
| tuttid WebSocket attach | Implemented for V1            | The route now upgrades through a custom route because strict generated handlers do not receive `http.ResponseWriter` and `*http.Request`. It supports `input`, `resize`, `detach`, `ping`, replay after `afterSeq`, live output, and exit/error frames.                                                                                                                                                                                                           |
| Shared xterm surface    | Runtime verified for Tutti V1 | `TerminalNode` mounts xterm with fit/search/serialize/web-links addons, hydrates from snapshot, attaches by `afterSeq`, writes transport output through a bounded scheduler, queues input until attach, sends resize, exposes find UI with case-sensitive and regex options, routes drops through the host hook, detects URL and file-path links, uses the committed screen-state cache on remount, and has a shared close-guard dialog for direct header closes. |
| Desktop adapter         | Runtime verified for Tutti V1 | `apps/desktop` registers the terminal node and maps tuttid HTTP/WebSocket APIs into launch, snapshot, write, resize, detach, terminate, close-guard, default workbench close, URL/file link handling, and drop-input contracts. Runtime testing verified launch, requested/default cwd behavior, input/output, minimize, remount, stale-session projection, and close guard.                                                                                      |
| TSH adapter             | Out of scope for this landing | TSH can adopt the package later, but this plan does not require migrating TSH now.                                                                                                                                                                                                                                                                                                                                                                                |

Post-landing follow-up order:

1. harden any new edge cases found from continued desktop use, especially
   replay, backpressure, close-guard precision, and stale-session UX
2. keep future TSH adoption work in host adapters or wrappers instead of
   restoring copied renderer source
3. leave TSH adapter migration to a later, separate plan

## Shared Package Boundary

The shared package is named by responsibility and exported as
`@tutti-os/workspace-terminal`.

Current public entrypoints:

```text
@tutti-os/workspace-terminal
@tutti-os/workspace-terminal/contracts
@tutti-os/workspace-terminal/react
@tutti-os/workspace-terminal/workbench
@tutti-os/workspace-terminal/i18n
@tutti-os/workspace-terminal/styles.css
```

The root export should stay narrow. It should expose the stable package-level
contract and high-level React/workbench helpers, not internal implementation
files.

The package may own:

- terminal transport TypeScript contracts
- terminal node external-state and launch intent contracts
- xterm lifecycle and renderer setup
- terminal attach, detach, hydration, and replay state machines
- scrollback, committed-screen-state, input queue, resize, find, and link
  helpers
- optional React body/header components for a workbench terminal node
- a helper that creates a `WorkbenchHostNodeDefinition`
- narrow default i18n resources for shared terminal UI
- package-local structural styles needed by the shared terminal surface

The package must not own:

- tuttid or desktopd client construction
- Electron preload calls
- WorkbenchHost snapshot repository construction
- local host pty spawning
- TSH VM, guest-agent, relay, or LD_PRELOAD routing behavior
- room, collaboration, or agent-provider business rules
- product-specific copy, toasts, settings, or permission policy
- durable daemon storage

## Public API

The package exposes one small public surface with multiple entrypoints. Type
names may still evolve during V1 verification, but only when runtime evidence
shows the current contract does not fit a real host integration.

Current and intended stable exports:

```text
@tutti-os/workspace-terminal
  closeTerminalSession
  createTerminalNodeFeature
  defaultTerminalNodeLimits
  type TerminalNodeFeature

@tutti-os/workspace-terminal/contracts
  terminal transport, launch, close guard, diagnostics, link, drop, and state
  contracts

@tutti-os/workspace-terminal/react
  TerminalNode
  TerminalNodeHeader
  TerminalCloseGuardDialog

@tutti-os/workspace-terminal/workbench
  createTerminalWorkbenchNodeDefinition
  createTerminalWorkbenchLaunchHandler
  defaultTerminalWorkbenchTypeId

@tutti-os/workspace-terminal/i18n
  terminalNodeI18nResources
  createTerminalNodeI18nRuntime
```

The root export should be enough for ordinary host integration. Deep entrypoints
exist to keep workbench, React, contracts, and i18n dependencies explicit.

### Feature Factory

The terminal package should be configured through a feature object, following
the same broad pattern as the Browser Node package:

```ts
export interface CreateTerminalNodeFeatureInput {
  closeGuard: TerminalCloseGuardService;
  diagnostics?: TerminalDiagnostics;
  dropInput?: TerminalDropInputResolver;
  i18n?: I18nRuntime<string>;
  launchService: TerminalLaunchService;
  limits?: TerminalNodeLimits;
  linkHandler?: TerminalLinkHandler;
  outputTransform?: TerminalOutputTransform;
  resolveTheme?: TerminalThemeResolver;
  transport: TerminalTransport;
}

export interface TerminalNodeFeature {
  closeGuard: TerminalCloseGuardService;
  diagnostics: TerminalDiagnostics;
  dropInput?: TerminalDropInputResolver;
  i18n: TerminalNodeI18nRuntime;
  launchService: TerminalLaunchService;
  limits: TerminalNodeLimits;
  linkHandler?: TerminalLinkHandler;
  outputTransform?: TerminalOutputTransform;
  resolveTheme: TerminalThemeResolver;
  transport: TerminalTransport;
}

export function createTerminalNodeFeature(
  input: CreateTerminalNodeFeatureInput
): TerminalNodeFeature;
```

Feature creation should not create sessions, attach transports, read globals, or
construct daemon clients. It only normalizes host capabilities for the shared
terminal surface.

### Launch And Lifecycle

Session creation and termination are host-owned:

```ts
export interface TerminalLaunchInput {
  cwd?: string | null;
  initialInput?: string | null;
  profileId?: string | null;
  reason: "dock" | "intent" | "restore";
  workspaceId: string;
}

export interface TerminalSessionDescriptor {
  cwd: string | null;
  profileId: string | null;
  runtimeKind: TerminalRuntimeKind;
  sessionId: string;
  status: TerminalSessionStatus;
  title: string;
}

export interface TerminalLaunchService {
  create(input: TerminalLaunchInput): Promise<TerminalSessionDescriptor>;
  get?(sessionId: string): Promise<TerminalSessionDescriptor | null>;
  terminate(input: { sessionId: string }): Promise<void>;
}
```

The shared package may call `create(...)` when a workbench dock item launches a
new terminal. Closing a terminal calls host-provided close guard and termination
capabilities; it must not be implemented as transport `detach(...)`.

### Close Guard

Closing a terminal means terminating the session. The shared UI owns the
confirmation flow, while the host owns process inspection and termination:

```ts
export type TerminalCloseGuardReason =
  | "foreground-process"
  | "not-running"
  | "running"
  | "unknown";

export interface TerminalCloseGuardResult {
  leaderCommand?: string | null;
  reason: TerminalCloseGuardReason;
  requiresConfirmation: boolean;
  status: TerminalSessionStatus;
}

export interface TerminalCloseGuardService {
  check(input: { sessionId: string }): Promise<TerminalCloseGuardResult>;
}
```

### Links, Drops, Diagnostics, And Output Hooks

Small extension hooks let hosts keep product policy outside the terminal core:

```ts
export interface TerminalLinkTarget {
  column?: number;
  line?: number;
  path?: string;
  url?: string;
}

export interface TerminalLinkHandler {
  open(target: TerminalLinkTarget): Promise<void> | void;
}

export interface TerminalDropInput {
  cwd: string | null;
  dataTransfer: DataTransfer;
  sessionId: string;
}

export type TerminalDropInputResolver = (
  input: TerminalDropInput
) => Promise<string | null> | string | null;

export type TerminalOutputTransform = (input: {
  data: string;
  sessionId: string;
}) => string | null;

export type TerminalDiagnosticEvent =
  | "attach-complete"
  | "attach-error"
  | "attach-start"
  | "close-confirmed"
  | "close-requested"
  | "dispose"
  | "hydration-complete"
  | "hydration-gap"
  | "hydration-start"
  | "mount"
  | "resize"
  | "snapshot-complete"
  | "snapshot-start"
  | "write-error";

export interface TerminalDiagnostics {
  log(
    event: TerminalDiagnosticEvent,
    details?: Record<string, string | number | boolean | null>
  ): void;
}
```

Diagnostics must avoid raw terminal input, environment values, tokens, and other
secrets. Output transforms are optional and host-provided; the shared package
must not bake in TSH agent or query cleanup rules.

### Workbench Helper

Workbench integration should be thin helpers around the current
`WorkbenchHost` model:

```ts
export interface CreateTerminalWorkbenchNodeDefinitionInput {
  dockIcon?: ReactNode;
  feature: TerminalNodeFeature;
  frame?: WorkbenchFrame;
  title?: string;
  typeId?: string;
}

export function createTerminalWorkbenchNodeDefinition(
  input: CreateTerminalWorkbenchNodeDefinitionInput
): WorkbenchHostNodeDefinition<TerminalWorkbenchIntent>;

export function createTerminalWorkbenchLaunchHandler(
  input: CreateTerminalWorkbenchLaunchHandlerInput
): (
  request: WorkbenchHostLaunchRequest
) => Promise<WorkbenchHostLaunchResult | null>;
```

The node-definition helper creates a multi-instance `WorkbenchHostNodeDefinition`
and renders the shared terminal body/header. The launch handler is optional but
recommended for host integration: it plugs into `WorkbenchHost`'s
`onLaunchRequest`, calls `TerminalLaunchService.create(...)`, and stores the
returned stable `sessionId` in both `instanceId` and `instanceKey`.

This split matches the current `packages/workbench/surface` API. A node
definition does not directly receive dock launch requests; launch authority is a
host-level `WorkbenchHost` callback. Neither helper should construct the
Workbench snapshot repository or own product routing.

## Transport Contract

The shared terminal surface should depend on a host-provided transport instead
of directly calling `window` globals or daemon clients.

```ts
export type TerminalRuntimeKind = "local" | "vm" | "remote" | string;

export type TerminalWriteEncoding = "utf8" | "binary";

export interface TerminalTransport {
  attach(input: TerminalTransportAttachInput): Promise<void>;
  detach(input: TerminalTransportDetachInput): Promise<void>;
  write(input: TerminalTransportWriteInput): Promise<void>;
  resize(input: TerminalTransportResizeInput): Promise<void>;
  snapshot(input: TerminalTransportSnapshotInput): Promise<TerminalSnapshot>;
  onData(listener: (event: TerminalDataEvent) => void): () => void;
  onExit(listener: (event: TerminalExitEvent) => void): () => void;
  onMetadata?(listener: (event: TerminalMetadataEvent) => void): () => void;
  onState(listener: (event: TerminalStateEvent) => void): () => void;
}

export interface TerminalTransportAttachInput {
  sessionId: string;
  clientId?: string;
  afterSeq?: number;
}

export interface TerminalTransportDetachInput {
  sessionId: string;
}

export interface TerminalTransportWriteInput {
  sessionId: string;
  data: string;
  encoding?: TerminalWriteEncoding;
  provenance?: "user" | "auto";
}

export interface TerminalTransportResizeInput {
  sessionId: string;
  cols: number;
  rows: number;
}

export interface TerminalTransportSnapshotInput {
  sessionId: string;
}

export interface TerminalSnapshot {
  data: string;
  fromSeq?: number;
  toSeq?: number;
  truncated?: boolean;
  updatedAt?: number;
}

export interface TerminalMetadataEvent {
  sessionId: string;
  cwd?: string | null;
  profileId?: string | null;
  resumeSessionId?: string | null;
  runtimeKind?: TerminalRuntimeKind;
  title?: string | null;
}
```

The transport may be backed by HTTP plus WebSocket, direct IPC, or another
host-owned stream. The package should only rely on the interface.

Recommended stream frame semantics for daemon-backed hosts:

Server-to-client frames:

| Frame      | Meaning                                                              |
| ---------- | -------------------------------------------------------------------- |
| `output`   | terminal output chunk with optional sequence number                  |
| `state`    | session state update such as running, detached, exited, or failed    |
| `metadata` | title, cwd, profile, runtime, or other non-secret session metadata   |
| `gap`      | replay could not provide all requested sequence numbers              |
| `exit`     | terminal process exited with an exit code or signal                  |
| `error`    | attach or stream failure that should be surfaced through diagnostics |

Client-to-server frames:

| Frame    | Meaning                                                     |
| -------- | ----------------------------------------------------------- |
| `input`  | terminal input bytes from the renderer                      |
| `resize` | terminal dimensions in columns and rows                     |
| `detach` | renderer stream is going away; do not terminate the session |
| `ping`   | optional liveness probe if the host transport needs one     |

This frame shape is already close to the TSH desktop transport and is a good
candidate for reuse by tuttid, but the shared React package should consume the
typed transport events, not raw WebSocket frames.

Close is intentionally not a stream frame. Closing a workbench terminal flows
through `TerminalCloseGuardService.check(...)` and
`TerminalLaunchService.terminate(...)` so that close and detach cannot be
confused.

## Session State Contract

Current `WorkbenchHost` snapshots store shell state: nodes, frames, stack order,
display mode, and `WorkbenchHostNodeData` fields such as `typeId`,
`instanceId`, and `instanceKey`. They should not become the durable store for
terminal process state, scrollback, host runtime metadata, or product business
state.

The shared terminal package should define a portable terminal session state
shape that can be read from package runtime state, a host-owned
`externalStateSource`, or a host-backed session repository. A workbench node may
use `instanceKey` for a stable terminal session id or launch key, but the
terminal state itself remains outside the generic Workbench snapshot.

A terminal workbench node must not switch to a different terminal session after
it has been bound. The `sessionId` is part of the node identity. If the backing
process exits or is lost, the node should project that terminal state rather
than silently reusing the same node for a new process. Opening a new terminal
creates a new session and, for multi-instance workbench integration, a new
terminal node or instance.

```ts
export type TerminalSessionStatus =
  | "created"
  | "starting"
  | "running"
  | "detached"
  | "exited"
  | "failed";

export interface TerminalNodeExternalState<
  THostMetadata extends Record<string, unknown> = Record<string, unknown>
> {
  sessionId: string | null;
  title: string;
  cwd: string | null;
  profileId: string | null;
  runtimeKind: TerminalRuntimeKind;
  status: TerminalSessionStatus;
  createdAt: string | null;
  updatedAt: string | null;
  endedAt: string | null;
  lastError: string | null;
  host: THostMetadata | null;
}
```

Scrollback and replay data should flow through `TerminalTransport.snapshot(...)`
or a host-owned terminal session store, not through `WorkbenchHost` node data.

Tutti host metadata can include local profile details such as shell path or
environment profile id.

TSH host metadata can include room id, agent provider hints, runtime session
metadata, or collaborative context. Those fields should remain host-owned unless
both products need the same behavior through the shared package.

## Recovery Model

The shared package should follow TSH's recovery split:

- the host daemon owns live terminal truth, including session state, process
  lifecycle, output sequencing, ring-buffer replay, and snapshot reads
- the renderer or app persistence layer may keep node hints, shell layout, and
  optional scrollback placeholders for a smoother reopen
- a reopened renderer should match persisted terminal node hints to live daemon
  sessions by `sessionId`; unmatched runtime hints are stale and must not be
  treated as live terminals
- a host may preserve scrollback for display after a session is gone, but that
  is not the same as restoring the process

Tutti should mirror this model for the first implementation. `tuttid` should
own live local pty sessions and output replay. Workbench snapshots should
recover shell layout. Any durable terminal history beyond the live daemon
session should be modeled as terminal history or placeholder state, not as proof
that the original process still exists.

## Agent Specialization

Agent nodes should be modeled as a specialization of terminal behavior rather
than as a branch inside the shared terminal core. The terminal package should
not learn agent providers, room collaboration, agent resume rules, or provider
session recovery.

If shared agent-terminal behavior becomes necessary later, build it as a wrapper
around `@tutti-os/workspace-terminal`: the wrapper can translate agent launch,
resume, provider status, and product metadata into terminal feature inputs while
leaving the core terminal surface host-agnostic.

The wrapper may own agent launch commands, provider settings, resume metadata,
agent-specific status projection, history placeholders, room/task/issue
linkage, and product chrome. It should compose the terminal package through
generic extension points such as launch services, external state, close guards,
diagnostics, title/status mapping, and optional header accessories. The terminal
core must not expose provider-specific branches such as `agentProvider` or
agent resume policy.

## Workbench Integration Contract

The shared package should provide a helper that creates a terminal node
definition for `WorkbenchHost`, while the consuming host supplies all authority
and integration points.

```ts
const terminalFeature = createTerminalNodeFeature({
  closeGuard,
  diagnostics,
  dropInput,
  i18n,
  launchService,
  linkHandler,
  resolveTheme,
  transport
});

createTerminalWorkbenchNodeDefinition({
  feature: terminalFeature,
  typeId: "workspace-terminal"
});

const onLaunchRequest = createTerminalWorkbenchLaunchHandler({
  feature: terminalFeature,
  typeId: "workspace-terminal"
});
```

The helper should return a `WorkbenchHostNodeDefinition` with shared body/header
rendering. The launch handler should be passed to `WorkbenchHost` or composed
inside the host's existing launch callback. The host remains responsible for
adding the definition to its workbench host service, passing any needed
`externalStateSource` to `WorkbenchHost`, and deciding when to launch or focus a
terminal.

Host responsibilities:

- create terminal sessions
- decide initial cwd and profile
- map daemon session state into terminal external state or package runtime state
- persist WorkbenchHost shell snapshots through the existing host repository
- persist terminal session state separately when a host needs durable terminal
  recovery beyond shell layout
- implement close-guard checks and terminal termination behind the shared close
  flow
- open file links in the host's file manager or editor surface
- merge package i18n defaults into the app-level runtime
- handle product-specific errors and notifications

## Tutti Local Terminal Path

Tutti's first implementation should target local host pty terminals.

`services/tuttid` should own:

- local pty process lifecycle
- session ids and state transitions
- workspace-scoped session ownership without a catalog-stored host-path lookup
- cwd resolution from an explicit request or the daemon's default local home
  directory
- environment/profile selection policy
- output ring buffer and sequence replay
- snapshot data
- WebSocket attach, resize, write, detach, close, and exit/lost behavior

The exact HTTP contract must be added to
`services/tuttid/api/openapi/tuttid.v1.yaml` before generated clients or
daemon handlers are changed.

Expected route family:

```text
GET    /v1/workspaces/{workspaceID}/terminals
POST   /v1/workspaces/{workspaceID}/terminals
GET    /v1/workspaces/{workspaceID}/terminals/{terminalID}
DELETE /v1/workspaces/{workspaceID}/terminals/{terminalID}
POST   /v1/workspaces/{workspaceID}/terminals/{terminalID}/resize
GET    /v1/workspaces/{workspaceID}/terminals/{terminalID}/snapshot
GET    /v1/workspaces/{workspaceID}/terminals/{terminalID}/ws
```

Tutti should not import TSH VM or routing code. It should treat terminal
execution as a local desktop capability mediated by tuttid.

### Windows ConPTY Backend

On Windows, `services/tuttid/service/workspace` uses a real ConPTY backend
through `github.com/UserExistsError/conpty` v0.1.4 (MIT). The backend is
selected at build time through platform-tagged files:

- `terminal_backend_unix.go` (`//go:build !windows`) - existing `creack/pty` path
- `terminal_backend_windows.go` (`//go:build windows`) - ConPTY path

Design decisions:

- The internal `terminalBackend` interface keeps the same session contract
  (read, write, resize, wait, kill, close, fd) for both platforms.
- If ConPTY is unavailable (the ConPTY API support probe determines this at
  start) the daemon returns an explicit actionable error. There is no silent
  pipe downgrade.
- Shell path quoting (for paths containing spaces) is handled by the Windows
  factory before passing the command line to `CreateProcess`.
- `Kill` and `Close` share one idempotent path on Windows (single `sync.Once`
  around `conpty.Close`). On Unix, `Kill` sends a signal and `Close` closes
  the PTY file descriptor separately.
- `waitLoop` closes the backend after natural exit on both platforms so
  ConPTY handles are released without waiting for an explicit `Terminate`
  call.

Known boundary:

- Foreground-process detection (`terminal_foreground_windows.go`) returns
  `false` on Windows. The close guard therefore reports `"not-running"` for
  idle shells; there is no foreground-command confirmation on Windows. This
  is a separate enhancement, not a ConPTY limitation.

Validation command (Windows):

```powershell
go `
  test -v -run "^TestWindows" -count=1 `
  ./service/workspace
```

## TSH VM Terminal Path

This section is future-facing only. TSH can adopt the same shared package later
after its workbench migration, but no TSH app migration is part of the current
Tutti landing.

TSH should keep:

- desktopd terminal session APIs
- VM/runtime ownership
- guest-agent shell stream
- relay path resolution
- terminal routing environment and LD_PRELOAD behavior
- room, collaboration, and agent-provider rules

A future TSH adapter should translate desktopd's existing terminal API and
WebSocket frames into the shared `TerminalTransport` contract. That would let
TSH share the terminal node experience without changing its execution authority.

## Port-Then-Refactor Strategy

The migration prioritized not losing TSH terminal behavior while the shared
package was extracted. For the current Tutti landing, the temporary quarantine
has served its purpose: host-agnostic behavior needed by Tutti was promoted,
and TSH app replacement remains a separate future plan. The preferred rhythm was:

1. Port the relevant TSH terminal code into a quarantined package-internal area.
2. Keep a ledger that assigns every ported file or behavior to its final home.
3. Replace product dependencies with package contracts.
4. Promote shared behavior into the official package modules.
5. Delete the quarantined port once every ledger item is either promoted,
   dropped, or assigned to a future host adapter/wrapper.

Do not copy TSH code directly into the package public surface. If future TSH
work needs an adapter, keep it outside the shared package modules unless the
behavior is deliberately promoted through a host-agnostic contract.

## Porting Ledger

The temporary porting ledger has been folded back into this document. Future TSH
adoption work should document durable package-boundary changes here when they
affect the shared terminal contract.

Use these destinations:

| Destination        | Meaning                                                              |
| ------------------ | -------------------------------------------------------------------- |
| `shared-contract`  | Public TypeScript contract under `src/contracts`.                    |
| `shared-core`      | Host-agnostic runtime behavior under `src/core`.                     |
| `shared-react`     | Host-agnostic React UI or hooks under `src/react`.                   |
| `shared-workbench` | Workbench definition helper under `src/workbench`.                   |
| `shared-i18n`      | Package-owned default copy under `src/i18n`.                         |
| `host-adapter`     | Tutti or TSH adapter code outside the package.                       |
| `agent-wrapper`    | Future agent-specialization wrapper or TSH-local wrapper.            |
| `drop`             | Dead, dormant, or product-specific behavior that should not migrate. |

Initial ledger groups:

| TSH area                                         | Initial destination                            | Notes                                                                                   |
| ------------------------------------------------ | ---------------------------------------------- | --------------------------------------------------------------------------------------- |
| terminal transport DTOs                          | `shared-contract`                              | Keep event semantics, sequence fields, snapshot shape, and metadata events.             |
| `terminalTransport.ts` concrete desktopd adapter | `host-adapter`                                 | Use as a reference for TSH adapter only; do not move desktopd calls into the package.   |
| terminal runtime store                           | `shared-core`                                  | Remove `WorkspaceNodeKind` and agent provider coupling.                                 |
| attachment controller                            | `shared-core`                                  | Depend on `TerminalTransport` and package diagnostics only.                             |
| hydration pipeline/router/finalization           | `shared-core`                                  | Keep base snapshot hydration; move agent placeholder behavior to wrapper/host.          |
| xterm session creation                           | `shared-core` and `shared-react`               | Keep lifecycle, addons, fit, links, search, serialize. Drop dormant WebGL path from V1. |
| output scheduler                                 | `shared-core`                                  | Keep bounded scheduling behavior and host-configurable limits.                          |
| scrollback helpers                               | `shared-core`                                  | Keep renderer buffer; persistence stays host-owned.                                     |
| committed screen state/cache                     | `shared-core`                                  | Keep stable node/session cache behavior with explicit invalidation.                     |
| input bridge and queue                           | `shared-core`                                  | Keep hydration gate; remove agent/provider-specific restored input delays from core.    |
| terminal find UI/hooks                           | `shared-react`                                 | Keep if product copy is moved to package i18n.                                          |
| link providers                                   | `shared-core`                                  | Emit URL/file targets; opening and path translation stay host-owned.                    |
| close guard dialog                               | `shared-react` and `shared-i18n`               | Shared UI flow, host-provided guard and terminate calls.                                |
| diagnostics helpers                              | `shared-contract` and `shared-core`            | Replace TSH event names with package-owned event names.                                 |
| output sanitizers                                | `host-adapter` hook                            | Provide hook in package; TSH-specific filters stay adapter-owned.                       |
| drop-to-terminal helpers                         | `shared-react` hook plus `host-adapter` policy | Package routes drop and inserts returned input; host maps payloads.                     |
| opencode theme bridge                            | `agent-wrapper` or `drop`                      | Not terminal core. Revisit only for agent terminal wrapper.                             |
| agent placeholder/resume/history protection      | `agent-wrapper`                                | Not terminal core.                                                                      |
| room/collaboration/status behavior               | `host-adapter` or `agent-wrapper`              | Not terminal core.                                                                      |
| WebGL renderer selection/pixel snapping          | `drop` for V1                                  | Dormant in TSH workspace terminal; reserve a narrow future option only.                 |
| Windows ConPTY backend                            | daemon implementation               | Implemented; see Tutti Local Terminal Path section.                                                                                                   |

## Refactor Phases

Phase status for the current branch:

| Phase                                       | Status                        | Current meaning                                                                                                                                                                                       |
| ------------------------------------------- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Phase 0: Inventory                          | Complete                      | TSH terminal source was inventoried during extraction; the temporary quarantine has since been deleted.                                                                                               |
| Phase 1: Package Skeleton And Contracts     | Complete for initial package  | Public package shape and contracts compile; API may still evolve only when runtime verification exposes a real integration mismatch.                                                                  |
| Phase 2: Quarantined TSH Port               | Removed after initial port    | The copied source snapshot and ledger were deleted after promoted behavior landed in the shared package.                                                                                              |
| Phase 3: Promote Shared Core                | In progress                   | Pure helpers plus first xterm mount/hydrate/attach/input/resize, file-path links, bounded output scheduling, and screen restoration path are promoted; runtime hardening remains.                     |
| Phase 4: Shared React And Workbench Surface | Runtime verified for Tutti V1 | Workbench helper, xterm body, find bar with case-sensitive and regex controls, drop hook, URL/file link activation, shared close flow, screen remount cache, and Tutti host link/drop policies exist. |
| Phase 5: Tutti Vertical Integration         | Runtime verified for Tutti V1 | HTTP daemon APIs, live WebSocket stream, desktop adapter, and workbench registration exist. Continued hardening remains.                                                                              |
| Phase 6: Future TSH Adoption                | Not part of this landing      | Migrate TSH only under a later dedicated plan through host adapters or wrappers, without restoring copied renderer source.                                                                            |

### Phase 0: Inventory

- generate the TSH terminal source list
- group files by the ledger above
- identify imports that mention `legacy TSH preload globals`, desktopd DTOs, room state,
  agent providers, React Flow, or product i18n
- decide whether each file is copied to quarantine, referenced only, or dropped

Exit criteria:

- every TSH terminal file considered for migration has a ledger row
- no package public API has been created from unreviewed TSH code

### Phase 1: Package Skeleton And Contracts

- create `packages/workspace/terminal`
- add package entrypoints, build config, and package-local i18n structure
- implement public contracts first: transport, launch, close guard, diagnostics,
  links, drop input, output transform, session state, and limits
- implement the workbench node-definition helper and launch-request handler
- add type-level tests or focused unit tests for pure contracts where useful

Exit criteria:

- the package builds with contracts only
- no xterm, React UI, or host adapter code is required yet

### Phase 2: Quarantined TSH Port

This temporary phase is closed. The copied source snapshot and local ledger were
deleted after the promoted shared behavior landed in `src/core`, `src/react`,
and `src/workbench`.

Exit criteria:

- no copied TSH renderer source remains in the package
- durable product-dependency decisions are recorded in this document

### Phase 3: Promote Shared Core

Promoted behavior followed this order:

1. pure helpers: limits, scrollback, output scheduling, input classification that
   is not product-specific
2. transport-independent state machines: attachment, hydration, replay gap
   handling, screen cache
3. xterm lifecycle: mount, addons, fit, resize, search binding, serialize, links
4. input bridge: write queue, binary/utf8 writes, hydration gate
5. close flow and diagnostics interfaces

Each promotion should remove product dependencies or turn them into explicit
host inputs.

Exit criteria:

- promoted modules compile without legacy TSH preload globals, desktopd clients, room
  state, agent provider types, React Flow DOM assumptions, or product i18n
- corresponding tests are either ported or replaced with package-local tests

### Phase 4: Shared React And Workbench Surface

- implement `TerminalNode`, `TerminalNodeHeader`, find UI, close guard dialog,
  and drop hook integration
- implement `createTerminalWorkbenchNodeDefinition` and
  `createTerminalWorkbenchLaunchHandler`
- make workbench close call the shared close flow, not transport detach
- keep optional extension slots generic rather than agent-specific

Exit criteria:

- a host can register a terminal node definition with `WorkbenchHost`
- terminal UI can launch, attach, hydrate, write, resize, find, close, and
  minimize using only package contracts

### Phase 5: Tutti Vertical Integration

- add tuttid OpenAPI terminal contracts before daemon/client changes
- implement local pty sessions, ring buffer, snapshot, sequence replay, resize,
  WebSocket attach, close guard, and terminate in `services/tuttid`
- implement the desktop renderer host adapter that satisfies the package
  contracts
- register the terminal node in `apps/desktop`

Exit criteria:

- open terminal
- input reaches the local pty
- resize updates the pty
- snapshot hydration and `afterSeq` replay work after renderer remount
- close terminates the session, confirms only when the host reports foreground
  work, and closes idle shells directly
- minimize keeps the session alive

### Phase 6: Future TSH Adoption

This phase is intentionally excluded from the current branch. If TSH adopts the
package later, that separate plan would need to cover:

- a TSH adapter around existing desktopd terminal APIs
- replacement of TSH renderer terminal internals with the shared package
  surface
- preservation of VM, guest-agent, room, agent, provider, routing, and
  collaboration logic outside terminal core
- an agent-terminal wrapper only if needed after the plain terminal path is
  stable

Future TSH exit criteria:

- TSH keeps current terminal behavior through the shared package
- remaining TSH-only behavior is explicitly adapter-owned or wrapper-owned
- no copied TSH renderer source is restored inside `packages/workspace/terminal`

## Migration Rules

- Public package modules must be narrow, reviewed, and host-agnostic.
- Do not keep compatibility shims for TSH globals in shared code.
- Do not introduce agent/provider branches into terminal core.
- Prefer deleting dormant code over preserving it because it existed in TSH.
- When behavior is intentionally left behind, record whether it is `drop`,
  `host-adapter`, or `agent-wrapper`.

## Feature Review List

The shared terminal package should be assembled from reviewed capabilities, not
by bulk-moving the full TSH terminal node. Use this list as the initial
extraction decision table:

| Capability                                        | Placement                                        | Decision                                                                                                                                                                                                                    |
| ------------------------------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| xterm mount, dispose, fit, resize                 | V1 shared terminal core                          | Own the xterm lifecycle, addon disposal, DOM mount, fit, and resize observer flow. Host renderer policy must be injected as options.                                                                                        |
| xterm renderer strategy                           | reserved option; no V1 implementation            | Use xterm's stable default renderer. Do not carry unused TSH renderer-selection code into the first package extraction; keep only a narrow future option such as `rendererMode`.                                            |
| Windows ConPTY backend                           | daemon implementation                             | Implemented in `services/tuttid/service/workspace` through `terminal_backend_windows.go`; see the Windows ConPTY Backend subsection for support boundary and validation command.                                          |
| terminal link provider                            | V1 shared core with host callback                | Detect URL and file-like links, including optional line/column. Host resolves cwd, VM/local path translation, and open policy.                                                                                              |
| terminal search addon binding                     | V1 shared UI                                     | Include find bar and xterm search addon binding when the package owns terminal body/header UI. Keep it host-configurable.                                                                                                   |
| light diagnostics hook                            | V1 shared interface                              | Provide host-injected diagnostics with package-owned, product-neutral event names. Default to no-op and avoid raw user input, env values, tokens, and product-specific logging dependencies.                                |
| WebGL pixel snapping                              | omit from V1                                     | TSH does not currently enable WebGL, and its dormant snapping code depends on product DOM/platform details. Reintroduce only with an active host requirement to enable WebGL.                                               |
| transport attach, detach, write, resize, snapshot | V1 shared contract plus host adapter             | The package defines typed transport contracts. Concrete HTTP, WebSocket, IPC, desktopd, or tuttid wiring stays in host adapters. `detach` means detach the renderer stream, not close or kill the terminal session.         |
| output sequencing and `afterSeq` replay           | V1 shared semantics; daemon-owned implementation | Use monotonic output sequence numbers, snapshot `fromSeq`/`toSeq`, attach `afterSeq`, and explicit replay gap/truncation signaling. Ring-buffer storage remains daemon-owned.                                               |
| snapshot hydration                                | V1 shared terminal core                          | Hydrate xterm from `TerminalTransport.snapshot`, attach with `afterSeq`, and surface truncation/gap state. Agent placeholder and advanced restored-history behavior stay out of V1 core.                                    |
| output scheduler and scrollback buffer            | V1 shared terminal core                          | Schedule xterm writes and keep bounded renderer scrollback for UI/persistence. Daemon replay remains authoritative; limits and persistence callbacks are host-configured.                                                   |
| input queue and hydration input gate              | V1 shared terminal core                          | Buffer user input until transport attach and initial hydration are ready, then flush in order. Agent-specific restored-input protection stays outside terminal core.                                                        |
| terminal find                                     | V1 shared terminal UI                            | Provide find bar, next/previous, case-sensitive and regex controls, backed by xterm search addon. Hosts may disable it.                                                                                                     |
| file path links                                   | V1 shared terminal core with host callback       | Emit file path plus optional line/column; host owns resolution and opening.                                                                                                                                                 |
| close guard                                       | V1 shared UI plus host checks                    | Closing a terminal means terminating the terminal session. If a command/process is still running, the shared UI asks for confirmation through a host-provided guard result; minimize is the background-running affordance.  |
| committed screen state / screen cache             | V1 shared terminal core                          | Preserve flicker-free remount for TUI/full-screen terminal states. Cache by stable node/session identity, invalidate on pending writes or session loss, and keep hydration ordering explicit.                               |
| diagnostics event coverage                        | V1 shared interfaces only                        | Expose package-owned terminal lifecycle, hydration, attach, resize, write, and close events for host logging without coupling to product loggers.                                                                           |
| output sanitizers                                 | V1 host-provided hook                            | Provide an optional output transform before writing to xterm. Do not bake in TSH agent/query filters or product-specific cleanup rules.                                                                                     |
| terminal drop input hook                          | V1 shared hook with host-owned policy            | The shared surface may route drag/drop events to a host hook and insert returned terminal input. Host owns accepted payloads, path mapping, shell quoting, and product UI.                                                  |
| agent/provider resume behavior                    | wrapper or host-owned, not terminal core         | Model agent terminals as a specialization wrapper around the shared terminal package. The wrapper owns launch, resume, provider status, history placeholders, and product chrome through generic terminal extension points. |

## First Implementation Milestones

The first milestones should prove both goals: preserve TSH behavior during the
port, and make Tutti consume a clean shared package.

1. **Inventory and quarantine**
   - create the TSH terminal source inventory
   - create `packages/workspace/terminal`
   - use temporary quarantine only during extraction
   - delete copied source once promoted behavior lands

2. **Contracts-first package shape**
   - add package entrypoints and build config
   - implement `TerminalTransport`, launch, close guard, diagnostics, link,
     drop, output transform, state, and limit contracts
   - keep all host calls out of the package

3. **Promote shared terminal runtime**
   - promote xterm lifecycle, scheduler, hydration, input queue, screen cache,
     find, links, close flow, diagnostics, and hooks into
     `src/core` and `src/react`
   - remove or invert `legacy TSH preload globals`, desktopd, room, agent-provider, and
     product-i18n dependencies as each module is promoted

4. **Tutti local terminal vertical**
   - add the terminal API contract to tuttid OpenAPI before daemon/client
     changes
   - implement local pty sessions, ring buffer, snapshot, sequence replay,
     resize, WebSocket attach, close guard, and terminate in `services/tuttid`
   - implement a desktop renderer adapter for the package contracts
   - register the terminal node from the desktop workbench host service

5. **Future TSH adoption**
   - out of scope for this Tutti landing
   - keep the TSH quarantine ledger available as reference material
   - migrate TSH only under a later dedicated plan if that product adopts the
     shared package

The Tutti vertical does not wait for TSH adapter migration. The shared package
is informed by the quarantined TSH port, but this plan is complete when the
Tutti local-terminal path is implemented, verified, and no longer failing its
checks.

## Tutti V1 Completion Checklist

The Tutti vertical is complete only when all required outcomes are implemented
and the runtime checks have been exercised in a running desktop workspace.

| Check                    | Required outcome                                                                                                                                                           | Current status                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Daemon session lifecycle | `tuttid` can create, list, inspect, resize, close-guard, terminate, snapshot, and stream local pty sessions.                                                               | Implemented and covered by focused Go tests.                                                                                                                                                                                                                                                                                                                                 |
| Live stream              | A renderer can attach to a session, receive replay after `afterSeq`, receive live output, write input, resize, detach, and observe exit.                                   | Implemented and runtime verified in Electron through xterm input, tuttid WebSocket write, daemon snapshot, and close exit.                                                                                                                                                                                                                                                   |
| Shared xterm surface     | The package owns xterm mount/dispose, fit, search, serialize, link detection, input queue, hydration, output scheduling, and screen cache behavior.                        | Implemented with package tests for pure helpers and runtime verified for mount, output, find UI, minimize, and remount.                                                                                                                                                                                                                                                      |
| Close flow               | Workbench close calls shared close flow, host close guard, and host terminate; detach never kills the process.                                                             | Implemented and runtime verified. tuttid now uses Unix pty foreground process group inspection so idle local shells close directly, foreground commands require confirmation, and unknown platforms remain conservative. Close confirmation currently enters through the workbench close callback; direct terminal-header dialog remains available for hosts that render it. |
| Minimize flow            | Minimize only changes workbench visibility and leaves the daemon session running.                                                                                          | Runtime verified: minimizing the terminal node kept the daemon session status `running`.                                                                                                                                                                                                                                                                                     |
| Desktop adapter          | `apps/desktop` maps tuttid HTTP/WebSocket APIs into `TerminalLaunchService`, `TerminalTransport`, close guard, diagnostics, link, and drop hooks.                          | Implemented and runtime verified against a real desktop window.                                                                                                                                                                                                                                                                                                              |
| Workbench registration   | `WorkspaceWorkbenchHostService` registers the terminal node definition and composes the terminal launch handler with existing launch behavior.                             | Implemented.                                                                                                                                                                                                                                                                                                                                                                 |
| Recovery                 | Restored workbench nodes bind to existing daemon sessions by `sessionId`; missing sessions project exited/lost state rather than silently creating a new process.          | Runtime verified: renderer reload reattached the same live `sessionId`; daemon-missing sessions now project `failed` after snapshot failure and do not create a replacement process.                                                                                                                                                                                         |
| Validation               | Package typecheck/test/build, desktop typecheck/test/build, i18n, generated API check, renderer-boundary check, TS lint, UI boundary check, and tuttid Go test/build pass. | Passed after the latest close-guard and adapter hardening.                                                                                                                                                                                                                                                                                                                   |

Do not call the migration complete merely because static checks pass. The V1
completion bar is a running desktop workspace where a local terminal can be
opened, used, resized, minimized, remounted, and closed with the expected
semantics.

## Runtime Verification Plan

Use this order when validating the current branch in `apps/desktop`:

1. Start the desktop app with the local daemon in development mode.
2. Open a workspace and launch a terminal from the workbench dock or launch
   intent.
3. Confirm a local pty starts in the expected requested cwd, or the daemon
   default cwd when no request is supplied, and renders an
   initial prompt.
4. Type input and verify it reaches the process through the WebSocket `input`
   path.
5. Resize the workbench panel/window and confirm the pty dimensions update
   without output corruption.
6. Run enough output to exercise scheduled writes, scrollback, find, URL links,
   and file-path links.
7. Minimize or hide the terminal node and confirm the session remains alive.
8. Remount or reopen the workbench node and confirm screen cache, snapshot
   hydration, and `afterSeq` replay reconcile without duplicated or missing
   visible output.
9. Close the terminal node. If the host reports foreground work, confirm the
   user is asked before `terminate`; otherwise close should terminate directly.
10. Stop the app and rerun package, desktop, client, generated API, and tuttid
    validation if any runtime fixes were made.

Record any runtime mismatch back in this document before changing package
contracts. If the mismatch is host-specific, prefer adapting the desktop or TSH
adapter rather than expanding terminal core.

### Runtime Verification Checkpoint

The first Electron runtime pass was completed against a local workspace window
using `pnpm --filter @tutti-os/desktop dev -- --remote-debugging-port=9223`.
Verified behavior:

- dock launch created a tuttid local pty session and rendered an xterm prompt
- created sessions used the requested cwd, or the daemon default home-directory
  cwd when none was supplied
- xterm input reached the shell through the WebSocket `input` path
- shell output appeared in the daemon snapshot and returned to the renderer
- find UI opened with search, case-sensitive, regex, previous, and next controls
- minimize hid the terminal node while the daemon session stayed `running`
- renderer reload restored the same terminal node by `sessionId` and reattached
  to the live daemon session
- the first Electron pass verified the workbench close path, confirmation
  cancellation, and terminal termination
- when the workbench snapshot referenced a terminal session that no longer
  existed in the in-memory daemon, the node projected `failed` after snapshot
  failure and did not silently create a replacement process

A second Electron runtime pass was completed after the close-guard precision
hardening:

- dock popup launch created a fresh tuttid local terminal session in the
  requested cwd
- xterm input reached the shell and daemon snapshot output included the
  `TUTTI_RUNTIME_VERIFY_1` marker
- closing an idle shell from the workbench window close button did not call
  `window.confirm` and the daemon session moved to `exited`
- running `sleep 30` made tuttid close guard return `foreground-process` with
  `requiresConfirmation: true` and a process label
- rejecting the foreground close confirmation kept the daemon session `running`
- accepting the foreground close confirmation terminated the daemon session and
  moved it to `exited`

Runtime mismatch found and fixed:

- after renderer reload, the desktop adapter lost in-memory session metadata and
  restored live terminals with the fallback title `Terminal`; `attach(...)` now
  reloads the session descriptor through tuttid before opening the WebSocket
- after daemon restart, stale terminal nodes stayed in the `created` projection
  when snapshot failed; `snapshot(...)` now records the failed projection in the
  desktop adapter before surfacing the error

## Current V1 Boundaries

These are deliberate boundaries for the current implementation:

- renderer selection uses xterm's default renderer; dormant TSH WebGL and pixel
  snapping code stays out of V1
- foreground-process confirmation is not implemented on Windows; the close guard
  reports `"not-running"` for idle shells without foreground-command detection
- file link detection is shared, but cwd resolution, VM/local path mapping, and
  open policy stay in host adapters
- drag/drop is a shared UI event hook only; each host decides accepted payloads,
  path mapping, and quoting
- output transforms are host-provided hooks; TSH-specific agent/query cleanup
  is not package behavior
- screen cache improves remount smoothness, but daemon snapshot and replay are
  still the authority for live terminal truth
- agent terminal behavior should be implemented as a wrapper or host adapter,
  not as branches inside terminal core

If runtime verification proves one of these boundaries is wrong, update this
document first with the reason, then adjust package contracts.

## Current Implementation Checkpoint

As of the current Tutti vertical checkpoint:

- `packages/workspace/terminal` exists as public package
  `@tutti-os/workspace-terminal`
- the package exposes `contracts`, `i18n`, `react`, `workbench`, and
  `styles.css` entrypoints
- shared contracts exist for transport, launch, close guard, diagnostics, link
  handling, drop input, output transform, session state, limits, and themes
- the feature factory normalizes host capabilities without constructing daemon
  clients, launching sessions, or reading product globals
- the workbench entrypoint provides both `createTerminalWorkbenchNodeDefinition`
  and `createTerminalWorkbenchLaunchHandler`, matching the current
  `WorkbenchHost` launch model
- the temporary TSH inventory ledger and copied renderer source snapshot have
  been deleted after promoted behavior landed
- the first promoted shared-core helpers cover scrollback truncation/merge,
  suffix-prefix overlap detection, initial terminal dimensions, session status
  projection, and committed screen-state cache semantics
- the shared React `TerminalNode` now mounts xterm using fit/search/serialize
  addons, hydrates from `TerminalTransport.snapshot(...)`, attaches with
  `afterSeq`, forwards terminal input to `TerminalTransport.write(...)`, sends
  resize events, and detaches the renderer stream on unmount
- the shared React surface now includes a first find bar, URL link activation
  through xterm's web-links addon, drag/drop routing through the host
  `dropInput` hook, and a shared close guard dialog for direct terminal-header
  closes
- file-path link detection is now promoted into shared core and connected to
  xterm's link provider API; it emits generic path, line, and column targets
  while host adapters still own path resolution and opening policy
- committed screen-state cache is now used by the React surface on remount:
  xterm serialized state is shown first for matching node/session identity and
  then reconciled against the daemon snapshot so daemon output remains
  authoritative
- terminal output writes are now scheduled in bounded batches using
  `TerminalNodeLimits.maxWriteBatchBytes`, preventing large output bursts from
  being pushed into xterm as one unbounded write
- the shared find UI now exposes case-sensitive and regex search options backed
  by xterm's search addon
- the package exposes `closeTerminalSession(...)` so workbench-level close
  paths can share the same close-guard and terminate semantics instead of
  treating close as transport detach
- the desktop renderer consumes the package i18n resources and stylesheet
  contract, registers the shared terminal node definition, composes the terminal
  launch handler with the existing files/browser launch handler, and provides a
  first tuttid-backed terminal adapter
- the desktop adapter reloads session descriptors during transport attach so
  renderer reloads can recover title, cwd, runtime kind, and status for live
  daemon sessions
- the desktop adapter projects snapshot failures into terminal external state so
  stale workbench nodes from missing daemon sessions render as failed instead of
  staying in a created-looking state
- the desktop adapter has focused unit coverage for attach-time session metadata
  recovery, snapshot-failure projection, WebSocket output/state/exit/write/detach
  routing, and host-owned link/drop policies
- `apps/desktop` wires WorkbenchHost terminal close requests through
  `closeTerminalSession(...)`, so the default window close button also
  terminates the daemon terminal session after close guard confirmation
- `apps/desktop` now provides terminal host policies for URL/file link handling
  and drag/drop input: dropped files are resolved through the desktop platform
  API and inserted as shell-quoted local paths, while file targets route through
  the host files API
- browser WebSocket clients cannot set `Authorization` headers, so tuttid
  bearer auth now accepts an `access_token` query parameter only for WebSocket
  upgrade requests; ordinary HTTP requests still require the bearer header
- the tuttid OpenAPI contract now defines terminal list/create/get/terminate,
  close-guard, resize, snapshot, and WebSocket attach routes; generated Go and
  TypeScript clients have been updated
- tuttid now has an in-memory local pty terminal service for list, create,
  get, terminate, resize, write, snapshot, close-guard, and attach-stream
  behavior
- tuttid close guard now inspects the Unix pty foreground process group: idle
  shells return `not-running` without confirmation, foreground commands return
  `foreground-process` with confirmation, and platforms where this cannot be
  inspected remain conservative
- the WebSocket attach route now uses a custom route handler for the real
  upgrade; the generated strict `AttachWorkspaceTerminal` method remains a
  service-unavailable fallback because oapi-codegen strict operation methods do
  not receive `http.ResponseWriter` or `*http.Request`
- the current WebSocket protocol supports client `input`, `resize`, `detach`,
  and `ping` frames plus server `output`, `state`, `gap`, `exit`, and `error`
  frames
- `@tutti-os/workspace-terminal` is included in the durable npm package release
  roster
- focused package validation has passed after the latest close-guard and adapter
  hardening for workspace-terminal typecheck/test/build, desktop
  typecheck/test/build, desktop renderer-boundary check, UI boundary check,
  i18n check, TS lint, tuttid Go test/build, client typecheck/test, and
  generated API checks

The package xterm surface and first Tutti desktop adapter have passed Electron
runtime verification. Further changes in this area should be treated as
post-landing hardening unless they uncover a concrete mismatch with the
contracts above.
