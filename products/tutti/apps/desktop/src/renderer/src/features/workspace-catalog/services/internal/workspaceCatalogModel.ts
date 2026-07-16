import type { WorkspaceCatalogStoreState } from "../workspaceCatalogTypes";

export function createInitialWorkspaceCatalogState(
  platform: NodeJS.Platform
): WorkspaceCatalogStoreState {
  return {
    createError: null,
    deleteError: null,
    deletingWorkspaceID: null,
    health: null,
    healthError: null,
    isCreating: false,
    isLoadingWorkspaces: false,
    openingWorkspaceID: null,
    platform,
    renameError: null,
    renamingWorkspaceID: null,
    routeView: "workspace",
    status: "loading",
    workspace: null,
    workspaceError: null,
    workspaceID: null,
    workspaces: [],
    workspacesError: null
  };
}
