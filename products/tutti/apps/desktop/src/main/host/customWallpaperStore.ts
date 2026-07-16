import { promises as fs } from "node:fs";
import path from "node:path";
import type {
  DesktopCustomWallpaperImage,
  DesktopSetCustomWallpaperInput
} from "../../shared/contracts/ipc";

interface CustomWallpaperMetadata {
  fullFile: string;
  height: number;
  mimeType: string;
  thumbnailFile: string;
  thumbnailMimeType: string;
  updatedAt: string;
  width: number;
}

export interface CustomWallpaperStore {
  clear(): Promise<void>;
  read(): Promise<DesktopCustomWallpaperImage | null>;
  write(
    input: DesktopSetCustomWallpaperInput
  ): Promise<DesktopCustomWallpaperImage>;
}

const metadataFileName = "metadata.json";

export function createCustomWallpaperStore(input: {
  directory: string;
}): CustomWallpaperStore {
  const directory = input.directory;
  const metadataPath = path.join(directory, metadataFileName);

  const readMetadata = async (): Promise<CustomWallpaperMetadata | null> => {
    try {
      const raw = await fs.readFile(metadataPath, "utf8");
      const parsed = JSON.parse(raw) as Partial<CustomWallpaperMetadata>;
      if (
        typeof parsed.fullFile !== "string" ||
        typeof parsed.thumbnailFile !== "string" ||
        typeof parsed.mimeType !== "string" ||
        typeof parsed.thumbnailMimeType !== "string" ||
        typeof parsed.width !== "number" ||
        typeof parsed.height !== "number" ||
        typeof parsed.updatedAt !== "string"
      ) {
        return null;
      }
      return {
        fullFile: parsed.fullFile,
        height: parsed.height,
        mimeType: parsed.mimeType,
        thumbnailFile: parsed.thumbnailFile,
        thumbnailMimeType: parsed.thumbnailMimeType,
        updatedAt: parsed.updatedAt,
        width: parsed.width
      };
    } catch {
      return null;
    }
  };

  return {
    async clear() {
      await fs.rm(directory, { force: true, recursive: true });
    },
    async read() {
      const metadata = await readMetadata();
      if (!metadata) {
        return null;
      }

      try {
        const [bytes, thumbnailBytes] = await Promise.all([
          fs.readFile(path.join(directory, metadata.fullFile)),
          fs.readFile(path.join(directory, metadata.thumbnailFile))
        ]);
        return {
          bytes,
          height: metadata.height,
          mimeType: metadata.mimeType,
          thumbnailBytes,
          thumbnailMimeType: metadata.thumbnailMimeType,
          updatedAt: metadata.updatedAt,
          width: metadata.width
        };
      } catch {
        return null;
      }
    },
    async write(value) {
      await fs.rm(directory, { force: true, recursive: true });
      await fs.mkdir(directory, { recursive: true });

      const fullFile = `wallpaper${extensionForMimeType(value.mimeType)}`;
      const thumbnailFile = `thumbnail${extensionForMimeType(value.thumbnailMimeType)}`;
      const updatedAt = new Date().toISOString();

      await Promise.all([
        fs.writeFile(path.join(directory, fullFile), Buffer.from(value.bytes)),
        fs.writeFile(
          path.join(directory, thumbnailFile),
          Buffer.from(value.thumbnailBytes)
        )
      ]);

      const metadata: CustomWallpaperMetadata = {
        fullFile,
        height: value.height,
        mimeType: value.mimeType,
        thumbnailFile,
        thumbnailMimeType: value.thumbnailMimeType,
        updatedAt,
        width: value.width
      };
      await fs.writeFile(metadataPath, JSON.stringify(metadata), "utf8");

      return {
        bytes: Buffer.from(value.bytes),
        height: value.height,
        mimeType: value.mimeType,
        thumbnailBytes: Buffer.from(value.thumbnailBytes),
        thumbnailMimeType: value.thumbnailMimeType,
        updatedAt,
        width: value.width
      };
    }
  };
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
