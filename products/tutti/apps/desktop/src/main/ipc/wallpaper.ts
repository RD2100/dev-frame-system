import path from "node:path";
import { app } from "electron";
import {
  desktopIpcChannels,
  type DesktopSetCustomWallpaperInput
} from "../../shared/contracts/ipc";
import { createCustomWallpaperStore } from "../host/customWallpaperStore";
import { registerDesktopIpcHandler } from "./handle";

export function registerWallpaperIpc(): void {
  const store = createCustomWallpaperStore({
    directory: path.join(app.getPath("userData"), "custom-wallpaper")
  });

  registerDesktopIpcHandler(desktopIpcChannels.wallpaper.getCustom, () =>
    store.read()
  );
  registerDesktopIpcHandler(
    desktopIpcChannels.wallpaper.setCustom,
    (_event, payload: DesktopSetCustomWallpaperInput) => store.write(payload)
  );
  registerDesktopIpcHandler(desktopIpcChannels.wallpaper.clearCustom, () =>
    store.clear()
  );
}
