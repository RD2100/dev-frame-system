import type { DesktopSetCustomWallpaperInput } from "@shared/contracts/ipc";

export type CustomWallpaperImageErrorCode =
  | "unsupported-type"
  | "too-large"
  | "decode-failed"
  | "encode-failed";

export class CustomWallpaperImageError extends Error {
  readonly code: CustomWallpaperImageErrorCode;

  constructor(code: CustomWallpaperImageErrorCode, message: string) {
    super(message);
    this.name = "CustomWallpaperImageError";
    this.code = code;
  }
}

const maxFullEdgePixels = 4096;
const thumbnailEdgePixels = 512;
const maxSourceBytes = 60 * 1024 * 1024;
const outputMimeType = "image/jpeg";
const fullQuality = 0.92;
const thumbnailQuality = 0.82;

export async function processCustomWallpaperImage(
  file: File
): Promise<DesktopSetCustomWallpaperInput> {
  if (!file.type.startsWith("image/")) {
    throw new CustomWallpaperImageError(
      "unsupported-type",
      `Unsupported wallpaper file type: ${file.type || "unknown"}`
    );
  }
  if (file.size > maxSourceBytes) {
    throw new CustomWallpaperImageError(
      "too-large",
      `Wallpaper file is too large: ${file.size} bytes`
    );
  }

  const bitmap = await decodeImage(file);
  try {
    const full = scaleToFit(bitmap.width, bitmap.height, maxFullEdgePixels);
    const thumbnail = scaleToFit(
      bitmap.width,
      bitmap.height,
      thumbnailEdgePixels
    );

    const [bytes, thumbnailBytes] = await Promise.all([
      renderToBytes(bitmap, full.width, full.height, fullQuality),
      renderToBytes(bitmap, thumbnail.width, thumbnail.height, thumbnailQuality)
    ]);

    return {
      bytes,
      height: full.height,
      mimeType: outputMimeType,
      thumbnailBytes,
      thumbnailMimeType: outputMimeType,
      width: full.width
    };
  } finally {
    bitmap.close();
  }
}

async function decodeImage(file: File): Promise<ImageBitmap> {
  try {
    return await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch (cause) {
    throw new CustomWallpaperImageError(
      "decode-failed",
      `Failed to decode wallpaper image: ${String(cause)}`
    );
  }
}

function scaleToFit(
  width: number,
  height: number,
  maxEdge: number
): { height: number; width: number } {
  const longestEdge = Math.max(width, height);
  if (longestEdge <= maxEdge) {
    return { height, width };
  }
  const scale = maxEdge / longestEdge;
  return {
    height: Math.max(1, Math.round(height * scale)),
    width: Math.max(1, Math.round(width * scale))
  };
}

async function renderToBytes(
  bitmap: ImageBitmap,
  width: number,
  height: number,
  quality: number
): Promise<Uint8Array> {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new CustomWallpaperImageError(
      "encode-failed",
      "Canvas 2D context is unavailable."
    );
  }
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(bitmap, 0, 0, width, height);

  const blob = await new Promise<Blob | null>((resolve) => {
    canvas.toBlob(resolve, outputMimeType, quality);
  });
  if (!blob) {
    throw new CustomWallpaperImageError(
      "encode-failed",
      "Failed to encode wallpaper image."
    );
  }
  return new Uint8Array(await blob.arrayBuffer());
}
