import { desktopIpcChannels } from "../../shared/contracts/ipc";
import type { DesktopWallpaperApi } from "../types";
import { invokeDesktopApi } from "./invoke";

export function createWallpaperDesktopApi(): DesktopWallpaperApi {
  return {
    clearCustom() {
      return invokeDesktopApi(desktopIpcChannels.wallpaper.clearCustom);
    },
    getCustom() {
      return invokeDesktopApi(desktopIpcChannels.wallpaper.getCustom);
    },
    setCustom(input) {
      return invokeDesktopApi(desktopIpcChannels.wallpaper.setCustom, input);
    }
  };
}
