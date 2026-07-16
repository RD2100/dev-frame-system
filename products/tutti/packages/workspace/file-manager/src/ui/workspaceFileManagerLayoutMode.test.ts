import assert from "node:assert/strict";
import test from "node:test";
import {
  readWorkspaceFileManagerLayoutMode,
  writeWorkspaceFileManagerLayoutMode,
  workspaceFileManagerLayoutModeStorageKey
} from "./workspaceFileManagerLayoutMode.ts";

test("workspace file manager layout mode defaults to list", () => {
  assert.equal(readWorkspaceFileManagerLayoutMode(), "list");
});

test("workspace file manager layout mode persists icon selection", () => {
  const storage = new Map<string, string>();
  const originalWindow = globalThis.window;

  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      localStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => {
          storage.set(key, value);
        }
      }
    }
  });

  try {
    writeWorkspaceFileManagerLayoutMode("icon");
    assert.equal(storage.get(workspaceFileManagerLayoutModeStorageKey), "icon");
    assert.equal(readWorkspaceFileManagerLayoutMode(), "icon");
  } finally {
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: originalWindow
    });
  }
});
