import assert from "node:assert/strict";
import test from "node:test";
import type { TrackEvent } from "@tutti-os/client-tuttid-ts";
import type { AppUpdateState } from "../shared/contracts/ipc.ts";
import {
  createAppUpdateStatusChangedEvent,
  startDesktopAppUpdateAnalytics
} from "./appUpdateAnalytics.ts";

test("app update analytics creates protocol-compatible status changed events", () => {
  assert.deepEqual(
    createAppUpdateStatusChangedEvent({
      availableVersion: "1.3.0",
      channel: "stable",
      clientTS: 1749124800000,
      fromStatus: "checking",
      toStatus: "available"
    }),
    {
      client_ts: 1749124800000,
      name: "app_update.status_changed",
      params: {
        available_version: "1.3.0",
        channel: "stable",
        from_status: "checking",
        to_status: "available"
      }
    }
  );
});

test("app update analytics tracks only real status transitions", async () => {
  const events: TrackEvent[][] = [];
  const updateService = createUpdateServiceStub();
  const analytics = startDesktopAppUpdateAnalytics({
    tuttidClient: {
      async trackEvents(nextEvents) {
        events.push(nextEvents);
      }
    },
    now: () => 1749124800000,
    updateService
  });

  updateService.emit(
    createState({ status: "idle" }),
    createState({ status: "idle" })
  );
  updateService.emit(
    createState({ status: "available", latestVersion: "1.3.0" }),
    createState({ status: "checking" })
  );
  analytics.release();
  updateService.emit(
    createState({ status: "downloaded", latestVersion: "1.3.0" }),
    createState({ status: "available", latestVersion: "1.3.0" })
  );

  await new Promise((resolve) => setImmediate(resolve));

  assert.deepEqual(events, [
    [
      {
        client_ts: 1749124800000,
        name: "app_update.status_changed",
        params: {
          available_version: "1.3.0",
          channel: "stable",
          from_status: "checking",
          to_status: "available"
        }
      }
    ]
  ]);
});

function createState(overrides: Partial<AppUpdateState>): AppUpdateState {
  return {
    channel: "stable",
    checkedAt: null,
    currentVersion: "1.0.0",
    downloadedBytes: null,
    downloadPercent: null,
    latestVersion: null,
    message: null,
    policy: "prompt",
    releaseDate: null,
    releaseName: null,
    releaseNotesUrl: null,
    status: "idle",
    totalBytes: null,
    ...overrides
  };
}

function createUpdateServiceStub(): {
  emit: (state: AppUpdateState, previousState: AppUpdateState) => void;
  onStateChanged: (
    listener: (state: AppUpdateState, previousState: AppUpdateState) => void
  ) => () => void;
} {
  const listeners = new Set<
    (state: AppUpdateState, previousState: AppUpdateState) => void
  >();

  return {
    emit(state, previousState) {
      for (const listener of listeners) {
        listener(state, previousState);
      }
    },
    onStateChanged(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    }
  };
}
