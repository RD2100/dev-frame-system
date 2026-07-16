import type { TuttidClient, TrackEvent } from "@tutti-os/client-tuttid-ts";
import type { AppUpdateState } from "../shared/contracts/ipc.ts";
import type { AppUpdateService } from "./update/appUpdateService.ts";

export interface DesktopAppUpdateAnalyticsHandle {
  release(): void;
}

export interface StartDesktopAppUpdateAnalyticsInput {
  tuttidClient: Pick<TuttidClient, "trackEvents">;
  now?: () => number;
  onError?: (error: unknown) => void;
  updateService: Pick<AppUpdateService, "onStateChanged">;
}

export function startDesktopAppUpdateAnalytics(
  input: StartDesktopAppUpdateAnalyticsInput
): DesktopAppUpdateAnalyticsHandle {
  const now = input.now ?? Date.now;
  const unsubscribe = input.updateService.onStateChanged(
    (state, previousState) => {
      if (state.status === previousState.status) {
        return;
      }

      void input.tuttidClient
        .trackEvents([
          createAppUpdateStatusChangedEvent({
            availableVersion: state.latestVersion,
            channel: state.channel,
            clientTS: now(),
            fromStatus: previousState.status,
            toStatus: state.status
          })
        ])
        .catch((error) => {
          input.onError?.(error);
        });
    }
  );

  return {
    release() {
      unsubscribe();
    }
  };
}

export function createAppUpdateStatusChangedEvent(input: {
  availableVersion: AppUpdateState["latestVersion"];
  channel: AppUpdateState["channel"];
  clientTS: number;
  fromStatus: AppUpdateState["status"];
  toStatus: AppUpdateState["status"];
}): TrackEvent {
  return {
    client_ts: input.clientTS,
    name: "app_update.status_changed",
    params: {
      available_version: input.availableVersion,
      channel: input.channel,
      from_status: input.fromStatus,
      to_status: input.toStatus
    }
  };
}
