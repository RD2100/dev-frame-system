import {
  resolveDesktopDaemonBaseUrl,
  type DesktopDaemonEndpoint
} from "../transport/paths.ts";

export const workspaceAppUserActiveEventName = "workspace_app.user_active";

export interface WorkspaceAppActivityContext {
  appID: string;
  workspaceID: string;
}

export interface WorkspaceAppUserActiveTrackEvent {
  client_ts: number;
  name: typeof workspaceAppUserActiveEventName;
  params: {
    app_id: string;
    workspace_id: string;
  };
}

export function createWorkspaceAppUserActiveTrackEvent(
  context: WorkspaceAppActivityContext,
  clientTS = Date.now()
): WorkspaceAppUserActiveTrackEvent {
  return {
    client_ts: clientTS,
    name: workspaceAppUserActiveEventName,
    params: {
      app_id: context.appID,
      workspace_id: context.workspaceID
    }
  };
}

export async function reportWorkspaceAppUserActive(
  endpoint: DesktopDaemonEndpoint,
  context: WorkspaceAppActivityContext
): Promise<void> {
  const baseUrl = resolveDesktopDaemonBaseUrl(endpoint);
  const event = createWorkspaceAppUserActiveTrackEvent(context);
  // oxlint-disable-next-line no-restricted-globals -- talks to the local daemon, not outbound
  const response = await fetch(new URL("/v1/track", baseUrl), {
    body: JSON.stringify({ events: [event] }),
    headers: {
      Authorization: `Bearer ${endpoint.accessToken}`,
      "Content-Type": "application/json"
    },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Track workspace app activity failed: ${response.status}`);
  }
}
