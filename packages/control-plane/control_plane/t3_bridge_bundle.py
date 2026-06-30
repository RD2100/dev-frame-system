"""T3 Code bridge bundle metadata and installable assets."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from .client_launcher import T3_RENDERER_CDP_DEFAULT_PORT, build_client_launch_plan


BRIDGE_NAME = "devframe-t3code-local-bridge"
T3_SOURCE_URL = "https://github.com/pingdotgg/t3code"
BRIDGE_SOURCE_RELATIVE_PATH = "apps/web/src/devframe/devframeShellBridge.ts"
BRIDGE_README_RELATIVE_PATH = "apps/web/src/devframe/README.md"
BRIDGE_SHELL_STATE_RELATIVE_PATH = "apps/web/src/state/shell.ts"
BRIDGE_THREAD_STATE_RELATIVE_PATH = "apps/web/src/state/threads.ts"
BRIDGE_CATALOG_RELATIVE_PATH = "apps/web/src/connection/catalog.ts"
BRIDGE_LOCAL_CONFIG_RELATIVE_PATH = "devframe.local.json"
BRIDGE_ENV_RELATIVE_PATH = ".env.devframe.local"
BRIDGE_T3_WEB_LAUNCHER_RELATIVE_PATH = "devframe.t3web.mjs"
BRIDGE_T3_DESKTOP_LAUNCHER_RELATIVE_PATH = "devframe.t3desktop.mjs"
BRIDGE_T3_DESKTOP_PROD_LAUNCHER_RELATIVE_PATH = "devframe.t3desktop.prod.mjs"


def build_t3_bridge_bundle(plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a machine-readable bundle that can be installed into a T3 checkout."""
    client_plan = plan or build_client_launch_plan()
    endpoints = client_plan["endpoints"]
    http_base_url = _base_url(endpoints["clientPlan"])
    return {
        "version": 1,
        "name": BRIDGE_NAME,
        "source": {
            "owner": "devframe-system",
            "contract": "t3_code_local_bridge_bundle",
            "devframeClientPlan": endpoints["clientPlan"],
        },
        "target": {
            "client": "t3code",
            "repository": T3_SOURCE_URL,
            "license": "MIT",
            "packageManager": "pnpm",
            "node": "^24",
            "apps": ["apps/web", "apps/desktop"],
        },
        "launch": {
            "devframe": client_plan["launch"],
            "t3DesktopCommand": "pnpm dev:desktop",
            "t3DesktopProdCommand": f"node {BRIDGE_T3_DESKTOP_PROD_LAUNCHER_RELATIVE_PATH}",
            "t3WebCommand": f"node {BRIDGE_T3_WEB_LAUNCHER_RELATIVE_PATH}",
        },
        # NOTE: VITE_DEVFRAME_T3_SHELL_URL is intentionally NOT injected here.
        #
        # That variable is the single switch that puts RD-Code into the
        # DevFrame read-only bridge mode: when present, the generated
        # catalog/shell/threads sources replace the native writable environment
        # with a synthetic read-only `devframe-local` view, and the provider,
        # source-control, and archive settings render read-only bridge notices.
        # In that mode the editor cannot add local project folders, configure
        # provider/API-key driven LLM backends, or edit projects.
        #
        # RD-Code is meant to be a fully usable native editor, so the bridge
        # overlay stays off by default and DevFrame's read model is surfaced
        # through the dashboard and MCP orchestration surface instead. The
        # DevFrame shell/team contract source is still generated for the
        # dashboard and future, explicitly opt-in re-integration.
        "environment": {
            "VITE_DEVFRAME_REALTIME_MODE": "polling",
            "VITE_DEVFRAME_CLIENT_PLAN_URL": endpoints["clientPlan"],
            "VITE_DEVFRAME_CLIENT_MANIFEST_URL": endpoints["manifest"],
            "VITE_HOSTED_APP_CHANNEL": "nightly",
        },
        "files": [
            {
                "path": BRIDGE_SOURCE_RELATIVE_PATH,
                "action": "add",
                "role": "Fetches DevFrame's T3 shell snapshot and exposes a small polling subscription.",
                "status": "ready",
            },
            {
                "path": BRIDGE_README_RELATIVE_PATH,
                "action": "add",
                "role": "Documents the T3-side wiring point without copying T3 source into DevFrame.",
                "status": "ready",
            },
            {
                "path": BRIDGE_LOCAL_CONFIG_RELATIVE_PATH,
                "action": "add",
                "role": "Machine-readable local binding for the T3 checkout.",
                "status": "ready",
            },
            {
                "path": BRIDGE_ENV_RELATIVE_PATH,
                "action": "add",
                "role": "Vite environment values for the local DevFrame control plane.",
                "status": "ready",
            },
            {
                "path": BRIDGE_T3_WEB_LAUNCHER_RELATIVE_PATH,
                "action": "add",
                "role": "Auxiliary fallback that starts T3 Web with DevFrame environment variables without overwriting T3's .env.local.",
                "status": "ready",
            },
            {
                "path": BRIDGE_T3_DESKTOP_LAUNCHER_RELATIVE_PATH,
                "action": "add",
                "role": "Primary launcher that starts T3 Desktop with DevFrame environment variables without overwriting T3's .env.local.",
                "status": "ready",
            },
            {
                "path": BRIDGE_T3_DESKTOP_PROD_LAUNCHER_RELATIVE_PATH,
                "action": "add",
                "role": "Production launcher that runs the prebuilt T3 Desktop (no Vite dev server or file watchers) for fast startup and low memory; builds once if no build is present.",
                "status": "ready",
            },
            {
                "path": BRIDGE_CATALOG_RELATIVE_PATH,
                "action": "patch",
                "role": "Falls back to T3's native writable environment catalog by default; only registers the read-only DevFrame environment when the (now opt-in) bridge shell URL is set.",
                "status": "ready",
            },
            {
                "path": BRIDGE_SHELL_STATE_RELATIVE_PATH,
                "action": "patch",
                "role": "Uses T3's native shell state by default; switches to DevFrame's read-only shell endpoint only when VITE_DEVFRAME_T3_SHELL_URL is set.",
                "status": "ready",
            },
            {
                "path": BRIDGE_THREAD_STATE_RELATIVE_PATH,
                "action": "patch",
                "role": "Uses T3's native thread detail state by default; switches to DevFrame's read-only threadDetails projection only when the bridge shell URL is set.",
                "status": "ready",
            },
        ],
        "integration": {
            "strategy": "reuse-t3-client-runtime-shell-and-thread-detail",
            "readModel": "OrchestrationShellSnapshot + OrchestrationThread",
            "pollIntervalMs": 2000,
            "mutationPolicy": "read-only",
            "nextRuntimeStep": f"Run DevFrame, install this bundle into a local T3 Code checkout with --force, then launch node {BRIDGE_T3_DESKTOP_LAUNCHER_RELATIVE_PATH} (primary) or node {BRIDGE_T3_WEB_LAUNCHER_RELATIVE_PATH} (auxiliary fallback).",
        },
        "acceptance": {
            "devframeServer": "devframe client serve --runtime-dir <runtime> --open",
            "t3Desktop": f"node {BRIDGE_T3_DESKTOP_LAUNCHER_RELATIVE_PATH}",
            "t3Web": f"node {BRIDGE_T3_WEB_LAUNCHER_RELATIVE_PATH}",
            "expected": [
                "T3 Code (RD-Code) launches as a fully usable native editor: add local project folders, configure provider/API-key LLM backends, and edit projects.",
                "OpenCode remains the executor surfaced by DevFrame sessions.",
                "DevFrame read model and orchestration are reached through the dashboard and MCP surface; the in-editor read-only overlay stays off unless VITE_DEVFRAME_T3_SHELL_URL is explicitly set.",
            ],
        },
    }


def render_t3_bridge_bundle_json(bundle: dict[str, Any] | None = None) -> str:
    return json.dumps(bundle or build_t3_bridge_bundle(), indent=2, ensure_ascii=True)


def render_t3_bridge_bundle_text(bundle: dict[str, Any]) -> str:
    env = bundle["environment"]
    lines = [
        "DevFrame T3 Code bridge bundle",
        f"name        : {bundle['name']}",
        f"client      : {bundle['target']['client']} ({bundle['target']['license']})",
        f"mode        : native editor (DevFrame read-only overlay off by default)",
        f"manifest    : {env['VITE_DEVFRAME_CLIENT_MANIFEST_URL']}",
        f"client plan : {env['VITE_DEVFRAME_CLIENT_PLAN_URL']}",
        f"strategy    : {bundle['integration']['strategy']}",
        f"write policy: {bundle['integration']['mutationPolicy']}",
        "",
        "Installable files",
    ]
    for file_entry in bundle["files"]:
        lines.append(f"- {file_entry['action']}: {file_entry['path']} ({file_entry['status']})")
    lines.extend([
        "",
        "Next T3 step",
        f"- {bundle['integration']['nextRuntimeStep']}",
    ])
    return "\n".join(lines) + "\n"


def write_t3_bridge_bundle(output_dir: str | Path, bundle: dict[str, Any]) -> list[Path]:
    """Write a standalone bridge bundle directory for review or packaging."""
    root = Path(output_dir).resolve()
    return _write_bridge_files(root, bundle, require_t3_root=False, force=True)


def install_t3_bridge_bundle(t3_root: str | Path, bundle: dict[str, Any], *, force: bool = False) -> list[Path]:
    """Install bridge files into a local T3 Code checkout without touching existing T3 files."""
    root = Path(t3_root).resolve()
    package_json = root / "package.json"
    apps_web = root / "apps" / "web"
    if not package_json.exists() or not apps_web.is_dir():
        raise ValueError(f"not a T3 Code checkout: {root}")
    return _write_bridge_files(root, bundle, require_t3_root=True, force=force)


def render_bridge_source() -> str:
    return """export type DevFrameThreadKind =
  | "native_chat"
  | "goal_conversation"
  | "global_coordinator";

export type DevFrameCoordinatorScope = "none" | "project" | "global";

export interface DevFrameProjectBinding {
  readonly mode: "required" | "optional" | "none";
  readonly projectId: string;
  readonly status: "bound" | "missing" | "not-applicable";
}

export interface DevFrameConversationModel {
  readonly globalCoordinatorThreadId: string;
  readonly goalProjectBindingRequired: boolean;
  readonly threadKinds: readonly DevFrameThreadKind[];
}

export interface DevFrameT3ThreadShell {
  readonly id: string;
  readonly projectId: string;
  readonly title: string;
  readonly threadKind: DevFrameThreadKind;
  readonly coordinatorScope: DevFrameCoordinatorScope;
  readonly projectBinding: DevFrameProjectBinding;
}

export interface DevFrameT3ShellSnapshot {
  readonly snapshotSequence: number;
  readonly projects: readonly unknown[];
  readonly threads: readonly DevFrameT3ThreadShell[];
  readonly threadDetails?: readonly DevFrameThreadDetail[];
  readonly updatedAt: string;
}

export type DevFrameThreadDetail = Record<string, unknown> &
  DevFrameThreadTeamRefs & {
    readonly threadKind?: DevFrameThreadKind;
    readonly coordinatorScope?: DevFrameCoordinatorScope;
    readonly projectBinding?: DevFrameProjectBinding;
  };

export interface DevFrameTeamAgent {
  readonly agentId: string;
  readonly role: string;
  readonly bindingId: string;
  readonly status: string;
  readonly sessionIds: readonly string[];
}

export interface DevFrameTeamTask {
  readonly taskId: string;
  readonly type: string;
  readonly projectId: string;
  readonly status: string;
  readonly agentIds: readonly string[];
  readonly sessionIds: readonly string[];
  readonly targetFiles: readonly string[];
}

export interface DevFrameTeamMessage {
  readonly messageId: string;
  readonly fromRole: string;
  readonly toRole: string;
  readonly kind: string;
  readonly runId: string;
  readonly summary: string;
}

export interface DevFrameTeamEvent {
  readonly eventId: string;
  readonly kind: string;
  readonly runId: string;
  readonly summary: string;
}

export interface DevFrameTeamEvidence {
  readonly evidenceId: string;
  readonly runId: string;
  readonly refType: string;
  readonly refPath: string;
}

export interface DevFrameTeamGate {
  readonly gateId: string;
  readonly kind: string;
  readonly status: string;
  readonly reason: string;
  readonly runId: string;
}

export interface DevFrameTeamConflict {
  readonly filePath: string;
  readonly ownerRunId: string;
  readonly ownerAgentId: string;
  readonly fileKind: string;
}

export interface DevFrameTeamProjection {
  readonly agentRegistry: readonly DevFrameTeamAgent[];
  readonly taskBoard: readonly DevFrameTeamTask[];
  readonly messageBus: readonly DevFrameTeamMessage[];
  readonly eventLog: readonly DevFrameTeamEvent[];
  readonly evidenceStore: readonly DevFrameTeamEvidence[];
  readonly reviewGates: readonly DevFrameTeamGate[];
  readonly conflictControl: readonly DevFrameTeamConflict[];
}

export interface DevFrameThreadTeamRefs {
  readonly teamTaskIds: readonly string[];
  readonly teamMessageIds: readonly string[];
  readonly teamEvidenceIds: readonly string[];
  readonly teamReviewGateIds: readonly string[];
  readonly teamConflictFiles: readonly string[];
}

export interface DevFrameT3ShellEnvelope {
  readonly version: number;
  readonly source: "devframe";
  readonly t3: DevFrameT3ShellSnapshot;
  readonly devframe: {
    readonly conversationModel: DevFrameConversationModel;
    readonly team: DevFrameTeamProjection;
  };
}

export interface DevFrameShellBridgeConfig {
  readonly shellUrl: string;
  readonly pollIntervalMs?: number;
}

interface DevFrameBridgeEnv {
  readonly VITE_DEVFRAME_T3_SHELL_URL?: string;
}

export type DevFrameShellListener = (snapshot: DevFrameT3ShellSnapshot) => void;
export type DevFrameShellErrorListener = (error: unknown) => void;

const DEFAULT_POLL_INTERVAL_MS = 2000;

export function readDevFrameShellBridgeConfig(
  env: DevFrameBridgeEnv = import.meta.env as DevFrameBridgeEnv,
): DevFrameShellBridgeConfig | null {
  const shellUrl = env.VITE_DEVFRAME_T3_SHELL_URL?.trim();
  if (!shellUrl) return null;
  return { shellUrl };
}

export async function fetchDevFrameT3ShellEnvelope(
  config: DevFrameShellBridgeConfig,
): Promise<DevFrameT3ShellEnvelope> {
  const response = await fetch(config.shellUrl, {
    method: "GET",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`DevFrame shell request failed: ${response.status}`);
  }
  const envelope = (await response.json()) as DevFrameT3ShellEnvelope;
  if (envelope.source !== "devframe" || !envelope.t3) {
    throw new Error("DevFrame shell response is not a T3 shell envelope.");
  }
  return envelope;
}

export async function fetchDevFrameT3Shell(
  config: DevFrameShellBridgeConfig,
): Promise<DevFrameT3ShellSnapshot> {
  return (await fetchDevFrameT3ShellEnvelope(config)).t3;
}

export function subscribeDevFrameT3Shell(
  config: DevFrameShellBridgeConfig,
  onSnapshot: DevFrameShellListener,
  onError: DevFrameShellErrorListener = console.warn,
): () => void {
  let disposed = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const pollIntervalMs = config.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;

  const poll = async () => {
    try {
      onSnapshot(await fetchDevFrameT3Shell(config));
    } catch (error) {
      onError(error);
    } finally {
      if (!disposed) timer = setTimeout(poll, pollIntervalMs);
    }
  };

  void poll();
  return () => {
    disposed = true;
    if (timer !== undefined) clearTimeout(timer);
  };
}
"""


def render_bridge_readme(bundle: dict[str, Any]) -> str:
    env = bundle["environment"]
    return f"""# DevFrame T3 Bridge

This directory is generated by `devframe client bridge`.

The bridge keeps T3 Code as the visual client and points it at DevFrame's
read-only local Agent Control Plane. DevFrame does not expose a WebSocket
endpoint, so the T3 client runs in polling mode using HTTP snapshots only.

## Runtime URLs

- realtime mode: `{env["VITE_DEVFRAME_REALTIME_MODE"]}`
- client plan: `{env["VITE_DEVFRAME_CLIENT_PLAN_URL"]}`
- manifest: `{env["VITE_DEVFRAME_CLIENT_MANIFEST_URL"]}`

> The read-only DevFrame shell overlay is off by default. RD-Code runs as a
> fully native editor. To opt into the legacy read-only bridge view, set
> `VITE_DEVFRAME_T3_SHELL_URL` to the DevFrame `/t3-shell.json` endpoint.

## Launch

Run `node {BRIDGE_T3_DESKTOP_LAUNCHER_RELATIVE_PATH}` from the T3 checkout root for the primary desktop experience, or `node {BRIDGE_T3_WEB_LAUNCHER_RELATIVE_PATH}` as an auxiliary fallback. Each launcher sets DevFrame-specific Vite variables in the child process and then runs the corresponding T3 dev command, so they do not need to overwrite T3's `.env.local`.

## Wiring point

`apps/web/src/state/shell.ts` and `apps/web/src/state/threads.ts` are generated
as the T3-side wiring points. They keep T3's native commands available, but
when `VITE_DEVFRAME_T3_SHELL_URL` is present they load shell snapshots and
thread detail snapshots from DevFrame instead of the native orchestration
streams. `apps/web/src/connection/catalog.ts` is also generated so T3's project
and thread views can see the DevFrame local environment in the catalog. The
desktop app can then reuse the web shell through the existing T3 desktop
wrapper.

The bridge is intentionally read-only. Future write actions must stay behind a
DevFrame human gate.

## DevFrame Team Contract

The bridge exports a typed team projection contract (`DevFrameTeamProjection`) with
seven top-level collections that mirror the devframe `team` block in
`CONTROL_PLANE_STATE.yaml`:

- `agentRegistry` — registered agents with role, binding, and session links.
- `taskBoard` — dispatched tasks with agent assignments and target files.
- `messageBus` — inter-agent coordination messages.
- `eventLog` — team-scoped dispatch and lifecycle events.
- `evidenceStore` — evidence references keyed by run.
- `reviewGates` — human and acceptance gates for team runs.
- `conflictControl` — file-level ownership records for conflict detection.

Per-thread team references (`DevFrameThreadTeamRefs`) are also typed so T3 consumers
can identify which tasks, messages, evidence, review gates, and conflict files are
linked to a given session.

Import the types from `devframeShellBridge` and use `fetchDevFrameT3ShellEnvelope()`
to access the full envelope including the `devframe.team` payload.
"""


def render_catalog_source(env: dict[str, str] | None = None) -> str:
    env = env or {}
    realtime_mode = env.get("VITE_DEVFRAME_REALTIME_MODE", "polling")
    ws_base_url_line = f'          wsBaseUrl: devFrameWsBaseUrl(),\n'

    return f"""import {{ PrimaryConnectionTarget, type SupervisorConnectionState }} from "@t3tools/client-runtime/connection";
import {{ createEnvironmentCatalogAtoms, type EnvironmentCatalogState }} from "@t3tools/client-runtime/state/connections";
import {{ EnvironmentId }} from "@t3tools/contracts";
import * as Option from "effect/Option";
import {{ AsyncResult, Atom }} from "effect/unstable/reactivity";

import {{ readDevFrameShellBridgeConfig }} from "../devframe/devframeShellBridge";
import {{ connectionAtomRuntime }} from "./runtime";

const nativeEnvironmentCatalog = createEnvironmentCatalogAtoms(connectionAtomRuntime);
const devFrameConfig = readDevFrameShellBridgeConfig();
const DEVFRAME_ENVIRONMENT_ID = EnvironmentId.make("devframe-local");
const DEVFRAME_LABEL = "DevFrame Local Agent Control Plane";

function devFrameHttpBaseUrl(): string {{
  return devFrameConfig === null ? "http://127.0.0.1:8765/" : new URL("/", devFrameConfig.shellUrl).toString();
}}

function devFrameWsBaseUrl(): string {{
  const url = new URL(devFrameHttpBaseUrl());
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}}

const DEVFRAME_CATALOG_STATE: EnvironmentCatalogState = {{
  isReady: true,
  entries: new Map([
    [
      DEVFRAME_ENVIRONMENT_ID,
      {{
        target: new PrimaryConnectionTarget({{
          environmentId: DEVFRAME_ENVIRONMENT_ID,
          label: DEVFRAME_LABEL,
          httpBaseUrl: devFrameHttpBaseUrl(),
{ws_base_url_line}        }}),
        profile: Option.none(),
      }},
    ],
  ]),
}};

const DEVFRAME_CONNECTED_STATE: SupervisorConnectionState = {{
  desired: false,
  network: "online",
  phase: "connected",
  stage: "polling",
  attempt: 0,
  generation: 1,
  lastFailure: null,
  retryAt: null,
}};

function createDevFrameEnvironmentCatalogAtoms() {{
  return {{
    ...nativeEnvironmentCatalog,
    catalogAtom: Atom.make(AsyncResult.success(DEVFRAME_CATALOG_STATE)).pipe(
      Atom.withLabel("devframe-environment-catalog"),
    ),
    catalogValueAtom: Atom.make(DEVFRAME_CATALOG_STATE).pipe(
      Atom.withLabel("devframe-environment-catalog-value"),
    ),
    networkStatusAtom: Atom.make(AsyncResult.success("online" as const)).pipe(
      Atom.withLabel("devframe-environment-network-status"),
    ),
    networkStatusValueAtom: Atom.make("online" as const).pipe(
      Atom.withLabel("devframe-environment-network-status-value"),
    ),
    realtimeModeAtom: Atom.make("{realtime_mode}" as const).pipe(
      Atom.withLabel("devframe-environment-realtime-mode"),
    ),
    realtimeModeValueAtom: Atom.make("{realtime_mode}" as const).pipe(
      Atom.withLabel("devframe-environment-realtime-mode-value"),
    ),
    stateAtom: Atom.family((environmentId: EnvironmentId) =>
      Atom.make(AsyncResult.success(DEVFRAME_CONNECTED_STATE)).pipe(
        Atom.withLabel(`devframe-environment-state:${{environmentId}}`),
      ),
    ),
  }};
}}

export const environmentCatalog =
  devFrameConfig === null ? nativeEnvironmentCatalog : createDevFrameEnvironmentCatalogAtoms();
"""


def render_t3_web_launcher_source(bundle: dict[str, Any]) -> str:
    env = bundle["environment"]
    env_json = json.dumps(env, indent=2, ensure_ascii=True)
    return f"""#!/usr/bin/env node
import {{ spawn }} from "node:child_process";
import {{ fileURLToPath }} from "node:url";
import {{ dirname }} from "node:path";

const devframeEnv = {env_json};
const root = dirname(fileURLToPath(import.meta.url));
const isWindows = process.platform === "win32";
const command = isWindows ? "pnpm" : "pnpm";
const args = ["--filter", "@t3tools/web", "dev"];
const childEnv = {{ ...process.env, ...devframeEnv }};

console.log("[devframe] Starting T3 Web with DevFrame local control plane.");
console.log(`[devframe] DevFrame env applied (native editor mode; client plan ${{devframeEnv.VITE_DEVFRAME_CLIENT_PLAN_URL}}).`);

const child = spawn(command, args, {{
  cwd: root,
  env: childEnv,
  stdio: "inherit",
  shell: isWindows,
}});

child.on("error", (error) => {{
  console.error(`[devframe] Failed to start T3 Web: ${{error.message}}`);
  process.exit(1);
}});

child.on("exit", (code, signal) => {{
  if (signal) {{
    process.kill(process.pid, signal);
    return;
  }}
  process.exit(code ?? 1);
}});
"""


def render_t3_desktop_launcher_source(bundle: dict[str, Any]) -> str:
    env = bundle["environment"]
    env_json = json.dumps(env, indent=2, ensure_ascii=True)
    direct_renderer_marker = "// devframe-direct-renderer: patched"
    patched_lines = [
        direct_renderer_marker,
        "    const applicationUrl =",
        '      process.env.T3CODE_DEVFRAME_DIRECT_RENDERER === "1" && environment.isDevelopment',
        "        ? Option.match(environment.devServerUrl, {",
        '            onSome: (url) => url.toString(),',
        '            onNone: () => getDesktopUrl(environment.isDevelopment),',
        "          })",
        "        : getDesktopUrl(environment.isDevelopment);",
    ]
    patched_desktop_window_block = "\n".join(patched_lines)
    remote_debugging_marker = "// devframe-remote-debugging-origin: patched"
    patched_dev_electron_lines = [
        remote_debugging_marker,
        "  const devframeDebugPort = process.env.T3CODE_DESKTOP_REMOTE_DEBUGGING_PORT || remoteDebuggingPort;",
        "  const cdpAllowOrigin = process.env.T3CODE_CDP_ALLOW_ORIGIN || devServer.origin;",
        "  const electronArgs = devframeDebugPort",
        "    ? [",
        "        `--remote-debugging-port=${devframeDebugPort}`,",
        '        "--remote-debugging-address=127.0.0.1",',
        "        `--remote-allow-origins=${cdpAllowOrigin}`,",
        "      ]",
        "    : [];",
    ]
    patched_dev_electron_block = "\n".join(patched_dev_electron_lines)
    dev_electron_upstream_block = (
        "  const electronArgs = remoteDebuggingPort\n"
        "    ? [`--remote-debugging-port=${remoteDebuggingPort}`]\n"
        "    : [];"
    )
    return f"""#!/usr/bin/env node
import {{ spawn }} from "node:child_process";
import {{ fileURLToPath }} from "node:url";
import {{ dirname, join }} from "node:path";
import {{ readFileSync, writeFileSync }} from "node:fs";

const devframeEnv = {env_json};
const root = dirname(fileURLToPath(import.meta.url));
const isWindows = process.platform === "win32";
const command = isWindows ? "pnpm" : "pnpm";
const args = ["dev:desktop"];
const childEnv = {{ ...process.env, ...devframeEnv }};
childEnv.T3CODE_DEVFRAME_DIRECT_RENDERER = "1";
childEnv.T3CODE_DESKTOP_REMOTE_DEBUGGING_PORT =
    process.env.T3CODE_DESKTOP_REMOTE_DEBUGGING_PORT ||
    childEnv.T3CODE_DESKTOP_REMOTE_DEBUGGING_PORT ||
    "{T3_RENDERER_CDP_DEFAULT_PORT}";
if (process.env.T3CODE_DEVFRAME_CDP_ALLOW_ORIGIN) {{
  childEnv.T3CODE_CDP_ALLOW_ORIGIN = process.env.T3CODE_DEVFRAME_CDP_ALLOW_ORIGIN;
}}

const desktopWindowPath = join(root, "apps", "desktop", "src", "window", "DesktopWindow.ts");
const desktopWindowMarker = {json.dumps(direct_renderer_marker)};
const desktopWindowUpstreamLine = {json.dumps("    const applicationUrl = getDesktopUrl(environment.isDevelopment);")};
const desktopWindowPatchedBlock = {json.dumps(patched_desktop_window_block)};
const devElectronPath = join(root, "apps", "desktop", "scripts", "dev-electron.mjs");
const devElectronMarker = {json.dumps(remote_debugging_marker)};
const devElectronUpstreamBlock = {json.dumps(dev_electron_upstream_block)};
const devElectronPatchedBlock = {json.dumps(patched_dev_electron_block)};
const devElectronNextLine = "  const launchArgs = devProtocolClient";

let desktopWindowContent = null;
try {{
  desktopWindowContent = readFileSync(desktopWindowPath, "utf8");
}} catch {{
  console.error(`[devframe] DesktopWindow.ts not found at ${{desktopWindowPath}}; cannot apply direct-renderer patch.`);
  process.exit(1);
}}

if (!desktopWindowContent.includes(desktopWindowMarker)) {{
  if (!desktopWindowContent.includes(desktopWindowUpstreamLine)) {{
    console.error(`[devframe] Cannot apply direct-renderer patch: upstream line not found in DesktopWindow.ts and no marker present.`);
    process.exit(1);
  }}
  const patched = desktopWindowContent.replace(desktopWindowUpstreamLine, desktopWindowPatchedBlock);
  writeFileSync(desktopWindowPath, patched, "utf8");
  console.log("[devframe] Patched DesktopWindow.ts for direct renderer.");
}} else {{
  console.log("[devframe] DesktopWindow.ts already patched for direct renderer.");
}}

function replaceDevElectronMarkedBlock(content) {{
  const start = content.indexOf(devElectronMarker);
  if (start < 0) return null;
  const end = content.indexOf(devElectronNextLine, start);
  if (end < 0) return null;
  return content.slice(0, start) + devElectronPatchedBlock + "\\n" + content.slice(end);
}}

let devElectronContent = null;
try {{
  devElectronContent = readFileSync(devElectronPath, "utf8");
}} catch {{
  console.error(`[devframe] dev-electron.mjs not found at ${{devElectronPath}}; cannot apply remote debugging origin patch.`);
  process.exit(1);
}}

if (!devElectronContent.includes(devElectronMarker)) {{
  if (!devElectronContent.includes(devElectronUpstreamBlock)) {{
    console.error(`[devframe] Cannot apply remote debugging origin patch: upstream block not found in dev-electron.mjs and no marker present.`);
    process.exit(1);
  }}
  const patched = devElectronContent.replace(devElectronUpstreamBlock, devElectronPatchedBlock);
  writeFileSync(devElectronPath, patched, "utf8");
  console.log("[devframe] Patched dev-electron.mjs for loopback remote debugging.");
}} else if (!devElectronContent.includes(devElectronPatchedBlock)) {{
  const patched = replaceDevElectronMarkedBlock(devElectronContent);
  if (patched === null) {{
    console.error(`[devframe] Cannot upgrade remote debugging origin patch: marker found but following launchArgs anchor is missing.`);
    process.exit(1);
  }}
  writeFileSync(devElectronPath, patched, "utf8");
  console.log("[devframe] Upgraded dev-electron.mjs loopback remote debugging patch.");
}} else {{
  console.log("[devframe] dev-electron.mjs already patched for loopback remote debugging.");
}}

console.log("[devframe] Starting T3 Desktop with DevFrame local control plane.");
console.log(`[devframe] DevFrame env applied (native editor mode; client plan ${{devframeEnv.VITE_DEVFRAME_CLIENT_PLAN_URL}}).`);

const child = spawn(command, args, {{
  cwd: root,
  env: childEnv,
  stdio: "inherit",
  shell: isWindows,
}});

child.on("error", (error) => {{
  console.error(`[devframe] Failed to start T3 Desktop: ${{error.message}}`);
  process.exit(1);
}});

child.on("exit", (code, signal) => {{
  if (signal) {{
    process.kill(process.pid, signal);
    return;
  }}
  process.exit(code ?? 1);
}});
"""


def render_t3_desktop_prod_launcher_source(bundle: dict[str, Any]) -> str:
    """Production launcher: run the prebuilt T3 Desktop (no Vite dev server).

    Dev mode (`pnpm dev:desktop`) keeps a Vite dev server plus file watchers
    resident and recompiles the renderer on every launch, which is the root
    cause of slow startup and high memory use for day-to-day product use. This
    launcher instead runs the production build:

    - If no build is present (or ``--build`` / ``DEVFRAME_T3_FORCE_BUILD=1`` is
      set) it runs ``pnpm build:desktop`` once with the DevFrame Vite variables
      set, so the client-plan/manifest URLs are inlined into the built bundle.
    - It then runs ``pnpm start:desktop``, which launches Electron against the
      built renderer with no dev server and no watchers.
    """
    env = bundle["environment"]
    # The production renderer connects to the desktop's own spawned local
    # server. VITE_HOSTED_APP_CHANNEL must NOT be baked into the desktop build:
    # `isHostedStaticApp()` treats any configured hosted channel as "this is the
    # hosted browser app" and short-circuits into the read-only onboarding
    # surface ("Connect an environment to get started"), which hides local
    # projects and the native editor. In dev that var is harmless because the
    # dev server injects VITE_HTTP_URL (a configured backend) which takes
    # precedence; the production build has no such backend URL, so the channel
    # would otherwise force hosted-static mode.
    prod_env = {k: v for k, v in env.items() if k != "VITE_HOSTED_APP_CHANNEL"}
    # Give the desktop client a distinct RD-Code Windows AppUserModelID. Windows
    # caches the taskbar icon per AppUserModelID, so the upstream default keeps
    # resurrecting the old T3 taskbar icon from cache even after the icon assets
    # are replaced. A separate RD-Code identity makes the OS use the current
    # window icon (apps/desktop/resources/icon.ico). Read at runtime via the
    # T3CODE_DESKTOP_APP_USER_MODEL_ID override, so no rebuild is required. This
    # is injected only into the generated launcher (not the schema-validated
    # bundle environment).
    prod_env["T3CODE_DESKTOP_APP_USER_MODEL_ID"] = "com.rdcode.client"
    env_json = json.dumps(prod_env, indent=2, ensure_ascii=True)
    return f"""#!/usr/bin/env node
import {{ spawn }} from "node:child_process";
import {{ fileURLToPath }} from "node:url";
import {{ dirname, join }} from "node:path";
import {{ existsSync }} from "node:fs";

const devframeEnv = {env_json};
const root = dirname(fileURLToPath(import.meta.url));
const isWindows = process.platform === "win32";
// DevFrame Vite variables must be present at BUILD time because Vite inlines
// `import.meta.env.VITE_*` into the production bundle.
const childEnv = {{ ...process.env, ...devframeEnv }};

const builtRenderer = join(root, "apps", "web", "dist", "index.html");
const builtMain = join(root, "apps", "desktop", "dist-electron", "main.cjs");

function run(args) {{
  return new Promise((resolve, reject) => {{
    const child = spawn("pnpm", args, {{
      cwd: root,
      env: childEnv,
      stdio: "inherit",
      shell: isWindows,
    }});
    child.on("error", reject);
    child.on("exit", (code, signal) => {{
      if (signal) {{
        process.kill(process.pid, signal);
        return;
      }}
      resolve(code ?? 0);
    }});
  }});
}}

const forceBuild =
  process.argv.includes("--build") || process.env.DEVFRAME_T3_FORCE_BUILD === "1";
const needsBuild = forceBuild || !existsSync(builtRenderer) || !existsSync(builtMain);

if (needsBuild) {{
  console.log("[devframe] Building T3 Desktop (production). This is a one-time step and can take a few minutes.");
  const buildCode = await run(["build:desktop"]);
  if (buildCode !== 0) {{
    console.error(`[devframe] Production build failed with exit code ${{buildCode}}.`);
    process.exit(buildCode);
  }}
}}

console.log("[devframe] Starting T3 Desktop (production build; no dev server, low memory).");
console.log(`[devframe] DevFrame env baked at build time (client plan ${{devframeEnv.VITE_DEVFRAME_CLIENT_PLAN_URL}}).`);

const startCode = await run(["start:desktop"]);
process.exit(startCode);
"""


def render_shell_state_source() -> str:
    return """import {
  createEnvironmentShellAtoms,
  createEnvironmentShellSummaryAtom,
  createEnvironmentSnapshotAtom,
  createShellEnvironmentAtoms,
  type EnvironmentShellState,
} from "@t3tools/client-runtime/state/shell";
import type { EnvironmentId, OrchestrationShellSnapshot } from "@t3tools/contracts";
import * as Effect from "effect/Effect";
import * as Option from "effect/Option";
import { AsyncResult, Atom } from "effect/unstable/reactivity";

import {
  fetchDevFrameT3Shell,
  readDevFrameShellBridgeConfig,
  type DevFrameT3ShellSnapshot,
} from "../devframe/devframeShellBridge";
import { environmentCatalog } from "../connection/catalog";
import { connectionAtomRuntime } from "../connection/runtime";

const nativeEnvironmentShell = createEnvironmentShellAtoms(connectionAtomRuntime);
const devFrameConfig = readDevFrameShellBridgeConfig();

const EMPTY_DEVFRAME_SHELL_STATE: EnvironmentShellState = {
  snapshot: Option.none(),
  status: "empty",
  error: Option.none(),
};

class DevFrameShellLoadError extends Error {
  override readonly name = "DevFrameShellLoadError";
}

function toDevFrameShellLoadError(cause: unknown): DevFrameShellLoadError {
  const message = cause instanceof Error ? cause.message : String(cause);
  return new DevFrameShellLoadError(message);
}

function devFrameSnapshotState(snapshot: DevFrameT3ShellSnapshot): EnvironmentShellState {
  return {
    snapshot: Option.some(snapshot as OrchestrationShellSnapshot),
    status: "live",
    error: Option.none(),
  };
}

function devFrameErrorState(error: unknown): EnvironmentShellState {
  const message = error instanceof Error ? error.message : String(error);
  return {
    snapshot: Option.none(),
    status: "empty",
    error: Option.some(message),
  };
}

function loadDevFrameShellState(): Effect.Effect<EnvironmentShellState> {
  if (devFrameConfig === null) {
    return Effect.succeed(EMPTY_DEVFRAME_SHELL_STATE);
  }
  return Effect.tryPromise({
    try: () => fetchDevFrameT3Shell(devFrameConfig),
    catch: toDevFrameShellLoadError,
  }).pipe(
    Effect.map(devFrameSnapshotState),
    Effect.catch((error: DevFrameShellLoadError) => Effect.succeed(devFrameErrorState(error))),
  );
}

function createDevFrameEnvironmentShellAtoms() {
  const stateAtom = Atom.family((environmentId: EnvironmentId) =>
    Atom.make(loadDevFrameShellState()).pipe(
      Atom.swr({
        staleTime: 0,
        revalidateOnMount: true,
      }),
      Atom.withRefresh(2000),
      Atom.setIdleTTL(0),
      Atom.withLabel(`devframe-environment-shell-state:${environmentId}`),
    ),
  );

  const stateValueAtom = Atom.family((environmentId: EnvironmentId) =>
    Atom.make((get) =>
      Option.getOrElse(
        AsyncResult.value(get(stateAtom(environmentId))),
        () => EMPTY_DEVFRAME_SHELL_STATE,
      ),
    ).pipe(Atom.withLabel(`devframe-environment-shell-state-value:${environmentId}`)),
  );

  return {
    stateAtom,
    stateValueAtom,
  };
}

export const shellEnvironment = createShellEnvironmentAtoms(connectionAtomRuntime);
export const environmentShell =
  devFrameConfig === null ? nativeEnvironmentShell : createDevFrameEnvironmentShellAtoms();
export const environmentSnapshotAtom = createEnvironmentSnapshotAtom(environmentShell.stateAtom);
export const environmentShellSummaryAtom = createEnvironmentShellSummaryAtom({
  catalogValueAtom: environmentCatalog.catalogValueAtom,
  shellStateValueAtom: environmentShell.stateValueAtom,
});
"""


def render_thread_state_source() -> str:
    return """import { useAtomValue } from "@effect/atom-react";
import {
  createEnvironmentThreadDetailAtoms,
  createEnvironmentThreadShellAtoms,
  createEnvironmentThreadStateAtoms,
  EMPTY_ENVIRONMENT_THREAD_STATE,
  type EnvironmentThreadState,
  createThreadEnvironmentAtoms,
} from "@t3tools/client-runtime/state/threads";
import type { EnvironmentId, OrchestrationThread, ThreadId } from "@t3tools/contracts";
import * as Effect from "effect/Effect";
import * as Option from "effect/Option";
import { AsyncResult, Atom } from "effect/unstable/reactivity";

import {
  fetchDevFrameT3Shell,
  readDevFrameShellBridgeConfig,
  type DevFrameT3ShellSnapshot,
} from "../devframe/devframeShellBridge";
import { environmentCatalog } from "../connection/catalog";
import { connectionAtomRuntime } from "../connection/runtime";
import { environmentSnapshotAtom } from "./shell";
import { parseThreadKey, threadKey } from "@t3tools/client-runtime/state/entities";

const nativeThreadEnvironment = createThreadEnvironmentAtoms(connectionAtomRuntime);
const nativeEnvironmentThreads = createEnvironmentThreadStateAtoms(connectionAtomRuntime);
const devFrameConfig = readDevFrameShellBridgeConfig();

class DevFrameThreadLoadError extends Error {
  override readonly name = "DevFrameThreadLoadError";
}

function toDevFrameThreadLoadError(cause: unknown): DevFrameThreadLoadError {
  const message = cause instanceof Error ? cause.message : String(cause);
  return new DevFrameThreadLoadError(message);
}

function hasThreadId(candidate: unknown, threadId: ThreadId): candidate is { readonly id: ThreadId } {
  return (
    typeof candidate === "object" &&
    candidate !== null &&
    (candidate as { readonly id?: unknown }).id === threadId
  );
}

function findDevFrameThreadDetail(
  snapshot: DevFrameT3ShellSnapshot,
  threadId: ThreadId,
): OrchestrationThread | null {
  const projectedDetail = snapshot.threadDetails?.find((candidate) => hasThreadId(candidate, threadId));
  if (projectedDetail !== undefined) {
    return projectedDetail as OrchestrationThread;
  }

  const shellThread = snapshot.threads.find((candidate) => hasThreadId(candidate, threadId));
  if (shellThread === undefined) {
    return null;
  }

  return {
    ...(shellThread as Record<string, unknown>),
    deletedAt: null,
    messages: [],
    proposedPlans: [],
    activities: [],
    checkpoints: [],
  } as unknown as OrchestrationThread;
}

function devFrameThreadState(
  snapshot: DevFrameT3ShellSnapshot,
  threadId: ThreadId,
): EnvironmentThreadState {
  const thread = findDevFrameThreadDetail(snapshot, threadId);
  if (thread === null) {
    return EMPTY_ENVIRONMENT_THREAD_STATE;
  }
  return {
    data: Option.some(thread),
    status: "live",
    error: Option.none(),
  };
}

function devFrameThreadErrorState(error: unknown): EnvironmentThreadState {
  const message = error instanceof Error ? error.message : String(error);
  return {
    data: Option.none(),
    status: "empty",
    error: Option.some(message),
  };
}

function loadDevFrameThreadState(threadId: ThreadId): Effect.Effect<EnvironmentThreadState> {
  if (devFrameConfig === null) {
    return Effect.succeed(EMPTY_ENVIRONMENT_THREAD_STATE);
  }
  return Effect.tryPromise({
    try: () => fetchDevFrameT3Shell(devFrameConfig),
    catch: toDevFrameThreadLoadError,
  }).pipe(
    Effect.map((snapshot) => devFrameThreadState(snapshot, threadId)),
    Effect.catch((error: DevFrameThreadLoadError) => Effect.succeed(devFrameThreadErrorState(error))),
  );
}

function createDevFrameEnvironmentThreadStateAtoms() {
  const family = Atom.family((key: string) => {
    const ref = parseThreadKey(key);
    return Atom.make(loadDevFrameThreadState(ref.threadId)).pipe(
      Atom.swr({
        staleTime: 0,
        revalidateOnMount: true,
      }),
      Atom.withRefresh(2000),
      Atom.setIdleTTL(0),
      Atom.withLabel(`devframe-environment-thread-state:${key}`),
    );
  });

  return {
    stateAtom: (environmentId: EnvironmentId, threadId: ThreadId) =>
      family(threadKey({ environmentId, threadId })),
  };
}

const devFrameRespondToApproval = {
  label: "devframe:thread:respond-to-approval",
  run: (_registry: unknown, value: { readonly input: { readonly requestId: string; readonly threadId: string; readonly decision: string } }) =>
    (async () => {
      const config = readDevFrameShellBridgeConfig();
      if (config === null) {
        return AsyncResult.success({ responded: false, decision: "native_unavailable" } as const);
      }
      const nativeDecision = value.input.decision;
      const mapped = ((["accept", "acceptForSession"] as readonly string[]).includes(nativeDecision)) ? "approve"
        : ((["decline", "cancel"] as readonly string[]).includes(nativeDecision)) ? "reject"
        : "reject";
      try {
        const base = new URL("/", config.shellUrl);
        const url = new URL("/api/t3/approval-response", base);
        const response = await fetch(url.toString(), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            requestId: value.input.requestId,
            threadId: value.input.threadId,
            decision: mapped,
          }),
        });
        if (!response.ok) {
          const errorBody = await response.text();
          throw new Error(`DevFrame approval response failed: ${response.status} ${errorBody}`);
        }
        return AsyncResult.success((await response.json()) as { responded: boolean; decision: string });
      } catch (error) {
        console.warn("[devframe] respondToApproval failed:", error);
        return AsyncResult.success({ responded: false, decision: "error" } as const);
      }
    })(),
};

export const threadEnvironment =
  devFrameConfig === null
    ? nativeThreadEnvironment
    : { ...nativeThreadEnvironment, respondToApproval: devFrameRespondToApproval };
export const environmentThreads =
  devFrameConfig === null ? nativeEnvironmentThreads : createDevFrameEnvironmentThreadStateAtoms();
export const environmentThreadDetails = createEnvironmentThreadDetailAtoms(
  environmentThreads.stateAtom,
);
export const environmentThreadShells = createEnvironmentThreadShellAtoms({
  catalogValueAtom: environmentCatalog.catalogValueAtom,
  snapshotAtom: environmentSnapshotAtom,
});

const EMPTY_THREAD_STATE_ATOM = Atom.make(AsyncResult.success(EMPTY_ENVIRONMENT_THREAD_STATE)).pipe(
  Atom.withLabel("web-environment-thread:empty"),
);

export function useEnvironmentThread(
  environmentId: EnvironmentId | null,
  threadId: ThreadId | null,
): EnvironmentThreadState {
  const result = useAtomValue(
    environmentId !== null && threadId !== null
      ? environmentThreads.stateAtom(environmentId, threadId)
      : EMPTY_THREAD_STATE_ATOM,
  );
  return Option.getOrElse(
    AsyncResult.value(result),
    () => EMPTY_ENVIRONMENT_THREAD_STATE,
  ) as EnvironmentThreadState;
}
"""


def _write_bridge_files(root: Path, bundle: dict[str, Any], *, require_t3_root: bool, force: bool) -> list[Path]:
    files = {
        BRIDGE_SOURCE_RELATIVE_PATH: render_bridge_source(),
        BRIDGE_README_RELATIVE_PATH: render_bridge_readme(bundle),
        BRIDGE_CATALOG_RELATIVE_PATH: render_catalog_source(bundle.get("environment")),
        BRIDGE_SHELL_STATE_RELATIVE_PATH: render_shell_state_source(),
        BRIDGE_THREAD_STATE_RELATIVE_PATH: render_thread_state_source(),
        BRIDGE_LOCAL_CONFIG_RELATIVE_PATH: render_t3_bridge_bundle_json(bundle) + "\n",
        BRIDGE_ENV_RELATIVE_PATH: _render_env_file(bundle),
        BRIDGE_T3_WEB_LAUNCHER_RELATIVE_PATH: render_t3_web_launcher_source(bundle),
        BRIDGE_T3_DESKTOP_LAUNCHER_RELATIVE_PATH: render_t3_desktop_launcher_source(bundle),
        BRIDGE_T3_DESKTOP_PROD_LAUNCHER_RELATIVE_PATH: render_t3_desktop_prod_launcher_source(bundle),
    }
    if require_t3_root and not force:
        existing = [root / relative_path for relative_path in files if (root / relative_path).exists()]
        if existing:
            raise FileExistsError(f"refusing to overwrite existing bridge file: {existing[0]}")
    written: list[Path] = []
    for relative_path, content in files.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def _render_env_file(bundle: dict[str, Any]) -> str:
    return "".join(f"{name}={value}\n" for name, value in bundle["environment"].items())


def _base_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, "/", "", "", ""))


def _websocket_base_url(http_base_url: str) -> str:
    parsed = urlparse(http_base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "/", "", "", ""))
