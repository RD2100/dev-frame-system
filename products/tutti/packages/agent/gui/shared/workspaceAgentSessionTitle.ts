import { normalizeAgentTitleText } from "./utils/agentTitleText";
import { isWorkspaceAgentUntitledTask } from "./workspaceAgentLatestActivitySummary";
import { workspaceAgentProviderLabel } from "./workspaceAgentProviderLabel";
import { isWorkspaceAgentSyntheticControlMessage } from "./workspaceAgentSyntheticMessages";
import type { WorkspaceAgentActivitySession } from "./workspaceAgentActivityTypes";

export function resolveDisplayableWorkspaceAgentSessionTitle(
  session: Pick<WorkspaceAgentActivitySession, "title" | "provider">
): string {
  const title = normalizeAgentTitleText(session.title);
  if (
    !title ||
    isWorkspaceAgentUntitledTask(title) ||
    isWorkspaceAgentSyntheticControlMessage(title)
  ) {
    return "";
  }
  const provider = session.provider?.trim();
  if (
    provider &&
    workspaceAgentProviderLabel(provider).toLowerCase() === title.toLowerCase()
  ) {
    return "";
  }
  return title;
}
