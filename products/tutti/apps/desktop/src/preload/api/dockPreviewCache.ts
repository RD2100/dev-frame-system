import { desktopIpcChannels } from "../../shared/contracts/ipc";
import type { DesktopDockPreviewCacheApi } from "../types";
import { invokeDesktopApi } from "./invoke";

export function createDockPreviewCacheDesktopApi(): DesktopDockPreviewCacheApi {
  return {
    read(input) {
      return invokeDesktopApi(desktopIpcChannels.dockPreviewCache.read, input);
    },
    write(input) {
      return invokeDesktopApi(desktopIpcChannels.dockPreviewCache.write, input);
    }
  };
}
