import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";

export const workspaceFileIconProtocolScheme = "tutti-file-icon";

export type WorkspaceFileIconCacheKey =
  | WorkspaceApplicationIconCacheKey
  | WorkspaceFileImageThumbnailCacheKey
  | WorkspaceFileTypeDefaultApplicationIconCacheKey;

export interface WorkspaceApplicationIconCacheKey {
  assetKind: "application-icon";
  mtimeMs: number | null;
  path: string;
  sizePx: number;
  workspaceID: string;
}

export interface WorkspaceFileTypeDefaultApplicationIconCacheKey {
  applicationPath: string;
  assetKind: "file-type-default-application-icon";
  fileExtension: string;
  platform: "darwin";
  sizePx: number;
}

export interface WorkspaceFileImageThumbnailCacheKey {
  assetKind: "image-thumbnail";
  mtimeMs: number | null;
  path: string;
  sizePx: number;
  workspaceID: string;
}

interface WorkspaceFileIconCacheIndexEntry {
  byteLength: number;
  file: string;
  mimeType: WorkspaceFileIconMimeType;
  updatedAtUnixMs: number;
}

interface WorkspaceFileIconCacheIndex {
  entries: Record<string, WorkspaceFileIconCacheIndexEntry>;
  version: 1;
}

export interface WorkspaceFileIconCacheStore {
  readUrl(key: WorkspaceFileIconCacheKey): Promise<string | null>;
  resolveProtocolUrl(
    url: string
  ): Promise<{ filePath: string; mimeType: WorkspaceFileIconMimeType } | null>;
  write(input: {
    bytes: Uint8Array;
    key: WorkspaceFileIconCacheKey;
    mimeType: WorkspaceFileIconMimeType;
  }): Promise<string | null>;
}

export interface WorkspaceFileIconCacheStoreOptions {
  directory: string;
  maxEntries?: number;
  maxEntryBytes?: number;
  maxTotalBytes?: number;
  protocolScheme?: string;
}

type WorkspaceFileIconMimeType = "image/png";

const indexFileName = "index.json";
const defaultMaxEntries = 500;
const defaultMaxEntryBytes = 512 * 1024;
const defaultMaxTotalBytes = 32 * 1024 * 1024;
const maxCacheKeyPartLength = 4096;

export function createWorkspaceFileIconCacheStore(
  options: WorkspaceFileIconCacheStoreOptions
): WorkspaceFileIconCacheStore {
  const directory = options.directory;
  const indexPath = path.join(directory, indexFileName);
  const maxEntries = options.maxEntries ?? defaultMaxEntries;
  const maxEntryBytes = options.maxEntryBytes ?? defaultMaxEntryBytes;
  const maxTotalBytes = options.maxTotalBytes ?? defaultMaxTotalBytes;
  const protocolScheme =
    options.protocolScheme ?? workspaceFileIconProtocolScheme;
  let lastUpdatedAtUnixMs = 0;
  let writeQueue = Promise.resolve<string | null>(null);

  function nextUpdatedAtUnixMs(): number {
    lastUpdatedAtUnixMs = Math.max(Date.now(), lastUpdatedAtUnixMs + 1);
    return lastUpdatedAtUnixMs;
  }

  const readIndex = async (): Promise<WorkspaceFileIconCacheIndex> => {
    try {
      const raw = await fs.readFile(indexPath, "utf8");
      const parsed = JSON.parse(raw) as Partial<WorkspaceFileIconCacheIndex>;
      if (parsed.version !== 1 || !parsed.entries) {
        return emptyIndex();
      }

      const entries: WorkspaceFileIconCacheIndex["entries"] = {};
      for (const [id, entry] of Object.entries(parsed.entries)) {
        if (
          !isValidIconCacheId(id) ||
          typeof entry?.file !== "string" ||
          !isValidIconCacheFileName(entry.file) ||
          entry.mimeType !== "image/png" ||
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
    index: WorkspaceFileIconCacheIndex
  ): Promise<void> => {
    await fs.mkdir(directory, { recursive: true });
    const tempPath = `${indexPath}.tmp`;
    await fs.writeFile(tempPath, JSON.stringify(index), "utf8");
    await fs.rename(tempPath, indexPath);
  };

  const writeNow = async (input: {
    bytes: Uint8Array;
    key: WorkspaceFileIconCacheKey;
    mimeType: WorkspaceFileIconMimeType;
  }): Promise<string | null> => {
    const bytes = Buffer.from(input.bytes);
    if (
      !isValidWorkspaceFileIconCacheKey(input.key) ||
      input.mimeType !== "image/png" ||
      bytes.byteLength === 0 ||
      bytes.byteLength > maxEntryBytes ||
      bytes.byteLength > maxTotalBytes
    ) {
      return null;
    }

    await fs.mkdir(directory, { recursive: true });
    const id = workspaceFileIconCacheKeyHash(input.key);
    const nextFile = `${id}.png`;
    const nextPath = path.join(directory, nextFile);
    const tempPath = `${nextPath}.tmp`;
    const index = await readIndex();
    const previous = index.entries[id];
    if (previous && previous.file !== nextFile) {
      await fs.rm(path.join(directory, previous.file), { force: true });
    }

    await fs.writeFile(tempPath, bytes);
    await fs.rename(tempPath, nextPath);
    index.entries[id] = {
      byteLength: bytes.byteLength,
      file: nextFile,
      mimeType: input.mimeType,
      updatedAtUnixMs: nextUpdatedAtUnixMs()
    };
    await pruneIndex({ directory, index, maxEntries, maxTotalBytes });
    await writeIndex(index);

    return buildWorkspaceFileIconProtocolUrl(id, protocolScheme);
  };

  const readCachedIconById = async (
    id: string
  ): Promise<{
    filePath: string;
    mimeType: WorkspaceFileIconMimeType;
  } | null> => {
    const index = await readIndex();
    const entry = index.entries[id];
    if (!entry || entry.byteLength > maxEntryBytes) {
      return null;
    }

    const filePath = path.join(directory, entry.file);
    try {
      const stat = await fs.stat(filePath);
      if (!stat.isFile() || stat.size === 0 || stat.size > maxEntryBytes) {
        return null;
      }
    } catch {
      return null;
    }

    return { filePath, mimeType: entry.mimeType };
  };

  return {
    async readUrl(key) {
      if (!isValidWorkspaceFileIconCacheKey(key)) {
        return null;
      }

      const id = workspaceFileIconCacheKeyHash(key);
      const cached = await readCachedIconById(id);
      return cached
        ? buildWorkspaceFileIconProtocolUrl(id, protocolScheme)
        : null;
    },
    async resolveProtocolUrl(url) {
      const id = parseWorkspaceFileIconProtocolUrl(url, protocolScheme);
      if (!id) {
        return null;
      }

      return readCachedIconById(id);
    },
    write(input) {
      writeQueue = writeQueue.catch(() => null).then(() => writeNow(input));
      return writeQueue;
    }
  };
}

function emptyIndex(): WorkspaceFileIconCacheIndex {
  return {
    entries: {},
    version: 1
  };
}

function isValidWorkspaceFileIconCacheKey(
  key: unknown
): key is WorkspaceFileIconCacheKey {
  if (!key || typeof key !== "object") {
    return false;
  }
  const typed = key as Partial<WorkspaceFileIconCacheKey>;
  if (typed.assetKind === "application-icon") {
    return (
      isValidCacheKeyPart(typed.path) &&
      isValidIconSize(typed.sizePx) &&
      isValidCacheKeyPart(typed.workspaceID) &&
      (typed.mtimeMs === null ||
        (typeof typed.mtimeMs === "number" && Number.isFinite(typed.mtimeMs)))
    );
  }

  if (typed.assetKind === "file-type-default-application-icon") {
    return (
      typed.platform === "darwin" &&
      isValidCacheKeyPart(typed.applicationPath) &&
      isValidIconSize(typed.sizePx) &&
      isValidWorkspaceFileIconExtension(typed.fileExtension)
    );
  }

  if (typed.assetKind === "image-thumbnail") {
    return (
      isValidCacheKeyPart(typed.path) &&
      isValidCacheKeyPart(typed.workspaceID) &&
      isValidIconSize(typed.sizePx) &&
      (typed.mtimeMs === null ||
        (typeof typed.mtimeMs === "number" && Number.isFinite(typed.mtimeMs)))
    );
  }

  return false;
}

function isValidCacheKeyPart(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= maxCacheKeyPartLength
  );
}

function isValidWorkspaceFileIconExtension(value: unknown): value is string {
  return (
    typeof value === "string" && /^[a-z0-9][a-z0-9+.-]{0,31}$/u.test(value)
  );
}

function isValidIconSize(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= 32 &&
    value <= 512
  );
}

function workspaceFileIconCacheKeyHash(key: WorkspaceFileIconCacheKey): string {
  let hashInput: unknown;
  if (key.assetKind === "application-icon") {
    hashInput = {
      assetKind: key.assetKind,
      mtimeMs: key.mtimeMs,
      path: key.path,
      sizePx: key.sizePx,
      workspaceID: key.workspaceID
    };
  } else if (key.assetKind === "image-thumbnail") {
    hashInput = {
      assetKind: key.assetKind,
      mtimeMs: key.mtimeMs,
      path: key.path,
      sizePx: key.sizePx,
      workspaceID: key.workspaceID
    };
  } else {
    hashInput = {
      applicationPath: key.applicationPath,
      assetKind: key.assetKind,
      fileExtension: key.fileExtension,
      platform: key.platform,
      sizePx: key.sizePx
    };
  }

  return createHash("sha256").update(JSON.stringify(hashInput)).digest("hex");
}

function buildWorkspaceFileIconProtocolUrl(
  id: string,
  protocolScheme: string
): string {
  return `${protocolScheme}://icon/${id}`;
}

function parseWorkspaceFileIconProtocolUrl(
  value: string,
  protocolScheme: string
): string | null {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return null;
  }

  if (
    parsed.protocol !== `${protocolScheme}:` ||
    parsed.hostname !== "icon" ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash
  ) {
    return null;
  }

  const id = parsed.pathname.startsWith("/")
    ? parsed.pathname.slice(1)
    : parsed.pathname;
  return isValidIconCacheId(id) ? id : null;
}

function isValidIconCacheId(value: string): boolean {
  return /^[a-f0-9]{64}$/u.test(value);
}

function isValidIconCacheFileName(value: string): boolean {
  return /^[a-f0-9]{64}\.png$/u.test(value);
}

async function pruneIndex(input: {
  directory: string;
  index: WorkspaceFileIconCacheIndex;
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
