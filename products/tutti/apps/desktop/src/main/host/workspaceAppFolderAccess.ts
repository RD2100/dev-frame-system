import { mkdir } from "node:fs/promises";
import { shell } from "electron";
import type { DesktopWorkspaceAppPayload } from "../../shared/contracts/ipc";
import { resolveDesktopDefaultsFromEnv } from "../defaults.ts";
import { resolveWorkspaceAppFolderPath } from "./workspaceAppFolderPaths.ts";

export async function openDesktopWorkspaceAppFolder(
  payload: DesktopWorkspaceAppPayload
): Promise<void> {
  const folderPath = resolveWorkspaceAppFolderPath(
    resolveDesktopDefaultsFromEnv().state.rootDir,
    payload
  );
  await mkdir(folderPath, { recursive: true });
  const openError = await shell.openPath(folderPath);
  if (openError) {
    throw new Error(openError);
  }
}
