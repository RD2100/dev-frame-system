export function extractDesktopDroppedPaths(
  dataTransfer: Pick<DataTransfer, "files" | "items">,
  resolveDroppedPaths?: (files: File[]) => string[]
): string[] {
  const files = collectDroppedFiles(dataTransfer);
  const resolvedPaths = resolveDroppedPaths?.(files) ?? [];
  const paths = new Set<string>();

  for (const filePath of resolvedPaths) {
    if (typeof filePath === "string" && filePath.length > 0) {
      paths.add(filePath);
    }
  }

  if (paths.size > 0) {
    return Array.from(paths);
  }

  for (const file of files) {
    const filePath = resolveLegacyDesktopFilePath(file);
    if (filePath) {
      paths.add(filePath);
    }
  }

  return Array.from(paths);
}

function collectDroppedFiles(
  dataTransfer: Pick<DataTransfer, "files" | "items">
): File[] {
  const files = Array.from(dataTransfer.files);
  if (files.length > 0) {
    return files;
  }

  return Array.from(dataTransfer.items)
    .map((item) => item.getAsFile())
    .filter((file): file is File => file !== null);
}

function resolveLegacyDesktopFilePath(file: File): string | null {
  const maybePath = (file as File & { path?: string }).path;
  return typeof maybePath === "string" && maybePath.length > 0
    ? maybePath
    : null;
}
