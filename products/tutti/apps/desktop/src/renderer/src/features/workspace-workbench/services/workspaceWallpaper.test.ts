import assert from "node:assert/strict";
import test from "node:test";
import {
  workbenchSnapshotSchemaVersion,
  type WorkbenchSnapshot
} from "@tutti-os/workbench-snapshot";
import {
  defaultWorkspaceWallpaperId,
  preserveWorkspaceWallpaperSnapshotMetadata,
  readWorkspaceWallpaperDisplayModeFromSnapshot,
  readWorkspaceWallpaperIdFromSnapshot,
  toWorkbenchSurfaceWallpaperFit,
  writeWorkspaceWallpaperDisplayModeToSnapshot,
  writeWorkspaceWallpaperIdToSnapshot
} from "./workspaceWallpaper.ts";

test("workspace wallpaper state reads default from missing or invalid snapshot metadata", () => {
  assert.equal(
    readWorkspaceWallpaperIdFromSnapshot(null),
    defaultWorkspaceWallpaperId
  );
  assert.equal(
    readWorkspaceWallpaperIdFromSnapshot({
      ...createSnapshot(),
      metadata: {
        workspaceWallpaper: {
          schemaVersion: 1,
          selectedWallpaperID: "unknown"
        }
      }
    }),
    defaultWorkspaceWallpaperId
  );
});

test("workspace wallpaper state preserves an explicit legacy default selection", () => {
  assert.equal(
    readWorkspaceWallpaperIdFromSnapshot({
      ...createSnapshot(),
      metadata: {
        workspaceWallpaper: {
          schemaVersion: 1,
          selectedWallpaperID: "default"
        }
      }
    }),
    "default"
  );
});

test("workspace wallpaper state round-trips through workbench snapshot metadata", () => {
  const snapshot = writeWorkspaceWallpaperIdToSnapshot(createSnapshot(), "sky");

  assert.equal(readWorkspaceWallpaperIdFromSnapshot(snapshot), "sky");
  assert.deepEqual(snapshot.metadata?.workspaceWallpaper, {
    displayMode: "original",
    schemaVersion: 1,
    selectedWallpaperID: "sky"
  });
});

test("workspace wallpaper display mode round-trips through workbench snapshot metadata", () => {
  const snapshot = writeWorkspaceWallpaperDisplayModeToSnapshot(
    createSnapshot(),
    "fit"
  );

  assert.equal(readWorkspaceWallpaperDisplayModeFromSnapshot(snapshot), "fit");
  assert.deepEqual(snapshot.metadata?.workspaceWallpaper, {
    displayMode: "fit",
    schemaVersion: 1,
    selectedWallpaperID: defaultWorkspaceWallpaperId
  });
});

test("workspace wallpaper display mode maps to workbench surface fit values", () => {
  assert.equal(toWorkbenchSurfaceWallpaperFit("original"), "center");
  assert.equal(toWorkbenchSurfaceWallpaperFit("fill"), "cover");
  assert.equal(toWorkbenchSurfaceWallpaperFit("fit"), "contain");
  assert.equal(toWorkbenchSurfaceWallpaperFit("stretch"), "stretch");
  assert.equal(toWorkbenchSurfaceWallpaperFit("center"), "center");
});

test("workspace wallpaper metadata is preserved across host snapshot saves", () => {
  const previousSnapshot = writeWorkspaceWallpaperIdToSnapshot(
    createSnapshot(),
    "ocean"
  );

  assert.equal(
    readWorkspaceWallpaperIdFromSnapshot(
      preserveWorkspaceWallpaperSnapshotMetadata(
        previousSnapshot,
        createSnapshot()
      )
    ),
    "ocean"
  );
});

test("workspace wallpaper state does not access localStorage", () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    get() {
      throw new Error("localStorage should not be accessed");
    }
  });
  try {
    const snapshot = writeWorkspaceWallpaperIdToSnapshot(
      createSnapshot(),
      "ocean"
    );
    assert.equal(readWorkspaceWallpaperIdFromSnapshot(snapshot), "ocean");
  } finally {
    if (original) {
      Object.defineProperty(globalThis, "localStorage", original);
    } else {
      Reflect.deleteProperty(globalThis, "localStorage");
    }
  }
});

function createSnapshot(): WorkbenchSnapshot {
  return {
    schemaVersion: workbenchSnapshotSchemaVersion,
    nodes: [],
    nodeStack: [],
    activeNodeId: null
  };
}
