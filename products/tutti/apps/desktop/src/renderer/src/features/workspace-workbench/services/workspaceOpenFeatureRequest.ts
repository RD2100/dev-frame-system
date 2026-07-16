import { normalizeAgentGuiWorkbenchProvider } from "@tutti-os/agent-gui/workbench/providerCatalog";
import type {
  AgentProviderAction,
  AgentProviderStatus
} from "@tutti-os/client-tuttid-ts";
import type { AgentGuiWorkbenchProvider } from "@tutti-os/agent-gui/workbench/types";

export function resolveWorkspaceAgentChatProvider(input: {
  defaultProvider?: string | null;
  requestedProvider?: string | null;
}): AgentGuiWorkbenchProvider {
  return normalizeAgentGuiWorkbenchProvider(
    input.requestedProvider ?? input.defaultProvider
  );
}

export type WorkspaceAgentProviderLaunchIntent =
  | { kind: "action"; actionId: AgentProviderAction["id"] }
  | { kind: "blocked" }
  | { kind: "launch" };

export function resolveWorkspaceAgentProviderLaunchIntent(
  status: Pick<AgentProviderStatus, "actions" | "availability"> | null
): WorkspaceAgentProviderLaunchIntent {
  if (!status) {
    return { kind: "blocked" };
  }
  if (status.availability.status === "ready") {
    return { kind: "launch" };
  }
  const actionId = resolveWorkspaceAgentProviderSetupAction(status);
  return actionId ? { actionId, kind: "action" } : { kind: "blocked" };
}

export function resolveWorkspaceAgentProviderSetupAction(
  status: Pick<AgentProviderStatus, "actions" | "availability">
): AgentProviderAction["id"] | null {
  if (status.availability.status === "not_installed") {
    return status.actions.find((action) => action.id === "install")?.id ?? null;
  }
  if (status.availability.status === "auth_required") {
    return status.actions.find((action) => action.id === "login")?.id ?? null;
  }
  return status.actions.find((action) => action.kind !== "refresh")?.id ?? null;
}
