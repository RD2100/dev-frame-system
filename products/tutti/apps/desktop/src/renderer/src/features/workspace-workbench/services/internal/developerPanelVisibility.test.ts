import assert from "node:assert/strict";
import test from "node:test";
import {
  readDeveloperPanelVisible,
  writeDeveloperPanelVisible
} from "./developerPanelVisibility.ts";

function createMemoryStorage(initial: Record<string, string> = {}) {
  const map = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => {
      map.set(key, value);
    },
    snapshot: () => Object.fromEntries(map)
  };
}

test("readDeveloperPanelVisible defaults to false when nothing is stored", () => {
  assert.equal(readDeveloperPanelVisible(createMemoryStorage()), false);
});

test("readDeveloperPanelVisible defaults to false when storage is unavailable", () => {
  assert.equal(readDeveloperPanelVisible(null), false);
});

test("readDeveloperPanelVisible reads a persisted enabled flag", () => {
  const storage = createMemoryStorage({
    "tutti.workspaceSettings.developerPanelVisible": "1"
  });
  assert.equal(readDeveloperPanelVisible(storage), true);
});

test("writeDeveloperPanelVisible persists the flag as 1/0", () => {
  const storage = createMemoryStorage();

  writeDeveloperPanelVisible(true, storage);
  assert.equal(readDeveloperPanelVisible(storage), true);
  assert.equal(
    storage.snapshot()["tutti.workspaceSettings.developerPanelVisible"],
    "1"
  );

  writeDeveloperPanelVisible(false, storage);
  assert.equal(readDeveloperPanelVisible(storage), false);
  assert.equal(
    storage.snapshot()["tutti.workspaceSettings.developerPanelVisible"],
    "0"
  );
});

test("writeDeveloperPanelVisible is a no-op when storage is unavailable", () => {
  assert.doesNotThrow(() => writeDeveloperPanelVisible(true, null));
});
