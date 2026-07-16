import type { WorkspaceLaunchOwnerWindow } from "./workspaceLaunch.ts";

export interface DesktopWindowAccess {
  approveClose(ownerWindow?: WorkspaceLaunchOwnerWindow | null): Promise<void>;
}

export function createDesktopWindowAccess(): DesktopWindowAccess {
  return {
    approveClose(ownerWindow) {
      forceDestroyWindow(ownerWindow);
      return Promise.resolve();
    }
  };
}

function forceDestroyWindow(
  ownerWindow?: WorkspaceLaunchOwnerWindow | null
): void {
  if (!ownerWindow) {
    return;
  }

  if (typeof ownerWindow.destroy === "function") {
    ownerWindow.destroy();
    return;
  }

  ownerWindow.close();
}
