import assert from "node:assert/strict";
import test from "node:test";
import type {
  WorkspaceWallpaperDisplayMode,
  WorkspaceWallpaperId
} from "../workspaceWallpaper.ts";
import type { ReporterEventInput } from "../../../analytics/services/reporterService.interface.ts";
import { createWorkspaceWallpaperSelectionController } from "./workspaceWallpaperSelectionController.ts";

function createWallpaperSelectionInput(input: {
  appearance?: "light" | "dark";
  customWallpaperUrl?: string | null;
  displayMode?: WorkspaceWallpaperDisplayMode;
  readWallpaperId: (workspaceId: string) => WorkspaceWallpaperId;
  workspaceId: string;
  writeDisplayMode?: (
    workspaceId: string,
    displayMode: WorkspaceWallpaperDisplayMode
  ) => void;
  writeWallpaperId?: (
    workspaceId: string,
    wallpaperID: WorkspaceWallpaperId
  ) => void;
  reporterCalls?: ReporterEventInput[][];
}) {
  return {
    appearance: input.appearance ?? "light",
    customWallpaperUrl: input.customWallpaperUrl ?? null,
    readDisplayMode: () => input.displayMode ?? "original",
    readWallpaperId: input.readWallpaperId,
    workspaceId: input.workspaceId,
    writeDisplayMode:
      input.writeDisplayMode ??
      (() => {
        return undefined;
      }),
    writeWallpaperId:
      input.writeWallpaperId ??
      (() => {
        return undefined;
      }),
    reporterNow: () => 1749124800000,
    reporterService: input.reporterCalls
      ? createReporterService(input.reporterCalls)
      : undefined
  };
}

test("workspace wallpaper selection controller initializes from the workspace preference", () => {
  const controller = createWorkspaceWallpaperSelectionController(
    createWallpaperSelectionInput({
      appearance: "dark",
      readWallpaperId: () => "default",
      workspaceId: "workspace-1"
    })
  );

  const snapshot = controller.getSnapshot();

  assert.equal(snapshot.selectedWallpaperID, "default");
  assert.equal(snapshot.displayMode, "original");
  assert.equal(snapshot.wallpaper.fit, "cover");
  assert.equal(snapshot.wallpaper.appearance, "dark");
  assert.match(snapshot.wallpaper.url, /default-dark\.png/);
});

test("workspace wallpaper selection controller initializes missing preference from the catalog default", () => {
  const controller = createWorkspaceWallpaperSelectionController(
    createWallpaperSelectionInput({
      appearance: "dark",
      readWallpaperId: () => "tutti",
      workspaceId: "workspace-default"
    })
  );

  const snapshot = controller.getSnapshot();

  assert.equal(snapshot.selectedWallpaperID, "tutti");
  assert.equal(snapshot.wallpaper.appearance, "dark");
  assert.match(snapshot.wallpaper.url, /tutti\.png/);
});

test("workspace wallpaper selection controller writes and publishes selections", () => {
  const writes: { wallpaperID: WorkspaceWallpaperId; workspaceId: string }[] =
    [];
  const controller = createWorkspaceWallpaperSelectionController(
    createWallpaperSelectionInput({
      readWallpaperId: () => "sky",
      workspaceId: "workspace-2",
      writeWallpaperId(workspaceId, wallpaperID) {
        writes.push({
          wallpaperID,
          workspaceId
        });
      }
    })
  );
  const selectedWallpaperIDs: WorkspaceWallpaperId[] = [];
  controller.subscribe(() => {
    selectedWallpaperIDs.push(controller.getSnapshot().selectedWallpaperID);
  });

  controller.selectWallpaper("ocean");

  assert.deepEqual(writes, [
    {
      wallpaperID: "ocean",
      workspaceId: "workspace-2"
    }
  ]);
  assert.deepEqual(selectedWallpaperIDs, ["ocean"]);
  assert.equal(controller.getSnapshot().selectedWallpaperID, "ocean");
  assert.equal(controller.getSnapshot().wallpaper.appearance, "dark");
});

test("workspace wallpaper selection controller tracks wallpaper changes", () => {
  const reporterCalls: ReporterEventInput[][] = [];
  const controller = createWorkspaceWallpaperSelectionController(
    createWallpaperSelectionInput({
      readWallpaperId: () => "sky",
      reporterCalls,
      workspaceId: "workspace-2"
    })
  );

  controller.selectWallpaper("custom");

  assert.deepEqual(reporterCalls, [
    [
      {
        clientTS: 1749124800000,
        name: "settings.wallpaper_changed",
        params: {
          wallpaper_id: null,
          wallpaper_type: "custom"
        }
      }
    ]
  ]);
});

test("workspace wallpaper selection controller persists repeated selections without notifying", () => {
  let writeCount = 0;
  let notificationCount = 0;
  const controller = createWorkspaceWallpaperSelectionController(
    createWallpaperSelectionInput({
      readWallpaperId: () => "sand",
      workspaceId: "workspace-3",
      writeWallpaperId() {
        writeCount += 1;
      }
    })
  );
  controller.subscribe(() => {
    notificationCount += 1;
  });

  controller.selectWallpaper("sand");

  assert.equal(writeCount, 1);
  assert.equal(notificationCount, 0);
  assert.equal(controller.getSnapshot().selectedWallpaperID, "sand");
});

test("workspace wallpaper selection controller reloads when its input changes", () => {
  const storedWallpaperIds = new Map<string, WorkspaceWallpaperId>([
    ["workspace-1", "default"],
    ["workspace-2", "ocean"]
  ]);
  const controller = createWorkspaceWallpaperSelectionController(
    createWallpaperSelectionInput({
      readWallpaperId: (workspaceId) =>
        storedWallpaperIds.get(workspaceId) ?? "default",
      workspaceId: "workspace-1"
    })
  );
  const notifications: WorkspaceWallpaperId[] = [];
  controller.subscribe(() => {
    notifications.push(controller.getSnapshot().selectedWallpaperID);
  });

  controller.update(
    createWallpaperSelectionInput({
      appearance: "dark",
      readWallpaperId: (workspaceId) =>
        storedWallpaperIds.get(workspaceId) ?? "default",
      workspaceId: "workspace-2"
    })
  );

  assert.equal(controller.getSnapshot().selectedWallpaperID, "ocean");
  assert.equal(controller.getSnapshot().wallpaper.appearance, "dark");
  assert.deepEqual(notifications, ["ocean"]);
});

test("workspace wallpaper selection controller writes and publishes display mode changes", () => {
  const writes: {
    displayMode: WorkspaceWallpaperDisplayMode;
    workspaceId: string;
  }[] = [];
  const controller = createWorkspaceWallpaperSelectionController(
    createWallpaperSelectionInput({
      readWallpaperId: () => "custom",
      workspaceId: "workspace-4",
      writeDisplayMode(workspaceId, displayMode) {
        writes.push({
          displayMode,
          workspaceId
        });
      }
    })
  );
  const displayModes: WorkspaceWallpaperDisplayMode[] = [];
  controller.subscribe(() => {
    displayModes.push(controller.getSnapshot().displayMode);
  });

  controller.selectDisplayMode("stretch");

  assert.deepEqual(writes, [
    {
      displayMode: "stretch",
      workspaceId: "workspace-4"
    }
  ]);
  assert.deepEqual(displayModes, ["stretch"]);
  assert.equal(controller.getSnapshot().displayMode, "stretch");
  assert.equal(controller.getSnapshot().wallpaper.fit, "stretch");
});

test("workspace wallpaper selection controller ignores display mode for built-in wallpapers", () => {
  const controller = createWorkspaceWallpaperSelectionController(
    createWallpaperSelectionInput({
      displayMode: "stretch",
      readWallpaperId: () => "ocean",
      workspaceId: "workspace-5"
    })
  );

  assert.equal(controller.getSnapshot().displayMode, "stretch");
  assert.equal(controller.getSnapshot().wallpaper.fit, "cover");
});

function createReporterService(calls: ReporterEventInput[][] = []) {
  return {
    async trackEvents(events: ReporterEventInput[]) {
      calls.push(events);
    }
  };
}
