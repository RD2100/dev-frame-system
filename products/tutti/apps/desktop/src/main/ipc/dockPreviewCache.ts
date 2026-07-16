import path from "node:path";
import { app } from "electron";
import {
  desktopIpcChannels,
  type DesktopReadDockPreviewInput,
  type DesktopWriteDockPreviewInput
} from "../../shared/contracts/ipc";
import { createWorkspaceDockPreviewCacheStore } from "../host/workspaceDockPreviewCacheStore";
import { registerDesktopIpcHandler } from "./handle";

export function registerDockPreviewCacheIpc(): void {
  const store = createWorkspaceDockPreviewCacheStore({
    directory: path.join(app.getPath("userData"), "workspace-dock-previews")
  });

  registerDesktopIpcHandler(
    desktopIpcChannels.dockPreviewCache.read,
    (_event, payload: DesktopReadDockPreviewInput) => store.read(payload.key)
  );
  registerDesktopIpcHandler(
    desktopIpcChannels.dockPreviewCache.write,
    (_event, payload: DesktopWriteDockPreviewInput) => {
      store.enqueueWrite(payload);
    }
  );
}
