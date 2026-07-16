import test from "node:test";
import assert from "node:assert/strict";
import { extractDesktopDroppedPaths } from "../services/desktopDroppedPaths.ts";

test("extractDesktopDroppedPaths returns unique file paths from dragged files", () => {
  const fileA = { path: "/tmp/a.txt" } as File;
  const fileB = { path: "/tmp/b.txt" } as File;
  const fileDuplicate = { path: "/tmp/a.txt" } as File;
  const dataTransfer = {
    files: [fileA, fileB, fileDuplicate],
    items: []
  } as unknown as Pick<DataTransfer, "files" | "items">;

  assert.deepEqual(extractDesktopDroppedPaths(dataTransfer), [
    "/tmp/a.txt",
    "/tmp/b.txt"
  ]);
});

test("extractDesktopDroppedPaths falls back to dataTransfer items when files are empty", () => {
  const itemA = {
    getAsFile(): File {
      return { path: "/tmp/folder" } as File;
    }
  } as DataTransferItem;
  const itemB = {
    getAsFile(): File | null {
      return null;
    }
  } as DataTransferItem;
  const dataTransfer = {
    files: [],
    items: [itemA, itemB]
  } as unknown as Pick<DataTransfer, "files" | "items">;

  assert.deepEqual(extractDesktopDroppedPaths(dataTransfer), ["/tmp/folder"]);
});

test("extractDesktopDroppedPaths prefers Electron-resolved file system paths", () => {
  const droppedFile = {} as File;
  const dataTransfer = {
    files: [droppedFile],
    items: []
  } as unknown as Pick<DataTransfer, "files" | "items">;

  assert.deepEqual(
    extractDesktopDroppedPaths(dataTransfer, (files) =>
      files.map(() => "/Users/example/Desktop/from-finder.txt")
    ),
    ["/Users/example/Desktop/from-finder.txt"]
  );
});
