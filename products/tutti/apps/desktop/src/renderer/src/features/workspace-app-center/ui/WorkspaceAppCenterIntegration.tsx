import { useEffect } from "react";
import { useWorkspaceAppCenterService } from "./useWorkspaceAppCenterService.ts";

export function WorkspaceAppCenterIntegration({
  workspaceId
}: {
  workspaceId: string;
}) {
  const { service } = useWorkspaceAppCenterService();

  useEffect(() => {
    return service.startWorkspacePolling(workspaceId);
  }, [service, workspaceId]);

  return null;
}
