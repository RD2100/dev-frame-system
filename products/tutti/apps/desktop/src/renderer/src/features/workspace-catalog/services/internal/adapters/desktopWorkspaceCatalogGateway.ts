import type {
  HealthStatusResponse,
  TuttidClient,
  WorkspaceSummary
} from "@tutti-os/client-tuttid-ts";
import type { DesktopHostWorkspaceApi } from "@preload/types";

export interface DesktopWorkspaceCatalogGateway {
  getHealth(): Promise<HealthStatusResponse>;
  getStartupWorkspace(): Promise<WorkspaceSummary | null>;
  getWorkspace(workspaceID: string): Promise<WorkspaceSummary>;
  renameWorkspace(
    workspaceID: string,
    payload: { name: string }
  ): Promise<WorkspaceSummary>;
}

export function createDesktopWorkspaceCatalogGateway(
  _hostWorkspaceApi: DesktopHostWorkspaceApi,
  tuttidClient: TuttidClient
): DesktopWorkspaceCatalogGateway {
  return {
    getHealth() {
      return tuttidClient.getHealth();
    },
    getStartupWorkspace() {
      return tuttidClient.getStartupWorkspace();
    },
    getWorkspace(workspaceID: string) {
      return tuttidClient.getWorkspace(workspaceID);
    },
    renameWorkspace(workspaceID: string, payload: { name: string }) {
      return tuttidClient.updateWorkspace(workspaceID, payload);
    }
  };
}
