import type {
  HealthStatusResponse,
  WorkspaceSummary
} from "@tutti-os/client-tuttid-ts";

export type WorkspaceCatalogStatus =
  | "loading"
  | "missing-context"
  | "ready"
  | "unavailable";

export interface WorkspaceCatalogStoreState {
  createError: string | null;
  deleteError: string | null;
  deletingWorkspaceID: string | null;
  health: HealthStatusResponse | null;
  healthError: string | null;
  isCreating: boolean;
  isLoadingWorkspaces: boolean;
  openingWorkspaceID: string | null;
  platform: NodeJS.Platform;
  renameError: string | null;
  renamingWorkspaceID: string | null;
  routeView: string;
  status: WorkspaceCatalogStatus;
  workspace: WorkspaceSummary | null;
  workspaceError: string | null;
  workspaceID: string | null;
  workspaces: WorkspaceSummary[];
  workspacesError: string | null;
}

export interface WorkspaceCatalogReadableStoreState {
  readonly createError: string | null;
  readonly deleteError: string | null;
  readonly deletingWorkspaceID: string | null;
  readonly health: HealthStatusResponse | null;
  readonly healthError: string | null;
  readonly isCreating: boolean;
  readonly isLoadingWorkspaces: boolean;
  readonly openingWorkspaceID: string | null;
  readonly platform: NodeJS.Platform;
  readonly renameError: string | null;
  readonly renamingWorkspaceID: string | null;
  readonly routeView: string;
  readonly status: WorkspaceCatalogStatus;
  readonly workspace: WorkspaceSummary | null;
  readonly workspaceError: string | null;
  readonly workspaceID: string | null;
  readonly workspaces: readonly WorkspaceSummary[];
  readonly workspacesError: string | null;
}
