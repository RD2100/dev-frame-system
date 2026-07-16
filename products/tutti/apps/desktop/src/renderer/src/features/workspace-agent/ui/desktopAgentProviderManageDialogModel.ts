import type {
  AgentProviderActionId,
  AgentProviderStatus,
  WorkspaceAgentProvider
} from "@tutti-os/client-tuttid-ts";
import type { AgentProviderStatusPendingAction } from "../services/agentProviderStatusService.interface";
import { desktopManagedAgentProviders } from "../services/internal/desktopManagedAgentProviders.ts";

export const desktopAgentProviderManageDialogProviders = [
  ...desktopManagedAgentProviders
] as const satisfies readonly WorkspaceAgentProvider[];

export type DesktopAgentProviderManageRowStatus =
  | "auth_required"
  | "available"
  | "checking"
  | "connected"
  | "unknown"
  | "unsupported";

export type DesktopAgentProviderManageRowAction = Extract<
  AgentProviderActionId,
  "install" | "login"
>;

export interface DesktopAgentProviderManageRow {
  actionDisabled: boolean;
  configDetected: boolean;
  pending: boolean;
  primaryActionId: DesktopAgentProviderManageRowAction | null;
  provider: (typeof desktopAgentProviderManageDialogProviders)[number];
  status: DesktopAgentProviderManageRowStatus;
}

export function projectDesktopAgentProviderManageRows(input: {
  hiddenProviders?: ReadonlySet<WorkspaceAgentProvider>;
  isLoading: boolean;
  pendingActions: readonly AgentProviderStatusPendingAction[];
  statuses: readonly AgentProviderStatus[];
}): DesktopAgentProviderManageRow[] {
  const statusByProvider = new Map<WorkspaceAgentProvider, AgentProviderStatus>(
    input.statuses.map((status) => [status.provider, status])
  );

  return desktopAgentProviderManageDialogProviders
    .filter((provider) => input.hiddenProviders?.has(provider) !== true)
    .map((provider) =>
      projectDesktopAgentProviderManageRow({
        isLoading: input.isLoading,
        pendingActions: input.pendingActions,
        provider,
        status: statusByProvider.get(provider) ?? null
      })
    );
}

export function projectDesktopAgentProviderManageRow(input: {
  isLoading: boolean;
  pendingActions: readonly AgentProviderStatusPendingAction[];
  provider: (typeof desktopAgentProviderManageDialogProviders)[number];
  status: AgentProviderStatus | null;
}): DesktopAgentProviderManageRow {
  const status = resolveDesktopAgentProviderManageRowStatus(
    input.status,
    input.isLoading
  );
  const primaryActionId = resolveDesktopAgentProviderManageRowAction(
    input.status
  );
  const pending =
    primaryActionId !== null &&
    input.pendingActions.some(
      (action) =>
        action.provider === input.provider &&
        action.actionId === primaryActionId
    );

  return {
    actionDisabled: primaryActionId === null || pending,
    configDetected: input.status?.adapter.installed ?? false,
    pending,
    primaryActionId,
    provider: input.provider,
    status
  };
}

function resolveDesktopAgentProviderManageRowStatus(
  status: AgentProviderStatus | null,
  isLoading: boolean
): DesktopAgentProviderManageRowStatus {
  if (!status) {
    return isLoading ? "checking" : "unknown";
  }

  switch (status.availability.status) {
    case "ready":
      return "connected";
    case "not_installed":
      return "available";
    case "auth_required":
      return "auth_required";
    case "unsupported":
      return "unsupported";
    case "unknown":
      return "unknown";
  }
}

function resolveDesktopAgentProviderManageRowAction(
  status: AgentProviderStatus | null
): DesktopAgentProviderManageRowAction | null {
  if (!status) {
    return null;
  }

  if (status.availability.status === "not_installed") {
    return status.actions.some((action) => action.id === "install")
      ? "install"
      : null;
  }

  if (status.availability.status === "auth_required") {
    return status.actions.some((action) => action.id === "login")
      ? "login"
      : null;
  }

  return null;
}
