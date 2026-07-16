import type { WorkbenchNode } from "../core/types.ts";
import type {
  WorkbenchHostExternalStateSource,
  WorkbenchHostNodeData
} from "./types.ts";

export interface WorkbenchHostExternalState {
  externalNodeState: unknown;
  externalWorkspaceState: unknown;
}

export function readWorkbenchHostExternalState(input: {
  externalStateSource?: WorkbenchHostExternalStateSource;
  node: WorkbenchNode<WorkbenchHostNodeData>;
  workspaceId: string;
}): WorkbenchHostExternalState {
  if (!input.externalStateSource) {
    return {
      externalNodeState: null,
      externalWorkspaceState: null
    };
  }

  const nodeStateInput = {
    instanceId: input.node.data.instanceId,
    instanceKey: input.node.data.instanceKey ?? null,
    nodeId: input.node.id,
    typeId: input.node.data.typeId,
    workspaceId: input.workspaceId,
    ...(input.node.data.projectionSubject
      ? { subject: input.node.data.projectionSubject }
      : {})
  };

  const sourceNodeState =
    input.externalStateSource.getNodeState(nodeStateInput);

  return {
    externalNodeState:
      sourceNodeState ?? input.node.data.snapshotNodeState ?? null,
    externalWorkspaceState: input.externalStateSource.getWorkspaceState({
      workspaceId: input.workspaceId
    })
  };
}
