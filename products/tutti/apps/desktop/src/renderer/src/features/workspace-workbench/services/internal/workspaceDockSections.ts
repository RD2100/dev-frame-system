import type { WorkbenchHostDockEntry } from "@tutti-os/workbench-surface";

export const workspaceTaskDockSectionId = "workspace-task-apps";

export function assignWorkspaceTaskDockSection(
  dockEntries: readonly WorkbenchHostDockEntry[]
): WorkbenchHostDockEntry[] {
  return dockEntries.map((entry) => ({
    ...entry,
    sectionId: workspaceTaskDockSectionId
  }));
}
