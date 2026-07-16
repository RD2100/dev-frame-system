import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import {
  createWorkspaceDockPreviewCacheStore,
  type WorkspaceDockPreviewCacheStore
} from "./workspaceDockPreviewCacheStore.ts";
import type { DesktopDockPreviewCacheKey } from "../../shared/contracts/ipc.ts";

const tinyPngDataUrl =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=";

test("workspace dock preview cache stores and reads a preview data url", async () => {
  const directory = await createTempDirectory("dock-preview-read");
  const store = createWorkspaceDockPreviewCacheStore({ directory });
  const key = testCacheKey("node-a");

  store.enqueueWrite({
    dataUrl: tinyPngDataUrl,
    key
  });

  assert.equal(await readEventually(store, key), tinyPngDataUrl);
});

test("workspace dock preview cache rejects invalid data urls", async () => {
  const directory = await createTempDirectory("dock-preview-invalid");
  const store = createWorkspaceDockPreviewCacheStore({ directory });
  const key = testCacheKey("node-a");

  store.enqueueWrite({
    dataUrl: "data:text/plain;base64,SGVsbG8=",
    key
  });

  await waitForWriteQueue();
  assert.equal(await store.read(key), null);
});

test("workspace dock preview cache rejects entries above the byte budget", async () => {
  const directory = await createTempDirectory("dock-preview-budget");
  const store = createWorkspaceDockPreviewCacheStore({
    directory,
    maxEntryBytes: 8
  });
  const key = testCacheKey("node-a");

  store.enqueueWrite({
    dataUrl: tinyPngDataUrl,
    key
  });

  await waitForWriteQueue();
  assert.equal(await store.read(key), null);
});

test("workspace dock preview cache rejects oversized encoded payloads before storing", async () => {
  const directory = await createTempDirectory("dock-preview-encoded-budget");
  const store = createWorkspaceDockPreviewCacheStore({
    directory,
    maxEntryBytes: 8
  });
  const key = testCacheKey("node-a");

  store.enqueueWrite({
    dataUrl: `data:image/png;base64,${"A".repeat(1024)}`,
    key
  });

  await waitForWriteQueue();
  assert.equal(await store.read(key), null);
});

test("workspace dock preview cache rejects oversized cache keys", async () => {
  const directory = await createTempDirectory("dock-preview-key-budget");
  const store = createWorkspaceDockPreviewCacheStore({ directory });
  const key = {
    ...testCacheKey("node-a"),
    nodeId: "x".repeat(5000)
  };

  store.enqueueWrite({
    dataUrl: tinyPngDataUrl,
    key
  });

  await waitForWriteQueue();
  assert.equal(await store.read(key), null);
});

test("workspace dock preview cache prunes older entries by count", async () => {
  const directory = await createTempDirectory("dock-preview-prune");
  const store = createWorkspaceDockPreviewCacheStore({
    directory,
    maxEntries: 1
  });
  const firstKey = testCacheKey("node-a");
  const secondKey = testCacheKey("node-b");

  store.enqueueWrite({ dataUrl: tinyPngDataUrl, key: firstKey });
  assert.equal(await readEventually(store, firstKey), tinyPngDataUrl);

  store.enqueueWrite({ dataUrl: tinyPngDataUrl, key: secondKey });
  assert.equal(await readEventually(store, secondKey), tinyPngDataUrl);
  await waitForWriteQueue();

  assert.equal(await store.read(firstKey), null);
});

async function createTempDirectory(prefix: string): Promise<string> {
  return fs.mkdtemp(path.join(tmpdir(), `${prefix}-`));
}

function testCacheKey(nodeId: string): DesktopDockPreviewCacheKey {
  return {
    instanceId: `instance-${nodeId}`,
    instanceKey: null,
    nodeId,
    typeId: "test-node",
    workspaceId: "workspace-a"
  };
}

async function readEventually(
  store: WorkspaceDockPreviewCacheStore,
  key: DesktopDockPreviewCacheKey
): Promise<string | null> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const value = await store.read(key);
    if (value) {
      return value;
    }
    await waitForWriteQueue();
  }
  return null;
}

function waitForWriteQueue(): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, 5);
  });
}
