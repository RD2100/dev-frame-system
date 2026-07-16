import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";
import type {
  DesktopDockPreviewCacheKey,
  DesktopWriteDockPreviewInput
} from "../../shared/contracts/ipc";

interface WorkspaceDockPreviewCacheIndexEntry {
  byteLength: number;
  file: string;
  mimeType: string;
  updatedAtUnixMs: number;
}

interface WorkspaceDockPreviewCacheIndex {
  entries: Record<string, WorkspaceDockPreviewCacheIndexEntry>;
  version: 1;
}

export interface WorkspaceDockPreviewCacheStore {
  enqueueWrite(input: DesktopWriteDockPreviewInput): void;
  read(key: DesktopDockPreviewCacheKey): Promise<string | null>;
}

export interface WorkspaceDockPreviewCacheStoreOptions {
  directory: string;
  maxEntries?: number;
  maxEntryBytes?: number;
  maxTotalBytes?: number;
}

const indexFileName = "index.json";
const defaultMaxEntries = 200;
const defaultMaxEntryBytes = 80 * 1024;
const defaultMaxTotalBytes = 20 * 1024 * 1024;
const maxCacheKeyPartLength = 1024;
const maxCacheKeyTotalLength = 4096;

export function createWorkspaceDockPreviewCacheStore(
  options: WorkspaceDockPreviewCacheStoreOptions
): WorkspaceDockPreviewCacheStore {
  const directory = options.directory;
  const indexPath = path.join(directory, indexFileName);
  const maxEntries = options.maxEntries ?? defaultMaxEntries;
  const maxEntryBytes = options.maxEntryBytes ?? defaultMaxEntryBytes;
  const maxTotalBytes = options.maxTotalBytes ?? defaultMaxTotalBytes;
  let writeQueue = Promise.resolve();
  let lastUpdatedAtUnixMs = 0;

  const readIndex = async (): Promise<WorkspaceDockPreviewCacheIndex> => {
    try {
      const raw = await fs.readFile(indexPath, "utf8");
      const parsed = JSON.parse(raw) as Partial<WorkspaceDockPreviewCacheIndex>;
      if (parsed.version !== 1 || !parsed.entries) {
        return emptyIndex();
      }
      const entries: WorkspaceDockPreviewCacheIndex["entries"] = {};
      for (const [id, entry] of Object.entries(parsed.entries)) {
        if (
          typeof entry?.file !== "string" ||
          typeof entry.mimeType !== "string" ||
          typeof entry.byteLength !== "number" ||
          typeof entry.updatedAtUnixMs !== "number"
        ) {
          continue;
        }
        entries[id] = {
          byteLength: entry.byteLength,
          file: entry.file,
          mimeType: entry.mimeType,
          updatedAtUnixMs: entry.updatedAtUnixMs
        };
      }
      return { entries, version: 1 };
    } catch {
      return emptyIndex();
    }
  };

  const writeIndex = async (
    index: WorkspaceDockPreviewCacheIndex
  ): Promise<void> => {
    await fs.mkdir(directory, { recursive: true });
    const tempPath = `${indexPath}.tmp`;
    await fs.writeFile(tempPath, JSON.stringify(index), "utf8");
    await fs.rename(tempPath, indexPath);
  };

  const writeNow = async (
    input: DesktopWriteDockPreviewInput
  ): Promise<void> => {
    if (!isValidDockPreviewCacheKey(input.key)) {
      return;
    }
    const image = parseDockPreviewDataUrl(input.dataUrl, maxEntryBytes);
    if (!image) {
      return;
    }

    await fs.mkdir(directory, { recursive: true });
    const id = dockPreviewCacheKeyHash(input.key);
    const nextFile = `${id}${extensionForMimeType(image.mimeType)}`;
    const nextPath = path.join(directory, nextFile);
    const tempPath = `${nextPath}.tmp`;
    const index = await readIndex();
    const previous = index.entries[id];
    if (previous && previous.file !== nextFile) {
      await fs.rm(path.join(directory, previous.file), { force: true });
    }

    await fs.writeFile(tempPath, image.bytes);
    await fs.rename(tempPath, nextPath);
    index.entries[id] = {
      byteLength: image.bytes.byteLength,
      file: nextFile,
      mimeType: image.mimeType,
      updatedAtUnixMs: nextUpdatedAtUnixMs()
    };
    await pruneIndex({ directory, index, maxEntries, maxTotalBytes });
    await writeIndex(index);
  };

  return {
    enqueueWrite(input) {
      writeQueue = writeQueue.catch(noop).then(() => writeNow(input));
      void writeQueue.catch(noop);
    },
    async read(key) {
      if (!isValidDockPreviewCacheKey(key)) {
        return null;
      }
      const index = await readIndex();
      const entry = index.entries[dockPreviewCacheKeyHash(key)];
      if (!entry || entry.byteLength > maxEntryBytes) {
        return null;
      }
      try {
        const bytes = await fs.readFile(path.join(directory, entry.file));
        if (bytes.byteLength > maxEntryBytes) {
          return null;
        }
        return `data:${entry.mimeType};base64,${bytes.toString("base64")}`;
      } catch {
        return null;
      }
    }
  };

  function nextUpdatedAtUnixMs(): number {
    lastUpdatedAtUnixMs = Math.max(Date.now(), lastUpdatedAtUnixMs + 1);
    return lastUpdatedAtUnixMs;
  }
}

function emptyIndex(): WorkspaceDockPreviewCacheIndex {
  return {
    entries: {},
    version: 1
  };
}

function parseDockPreviewDataUrl(
  dataUrl: string,
  maxEntryBytes: number
): { bytes: Buffer; mimeType: string } | null {
  if (dataUrl.length > maxDataUrlLength(maxEntryBytes)) {
    return null;
  }
  const match =
    /^data:(image\/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$/u.exec(dataUrl);
  if (!match) {
    return null;
  }
  const mimeType = match[1];
  const encodedBytes = match[2];
  if (!mimeType || !encodedBytes) {
    return null;
  }
  const bytes = Buffer.from(encodedBytes, "base64");
  if (bytes.byteLength === 0 || bytes.byteLength > maxEntryBytes) {
    return null;
  }
  return {
    bytes,
    mimeType
  };
}

function maxDataUrlLength(maxEntryBytes: number): number {
  return "data:image/jpeg;base64,".length + Math.ceil(maxEntryBytes / 3) * 4;
}

function isValidDockPreviewCacheKey(
  key: unknown
): key is DesktopDockPreviewCacheKey {
  if (!key || typeof key !== "object") {
    return false;
  }
  const typed = key as Partial<DesktopDockPreviewCacheKey>;
  const parts = [
    typed.instanceId,
    typed.instanceKey ?? "",
    typed.nodeId,
    typed.typeId,
    typed.workspaceId
  ];
  if (
    !isValidRequiredCacheKeyPart(typed.instanceId) ||
    !isValidOptionalCacheKeyPart(typed.instanceKey) ||
    !isValidRequiredCacheKeyPart(typed.nodeId) ||
    !isValidRequiredCacheKeyPart(typed.typeId) ||
    !isValidRequiredCacheKeyPart(typed.workspaceId)
  ) {
    return false;
  }
  return parts.join("").length <= maxCacheKeyTotalLength;
}

function isValidRequiredCacheKeyPart(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= maxCacheKeyPartLength
  );
}

function isValidOptionalCacheKeyPart(value: unknown): value is string | null {
  return (
    value === null ||
    value === undefined ||
    (typeof value === "string" && value.length <= maxCacheKeyPartLength)
  );
}

function dockPreviewCacheKeyHash(key: DesktopDockPreviewCacheKey): string {
  return createHash("sha256")
    .update(
      JSON.stringify({
        instanceId: key.instanceId,
        instanceKey: key.instanceKey ?? null,
        nodeId: key.nodeId,
        typeId: key.typeId,
        workspaceId: key.workspaceId
      })
    )
    .digest("hex");
}

async function pruneIndex(input: {
  directory: string;
  index: WorkspaceDockPreviewCacheIndex;
  maxEntries: number;
  maxTotalBytes: number;
}): Promise<void> {
  const entries = Object.entries(input.index.entries).sort(
    (left, right) => right[1].updatedAtUnixMs - left[1].updatedAtUnixMs
  );
  let totalBytes = 0;
  const retained = new Set<string>();

  for (const [id, entry] of entries) {
    const canRetain =
      retained.size < input.maxEntries &&
      totalBytes + entry.byteLength <= input.maxTotalBytes;
    if (!canRetain) {
      continue;
    }
    retained.add(id);
    totalBytes += entry.byteLength;
  }

  await Promise.all(
    entries
      .filter(([id]) => !retained.has(id))
      .map(([, entry]) =>
        fs.rm(path.join(input.directory, entry.file), { force: true })
      )
  );

  for (const [id] of entries) {
    if (!retained.has(id)) {
      delete input.index.entries[id];
    }
  }
}

function extensionForMimeType(mimeType: string): string {
  switch (mimeType) {
    case "image/jpeg":
      return ".jpg";
    case "image/png":
      return ".png";
    case "image/webp":
      return ".webp";
    default:
      return ".bin";
  }
}

function noop(): void {}
