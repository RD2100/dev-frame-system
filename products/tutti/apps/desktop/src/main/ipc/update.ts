import {
  desktopIpcChannels,
  type ConfigureAppUpdatesInput
} from "../../shared/contracts/ipc";
import type { AppUpdateService } from "../update/appUpdateService";
import { createAppUpdateAccess } from "../update/appUpdateAccess";
import { registerDesktopIpcHandler } from "./handle";

export function registerUpdateIpc(updateService: AppUpdateService): void {
  const access = createAppUpdateAccess(updateService);

  registerDesktopIpcHandler(desktopIpcChannels.update.getState, () =>
    access.getState()
  );
  registerDesktopIpcHandler(
    desktopIpcChannels.update.configure,
    (_event, payload: ConfigureAppUpdatesInput) => access.configure(payload)
  );
  registerDesktopIpcHandler(desktopIpcChannels.update.check, () =>
    access.checkForUpdates()
  );
  registerDesktopIpcHandler(desktopIpcChannels.update.download, () =>
    access.downloadUpdate()
  );
  registerDesktopIpcHandler(desktopIpcChannels.update.install, () =>
    access.installUpdate()
  );
}
