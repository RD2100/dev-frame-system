import type {
  WorkbenchDockPlacement,
  WorkbenchLayoutConstraintsInput
} from "@tutti-os/workbench-surface";

const workspaceWorkbenchTopSafeArea = 52;
const workspaceWorkbenchDockSafeArea = 65;
const workspaceWorkbenchDockSafetyGap = 14;
const workspaceWorkbenchBottomSafeArea =
  workspaceWorkbenchDockSafeArea + workspaceWorkbenchDockSafetyGap;
const workspaceWorkbenchLeftDockSafeArea = 80;

const workspaceWorkbenchBottomDockLayoutConstraints: WorkbenchLayoutConstraintsInput =
  {
    minWidth: 280,
    minHeight: 160,
    surfacePadding: 0,
    safeArea: {
      top: workspaceWorkbenchTopSafeArea,
      left: 0,
      bottom: workspaceWorkbenchBottomSafeArea
    }
  };

const workspaceWorkbenchLeftDockLayoutConstraints: WorkbenchLayoutConstraintsInput =
  {
    minWidth: 280,
    minHeight: 160,
    surfacePadding: 0,
    safeArea: {
      top: workspaceWorkbenchTopSafeArea,
      bottom: 0,
      left: workspaceWorkbenchLeftDockSafeArea
    }
  };

export function resolveWorkspaceWorkbenchLayoutConstraints(
  dockPlacement: WorkbenchDockPlacement
): WorkbenchLayoutConstraintsInput {
  return dockPlacement === "left"
    ? workspaceWorkbenchLeftDockLayoutConstraints
    : workspaceWorkbenchBottomDockLayoutConstraints;
}
