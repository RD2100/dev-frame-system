import { desktopIpcChannels } from "../../shared/contracts/ipc";
import type { DesktopWorkspaceAppPayload } from "../../shared/contracts/ipc";
import { createWorkspaceHostAccess } from "../host/workspaceHostAccess.ts";
import type { WorkspaceLaunch } from "../host/workspaceLaunch";
import { registerDesktopIpcHandler } from "./handle";
import { resolveOwnerWindowFromEvent } from "./ownerWindow";

export interface HostWorkspaceIpcDependencies {
  openWorkspaceAppFolder?: (
    payload: DesktopWorkspaceAppPayload
  ) => Promise<void>;
  workspaceLaunch: Pick<WorkspaceLaunch, "showWorkspace">;
}

export function registerHostWorkspaceIpc(
  deps: HostWorkspaceIpcDependencies
): void {
  const hostAccess = createWorkspaceHostAccess({
    openWorkspaceAppFolder: deps.openWorkspaceAppFolder,
    workspaceLaunch: deps.workspaceLaunch
  });

  registerDesktopIpcHandler(
    desktopIpcChannels.host.workspace.openWorkspaceAppFolder,
    (_event, payload: DesktopWorkspaceAppPayload) =>
      hostAccess.openWorkspaceAppFolder(payload)
  );
  registerDesktopIpcHandler(
    desktopIpcChannels.host.workspace.showWorkspace,
    (event, workspaceID: string) =>
      hostAccess.showWorkspace(resolveOwnerWindowFromEvent(event), workspaceID)
  );
}
