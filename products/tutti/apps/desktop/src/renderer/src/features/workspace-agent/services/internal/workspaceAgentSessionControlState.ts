import type {
  TuttidClient,
  WorkspaceAgentSession
} from "@tutti-os/client-tuttid-ts";
import type { AgentHostAgentSessionState } from "@shared/contracts/dto";
import {
  desktopAgentHostWorkspaceState,
  resolveAgentSessionStateDefaults
} from "./desktopAgentHostWorkspaceState.ts";
import { toAgentHostAgentSessionState } from "./desktopAgentHostProjection.ts";

export async function loadWorkspaceAgentSessionControlState(input: {
  agentSessionId: string;
  tuttidClient: TuttidClient;
  session?: WorkspaceAgentSession | null;
  workspaceId: string;
}): Promise<AgentHostAgentSessionState> {
  const normalizedWorkspaceId = input.workspaceId.trim();
  const normalizedAgentSessionId = input.agentSessionId.trim();
  const session =
    input.session ??
    (await input.tuttidClient.getWorkspaceAgentSession(
      normalizedWorkspaceId,
      normalizedAgentSessionId
    ));
  return toAgentHostAgentSessionState(normalizedWorkspaceId, session, {
    defaults: resolveAgentSessionStateDefaults(
      desktopAgentHostWorkspaceState(normalizedWorkspaceId),
      normalizedAgentSessionId
    )
  });
}
