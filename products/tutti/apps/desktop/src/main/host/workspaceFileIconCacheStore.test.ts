import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import {
  createWorkspaceFileIconCacheStore,
  type WorkspaceApplicationIconCacheKey,
  type WorkspaceFileIconCacheKey
} from "./workspaceFileIconCacheStore.ts";

test("workspace file icon cache writes and resolves protocol urls", async () => {
  const directory = await createTempDirectory("file-icon-read");
  const store = createWorkspaceFileIconCacheStore({ directory });
  const key = testCacheKey("/workspace/App.app");

  const url = await store.write({
    bytes: Buffer.from([1, 2, 3]),
    key,
    mimeType: "image/png"
  });

  assert.match(url ?? "", /^tutti-file-icon:\/\/icon\/[a-f0-9]{64}$/u);
  assert.equal(await store.readUrl(key), url);
  const resolved = await store.resolveProtocolUrl(url ?? "");
  assert.equal(resolved?.mimeType, "image/png");
  assert.deepEqual(
    await fs.readFile(resolved?.filePath ?? ""),
    Buffer.from([1, 2, 3])
  );
});

test("workspace file icon cache rejects invalid protocol urls", async () => {
  const directory = await createTempDirectory("file-icon-invalid-url");
  const store = createWorkspaceFileIconCacheStore({ directory });

  assert.equal(await store.resolveProtocolUrl("file:///etc/passwd"), null);
  assert.equal(
    await store.resolveProtocolUrl("tutti-file-icon://icon/../../etc/passwd"),
    null
  );
  assert.equal(
    await store.resolveProtocolUrl(
      "tutti-file-icon://icon/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa?path=/etc/passwd"
    ),
    null
  );
});

test("workspace file icon cache returns null for missing cached files", async () => {
  const directory = await createTempDirectory("file-icon-missing-file");
  const store = createWorkspaceFileIconCacheStore({ directory });

  const url = await store.write({
    bytes: Buffer.from([1, 2, 3]),
    key: testCacheKey("/workspace/App.app"),
    mimeType: "image/png"
  });
  const resolved = await store.resolveProtocolUrl(url ?? "");
  await fs.rm(resolved?.filePath ?? "", { force: true });

  assert.equal(await store.resolveProtocolUrl(url ?? ""), null);
  assert.equal(await store.readUrl(testCacheKey("/workspace/App.app")), null);
});

test("workspace file icon cache reads by exact cache key", async () => {
  const directory = await createTempDirectory("file-icon-key-read");
  const store = createWorkspaceFileIconCacheStore({ directory });
  const key = testCacheKey("/workspace/App.app");

  const url = await store.write({
    bytes: Buffer.from([1, 2, 3]),
    key,
    mimeType: "image/png"
  });

  assert.equal(await store.readUrl(key), url);
  assert.equal(
    await store.readUrl({ ...key, mtimeMs: 1_700_000_000_001 }),
    null
  );
  assert.equal(
    await store.readUrl({ ...key, path: "/workspace/Other.app" }),
    null
  );
  assert.equal(await store.readUrl({ ...key, sizePx: 128 }), null);
});

test("workspace file icon cache reads file type icons by extension and application", async () => {
  const directory = await createTempDirectory("file-icon-file-type");
  const store = createWorkspaceFileIconCacheStore({ directory });
  const key = testFileTypeCacheKey("pdf", "/Applications/Preview.app");

  const url = await store.write({
    bytes: Buffer.from([1, 2, 3]),
    key,
    mimeType: "image/png"
  });

  assert.equal(await store.readUrl(key), url);
  assert.equal(
    await store.readUrl(
      testFileTypeCacheKey("docx", "/Applications/Preview.app")
    ),
    null
  );
  assert.equal(
    await store.readUrl(testFileTypeCacheKey("pdf", "/Applications/Other.app")),
    null
  );
  assert.equal(
    await store.readUrl({
      ...testFileTypeCacheKey("pdf", "/Applications/Preview.app"),
      sizePx: 128
    }),
    null
  );
});

test("workspace file icon cache reads image thumbnails by file identity and size", async () => {
  const directory = await createTempDirectory("file-icon-thumbnail");
  const store = createWorkspaceFileIconCacheStore({ directory });
  const key = testImageThumbnailCacheKey("/workspace/photo.png", 160);

  const url = await store.write({
    bytes: Buffer.from([1, 2, 3]),
    key,
    mimeType: "image/png"
  });

  assert.equal(await store.readUrl(key), url);
  assert.equal(
    await store.readUrl(
      testImageThumbnailCacheKey("/workspace/photo.png", 256)
    ),
    null
  );
  assert.equal(
    await store.readUrl(
      testImageThumbnailCacheKey("/workspace/other.png", 160)
    ),
    null
  );
});

test("workspace file icon cache rejects entries above the byte budget", async () => {
  const directory = await createTempDirectory("file-icon-budget");
  const store = createWorkspaceFileIconCacheStore({
    directory,
    maxEntryBytes: 2
  });

  assert.equal(
    await store.write({
      bytes: Buffer.from([1, 2, 3]),
      key: testCacheKey("/workspace/App.app"),
      mimeType: "image/png"
    }),
    null
  );
});

test("workspace file icon cache prunes older entries by count", async () => {
  const directory = await createTempDirectory("file-icon-prune");
  const store = createWorkspaceFileIconCacheStore({
    directory,
    maxEntries: 1
  });

  const firstUrl = await store.write({
    bytes: Buffer.from([1]),
    key: testCacheKey("/workspace/First.app"),
    mimeType: "image/png"
  });
  const secondUrl = await store.write({
    bytes: Buffer.from([2]),
    key: testCacheKey("/workspace/Second.app"),
    mimeType: "image/png"
  });

  assert.equal(await store.resolveProtocolUrl(firstUrl ?? ""), null);
  assert.notEqual(await store.resolveProtocolUrl(secondUrl ?? ""), null);
});

test("workspace file icon cache preserves concurrent writes", async () => {
  const directory = await createTempDirectory("file-icon-concurrent");
  const store = createWorkspaceFileIconCacheStore({ directory });

  const [firstUrl, secondUrl] = await Promise.all([
    store.write({
      bytes: Buffer.from([1]),
      key: testCacheKey("/workspace/First.app"),
      mimeType: "image/png"
    }),
    store.write({
      bytes: Buffer.from([2]),
      key: testCacheKey("/workspace/Second.app"),
      mimeType: "image/png"
    })
  ]);

  assert.notEqual(await store.resolveProtocolUrl(firstUrl ?? ""), null);
  assert.notEqual(await store.resolveProtocolUrl(secondUrl ?? ""), null);
});

async function createTempDirectory(prefix: string): Promise<string> {
  return fs.mkdtemp(path.join(tmpdir(), `${prefix}-`));
}

function testCacheKey(path: string): WorkspaceApplicationIconCacheKey {
  return {
    assetKind: "application-icon",
    mtimeMs: 1_700_000_000_000,
    path,
    sizePx: 256,
    workspaceID: "workspace-a"
  };
}

function testFileTypeCacheKey(
  fileExtension: string,
  applicationPath: string
): WorkspaceFileIconCacheKey {
  return {
    applicationPath,
    assetKind: "file-type-default-application-icon",
    fileExtension,
    platform: "darwin",
    sizePx: 256
  };
}

function testImageThumbnailCacheKey(
  filePath: string,
  sizePx: number
): WorkspaceFileIconCacheKey {
  return {
    assetKind: "image-thumbnail",
    mtimeMs: 1_700_000_000_000,
    path: filePath,
    sizePx,
    workspaceID: "workspace-a"
  };
}
