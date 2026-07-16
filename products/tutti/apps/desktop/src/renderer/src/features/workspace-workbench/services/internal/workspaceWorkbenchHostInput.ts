import type { WorkbenchHostDockEntry } from "@tutti-os/workbench-surface";
import type { WorkspaceWorkbenchHostInput } from "../workspaceWorkbenchHostService.interface";

export function createWorkspaceWorkbenchHostInputWithDockEntries(
  baseHostInput: WorkspaceWorkbenchHostInput,
  dockEntries: readonly WorkbenchHostDockEntry[]
): WorkspaceWorkbenchHostInput {
  return {
    ...baseHostInput,
    dockEntries
  };
}
