import {
  appUpdateChannels,
  appUpdatePolicies,
  type AppUpdateChannel,
  type AppUpdatePolicy,
  type AppUpdateState,
  type ConfigureAppUpdatesInput
} from "../../shared/contracts/ipc.ts";
import type { AppUpdateService } from "./appUpdateService.ts";

export interface AppUpdateAccess {
  checkForUpdates(): Promise<AppUpdateState>;
  configure(payload: unknown): Promise<AppUpdateState>;
  downloadUpdate(): Promise<AppUpdateState>;
  getState(): AppUpdateState;
  installUpdate(): Promise<void>;
}

export function createAppUpdateAccess(
  updateService: AppUpdateService
): AppUpdateAccess {
  return {
    checkForUpdates() {
      return updateService.checkForUpdates();
    },
    async configure(payload) {
      return updateService.configure(normalizeConfigurePayload(payload));
    },
    downloadUpdate() {
      return updateService.downloadUpdate();
    },
    getState() {
      return updateService.getState();
    },
    installUpdate() {
      return updateService.installUpdate();
    }
  };
}

function isValidPolicy(value: unknown): value is AppUpdatePolicy {
  return (
    typeof value === "string" &&
    appUpdatePolicies.includes(value as AppUpdatePolicy)
  );
}

function isValidChannel(value: unknown): value is AppUpdateChannel {
  return (
    typeof value === "string" &&
    appUpdateChannels.includes(value as AppUpdateChannel)
  );
}

function normalizeConfigurePayload(payload: unknown): ConfigureAppUpdatesInput {
  if (!payload || typeof payload !== "object") {
    throw new Error("update configure payload must be an object");
  }

  const channel = (payload as { channel?: unknown }).channel;
  const policy = (payload as { policy?: unknown }).policy;
  if (!isValidPolicy(policy)) {
    throw new Error("update configure payload must include a valid policy");
  }
  if (channel !== undefined && !isValidChannel(channel)) {
    throw new Error("update configure payload must include a valid channel");
  }

  return { channel, policy };
}
