import type {
  WorkspaceLaunch,
  WorkspaceLaunchOwnerWindow
} from "./workspaceLaunch.ts";
import type { DesktopWorkspaceAppPayload } from "../../shared/contracts/ipc";

export interface WorkspaceHostAccess {
  openWorkspaceAppFolder(payload: DesktopWorkspaceAppPayload): Promise<void>;
  showWorkspace(
    ownerWindow: WorkspaceLaunchOwnerWindow | null,
    workspaceID: string
  ): Promise<void>;
}

export interface WorkspaceHostAccessDependencies {
  openWorkspaceAppFolder?: (
    payload: DesktopWorkspaceAppPayload
  ) => Promise<void>;
  workspaceLaunch: Pick<WorkspaceLaunch, "showWorkspace">;
}

export function createWorkspaceHostAccess(
  deps: WorkspaceHostAccessDependencies
): WorkspaceHostAccess {
  return {
    openWorkspaceAppFolder(payload) {
      return (deps.openWorkspaceAppFolder ?? defaultOpenWorkspaceAppFolder)(
        payload
      );
    },
    showWorkspace(ownerWindow, workspaceID) {
      return deps.workspaceLaunch.showWorkspace(ownerWindow, workspaceID);
    }
  };
}

function defaultOpenWorkspaceAppFolder(
  payload: DesktopWorkspaceAppPayload
): Promise<void> {
  return Promise.reject(
    new Error(
      `openWorkspaceAppFolder host adapter is not configured for workspace ${payload.workspaceId} app ${payload.appId}`
    )
  );
}
