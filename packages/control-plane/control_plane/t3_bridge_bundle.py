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
        # M13B controlled conversation requires both the shell snapshot URL and
        # an independently derived control-plane base from client plan/manifest.
        # The generated client fails closed to read-only mode when either side
        # of that pair is missing.
        "environment": {
            "VITE_DEVFRAME_REALTIME_MODE": "polling",
            "VITE_DEVFRAME_T3_SHELL_URL": endpoints["t3Shell"],
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
                "role": "Registers the DevFrame local environment when the launcher supplies the shell URL; catalog mutations remain read-only.",
                "status": "ready",
            },
            {
                "path": BRIDGE_SHELL_STATE_RELATIVE_PATH,
                "action": "patch",
                "role": "Loads DevFrame shell snapshots when the launcher supplies VITE_DEVFRAME_T3_SHELL_URL.",
                "status": "ready",
            },
            {
                "path": BRIDGE_THREAD_STATE_RELATIVE_PATH,
                "action": "patch",
                "role": "Loads DevFrame thread details and enables only the bounded M13B conversation, approval, and cancellation commands when shell and control configuration are both present.",
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
                "T3 Code (RD-Code) launches with the DevFrame local shell and native Global Coordinator conversation entry enabled.",
                "OpenCode remains the executor surfaced by DevFrame sessions.",
                "The launcher supplies shell plus client-plan/manifest control configuration; missing either side fails closed instead of enabling conversation writes.",
                "The T3 adapter keeps its default mutation surface read-only and permits only durable conversation intake, approval response, and active-run cancellation.",
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
        "mode        : M13B controlled conversation (shell + control)",
        f"shell       : {env['VITE_DEVFRAME_T3_SHELL_URL']}",
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

export interface DevFrameProjectOption {
  readonly projectId: string;
  readonly projectPath: string;
  readonly workspaceRoot: string;
  readonly label: string;
}

export interface DevFrameT3ThreadShell {
  readonly id: string;
  readonly projectId: string;
  readonly title: string;
  readonly threadKind: DevFrameThreadKind;
  readonly coordinatorScope: DevFrameCoordinatorScope;
  readonly projectBinding: DevFrameProjectBinding;
  readonly threadListPriority?: number;
  readonly threadListSummary?: string;
  readonly updatedAt?: string;
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
    readonly threadListPriority?: number;
    readonly threadListSummary?: string;
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

export interface DevFrameControlPlaneConfig {
  readonly controlPlaneBaseUrl: string;
  readonly shellUrl?: string;
  readonly clientPlanUrl?: string;
  readonly manifestUrl?: string;
  readonly pollIntervalMs?: number;
}

export interface DevFrameConversationTurnInput {
  readonly environmentId: string;
  readonly threadId: string;
  readonly projectId: string;
  readonly messageId: string;
  readonly message: string;
}

export interface DevFrameConversationTurnResponse {
  readonly accepted: true;
  readonly replayed: boolean;
  readonly threadId: string;
  readonly projectId: string;
  readonly eventId: string;
  readonly turnId: string;
  readonly status: "answered" | "proposal_pending";
  readonly assistantMessageId: string;
  readonly proposalId?: string;
}

export type DevFrameApprovalDecision = "approve" | "reject";

export interface DevFrameApprovalResponseInput {
  readonly requestId: string;
  readonly threadId: string;
  readonly decision: DevFrameApprovalDecision;
}

export interface DevFrameApprovalResponse {
  readonly responded: true;
  readonly decision: DevFrameApprovalDecision;
  readonly requestId: string;
  readonly threadId: string;
  readonly executed: boolean;
  readonly status: "started" | "rejected";
  readonly replayed: boolean;
  readonly runId?: string;
}

export interface DevFrameClusterRunCancelInput {
  readonly runId: string;
}

export interface DevFrameClusterRunCancelResponse {
  readonly cancelRequested: boolean;
  readonly runId: string;
  readonly status: "cancel_requested" | "cancelled";
}

interface DevFrameBridgeEnv {
  readonly VITE_DEVFRAME_T3_SHELL_URL?: string;
  readonly VITE_DEVFRAME_CLIENT_PLAN_URL?: string;
  readonly VITE_DEVFRAME_CLIENT_MANIFEST_URL?: string;
}

export type DevFrameShellListener = (snapshot: DevFrameT3ShellSnapshot) => void;
export type DevFrameShellErrorListener = (error: unknown) => void;

export interface DevFrameCoordinatorShellEntry {
  readonly version: number;
  readonly source: "devframe";
  readonly updatedAt: string;
  readonly conversationModel: DevFrameConversationModel;
  readonly projects: readonly DevFrameProjectOption[];
  readonly projectOptions: readonly DevFrameProjectOption[];
  readonly selectedProject: DevFrameProjectOption | null;
  readonly projectCoordinatorThread: DevFrameT3ThreadShell | null;
  readonly shellThreads: readonly DevFrameT3ThreadShell[];
  readonly globalCoordinatorThread: DevFrameT3ThreadShell | null;
  readonly goalConversations: readonly DevFrameT3ThreadShell[];
  readonly sortedShell: DevFrameT3ShellSnapshot;
  readonly canStartCoordinatorGoal: boolean;
  readonly emptyStateReason: string | null;
  readonly disabledReason: string | null;
}

const DEFAULT_POLL_INTERVAL_MS = 2000;
const DEFAULT_CONVERSATION_MODEL: DevFrameConversationModel = {
  globalCoordinatorThreadId: "devframe-team-workbench-session",
  goalProjectBindingRequired: true,
  threadKinds: ["native_chat", "goal_conversation", "global_coordinator"],
};

function trimOptionalUrl(value: string | undefined): string | undefined {
  const text = value?.trim();
  return text ? text : undefined;
}

function deriveControlPlaneBaseUrl(
  clientPlanUrl?: string,
  manifestUrl?: string,
): string | null {
  const source = clientPlanUrl || manifestUrl;
  if (!source) return null;
  return new URL("/", source).toString();
}

export function readDevFrameControlPlaneConfig(
  env: DevFrameBridgeEnv = import.meta.env as DevFrameBridgeEnv,
): DevFrameControlPlaneConfig | null {
  const shellUrl = trimOptionalUrl(env.VITE_DEVFRAME_T3_SHELL_URL);
  const clientPlanUrl = trimOptionalUrl(env.VITE_DEVFRAME_CLIENT_PLAN_URL);
  const manifestUrl = trimOptionalUrl(env.VITE_DEVFRAME_CLIENT_MANIFEST_URL);
  const controlPlaneBaseUrl = deriveControlPlaneBaseUrl(clientPlanUrl, manifestUrl);
  if (!controlPlaneBaseUrl) return null;
  return {
    controlPlaneBaseUrl,
    ...(shellUrl ? { shellUrl } : {}),
    ...(clientPlanUrl ? { clientPlanUrl } : {}),
    ...(manifestUrl ? { manifestUrl } : {}),
  };
}

export function readDevFrameShellBridgeConfig(
  env: DevFrameBridgeEnv = import.meta.env as DevFrameBridgeEnv,
): DevFrameShellBridgeConfig | null {
  const shellUrl = trimOptionalUrl(env.VITE_DEVFRAME_T3_SHELL_URL);
  if (!shellUrl) return null;
  return { shellUrl };
}

function isUnknownRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isCanonicalDevFrameRunId(value: unknown): value is string {
  return typeof value === "string" && /^g-[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value);
}

export function isCanonicalDevFrameProposalId(value: unknown): value is string {
  return typeof value === "string" && /^ctp-[0-9a-f]{24}$/.test(value);
}

function hasExactKeys(value: Record<string, unknown>, allowedKeys: ReadonlySet<string>): boolean {
  const keys = Object.keys(value);
  return keys.length === allowedKeys.size && keys.every((key) => allowedKeys.has(key));
}

function parseDevFrameConversationTurnResponse(
  value: unknown,
  input: DevFrameConversationTurnInput,
): DevFrameConversationTurnResponse {
  const status =
    isUnknownRecord(value) && (value.status === "answered" || value.status === "proposal_pending")
      ? value.status
      : null;
  const allowedKeys = new Set([
    "accepted",
    "replayed",
    "threadId",
    "projectId",
    "eventId",
    "turnId",
    "status",
    "assistantMessageId",
    ...(status === "proposal_pending" ? ["proposalId"] : []),
  ]);
  if (
    !isUnknownRecord(value) ||
    status === null ||
    !hasExactKeys(value, allowedKeys) ||
    value.accepted !== true ||
    typeof value.replayed !== "boolean" ||
    value.threadId !== input.threadId ||
    value.projectId !== input.projectId ||
    typeof value.eventId !== "string" ||
    !/^ci-[0-9a-f]{24}$/.test(value.eventId) ||
    value.turnId !== input.messageId ||
    typeof value.assistantMessageId !== "string" ||
    !/^cam-[0-9a-f]{24}$/.test(value.assistantMessageId) ||
    (status === "proposal_pending" && !isCanonicalDevFrameProposalId(value.proposalId))
  ) {
    throw new Error("DevFrame conversation intake response is invalid.");
  }
  return {
    accepted: true,
    replayed: value.replayed,
    threadId: value.threadId,
    projectId: value.projectId,
    eventId: value.eventId,
    turnId: value.turnId,
    status,
    assistantMessageId: value.assistantMessageId,
    ...(status === "proposal_pending" ? { proposalId: value.proposalId as string } : {}),
  };
}

export async function startDevFrameConversationTurn(
  config: DevFrameControlPlaneConfig,
  input: DevFrameConversationTurnInput,
): Promise<DevFrameConversationTurnResponse> {
  const response = await fetch(
    new URL("/api/t3/conversation-intake", config.controlPlaneBaseUrl).toString(),
    {
      method: "POST",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        environmentId: input.environmentId,
        threadId: input.threadId,
        projectId: input.projectId,
        clientRequestId: input.messageId,
        message: input.message,
      }),
    },
  );
  if (!response.ok) {
    throw new Error(`DevFrame conversation intake request failed: ${response.status}`);
  }
  return parseDevFrameConversationTurnResponse(await response.json(), input);
}

function parseDevFrameApprovalResponse(
  value: unknown,
  input: DevFrameApprovalResponseInput,
): DevFrameApprovalResponse {
  const approving = input.decision === "approve";
  const allowedKeys = new Set([
    "responded",
    "decision",
    "requestId",
    "threadId",
    "executed",
    "status",
    "replayed",
    ...(approving ? ["runId"] : []),
  ]);
  if (
    !isUnknownRecord(value) ||
    !hasExactKeys(value, allowedKeys) ||
    value.responded !== true ||
    value.decision !== input.decision ||
    value.requestId !== input.requestId ||
    value.threadId !== input.threadId ||
    typeof value.replayed !== "boolean" ||
    (approving
      ? value.executed !== true ||
        value.status !== "started" ||
        !isCanonicalDevFrameRunId(value.runId)
      : value.executed !== false || value.status !== "rejected")
  ) {
    throw new Error("DevFrame approval response is invalid.");
  }
  return {
    responded: true,
    decision: input.decision,
    requestId: input.requestId,
    threadId: input.threadId,
    executed: approving,
    status: approving ? "started" : "rejected",
    replayed: value.replayed,
    ...(approving ? { runId: value.runId as string } : {}),
  };
}

export async function respondToDevFrameApproval(
  config: DevFrameControlPlaneConfig,
  input: DevFrameApprovalResponseInput,
): Promise<DevFrameApprovalResponse> {
  if (!isCanonicalDevFrameProposalId(input.requestId)) {
    throw new Error("DevFrame semantic proposal id is invalid.");
  }
  const response = await fetch(
    new URL("/api/t3/approval-response", config.controlPlaneBaseUrl).toString(),
    {
      method: "POST",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(input),
    },
  );
  if (!response.ok) {
    throw new Error(`DevFrame approval response request failed: ${response.status}`);
  }
  return parseDevFrameApprovalResponse(await response.json(), input);
}

export async function cancelDevFrameClusterRun(
  config: DevFrameControlPlaneConfig,
  input: DevFrameClusterRunCancelInput,
): Promise<DevFrameClusterRunCancelResponse> {
  if (!isCanonicalDevFrameRunId(input.runId)) {
    throw new Error("DevFrame cluster run id is invalid.");
  }
  const response = await fetch(
    new URL("/api/t3/cluster-run-cancel", config.controlPlaneBaseUrl).toString(),
    {
      method: "POST",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        runId: input.runId,
        requestedBy: "rd-code-editor",
      }),
    },
  );
  if (!response.ok) {
    throw new Error(`DevFrame cluster run cancel request failed: ${response.status}`);
  }
  const value: unknown = await response.json();
  if (
    !isUnknownRecord(value) ||
    !hasExactKeys(value, new Set(["cancelRequested", "runId", "status"])) ||
    value.runId !== input.runId ||
    !(
      (value.cancelRequested === true && value.status === "cancel_requested") ||
      (value.cancelRequested === false && value.status === "cancelled")
    )
  ) {
    throw new Error("DevFrame cluster run cancel response is invalid.");
  }
  return {
    cancelRequested: value.cancelRequested,
    runId: value.runId,
    status: value.status,
  };
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
  return sortDevFrameThreadsForDisplay((await fetchDevFrameT3ShellEnvelope(config)).t3);
}

export async function fetchDevFrameConversationModel(
  config: DevFrameControlPlaneConfig,
): Promise<DevFrameConversationModel> {
  const response = await fetch(new URL("/api/t3/conversation-model", config.controlPlaneBaseUrl).toString(), {
    method: "GET",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`DevFrame conversation model request failed: ${response.status}`);
  }
  return (await response.json()) as DevFrameConversationModel;
}

export async function fetchDevFrameProjectOptions(
  config: DevFrameControlPlaneConfig,
): Promise<readonly DevFrameProjectOption[]> {
  const projectsUrl = new URL("/api/t3/projects", config.controlPlaneBaseUrl).toString();
  const response = await fetch(projectsUrl, {
    method: "GET",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`DevFrame project options request failed: ${response.status}`);
  }
  const payload = (await response.json()) as { readonly projects?: readonly DevFrameProjectOption[] };
  return Array.isArray(payload.projects) ? payload.projects : [];
}

function threadSortKey(thread: DevFrameT3ThreadShell): [number, string, string] {
  return [
    thread.threadListPriority ?? 99,
    thread.updatedAt ?? "",
    thread.title,
  ];
}

export function sortDevFrameThreadsForDisplay(
  snapshot: DevFrameT3ShellSnapshot,
): DevFrameT3ShellSnapshot {
  const detailsById = new Map(
    (snapshot.threadDetails ?? []).map((detail) => [String((detail as { id?: unknown }).id ?? ""), detail]),
  );
  const threads = [...snapshot.threads].sort((a, b) => {
    const [ap, au, at] = threadSortKey(a);
    const [bp, bu, bt] = threadSortKey(b);
    if (ap !== bp) return ap - bp;
    if (au !== bu) return au < bu ? 1 : -1;
    return at.localeCompare(bt);
  });
  const threadDetails = threads
    .map((thread) => detailsById.get(thread.id))
    .filter((detail): detail is DevFrameThreadDetail => detail !== undefined);
  return {
    ...snapshot,
    threads,
    threadDetails,
  };
}

function dedupeShellProjects(projects: readonly unknown[]): readonly unknown[] {
  const seen = new Set<string>();
  return projects.filter((project) => {
    if (typeof project !== "object" || project === null) {
      return true;
    }
    const id = (project as { readonly id?: unknown }).id;
    if (typeof id !== "string" || id.length === 0) {
      return true;
    }
    if (seen.has(id)) {
      return false;
    }
    seen.add(id);
    return true;
  });
}

function normalizeDevFrameShellSnapshot(snapshot: DevFrameT3ShellSnapshot): DevFrameT3ShellSnapshot {
  return sortDevFrameThreadsForDisplay({
    ...snapshot,
    projects: dedupeShellProjects(snapshot.projects),
  });
}

function isSelectedProjectGoalThread(
  thread: DevFrameT3ThreadShell | null,
  selectedProject: DevFrameProjectOption | null,
): thread is DevFrameT3ThreadShell {
  return (
    thread !== null &&
    selectedProject !== null &&
    thread.threadKind === "goal_conversation" &&
    thread.projectId === selectedProject.projectId
  );
}

export function buildDevFrameCoordinatorShellEntry(
  envelope: DevFrameT3ShellEnvelope,
  projects: readonly DevFrameProjectOption[] = [],
  conversationModel?: DevFrameConversationModel,
): DevFrameCoordinatorShellEntry {
  const resolvedConversationModel =
    conversationModel ?? envelope.devframe?.conversationModel ?? DEFAULT_CONVERSATION_MODEL;
  const sortedShell = normalizeDevFrameShellSnapshot(envelope.t3);
  const shellThreads = sortedShell.threads;
  const projectOptions = [...projects];
  const selectedProject = projectOptions[0] ?? null;
  const selectedProjectId = selectedProject?.projectId ?? "";
  const projectCoordinatorThread =
    shellThreads.find((thread) => thread.projectId === selectedProjectId && thread.threadKind === "goal_conversation") ??
    null;
  const globalCoordinatorThread =
    sortedShell.threads.find((thread) => thread.id === resolvedConversationModel.globalCoordinatorThreadId) ??
    sortedShell.threads.find((thread) => thread.threadKind === "global_coordinator") ??
    null;
  const goalConversations = sortedShell.threads.filter(
    (thread) => thread.threadKind === "goal_conversation",
  );
  return {
    version: 1,
    source: "devframe",
    updatedAt: sortedShell.updatedAt,
    conversationModel: resolvedConversationModel,
    projects,
    projectOptions,
    selectedProject,
    projectCoordinatorThread,
    shellThreads,
    globalCoordinatorThread,
    goalConversations,
    sortedShell,
    canStartCoordinatorGoal: !resolvedConversationModel.goalProjectBindingRequired || projects.length > 0,
    emptyStateReason: shellThreads.length === 0 ? "no_threads" : null,
    disabledReason: !resolvedConversationModel.goalProjectBindingRequired || projects.length > 0 ? null : "missing_required_project",
  };
}

export function buildDevFrameCoordinatorShellEntryFromShellSnapshot(
  snapshot: DevFrameT3ShellSnapshot,
  projects: readonly DevFrameProjectOption[] = [],
  conversationModel?: DevFrameConversationModel,
): DevFrameCoordinatorShellEntry {
  return buildDevFrameCoordinatorShellEntry(
    {
      version: 1,
      source: "devframe",
      t3: snapshot,
      devframe: {
        conversationModel: conversationModel ?? DEFAULT_CONVERSATION_MODEL,
        team: {
          agentRegistry: [],
          taskBoard: [],
          messageBus: [],
          eventLog: [],
          evidenceStore: [],
          reviewGates: [],
          conflictControl: [],
        },
      },
    },
    projects,
    conversationModel,
  );
}

function normalizeDevFrameCoordinatorShellEntry(
  entry: DevFrameCoordinatorShellEntry,
): DevFrameCoordinatorShellEntry {
  const sortedShell = normalizeDevFrameShellSnapshot(entry.sortedShell);
  const shellThreads = sortDevFrameThreadsForDisplay({
    snapshotSequence: sortedShell.snapshotSequence,
    projects: sortedShell.projects,
    threads: entry.shellThreads,
    updatedAt: sortedShell.updatedAt,
  }).threads;
  const projectCoordinatorThread = isSelectedProjectGoalThread(
    entry.projectCoordinatorThread,
    entry.selectedProject,
  )
    ? entry.projectCoordinatorThread
    : shellThreads.find((thread) => isSelectedProjectGoalThread(thread, entry.selectedProject)) ?? null;
  return {
    ...entry,
    sortedShell,
    shellThreads,
    projectCoordinatorThread,
    globalCoordinatorThread:
      entry.globalCoordinatorThread ??
      shellThreads.find((thread) => thread.id === entry.conversationModel.globalCoordinatorThreadId) ??
      shellThreads.find((thread) => thread.threadKind === "global_coordinator") ??
      null,
    goalConversations: shellThreads.filter((thread) => thread.threadKind === "goal_conversation"),
  };
}

export async function fetchDevFrameCoordinatorShellEntry(
  config: DevFrameControlPlaneConfig,
): Promise<DevFrameCoordinatorShellEntry> {
  const response = await fetch(new URL("/api/t3/coordinator-entry", config.controlPlaneBaseUrl).toString(), {
    method: "GET",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`DevFrame coordinator entry request failed: ${response.status}`);
  }
  return normalizeDevFrameCoordinatorShellEntry((await response.json()) as DevFrameCoordinatorShellEntry);
}

export interface DevFrameClusterTarget {
  readonly id: string;
  readonly kind: string;
  readonly label: string;
  readonly role?: string;
}

export interface DevFrameClusterTargetsResponse {
  readonly projectId: string;
  readonly targets: readonly DevFrameClusterTarget[];
}

export interface DevFrameCoordinatorGoalRequest {
  readonly projectId: string;
  readonly target: string;
  readonly goal: string;
  readonly proposedBy?: string;
}

export interface DevFrameCoordinatorGoalResponse {
  readonly started: boolean;
  readonly runId: string;
  readonly projectId?: string;
  readonly target: string;
  readonly goal: string;
  readonly projectPath?: string;
  readonly conversationKind?: string;
  readonly coordinatorScope?: string;
  readonly projectBinding?: Record<string, unknown>;
  readonly kind?: string;
  readonly answer?: string;
  readonly note?: string;
}

export async function fetchDevFrameClusterTargets(
  config: DevFrameControlPlaneConfig,
  projectId: string,
): Promise<DevFrameClusterTargetsResponse> {
  const targetsUrl = new URL("/api/t3/cluster-targets", config.controlPlaneBaseUrl);
  if (projectId.trim()) targetsUrl.searchParams.set("project", projectId.trim());
  const response = await fetch(targetsUrl.toString(), {
    method: "GET",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`DevFrame cluster targets request failed: ${response.status}`);
  }
  return (await response.json()) as DevFrameClusterTargetsResponse;
}

export async function startDevFrameCoordinatorGoal(
  config: DevFrameControlPlaneConfig,
  input: DevFrameCoordinatorGoalRequest,
): Promise<DevFrameCoordinatorGoalResponse> {
  const response = await fetch(new URL("/api/t3/cluster-run", config.controlPlaneBaseUrl).toString(), {
    method: "POST",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      projectId: input.projectId,
      target: input.target,
      goal: input.goal,
      ...(input.proposedBy ? { proposedBy: input.proposedBy } : {}),
    }),
  });
  if (!response.ok) {
    throw new Error(`DevFrame coordinator goal request failed: ${response.status}`);
  }
  return (await response.json()) as DevFrameCoordinatorGoalResponse;
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
local Agent Control Plane. DevFrame does not expose a WebSocket endpoint, so
the T3 client runs in polling mode using HTTP snapshots and bounded HTTP
commands.

## Runtime URLs

- realtime mode: `{env["VITE_DEVFRAME_REALTIME_MODE"]}`
- shell: `{env["VITE_DEVFRAME_T3_SHELL_URL"]}`
- client plan: `{env["VITE_DEVFRAME_CLIENT_PLAN_URL"]}`
- manifest: `{env["VITE_DEVFRAME_CLIENT_MANIFEST_URL"]}`

The generated launchers enable M13B controlled conversation by supplying the
shell URL together with client-plan and manifest URLs. Shell-only or
control-only partial configuration fails closed: it never enables conversation
writes.

## Launch

Run `node {BRIDGE_T3_DESKTOP_LAUNCHER_RELATIVE_PATH}` from the T3 checkout root for the primary desktop experience, or `node {BRIDGE_T3_WEB_LAUNCHER_RELATIVE_PATH}` as an auxiliary fallback. Each launcher sets DevFrame-specific Vite variables in the child process and then runs the corresponding T3 dev command, so they do not need to overwrite T3's `.env.local`.

## Wiring point

`apps/web/src/state/shell.ts` and `apps/web/src/state/threads.ts` are generated
as the T3-side wiring points. With the complete shell-plus-control
configuration they load DevFrame snapshots and expose the native Global
Coordinator conversation entry. `apps/web/src/connection/catalog.ts` registers
the DevFrame local environment, and the desktop app reuses that web shell
through the existing T3 desktop wrapper.

The bridge remains read-only by default. Its controlled thread adapter permits
only durable conversation intake, proposal approval/rejection, and active-run
cancellation. All other mutations stay blocked, and partial configuration
selects the read-only adapter.

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
Use `fetchDevFrameConversationModel()` for the coordinator conversation contract
and `fetchDevFrameProjectOptions()` for the project-binding picker that powers
new coordinator-owned goals.
Use `readDevFrameControlPlaneConfig()` for the independently configured control
base and `readDevFrameShellBridgeConfig()` for snapshots. The controlled
conversation adapter is enabled only when both return a configuration.
`fetchDevFrameClusterTargets()` and `startDevFrameCoordinatorGoal()` remain
available for explicitly governed coordinator actions.
Use `sortDevFrameThreadsForDisplay()` to present the inbox in product order:
global coordinator first, then goal conversations, then ordinary chats.
Use `fetchDevFrameCoordinatorShellEntry()` when the shell wants one directly
consumable entry model: sorted shell snapshot, global coordinator thread, goal
conversations, project picker options, and whether project-bound goal creation
can start.
"""


def render_catalog_source(env: dict[str, str] | None = None) -> str:
    env = env or {}
    realtime_mode = env.get("VITE_DEVFRAME_REALTIME_MODE", "polling")
    ws_base_url_line = f'          wsBaseUrl: devFrameWsBaseUrl(),\n'

    return f"""import {{ PrimaryConnectionTarget, type SupervisorConnectionState }} from "@t3tools/client-runtime/connection";
import {{ createEnvironmentCatalogAtoms, type EnvironmentCatalogState }} from "@t3tools/client-runtime/state/connections";
import {{ EnvironmentId }} from "@t3tools/contracts";
import * as Cause from "effect/Cause";
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
  stage: "synchronizing",
  attempt: 0,
  generation: 1,
  lastFailure: null,
  retryAt: null,
}};

function createDevFrameEnvironmentCatalogAtoms() {{
  const readOnlyCommand = (label: string) => ({{
    label: `devframe:catalog:read-only:${{label}}`,
    run: async (_registry: unknown, _value: unknown) =>
      AsyncResult.failure(
        Cause.fail(new Error(`DevFrame bridge is read-only; catalog ${{label}} is unavailable.`)),
      ),
  }});

  return {{
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
    register: readOnlyCommand("register"),
    remove: readOnlyCommand("remove"),
    removeRelayEnvironments: readOnlyCommand("removeRelayEnvironments"),
    retryNow: readOnlyCommand("retryNow"),
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
console.log(`[devframe] M13B controlled conversation enabled (shell ${{devframeEnv.VITE_DEVFRAME_T3_SHELL_URL}}; client plan ${{devframeEnv.VITE_DEVFRAME_CLIENT_PLAN_URL}}).`);

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
    return f"""#!/usr/bin/env node
import {{ spawn }} from "node:child_process";
import {{ fileURLToPath }} from "node:url";
import {{ dirname }} from "node:path";

const devframeEnv = {env_json};
const root = dirname(fileURLToPath(import.meta.url));
const isWindows = process.platform === "win32";
const command = isWindows ? "pnpm" : "pnpm";
const args = ["dev:desktop"];
const childEnv = {{ ...process.env, ...devframeEnv }};
childEnv.T3CODE_DESKTOP_REMOTE_DEBUGGING_PORT =
    process.env.T3CODE_DESKTOP_REMOTE_DEBUGGING_PORT ||
    childEnv.T3CODE_DESKTOP_REMOTE_DEBUGGING_PORT ||
    "{T3_RENDERER_CDP_DEFAULT_PORT}";

console.log("[devframe] Starting T3 Desktop with DevFrame local control plane.");
console.log(`[devframe] M13B controlled conversation enabled (shell ${{devframeEnv.VITE_DEVFRAME_T3_SHELL_URL}}; client plan ${{devframeEnv.VITE_DEVFRAME_CLIENT_PLAN_URL}}).`);

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
      set, so the shell/client-plan/manifest URLs are inlined into the built
      bundle.
    - It then runs ``pnpm start:desktop``, which launches Electron against the
      built renderer with no dev server and no watchers.
    """
    env = bundle["environment"]
    # The production renderer connects to the desktop's own spawned local
    # server. VITE_HOSTED_APP_CHANNEL must NOT be baked into the desktop build:
    # `isHostedStaticApp()` treats any configured hosted channel as "this is the
    # hosted browser app" and short-circuits into the onboarding
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
console.log(`[devframe] M13B controlled conversation baked at build time (shell ${{devframeEnv.VITE_DEVFRAME_T3_SHELL_URL}}; client plan ${{devframeEnv.VITE_DEVFRAME_CLIENT_PLAN_URL}}).`);

const startCode = await run(["start:desktop"]);
process.exit(startCode);
"""


def render_shell_state_source() -> str:
    return """import {
  AVAILABLE_CONNECTION_STATE,
  connectionProjectionPhase,
} from "@t3tools/client-runtime/connection";
import {
  createEnvironmentShellAtoms,
  createEnvironmentShellSummaryAtom,
  createEnvironmentSnapshotAtom,
  createShellEnvironmentAtoms,
  type EnvironmentShellState,
} from "@t3tools/client-runtime/state/shell";
import type { EnvironmentId, OrchestrationShellSnapshot } from "@t3tools/contracts";
import * as Cause from "effect/Cause";
import * as Effect from "effect/Effect";
import * as Option from "effect/Option";
import { AsyncResult, Atom } from "effect/unstable/reactivity";

import {
  fetchDevFrameCoordinatorShellEntry,
  fetchDevFrameT3Shell,
  readDevFrameControlPlaneConfig,
  readDevFrameShellBridgeConfig,
  type DevFrameCoordinatorShellEntry,
  type DevFrameT3ShellSnapshot,
} from "../devframe/devframeShellBridge";
import { environmentCatalog } from "../connection/catalog";
import { connectionAtomRuntime } from "../connection/runtime";

const nativeEnvironmentShell = createEnvironmentShellAtoms(connectionAtomRuntime);
const nativeShellEnvironment = createShellEnvironmentAtoms(connectionAtomRuntime);
const devFrameConfig = readDevFrameShellBridgeConfig();
const devFrameControlPlaneConfig = readDevFrameControlPlaneConfig();

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
    snapshot: Option.some(snapshot as unknown as OrchestrationShellSnapshot),
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

function loadDevFrameCoordinatorShellEntry(): Effect.Effect<
  Option.Option<DevFrameCoordinatorShellEntry>
> {
  if (devFrameControlPlaneConfig === null) {
    return Effect.succeed(Option.none());
  }
  return Effect.tryPromise({
    try: () => fetchDevFrameCoordinatorShellEntry(devFrameControlPlaneConfig),
    catch: toDevFrameShellLoadError,
  }).pipe(
    Effect.map((entry) => Option.some(entry)),
    Effect.orElseSucceed(() => Option.none()),
  );
}

function createDevFrameCoordinatorShellEntryAtoms() {
  const stateAtom = Atom.family((environmentId: EnvironmentId) =>
    Atom.make(loadDevFrameCoordinatorShellEntry()).pipe(
      Atom.swr({
        staleTime: 0,
        revalidateOnMount: true,
      }),
      Atom.withRefresh(2000),
      Atom.setIdleTTL(0),
      Atom.withLabel(`devframe-coordinator-shell-entry:${environmentId}`),
    ),
  );

  const stateValueAtom = Atom.family((environmentId: EnvironmentId) =>
    Atom.make((get) =>
      Option.getOrElse(
        AsyncResult.value(get(stateAtom(environmentId))),
        () => Option.none<DevFrameCoordinatorShellEntry>(),
      ),
    ).pipe(Atom.withLabel(`devframe-coordinator-shell-entry-value:${environmentId}`)),
  );

  return {
    stateAtom,
    stateValueAtom,
  };
}

const devFrameReadOnlyShellEnvironment = {
  openInEditor: {
    label: "devframe:shell:read-only:open-in-editor",
    run: async (_registry: unknown, _value: unknown) =>
      AsyncResult.failure(
        Cause.fail(new Error("DevFrame bridge is read-only; openInEditor is unavailable.")),
      ),
  },
};

export const shellEnvironment =
  devFrameConfig === null ? nativeShellEnvironment : devFrameReadOnlyShellEnvironment;
export const environmentShell =
  devFrameConfig === null ? nativeEnvironmentShell : createDevFrameEnvironmentShellAtoms();
export const environmentCoordinatorShellEntry = createDevFrameCoordinatorShellEntryAtoms();
export const environmentSnapshotAtom = createEnvironmentSnapshotAtom(environmentShell.stateAtom);
export const environmentShellSummaryAtom = createEnvironmentShellSummaryAtom({
  catalogValueAtom: environmentCatalog.catalogValueAtom,
  shellStateValueAtom: environmentShell.stateValueAtom,
});

export const allEnvironmentShellsBootstrappedAtom = Atom.make((get) => {
  const catalog = AsyncResult.value(get(environmentCatalog.catalogAtom));
  if (Option.isNone(catalog)) {
    return false;
  }
  for (const environmentId of catalog.value.entries.keys()) {
    if (Option.isSome(get(environmentShell.stateValueAtom(environmentId)).snapshot)) {
      continue;
    }
    const connection = Option.getOrElse(
      AsyncResult.value(get(environmentCatalog.stateAtom(environmentId))),
      () => AVAILABLE_CONNECTION_STATE,
    );
    if (connectionProjectionPhase(connection) !== "disconnected") {
      return false;
    }
    if (connection.phase === "backoff" && connection.desired && connection.attempt <= 2) {
      return false;
    }
  }
  return true;
}).pipe(Atom.withLabel("web-all-environment-shells-bootstrapped"));
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
import * as Cause from "effect/Cause";
import * as Effect from "effect/Effect";
import * as Option from "effect/Option";
import { AsyncResult, Atom } from "effect/unstable/reactivity";

import {
  cancelDevFrameClusterRun,
  fetchDevFrameT3Shell,
  isCanonicalDevFrameProposalId,
  isCanonicalDevFrameRunId,
  readDevFrameControlPlaneConfig,
  readDevFrameShellBridgeConfig,
  respondToDevFrameApproval,
  startDevFrameConversationTurn,
  type DevFrameControlPlaneConfig,
  type DevFrameT3ShellSnapshot,
} from "../devframe/devframeShellBridge";
import { environmentCatalog } from "../connection/catalog";
import { connectionAtomRuntime } from "../connection/runtime";
import { environmentSnapshotAtom } from "./shell";
import { parseThreadKey, threadKey } from "@t3tools/client-runtime/state/entities";

const nativeThreadEnvironment = createThreadEnvironmentAtoms(connectionAtomRuntime);
const nativeEnvironmentThreads = createEnvironmentThreadStateAtoms(connectionAtomRuntime);
const devFrameConfig = readDevFrameShellBridgeConfig();
const devFrameControlPlaneConfig = readDevFrameControlPlaneConfig();
const DEVFRAME_ENVIRONMENT_ID = "devframe-local";
const DEVFRAME_GLOBAL_COORDINATOR_THREAD_ID = "devframe-team-workbench-session";
const devFrameProjectIdByThreadId = new Map<string, string>();

export function resolveDevFrameThreadBridgeMode(
  shellConfig: object | null,
  controlPlaneConfig: object | null,
): "native" | "read-only" | "conversation" {
  if (shellConfig === null && controlPlaneConfig === null) {
    return "native";
  }
  if (shellConfig !== null && controlPlaneConfig !== null) {
    return "conversation";
  }
  return "read-only";
}

const devFrameThreadBridgeMode = resolveDevFrameThreadBridgeMode(
  devFrameConfig,
  devFrameControlPlaneConfig,
);

function isUnknownRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

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
    return projectedDetail as unknown as OrchestrationThread;
  }

  const shellThread = snapshot.threads.find((candidate) => hasThreadId(candidate, threadId));
  if (shellThread === undefined) {
    return null;
  }

  return {
    ...(shellThread as unknown as Record<string, unknown>),
    deletedAt: null,
    messages: [],
    proposedPlans: [],
    activities: [],
    checkpoints: [],
  } as unknown as OrchestrationThread;
}

export function resolveDevFrameConversationProjectId(
  snapshot: DevFrameT3ShellSnapshot,
  threadId: string,
): string | null {
  if (snapshot.projects.length !== 1 || !isUnknownRecord(snapshot.projects[0])) {
    return null;
  }
  const projectId = snapshot.projects[0].id;
  if (
    typeof projectId !== "string" ||
    !projectId.trim() ||
    projectId !== projectId.trim()
  ) {
    return null;
  }
  const thread = findDevFrameThreadDetail(snapshot, threadId as ThreadId);
  return thread?.projectId === projectId ? projectId : null;
}

function devFrameThreadState(
  snapshot: DevFrameT3ShellSnapshot,
  threadId: ThreadId,
): EnvironmentThreadState {
  const thread = findDevFrameThreadDetail(snapshot, threadId);
  if (thread === null) {
    devFrameProjectIdByThreadId.delete(threadId);
    return EMPTY_ENVIRONMENT_THREAD_STATE;
  }
  const projectId = resolveDevFrameConversationProjectId(snapshot, threadId);
  if (projectId !== null) {
    devFrameProjectIdByThreadId.set(threadId, projectId);
  } else {
    devFrameProjectIdByThreadId.delete(threadId);
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

function loadDevFrameThreadState(
  _environmentId: EnvironmentId,
  threadId: ThreadId,
): Effect.Effect<EnvironmentThreadState> {
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
    return Atom.make(loadDevFrameThreadState(ref.environmentId, ref.threadId)).pipe(
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

function devFrameReadOnlyCommand(label: string) {
  return {
    label: `devframe:thread:read-only:${label}`,
    run: async (_registry: unknown, _value: unknown) =>
      AsyncResult.failure(
        Cause.fail(new Error(`DevFrame bridge is read-only; ${label} is unavailable.`)),
      ),
  };
}

function devFrameRespondToApprovalCommand(config: DevFrameControlPlaneConfig) {
  return {
    label: "devframe:thread:respond-to-approval",
    run: async (_registry: unknown, value: unknown) => {
      if (!isUnknownRecord(value) || !isUnknownRecord(value.input)) {
        return AsyncResult.failure(
          Cause.fail(new Error("DevFrame approval response binding is invalid.")),
        );
      }
      const input = value.input;
      const decision =
        input.decision === "accept"
          ? "approve"
          : input.decision === "decline" || input.decision === "cancel"
            ? "reject"
            : null;
      if (
        value.environmentId !== DEVFRAME_ENVIRONMENT_ID ||
        input.threadId !== DEVFRAME_GLOBAL_COORDINATOR_THREAD_ID ||
        !isCanonicalDevFrameProposalId(input.requestId) ||
        decision === null
      ) {
        return AsyncResult.failure(
          Cause.fail(new Error("DevFrame approval response binding is invalid.")),
        );
      }
      try {
        await respondToDevFrameApproval(config, {
          requestId: input.requestId,
          threadId: input.threadId,
          decision,
        });
        return AsyncResult.success({ sequence: 0 });
      } catch (error) {
        return AsyncResult.failure(Cause.fail(error));
      }
    },
  };
}

function devFrameStartTurnCommand(
  config: DevFrameControlPlaneConfig,
  resolveProjectId: (threadId: string) => string | null,
) {
  return {
    label: "devframe:thread:start-turn",
    run: async (_registry: unknown, value: unknown) => {
      if (!isUnknownRecord(value) || !isUnknownRecord(value.input)) {
        return AsyncResult.failure(
          Cause.fail(new Error("DevFrame Global Coordinator turn binding is invalid.")),
        );
      }
      const input = value.input;
      const allowedInputKeys = new Set([
        "threadId",
        "message",
        "modelSelection",
        "titleSeed",
        "runtimeMode",
        "interactionMode",
        "createdAt",
        "commandId",
      ]);
      const message = input.message;
      const allowedMessageKeys = new Set(["messageId", "role", "text", "attachments"]);
      if (
        value.environmentId !== DEVFRAME_ENVIRONMENT_ID ||
        input.threadId !== DEVFRAME_GLOBAL_COORDINATOR_THREAD_ID ||
        Object.keys(input).some((key) => !allowedInputKeys.has(key)) ||
        !isUnknownRecord(message) ||
        Object.keys(message).length !== allowedMessageKeys.size ||
        Object.keys(message).some((key) => !allowedMessageKeys.has(key)) ||
        message.role !== "user" ||
        typeof message.messageId !== "string" ||
        !message.messageId.trim() ||
        typeof message.text !== "string" ||
        !message.text.trim() ||
        !Array.isArray(message.attachments) ||
        message.attachments.length !== 0
      ) {
        return AsyncResult.failure(
          Cause.fail(new Error("DevFrame Global Coordinator turn binding is invalid.")),
        );
      }
      const projectId = resolveProjectId(input.threadId);
      if (!projectId) {
        return AsyncResult.failure(
          Cause.fail(new Error("DevFrame Global Coordinator project binding is missing.")),
        );
      }
      try {
        await startDevFrameConversationTurn(config, {
          environmentId: value.environmentId,
          threadId: input.threadId,
          projectId,
          messageId: message.messageId,
          message: message.text,
        });
        return AsyncResult.success({ sequence: 0 });
      } catch (error) {
        return AsyncResult.failure(Cause.fail(error));
      }
    },
  };
}

function devFrameInterruptTurnCommand(config: DevFrameControlPlaneConfig) {
  return {
    label: "devframe:thread:interrupt-turn",
    run: async (_registry: unknown, value: unknown) => {
      if (!isUnknownRecord(value) || !isUnknownRecord(value.input)) {
        return AsyncResult.failure(
          Cause.fail(new Error("DevFrame cluster run cancel binding is invalid.")),
        );
      }
      const input = value.input;
      if (
        value.environmentId !== DEVFRAME_ENVIRONMENT_ID ||
        input.threadId !== DEVFRAME_GLOBAL_COORDINATOR_THREAD_ID ||
        !isCanonicalDevFrameRunId(input.turnId)
      ) {
        return AsyncResult.failure(
          Cause.fail(new Error("DevFrame cluster run cancel binding is invalid.")),
        );
      }
      try {
        await cancelDevFrameClusterRun(config, { runId: input.turnId });
        return AsyncResult.success({ sequence: 0 });
      } catch (error) {
        return AsyncResult.failure(Cause.fail(error));
      }
    },
  };
}

function devFrameGlobalThreadNoopCommand(label: string) {
  return {
    label: `devframe:thread:bounded-noop:${label}`,
    run: async (_registry: unknown, value: unknown) =>
      isUnknownRecord(value) &&
      isUnknownRecord(value.input) &&
      value.environmentId === DEVFRAME_ENVIRONMENT_ID &&
      value.input.threadId === DEVFRAME_GLOBAL_COORDINATOR_THREAD_ID
        ? AsyncResult.success({ sequence: 0 })
        : AsyncResult.failure(
            Cause.fail(new Error(`DevFrame ${label} binding is invalid.`)),
          ),
  };
}

// Keep this surface explicit: spreading nativeThreadEnvironment here would
// silently expose current or future native mutations through the DevFrame
// bridge.
const devFrameReadOnlyThreadEnvironment = {
  create: devFrameReadOnlyCommand("create"),
  delete: devFrameReadOnlyCommand("delete"),
  archive: devFrameReadOnlyCommand("archive"),
  unarchive: devFrameReadOnlyCommand("unarchive"),
  settle: devFrameReadOnlyCommand("settle"),
  unsettle: devFrameReadOnlyCommand("unsettle"),
  snooze: devFrameReadOnlyCommand("snooze"),
  unsnooze: devFrameReadOnlyCommand("unsnooze"),
  updateMetadata: devFrameReadOnlyCommand("updateMetadata"),
  setRuntimeMode: devFrameReadOnlyCommand("setRuntimeMode"),
  setInteractionMode: devFrameReadOnlyCommand("setInteractionMode"),
  startTurn: devFrameReadOnlyCommand("startTurn"),
  interruptTurn: devFrameReadOnlyCommand("interruptTurn"),
  respondToApproval: devFrameReadOnlyCommand("respondToApproval"),
  respondToUserInput: devFrameReadOnlyCommand("respondToUserInput"),
  revertCheckpoint: devFrameReadOnlyCommand("revertCheckpoint"),
  stopSession: devFrameReadOnlyCommand("stopSession"),
};

export function createDevFrameThreadEnvironment(
  config: DevFrameControlPlaneConfig,
  resolveProjectId: (threadId: string) => string | null = (threadId) =>
    devFrameProjectIdByThreadId.get(threadId) ?? null,
) {
  return {
    ...devFrameReadOnlyThreadEnvironment,
    updateMetadata: devFrameGlobalThreadNoopCommand("updateMetadata"),
    setRuntimeMode: devFrameGlobalThreadNoopCommand("setRuntimeMode"),
    setInteractionMode: devFrameGlobalThreadNoopCommand("setInteractionMode"),
    startTurn: devFrameStartTurnCommand(config, resolveProjectId),
    interruptTurn: devFrameInterruptTurnCommand(config),
    respondToApproval: devFrameRespondToApprovalCommand(config),
  };
}

export const threadEnvironment =
  devFrameThreadBridgeMode === "native"
    ? nativeThreadEnvironment
    : devFrameThreadBridgeMode === "conversation" &&
        devFrameControlPlaneConfig !== null
      ? createDevFrameThreadEnvironment(devFrameControlPlaneConfig)
      : devFrameReadOnlyThreadEnvironment;
export const environmentThreads =
  devFrameThreadBridgeMode === "native"
    ? nativeEnvironmentThreads
    : createDevFrameEnvironmentThreadStateAtoms();
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
