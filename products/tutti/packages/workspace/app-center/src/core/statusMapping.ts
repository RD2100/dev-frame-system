import type {
  WorkspaceAppRuntimeState,
  WorkspaceAppRuntimeStatus
} from "../contracts/runtime.ts";
import type { WorkspaceAppStatusTone } from "../contracts/viewModel.ts";

export interface WorkspaceAppStatusPresentation {
  readonly labelKey: string;
  readonly pulse: boolean;
  readonly tone: WorkspaceAppStatusTone;
}

const statusAliases = new Map<string, WorkspaceAppRuntimeStatus>([
  ["active", "running"],
  ["created", "idle"],
  ["crashed", "failed"],
  ["error", "failed"],
  ["failed", "failed"],
  ["idle", "idle"],
  ["installed", "idle"],
  ["installed_pending_restart", "installed_pending_restart"],
  ["installing", "installing"],
  ["downloading_runtime", "preparing"],
  ["launching", "starting"],
  ["pending", "starting"],
  ["preparing", "preparing"],
  ["ready", "idle"],
  ["running", "running"],
  ["runner_unavailable", "unavailable"],
  ["runtime_unavailable", "unavailable"],
  ["sandbox_unavailable", "unavailable"],
  ["started", "running"],
  ["starting", "starting"],
  ["stale", "unavailable"],
  ["stopped", "idle"],
  ["stopping", "stopping"],
  ["terminated", "idle"],
  ["terminating", "stopping"],
  ["unavailable", "unavailable"],
  ["unreachable", "unavailable"]
]);

export function mapWorkspaceAppRuntimeStatus(
  value: unknown
): WorkspaceAppRuntimeStatus {
  if (typeof value !== "string") {
    return "idle";
  }

  return statusAliases.get(value.trim().toLowerCase()) ?? "idle";
}

export function normalizeWorkspaceAppRuntimeState(
  state: Omit<WorkspaceAppRuntimeState, "status"> & {
    readonly status?: unknown;
  }
): WorkspaceAppRuntimeState {
  return {
    ...state,
    status: mapWorkspaceAppRuntimeStatus(state.status)
  };
}

export function resolveWorkspaceAppStatusPresentation(
  status: WorkspaceAppRuntimeStatus
): WorkspaceAppStatusPresentation {
  switch (status) {
    case "installing":
      return {
        labelKey: "status.installing",
        pulse: true,
        tone: "blue"
      };
    case "preparing":
      return {
        labelKey: "status.preparing",
        pulse: true,
        tone: "blue"
      };
    case "starting":
      return {
        labelKey: "status.starting",
        pulse: true,
        tone: "blue"
      };
    case "running":
      return {
        labelKey: "status.running",
        pulse: false,
        tone: "green"
      };
    case "installed_pending_restart":
      return {
        labelKey: "status.installedPendingRestart",
        pulse: false,
        tone: "amber"
      };
    case "failed":
      return {
        labelKey: "status.failed",
        pulse: false,
        tone: "red"
      };
    case "stopping":
      return {
        labelKey: "status.stopping",
        pulse: true,
        tone: "amber"
      };
    case "unavailable":
      return {
        labelKey: "status.unavailable",
        pulse: false,
        tone: "amber"
      };
    case "idle":
      return {
        labelKey: "actions.openApp",
        pulse: false,
        tone: "neutral"
      };
  }
}
