import { useEffect, useRef, useSyncExternalStore } from "react";
import type {
  WorkbenchController,
  WorkbenchHostNodeData
} from "@tutti-os/workbench-surface";
import {
  createWorkspaceChromeController,
  type WorkspaceChromeController,
  type WorkspaceChromeControllerSnapshot,
  type WorkspaceChromeHostLayoutAdapter
} from "../services/workspaceChromeController";

const browserHostLayoutAdapter: WorkspaceChromeHostLayoutAdapter = {
  isNativeCompactTitlebar() {
    return (
      typeof document !== "undefined" &&
      document.documentElement.dataset.tuttiCompactTitlebar === "true"
    );
  },
  subscribe(listener) {
    if (typeof window === "undefined") {
      return () => {};
    }

    window.addEventListener("tutti-host-window-layout", listener);
    return () => {
      window.removeEventListener("tutti-host-window-layout", listener);
    };
  }
};

export function useWorkspaceChromeState({
  platform,
  workbenchController
}: {
  platform: NodeJS.Platform;
  workbenchController?: WorkbenchController<WorkbenchHostNodeData>;
}): WorkspaceChromeControllerSnapshot {
  const controllerRef = useRef<WorkspaceChromeController | null>(null);

  if (!controllerRef.current) {
    controllerRef.current = createWorkspaceChromeController({
      hostLayout: browserHostLayoutAdapter,
      platform,
      workbenchController
    });
  }

  const controller = controllerRef.current;
  const snapshot = useSyncExternalStore(
    (listener) => controller.subscribe(listener),
    () => controller.getSnapshot(),
    () => controller.getSnapshot()
  );

  useEffect(() => {
    controller.update({
      hostLayout: browserHostLayoutAdapter,
      platform,
      workbenchController
    });
  }, [controller, platform, workbenchController]);

  useEffect(() => {
    return () => {
      controller.dispose();
    };
  }, [controller]);

  return snapshot;
}
