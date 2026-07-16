import {
  customWorkspaceWallpaperId,
  getWorkspaceWallpaperOption,
  resolveWorkspaceWallpaperDisplayMode,
  toWorkbenchSurfaceWallpaperFit,
  type WorkspaceWallpaperAppearance,
  type WorkspaceWallpaperDisplayMode,
  type WorkspaceWallpaperId
} from "../workspaceWallpaper.ts";
import { SettingsWallpaperChangedReporter } from "../../../analytics/reporters/settings-wallpaper-changed/settingsWallpaperChangedReporter.ts";
import type { IReporterService } from "../../../analytics/services/reporterService.interface.ts";

export interface WorkspaceWallpaperSelectionSnapshot {
  displayMode: WorkspaceWallpaperDisplayMode;
  selectedWallpaperID: WorkspaceWallpaperId;
  wallpaper: {
    appearance: WorkspaceWallpaperAppearance;
    fit: ReturnType<typeof toWorkbenchSurfaceWallpaperFit>;
    url: string;
  };
}

export interface WorkspaceWallpaperSelectionController {
  getSnapshot: () => WorkspaceWallpaperSelectionSnapshot;
  selectDisplayMode: (displayMode: WorkspaceWallpaperDisplayMode) => void;
  selectWallpaper: (wallpaperID: WorkspaceWallpaperId) => void;
  subscribe: (listener: () => void) => () => void;
  update: (input: WorkspaceWallpaperSelectionControllerInput) => void;
}

export interface WorkspaceWallpaperSelectionControllerInput {
  appearance: WorkspaceWallpaperAppearance;
  customWallpaperUrl: string | null;
  readDisplayMode(workspaceId: string): WorkspaceWallpaperDisplayMode;
  readWallpaperId(workspaceId: string): WorkspaceWallpaperId;
  workspaceId: string;
  writeDisplayMode(
    workspaceId: string,
    displayMode: WorkspaceWallpaperDisplayMode
  ): void;
  writeWallpaperId(
    workspaceId: string,
    wallpaperId: WorkspaceWallpaperId
  ): void;
  reporterService?: Pick<IReporterService, "trackEvents">;
  reporterNow?: () => number;
}

export function createWorkspaceWallpaperSelectionController(
  input: WorkspaceWallpaperSelectionControllerInput
): WorkspaceWallpaperSelectionController {
  let currentInput = input;
  let selectedWallpaperID = currentInput.readWallpaperId(
    currentInput.workspaceId
  );
  let displayMode = currentInput.readDisplayMode(currentInput.workspaceId);
  let snapshot = createSnapshot({
    appearance: currentInput.appearance,
    customWallpaperUrl: currentInput.customWallpaperUrl,
    displayMode,
    selectedWallpaperID
  });
  const listeners = new Set<() => void>();

  const notify = () => {
    for (const listener of listeners) {
      listener();
    }
  };
  const setSnapshot = (nextSnapshot: WorkspaceWallpaperSelectionSnapshot) => {
    if (isSameSnapshot(snapshot, nextSnapshot)) {
      return;
    }

    snapshot = nextSnapshot;
    notify();
  };
  const publishSelectedWallpaper = () => {
    setSnapshot(
      createSnapshot({
        appearance: currentInput.appearance,
        customWallpaperUrl: currentInput.customWallpaperUrl,
        displayMode,
        selectedWallpaperID
      })
    );
  };
  const setSelectedWallpaperID = (wallpaperID: WorkspaceWallpaperId) => {
    if (selectedWallpaperID === wallpaperID) {
      return;
    }

    selectedWallpaperID = wallpaperID;
    publishSelectedWallpaper();
  };
  const setDisplayMode = (nextDisplayMode: WorkspaceWallpaperDisplayMode) => {
    if (displayMode === nextDisplayMode) {
      return;
    }

    displayMode = nextDisplayMode;
    publishSelectedWallpaper();
  };

  return {
    getSnapshot: () => snapshot,
    selectDisplayMode: (nextDisplayMode) => {
      currentInput.writeDisplayMode(currentInput.workspaceId, nextDisplayMode);
      setDisplayMode(nextDisplayMode);
    },
    selectWallpaper: (wallpaperID) => {
      const changed = selectedWallpaperID !== wallpaperID;
      currentInput.writeWallpaperId(currentInput.workspaceId, wallpaperID);
      setSelectedWallpaperID(wallpaperID);
      if (changed) {
        reportWallpaperChanged(wallpaperID, currentInput);
      }
    },
    subscribe: (listener) => {
      listeners.add(listener);

      return () => {
        listeners.delete(listener);
      };
    },
    update: (nextInput) => {
      currentInput = nextInput;
      selectedWallpaperID = currentInput.readWallpaperId(
        currentInput.workspaceId
      );
      displayMode = currentInput.readDisplayMode(currentInput.workspaceId);
      publishSelectedWallpaper();
    }
  };
}

function reportWallpaperChanged(
  wallpaperID: WorkspaceWallpaperId,
  input: WorkspaceWallpaperSelectionControllerInput
): void {
  if (!input.reporterService) {
    return;
  }

  const isCustom = wallpaperID === customWorkspaceWallpaperId;
  void new SettingsWallpaperChangedReporter(
    {
      wallpaperId: isCustom ? null : wallpaperID,
      wallpaperType: isCustom ? "custom" : "preset"
    },
    {
      reporterService: input.reporterService,
      now: input.reporterNow
    }
  ).report();
}

function createSnapshot(input: {
  appearance: WorkspaceWallpaperAppearance;
  customWallpaperUrl: string | null;
  displayMode: WorkspaceWallpaperDisplayMode;
  selectedWallpaperID: WorkspaceWallpaperId;
}): WorkspaceWallpaperSelectionSnapshot {
  const wallpaper = getWorkspaceWallpaperOption(
    input.selectedWallpaperID,
    input.appearance,
    input.customWallpaperUrl
  );

  const resolvedDisplayMode = resolveWorkspaceWallpaperDisplayMode(
    input.selectedWallpaperID,
    input.displayMode
  );

  return {
    displayMode: input.displayMode,
    selectedWallpaperID: input.selectedWallpaperID,
    wallpaper: {
      appearance: wallpaper.appearance,
      fit: toWorkbenchSurfaceWallpaperFit(resolvedDisplayMode),
      url: wallpaper.url
    }
  };
}

function isSameSnapshot(
  current: WorkspaceWallpaperSelectionSnapshot,
  next: WorkspaceWallpaperSelectionSnapshot
): boolean {
  return (
    current.displayMode === next.displayMode &&
    current.selectedWallpaperID === next.selectedWallpaperID &&
    current.wallpaper.appearance === next.wallpaper.appearance &&
    current.wallpaper.fit === next.wallpaper.fit &&
    current.wallpaper.url === next.wallpaper.url
  );
}
